"""
Local surface curvature analysis of cell membranes at ECS-facing surfaces.

For each cell, computes mean curvature H at every ECS-facing surface voxel
using the level-set curvature formula on a Gaussian-smoothed binary mask.

Smoothing uses a fixed physical scale (SIGMA_NM) so curvature is comparable
across resolutions. Curvature in units of 1/nm (positive = convex outward,
negative = concave/invagination).

Reports per-cell: median |H|, mean |H|, fraction convex, fraction concave,
curvature std. Also reports per-crop aggregates.
"""
import zarr
import numpy as np
from scipy.ndimage import gaussian_filter, binary_dilation, binary_erosion
import csv
import os
import time

NRS_BASE = "/Volumes/cellmap-1/data"
SIGMA_NM = 16.0  # Physical smoothing scale (nm) — 2 voxels at 8nm
MIN_VOL_NM3 = 2560000  # Physical volume filter matching SA/V analysis

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


def compute_mean_curvature(cell_mask, voxel_size_nm):
    """Compute mean curvature at the surface of a binary mask.

    Uses the level-set formula:
    H = (phi_xx*(phi_y^2 + phi_z^2) + phi_yy*(phi_x^2 + phi_z^2) +
         phi_zz*(phi_x^2 + phi_y^2) -
         2*(phi_x*phi_y*phi_xy + phi_x*phi_z*phi_xz + phi_y*phi_z*phi_yz)) /
        (2 * (phi_x^2 + phi_y^2 + phi_z^2)^(3/2))

    Returns curvature array (same shape as input, valid at surface voxels).
    Positive = convex (bulging outward), negative = concave.
    """
    # Gaussian smooth the binary mask
    sigma_voxels = [SIGMA_NM / v for v in voxel_size_nm]
    phi = gaussian_filter(cell_mask.astype(np.float32), sigma=sigma_voxels)

    # Compute first derivatives (using physical spacing)
    dz = np.gradient(phi, voxel_size_nm[0], axis=0)
    dy = np.gradient(phi, voxel_size_nm[1], axis=1)
    dx = np.gradient(phi, voxel_size_nm[2], axis=2)

    # Compute second derivatives
    dzz = np.gradient(dz, voxel_size_nm[0], axis=0)
    dyy = np.gradient(dy, voxel_size_nm[1], axis=1)
    dxx = np.gradient(dx, voxel_size_nm[2], axis=2)
    dzy = np.gradient(dz, voxel_size_nm[1], axis=1)
    dzx = np.gradient(dz, voxel_size_nm[2], axis=2)
    dyx = np.gradient(dy, voxel_size_nm[2], axis=2)

    # Gradient magnitude squared
    grad_mag_sq = dz**2 + dy**2 + dx**2

    # Avoid division by zero
    eps = 1e-20
    safe_denom = np.maximum(grad_mag_sq, eps) ** 1.5

    # Mean curvature (level-set formula)
    numerator = (dxx * (dy**2 + dz**2) +
                 dyy * (dx**2 + dz**2) +
                 dzz * (dx**2 + dy**2) -
                 2 * (dx * dy * dyx + dx * dz * dzx + dy * dz * dzy))

    H = numerator / (2 * safe_denom)

    return H


def find_ecs_surface_voxels(cell_mask, ecs_mask):
    """Find cell voxels that face ECS (6-connected boundary)."""
    surface = np.zeros_like(cell_mask, dtype=bool)
    for axis in range(3):
        # Forward neighbor
        slc_fwd = [slice(None)] * 3
        slc_bwd = [slice(None)] * 3
        slc_fwd[axis] = slice(1, None)
        slc_bwd[axis] = slice(None, -1)
        # Cell voxel with ECS neighbor forward
        surface[tuple(slc_bwd)] |= cell_mask[tuple(slc_bwd)] & ecs_mask[tuple(slc_fwd)]
        # Cell voxel with ECS neighbor backward
        surface[tuple(slc_fwd)] |= cell_mask[tuple(slc_fwd)] & ecs_mask[tuple(slc_bwd)]
    return surface


def analyze_crop(local_path, dataset, crop_name, tissue, prep):
    """Analyze curvature for all cells in a crop."""
    if not os.path.isdir(local_path):
        print(f"  NOT FOUND")
        return []

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        print(f"  ERROR: {e}")
        return []

    has_ecs = "ecs" in z and "s0" in z.get("ecs", {})
    has_cell = "cell" in z and "s0" in z.get("cell", {})
    if not has_ecs or not has_cell:
        print(f"  MISSING LABELS")
        return []

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        print(f"  NO VOXEL SIZE")
        return []

    vx = [float(v) for v in voxel_size]
    voxel_vol = vx[0] * vx[1] * vx[2]

    t0 = time.time()
    ecs_data = z["ecs"]["s0"][:]
    cell_data = z["cell"]["s0"][:]
    print(f"  Loaded in {time.time()-t0:.1f}s, shape={ecs_data.shape}, voxel={vx[0]}nm")

    ecs_binary = (ecs_data == 1)

    # Find cells above volume threshold
    cell_ids = np.unique(cell_data)
    cell_ids = cell_ids[cell_ids != 0]

    cell_ids_large = []
    for cid in cell_ids:
        n = int(np.count_nonzero(cell_data == cid))
        vol = n * voxel_vol
        if vol >= MIN_VOL_NM3:
            cell_ids_large.append((cid, n))

    print(f"  {len(cell_ids_large)} cells above volume threshold")

    per_cell_rows = []
    t1 = time.time()

    for i, (cid, n_voxels) in enumerate(cell_ids_large):
        # Extract bounding box with padding for smoothing
        coords = np.argwhere(cell_data == cid)
        pad = max(int(SIGMA_NM / min(vx) * 3), 4)  # 3-sigma padding
        slices = []
        for dim in range(3):
            lo = max(0, coords[:, dim].min() - pad)
            hi = min(cell_data.shape[dim], coords[:, dim].max() + pad + 1)
            slices.append(slice(lo, hi))

        sub_cell = cell_data[slices[0], slices[1], slices[2]]
        sub_ecs = ecs_binary[slices[0], slices[1], slices[2]]
        cell_mask = (sub_cell == cid)

        # Find ECS-facing surface voxels
        surface = find_ecs_surface_voxels(cell_mask, sub_ecs)
        n_surface = int(np.count_nonzero(surface))

        if n_surface < 10:
            continue

        # Compute curvature on the cell mask
        H = compute_mean_curvature(cell_mask, vx)

        # Extract curvature at ECS surface voxels
        curv_at_surface = H[surface]

        # Convert to radius of curvature where meaningful
        abs_curv = np.abs(curv_at_surface)
        median_abs_H = float(np.median(abs_curv))
        mean_abs_H = float(np.mean(abs_curv))
        std_H = float(np.std(curv_at_surface))
        p25_H = float(np.percentile(curv_at_surface, 25))
        p75_H = float(np.percentile(curv_at_surface, 75))

        # Fraction convex (H > 0) vs concave (H < 0)
        frac_convex = float(np.mean(curv_at_surface > 0))
        frac_concave = float(np.mean(curv_at_surface < 0))

        # Median radius of curvature (1/|H|) for interpretability
        median_radius_nm = 1.0 / median_abs_H if median_abs_H > 1e-10 else float('inf')

        per_cell_rows.append({
            "tissue": tissue,
            "dataset": dataset,
            "crop": crop_name,
            "prep": prep,
            "cell_id": int(cid),
            "n_voxels": n_voxels,
            "volume_nm3": round(n_voxels * voxel_vol, 1),
            "n_surface_voxels": n_surface,
            "median_abs_H": round(median_abs_H, 8),
            "mean_abs_H": round(mean_abs_H, 8),
            "std_H": round(std_H, 8),
            "p25_H": round(p25_H, 8),
            "p75_H": round(p75_H, 8),
            "frac_convex": round(frac_convex, 4),
            "frac_concave": round(frac_concave, 4),
            "median_radius_nm": round(median_radius_nm, 1),
        })

    elapsed = time.time() - t1
    print(f"  Curvature: {len(per_cell_rows)} cells in {elapsed:.1f}s")

    if per_cell_rows:
        abs_h = [r['median_abs_H'] for r in per_cell_rows]
        radii = [r['median_radius_nm'] for r in per_cell_rows if r['median_radius_nm'] < 1e6]
        convex = [r['frac_convex'] for r in per_cell_rows]
        print(f"    Median |H|: {np.median(abs_h):.6f} 1/nm")
        if radii:
            print(f"    Median radius of curvature: {np.median(radii):.1f} nm")
        print(f"    Fraction convex: {np.mean(convex):.3f}")

    return per_cell_rows


def main():
    base_dir = os.path.dirname(__file__)
    out_csv = os.path.join(base_dir, "cell_curvature.csv")

    all_rows = []

    for dataset, crop, tissue, prep, local in CROPS:
        print(f"\nProcessing {dataset}/{crop} ({tissue}, {prep})...")
        rows = analyze_crop(local, dataset, crop, tissue, prep)
        all_rows.extend(rows)

    if all_rows:
        fields = [
            "tissue", "dataset", "crop", "prep", "cell_id",
            "n_voxels", "volume_nm3", "n_surface_voxels",
            "median_abs_H", "mean_abs_H", "std_H", "p25_H", "p75_H",
            "frac_convex", "frac_concave", "median_radius_nm",
        ]
        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\nCurvature results saved to {out_csv} ({len(all_rows)} cells)")

    # Summary
    from collections import defaultdict
    import statistics as stat
    groups = defaultdict(lambda: {"abs_h": [], "radius": [], "convex": []})
    for r in all_rows:
        key = (r["tissue"], r["prep"])
        groups[key]["abs_h"].append(r["median_abs_H"])
        if r["median_radius_nm"] < 1e6:
            groups[key]["radius"].append(r["median_radius_nm"])
        groups[key]["convex"].append(r["frac_convex"])

    print("\n=== Mean Curvature |H| (1/nm) by group ===")
    for (tissue, prep), vals in sorted(groups.items()):
        h = vals["abs_h"]
        n = len(h)
        m = stat.mean(h)
        sem = stat.stdev(h) / n**0.5 if n > 1 else 0
        print(f"  {tissue:8s} {prep:12s}  n={n:>4}  mean={m:.6f} +/- {sem:.6f}")

    print("\n=== Median Radius of Curvature (nm) by group ===")
    for (tissue, prep), vals in sorted(groups.items()):
        r = vals["radius"]
        n = len(r)
        if n > 0:
            m = stat.mean(r)
            md = stat.median(r)
            sem = stat.stdev(r) / n**0.5 if n > 1 else 0
            print(f"  {tissue:8s} {prep:12s}  n={n:>4}  mean={m:.1f} +/- {sem:.1f}  median={md:.1f}")

    print("\n=== Fraction Convex Surface by group ===")
    for (tissue, prep), vals in sorted(groups.items()):
        c = vals["convex"]
        n = len(c)
        m = stat.mean(c)
        sem = stat.stdev(c) / n**0.5 if n > 1 else 0
        print(f"  {tissue:8s} {prep:12s}  n={n:>4}  mean={m:.3f} +/- {sem:.3f}")


if __name__ == "__main__":
    main()
