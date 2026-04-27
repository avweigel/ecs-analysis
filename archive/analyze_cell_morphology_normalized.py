"""
Cell morphology analysis with resolution normalization.

All data is downsampled to 8nm isotropic (matching HPF resolution) before
computing SA/V ratio and sphericity. This eliminates the voxel-size confound
that systematically biases finer-resolution chemical data toward higher SA/V.

Downsampling uses scipy.ndimage.zoom with order=0 (nearest-neighbor) to
preserve label identities.
"""
import zarr
import numpy as np
from scipy.ndimage import zoom
import csv
import os
import time
import json

NRS_BASE = "/Volumes/cellmap/data"
TARGET_VOXEL_NM = 8.0  # Normalize everything to 8nm isotropic

DATASETS = [
    ("jrc_mus-kidney", "Kidney", "Chemical",
     ["crop1026", "crop1027", "crop1028", "crop1029", "crop1030", "crop1031", "crop1032"]),
    ("jrc_mus-kidney-4", "Kidney", "Rapid HPF",
     ["crop1134", "crop1136", "crop1137", "crop1144"]),
    ("jrc_mus-heart-6", "Heart", "Chemical",
     ["crop1145", "crop1146", "crop1147"]),
    ("jrc_mus-liver", "Liver", "Chemical",
     ["crop1038", "crop1039", "crop1040", "crop1041", "crop1042", "crop1043", "crop1044"]),
    ("jrc_mus-liver-8", "Liver", "Rapid HPF",
     ["crop1123", "crop1124", "crop1125", "crop1126", "crop1127",
      "crop1071", "crop1072", "crop1073", "crop1074", "crop1075"]),
    ("jrc_mus-cortex-2", "Cortex", "Rapid HPF",
     ["crop1116", "crop1117"]),
    ("jrc_mus-cortex-3", "Cortex", "Chemical",
     ["crop1033", "crop1034", "crop1035", "crop1036", "crop1037", "crop1045", "crop1046"]),
    ("jrc_mus-cortex-4", "Cortex", "Rapid HPF",
     ["crop1139", "crop1141"]),
]

CROPS = []
for dataset, tissue, prep, crop_list in DATASETS:
    for crop in crop_list:
        local = f"{NRS_BASE}/{dataset}/{dataset}.zarr/recon-1/labels/groundtruth/{crop}"
        CROPS.append((dataset, crop, tissue, prep, local))

MIN_CELL_VOXELS = 5000  # At original resolution
MIN_CELL_VOXELS_8NM = 100  # Minimum at 8nm (after downsampling)


def get_voxel_size(zarr_group):
    """Get voxel size from multiscales metadata."""
    for label_name in ["ecs", "cell"]:
        if label_name not in zarr_group:
            continue
        attrs = dict(zarr_group[label_name].attrs)
        ms = attrs.get("cellmap", {}).get("multiscales") or attrs.get("multiscales")
        if not ms:
            continue
        datasets = ms[0].get("datasets", [])
        if not datasets:
            continue
        for t in datasets[0].get("coordinateTransformations", []):
            if t.get("type") == "scale":
                return t["scale"]
    return None


def downsample_labels(data, voxel_size, target_nm):
    """Downsample a label array to target resolution using nearest-neighbor.

    Returns (downsampled_array, actual_voxel_size_after).
    If already at target resolution, returns the original array.
    """
    factors = [v / target_nm for v in voxel_size]

    # If already at target resolution (within tolerance), skip
    if all(abs(f - 1.0) < 0.01 for f in factors):
        return data, voxel_size

    # zoom factors < 1 means downsampling (fewer voxels)
    zoom_factors = [1.0 / max(f, 1.0) for f in [target_nm / v for v in voxel_size]]
    # Actually: we want output voxels to be target_nm.
    # If input voxel is v nm, output should have v/target_nm the number of voxels per dim.
    # zoom factor = v / target_nm (< 1 for downsampling)
    zoom_factors = [v / target_nm for v in voxel_size]

    downsampled = zoom(data, zoom_factors, order=0, mode='nearest')
    new_voxel = [target_nm] * 3
    return downsampled, new_voxel


def count_ecs_boundary_faces(ecs_mask, cell_array, cell_id):
    """Count voxel faces on the boundary between a cell and ECS.

    Returns (ecs_faces, total_faces).
    Only counts faces touching ECS (not crop boundary or other cells) for ecs_faces.
    total_faces counts all non-self faces.
    """
    coords = np.argwhere(cell_array == cell_id)
    slices = []
    for dim in range(3):
        lo = max(0, coords[:, dim].min() - 1)
        hi = min(cell_array.shape[dim], coords[:, dim].max() + 2)
        slices.append(slice(lo, hi))

    sub_cell = cell_array[slices[0], slices[1], slices[2]]
    sub_ecs = ecs_mask[slices[0], slices[1], slices[2]]
    cell_mask = (sub_cell == cell_id)

    ecs_faces = 0
    total_boundary_faces = 0

    for axis in range(3):
        interior = np.take(cell_mask, range(0, cell_mask.shape[axis] - 1), axis=axis)
        forward = np.take(cell_mask, range(1, cell_mask.shape[axis]), axis=axis)
        forward_ecs = np.take(sub_ecs, range(1, sub_ecs.shape[axis]), axis=axis)

        boundary = interior & ~forward
        ecs_faces += int(np.count_nonzero(boundary & forward_ecs))
        total_boundary_faces += int(np.count_nonzero(boundary))

        boundary_rev = forward & ~interior
        backward_ecs = np.take(sub_ecs, range(0, sub_ecs.shape[axis] - 1), axis=axis)
        ecs_faces += int(np.count_nonzero(boundary_rev & backward_ecs))
        total_boundary_faces += int(np.count_nonzero(boundary_rev))

    # Faces at volume boundary (crop edge)
    for axis in range(3):
        first = np.take(cell_mask, [0], axis=axis).squeeze(axis=axis)
        total_boundary_faces += int(np.count_nonzero(first))
        last = np.take(cell_mask, [cell_mask.shape[axis] - 1], axis=axis).squeeze(axis=axis)
        total_boundary_faces += int(np.count_nonzero(last))

    return ecs_faces, total_boundary_faces


def analyze_crop(local_path, dataset, crop_name, tissue, prep):
    """Analyze a single crop with resolution normalization."""
    result = {
        "dataset": dataset,
        "crop": crop_name,
        "tissue": tissue,
        "prep": prep,
        "status": "OK",
    }

    if not os.path.isdir(local_path):
        result["status"] = "NOT FOUND"
        return result, []

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        result["status"] = f"ERROR: {e}"
        return result, []

    has_ecs = "ecs" in z and "s0" in z.get("ecs", {})
    has_cell = "cell" in z and "s0" in z.get("cell", {})

    if not has_ecs or not has_cell:
        result["status"] = "MISSING LABELS"
        return result, []

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        result["status"] = "NO VOXEL SIZE"
        return result, []

    vx_nm = [float(v) for v in voxel_size]
    result["original_voxel_nm"] = vx_nm[0]

    # Load data
    t0 = time.time()
    ecs_data = z["ecs"]["s0"][:]
    cell_data = z["cell"]["s0"][:]
    load_time = time.time() - t0
    print(f"  Loaded in {load_time:.1f}s, shape={ecs_data.shape}")

    # Downsample to 8nm if needed
    t1 = time.time()
    if abs(vx_nm[0] - TARGET_VOXEL_NM) > 0.5:
        print(f"  Downsampling from {vx_nm[0]}nm to {TARGET_VOXEL_NM}nm...")
        ecs_data, _ = downsample_labels(ecs_data, vx_nm, TARGET_VOXEL_NM)
        cell_data, _ = downsample_labels(cell_data, vx_nm, TARGET_VOXEL_NM)
        print(f"  Downsampled shape: {ecs_data.shape} [{time.time()-t1:.1f}s]")
        result["downsampled"] = True
    else:
        print(f"  Already at {vx_nm[0]}nm, no downsampling needed")
        result["downsampled"] = False

    result["analysis_voxel_nm"] = TARGET_VOXEL_NM
    result["analysis_shape"] = str(ecs_data.shape)

    # All computations now use 8nm isotropic
    voxel_vol = TARGET_VOXEL_NM ** 3  # nm³
    face_area = TARGET_VOXEL_NM ** 2  # nm² (isotropic)

    ecs_binary = (ecs_data == 1)

    # Find cells and filter by size
    cell_ids = np.unique(cell_data)
    cell_ids = cell_ids[cell_ids != 0]

    cell_ids_large = []
    for cid in cell_ids:
        n = int(np.count_nonzero(cell_data == cid))
        if n >= MIN_CELL_VOXELS_8NM:
            cell_ids_large.append((cid, n))

    print(f"  {len(cell_ids_large)} cells >= {MIN_CELL_VOXELS_8NM} voxels at 8nm "
          f"(of {len(cell_ids)} total)")

    per_cell_rows = []
    t2 = time.time()

    for cid, n_voxels in cell_ids_large:
        cell_vol_nm3 = n_voxels * voxel_vol

        ecs_faces, total_faces = count_ecs_boundary_faces(ecs_binary, cell_data, cid)
        ecs_sa_nm2 = ecs_faces * face_area
        total_sa_nm2 = total_faces * face_area
        sa_v = ecs_sa_nm2 / cell_vol_nm3 if cell_vol_nm3 > 0 else 0

        # Sphericity: SA of equivalent sphere / actual SA (using ECS-facing SA)
        r_equiv = (3 * cell_vol_nm3 / (4 * np.pi)) ** (1/3)
        sa_sphere = 4 * np.pi * r_equiv ** 2
        sphericity = sa_sphere / ecs_sa_nm2 if ecs_sa_nm2 > 0 else 0

        per_cell_rows.append({
            "dataset": dataset,
            "crop": crop_name,
            "tissue": tissue,
            "prep": prep,
            "cell_id": int(cid),
            "voxels_8nm": n_voxels,
            "volume_nm3": round(cell_vol_nm3, 1),
            "volume_um3": round(cell_vol_nm3 / 1e9, 4),
            "ecs_faces": ecs_faces,
            "total_faces": total_faces,
            "ecs_sa_nm2": round(ecs_sa_nm2, 1),
            "total_sa_nm2": round(total_sa_nm2, 1),
            "sa_v_ratio": round(sa_v, 8),
            "sphericity": round(sphericity, 4),
        })

    cell_time = time.time() - t2
    print(f"  Per-cell metrics: {len(per_cell_rows)} cells in {cell_time:.1f}s")
    if per_cell_rows:
        sav_vals = [r["sa_v_ratio"] for r in per_cell_rows]
        sph_vals = [r["sphericity"] for r in per_cell_rows]
        print(f"    SA/V: mean={np.mean(sav_vals):.6f}, median={np.median(sav_vals):.6f}")
        print(f"    Sphericity: mean={np.mean(sph_vals):.4f}, median={np.median(sph_vals):.4f}")

    result["n_cells"] = len(per_cell_rows)

    return result, per_cell_rows


def main():
    base_dir = os.path.dirname(__file__)
    cell_csv = os.path.join(base_dir, "cell_morphology_normalized.csv")

    all_cell_rows = []

    for dataset, crop, tissue, prep, local in CROPS:
        print(f"\nProcessing {dataset}/{crop} ({tissue}, {prep})...")
        result, cell_rows = analyze_crop(local, dataset, crop, tissue, prep)
        all_cell_rows.extend(cell_rows)

        if result["status"] != "OK":
            print(f"  -> {result['status']}")

    # Write per-cell CSV
    if all_cell_rows:
        cell_fields = [
            "tissue", "dataset", "crop", "prep", "cell_id",
            "voxels_8nm", "volume_nm3", "volume_um3",
            "ecs_faces", "total_faces", "ecs_sa_nm2", "total_sa_nm2",
            "sa_v_ratio", "sphericity",
        ]
        with open(cell_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cell_fields)
            writer.writeheader()
            writer.writerows(all_cell_rows)
        print(f"\nNormalized per-cell results saved to {cell_csv} ({len(all_cell_rows)} cells)")

    # Print summary
    from collections import defaultdict
    import statistics as stat
    groups = defaultdict(lambda: {"sav": [], "sph": []})
    for r in all_cell_rows:
        key = (r["tissue"], r["prep"])
        groups[key]["sav"].append(r["sa_v_ratio"])
        groups[key]["sph"].append(r["sphericity"])

    print("\n=== Resolution-normalized SA/V (all at 8nm) ===")
    for (tissue, prep), vals in sorted(groups.items()):
        sv = vals["sav"]
        n = len(sv)
        m = stat.mean(sv)
        s = stat.stdev(sv) if n > 1 else 0
        sem = s / n**0.5
        print(f"  {tissue:8s} {prep:12s}  n={n:>4}  mean={m:.4f} ± {sem:.4f} (SEM)")

    print("\n=== Resolution-normalized Sphericity (all at 8nm) ===")
    for (tissue, prep), vals in sorted(groups.items()):
        sp = vals["sph"]
        n = len(sp)
        m = stat.mean(sp)
        s = stat.stdev(sp) if n > 1 else 0
        sem = s / n**0.5
        print(f"  {tissue:8s} {prep:12s}  n={n:>4}  mean={m:.4f} ± {sem:.4f} (SEM)")


if __name__ == "__main__":
    main()
