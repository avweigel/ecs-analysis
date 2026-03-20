"""
Cell morphology analysis: SA/V ratio, sphericity, narrow-channel ECS width,
and cell-cell contact distance mapping.

Metrics computed per crop:
1. Per-cell SA/V ratio (ECS-facing surface area / cell volume, in 1/nm)
2. Per-cell sphericity (ratio of equivalent-sphere SA to actual SA)
3. Narrow-channel ECS width (distance transform filtered to <200nm)
4. Cell-cell contact fraction at multiple distance thresholds
"""
import zarr
import numpy as np
from scipy.ndimage import distance_transform_edt, label as ndi_label
import csv
import os
import time
import json

NRS_BASE = "/Volumes/cellmap/data"

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

# Distance thresholds (nm) for cell-cell contact mapping
CONTACT_THRESHOLDS = [10, 20, 40, 80, 160]

# Minimum cell size in voxels to include in per-cell analysis
MIN_CELL_VOXELS = 5000


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


def count_boundary_faces(mask, cell_array, cell_id):
    """Count voxel faces on the boundary between a cell and ECS.

    For each voxel of the cell, checks 6-connected neighbors.
    A face is on the ECS boundary if the neighbor is ECS (ecs_mask=True).
    Returns (ecs_faces, total_faces) where total_faces includes faces
    at the volume boundary and faces touching other cells.
    """
    # Get bounding box with 1-voxel padding
    coords = np.argwhere(cell_array == cell_id)
    slices = []
    for dim in range(3):
        lo = max(0, coords[:, dim].min() - 1)
        hi = min(cell_array.shape[dim], coords[:, dim].max() + 2)
        slices.append(slice(lo, hi))

    sub_cell = cell_array[slices[0], slices[1], slices[2]]
    sub_ecs = mask[slices[0], slices[1], slices[2]]
    cell_mask = (sub_cell == cell_id)

    ecs_faces = 0
    total_boundary_faces = 0

    for axis in range(3):
        # Forward direction
        interior = np.take(cell_mask, range(0, cell_mask.shape[axis] - 1), axis=axis)
        forward = np.take(cell_mask, range(1, cell_mask.shape[axis]), axis=axis)
        forward_ecs = np.take(sub_ecs, range(1, sub_ecs.shape[axis]), axis=axis)

        # Faces where cell meets non-cell
        boundary = interior & ~forward
        ecs_faces += int(np.count_nonzero(boundary & forward_ecs))
        total_boundary_faces += int(np.count_nonzero(boundary))

        # Reverse direction
        boundary_rev = forward & ~interior
        backward_ecs = np.take(sub_ecs, range(0, sub_ecs.shape[axis] - 1), axis=axis)
        ecs_faces += int(np.count_nonzero(boundary_rev & backward_ecs))
        total_boundary_faces += int(np.count_nonzero(boundary_rev))

    # Add faces at volume boundary
    for axis in range(3):
        # First slice
        first = np.take(cell_mask, [0], axis=axis).squeeze(axis=axis)
        total_boundary_faces += int(np.count_nonzero(first))
        # Last slice
        last = np.take(cell_mask, [cell_mask.shape[axis] - 1], axis=axis).squeeze(axis=axis)
        total_boundary_faces += int(np.count_nonzero(last))

    return ecs_faces, total_boundary_faces


def analyze_crop(local_path, dataset, crop_name, tissue, prep):
    """Analyze a single crop for all 4 metrics."""
    crop_result = {
        "dataset": dataset,
        "crop": crop_name,
        "tissue": tissue,
        "prep": prep,
        "status": "OK",
        "voxel_size_nm": None,
    }

    if not os.path.isdir(local_path):
        crop_result["status"] = "NOT FOUND"
        return crop_result, [], {}

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        crop_result["status"] = f"ERROR: {e}"
        return crop_result, [], {}

    has_ecs = "ecs" in z and "s0" in z.get("ecs", {})
    has_cell = "cell" in z and "s0" in z.get("cell", {})

    if not has_ecs or not has_cell:
        crop_result["status"] = "MISSING LABELS"
        return crop_result, [], {}

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        crop_result["status"] = "NO VOXEL SIZE"
        return crop_result, [], {}

    crop_result["voxel_size_nm"] = str(voxel_size)
    vx = voxel_size  # [z, y, x] in nm
    face_areas = [vx[1] * vx[2], vx[0] * vx[2], vx[0] * vx[1]]  # yz, xz, xy
    voxel_vol = vx[0] * vx[1] * vx[2]  # nm³

    # Load data
    t0 = time.time()
    ecs_data = z["ecs"]["s0"][:]
    cell_data = z["cell"]["s0"][:]
    load_time = time.time() - t0
    print(f"  Loaded in {load_time:.1f}s, shape={ecs_data.shape}")

    ecs_binary = (ecs_data == 1)

    # ---- Metric 3: Narrow-channel ECS width ----
    t1 = time.time()
    dt_ecs = distance_transform_edt(ecs_binary, sampling=voxel_size)
    narrow_mask = ecs_binary & (dt_ecs > 0) & (dt_ecs < 200)
    narrow_distances = dt_ecs[narrow_mask]
    dt_time = time.time() - t1

    crop_result["narrow_ecs_median_nm"] = round(float(np.median(narrow_distances)), 2) if len(narrow_distances) > 0 else None
    crop_result["narrow_ecs_mean_nm"] = round(float(np.mean(narrow_distances)), 2) if len(narrow_distances) > 0 else None
    crop_result["narrow_ecs_p25_nm"] = round(float(np.percentile(narrow_distances, 25)), 2) if len(narrow_distances) > 0 else None
    crop_result["narrow_ecs_p75_nm"] = round(float(np.percentile(narrow_distances, 75)), 2) if len(narrow_distances) > 0 else None
    crop_result["narrow_ecs_voxels"] = int(np.count_nonzero(narrow_mask))
    crop_result["total_ecs_voxels"] = int(np.count_nonzero(ecs_binary))
    print(f"  Narrow-channel ECS: median={crop_result['narrow_ecs_median_nm']}nm "
          f"({crop_result['narrow_ecs_voxels']}/{crop_result['total_ecs_voxels']} voxels) [{dt_time:.1f}s]")

    # ---- Metric 4: Cell-cell contact distance mapping ----
    # Dilate each cell by distance thresholds and check overlap with other cells
    t2 = time.time()
    cell_ids = np.unique(cell_data)
    cell_ids = cell_ids[cell_ids != 0]  # Remove background

    # For each cell, compute distance from cell boundary into ECS
    # A cell-cell "contact" at threshold T means: a voxel of cell A's boundary
    # has another cell B within T nm through ECS
    #
    # Efficient approach: compute distance transform from ALL non-ECS voxels,
    # then for each ECS voxel, check if it's within threshold of multiple cells.
    # But we need per-cell distances, so instead:
    # For each cell, compute distance from that cell's boundary outward into ECS.
    # Where this distance < threshold AND another cell exists, that's a contact.

    # Simpler approach: use the ECS distance transform we already have.
    # For contact fraction, we ask: what fraction of each cell's surface faces
    # are within T nm of another cell (through ECS)?

    # Most efficient: compute distance from each cell into ECS, find where
    # two cells' influence zones overlap within threshold.

    # Practical approach for contact mapping:
    # 1. For each ECS voxel, find distance to nearest cell boundary (already have dt_ecs)
    # 2. For ECS voxels with dt_ecs < T/2, they are within a "contact zone"
    # 3. Check if multiple cells border these thin ECS regions

    # Even simpler: for each cell, count surface faces where the nearest
    # non-self cell is within each threshold distance.

    contact_results = {}
    # Pre-compute: for each cell, the distance to nearest OTHER cell through ECS
    # We do this by computing distance from non-cell regions for each cell,
    # but that's expensive per cell.

    # Better approach: compute a "gap width" map.
    # At each ECS voxel, the gap width = 2 * dt_ecs (distance to nearest boundary).
    # But this gives half-width from either side.
    # For cell-cell contact: we need ECS regions where the total gap between
    # two cells is < threshold.

    # Most practical: find ECS skeleton (medial axis) and measure gap width there.
    # Or: for each ECS voxel, gap_width = dt_ecs * 2 approximates the channel width.
    # A cell-cell contact at threshold T occurs where gap_width < T, i.e., dt_ecs < T/2.

    # Count: for each threshold, what fraction of cell-boundary ECS faces
    # are in regions where dt_ecs < T/2 (meaning the gap is narrow enough
    # that another cell is likely within T nm)?

    # For more accuracy: at each cell boundary face, trace into ECS and check
    # if another cell is within T. We approximate this by checking if the
    # ECS half-width at that face is < T (the gap to the other side is < T).

    # Compute for each cell boundary voxel the distance to nearest OTHER cell
    # We'll compute distance from all cells, then for each cell, the contact
    # distance is the distance from its boundary through ECS to the next cell.

    # Build a "nearest cell distance" field: for each ECS voxel, distance to
    # nearest cell boundary. This is just dt_ecs (distance from ECS voxel to
    # nearest non-ECS = cell boundary). So gap width at an ECS voxel =
    # dt_ecs from one side + dt_ecs from the other side. But dt_ecs gives
    # distance to nearest boundary, so for a thin channel between two cells,
    # a voxel in the middle has dt_ecs = half the gap width.

    # For cell boundary faces: the adjacent ECS voxel has dt_ecs = 1 voxel.
    # We need to know if ANOTHER cell is within T nm on the other side.

    # Best practical approach: for each cell, compute distance from that cell
    # outward through ECS. Where this distance < T AND another cell exists,
    # that's a contact.

    # To avoid per-cell distance transforms (expensive), use this trick:
    # 1. Compute dt from ALL cell boundaries into ECS (already have: dt_ecs)
    # 2. For each ECS voxel with dt_ecs < T, it's within T of SOME cell
    # 3. To check if TWO cells are within T of each other through that voxel,
    #    we need the voxel to be within T of cell A AND within T of cell B
    # 4. But dt_ecs gives distance to nearest cell, so we need distance to
    #    SECOND nearest cell.

    # Simplification that works well in practice:
    # Use the medial axis approach. At each point on the ECS medial axis
    # (local maximum of dt_ecs), the value represents the half-width.
    # If 2 * dt_ecs < T at a medial axis point, the two cells on either
    # side are within T of each other.

    # Let's use a direct approach: dilate each cell by threshold and check overlaps.
    # This is O(n_cells * n_thresholds) distance transforms, but most cells are small.

    # Actually the most efficient approach:
    # For each threshold T:
    #   - Find all ECS voxels where dt_ecs < T/2 (narrow channels)
    #   - In these narrow regions, find connected components
    #   - For each component, check which cell IDs border it
    #   - If >= 2 cell IDs border it, those cells are in "contact" at threshold T

    # Let's use a slightly different efficient approach:
    # 1. Invert: compute distance from cell boundary into ECS (= dt_ecs, done)
    # 2. For threshold T: consider ECS voxels with dt_ecs <= T/2
    #    These voxels are within T/2 of some cell boundary.
    #    If two cells each have boundary within T/2 of the same ECS voxel,
    #    those cells are within T of each other.
    # 3. For each cell: its "contact zone" at threshold T =
    #    cell boundary voxels whose nearest ECS neighbor has dt_ecs <= T/2
    #    (meaning the channel is <= T wide there)

    # For the per-crop summary, compute:
    # - fraction of total cell surface area in contact at each threshold
    # - number of cell pairs in contact at each threshold

    # Simple efficient implementation:
    # For each threshold, find narrow ECS (dt_ecs <= T/2),
    # then check which cells border these narrow regions.

    for T in CONTACT_THRESHOLDS:
        half_T = T / 2.0
        # ECS voxels in narrow channels (half-width < T/2)
        narrow_ecs = ecs_binary & (dt_ecs > 0) & (dt_ecs <= half_T)

        # For each cell, count how many of its boundary faces touch narrow ECS
        # We approximate by dilating narrow_ecs by 1 voxel and checking overlap with cells
        # Actually: cell boundary voxels are cell voxels adjacent to ECS.
        # We want cell boundary voxels adjacent to NARROW ECS.

        # Efficient: for each axis, check if cell voxel has narrow_ecs neighbor
        contact_mask = np.zeros_like(cell_data, dtype=bool)
        for axis in range(3):
            # Forward neighbor is narrow ECS
            cell_slice = [slice(None)] * 3
            ecs_slice = [slice(None)] * 3
            cell_slice[axis] = slice(0, -1)
            ecs_slice[axis] = slice(1, None)
            contact_mask[tuple(cell_slice)] |= (
                (cell_data[tuple(cell_slice)] != 0) & narrow_ecs[tuple(ecs_slice)]
            )
            # Backward neighbor
            cell_slice2 = [slice(None)] * 3
            ecs_slice2 = [slice(None)] * 3
            cell_slice2[axis] = slice(1, None)
            ecs_slice2[axis] = slice(0, -1)
            contact_mask[tuple(cell_slice2)] |= (
                (cell_data[tuple(cell_slice2)] != 0) & narrow_ecs[tuple(ecs_slice2)]
            )

        n_contact_voxels = int(np.count_nonzero(contact_mask))

        # Also compute: cell boundary voxels adjacent to ANY ECS (total boundary)
        if T == CONTACT_THRESHOLDS[0]:
            # Only compute total boundary once
            boundary_mask = np.zeros_like(cell_data, dtype=bool)
            for axis in range(3):
                cell_slice = [slice(None)] * 3
                ecs_slice = [slice(None)] * 3
                cell_slice[axis] = slice(0, -1)
                ecs_slice[axis] = slice(1, None)
                boundary_mask[tuple(cell_slice)] |= (
                    (cell_data[tuple(cell_slice)] != 0) & ecs_binary[tuple(ecs_slice)]
                )
                cell_slice2 = [slice(None)] * 3
                ecs_slice2 = [slice(None)] * 3
                cell_slice2[axis] = slice(1, None)
                ecs_slice2[axis] = slice(0, -1)
                boundary_mask[tuple(cell_slice2)] |= (
                    (cell_data[tuple(cell_slice2)] != 0) & ecs_binary[tuple(ecs_slice2)]
                )
            total_boundary_voxels = int(np.count_nonzero(boundary_mask))
            crop_result["total_boundary_voxels"] = total_boundary_voxels

        frac = n_contact_voxels / total_boundary_voxels if total_boundary_voxels > 0 else 0
        contact_results[T] = {
            "contact_voxels": n_contact_voxels,
            "contact_fraction": round(frac, 4),
        }

    contact_time = time.time() - t2
    print(f"  Contact mapping: {contact_time:.1f}s")
    for T in CONTACT_THRESHOLDS:
        cr = contact_results[T]
        print(f"    T={T}nm: {cr['contact_fraction']*100:.1f}% of boundary in contact")

    crop_result["contact_results"] = contact_results

    # ---- Metrics 1 & 2: Per-cell SA/V and sphericity ----
    t3 = time.time()
    per_cell_rows = []

    # Filter to cells with enough voxels
    cell_ids_large = []
    for cid in cell_ids:
        n = int(np.count_nonzero(cell_data == cid))
        if n >= MIN_CELL_VOXELS:
            cell_ids_large.append((cid, n))

    print(f"  {len(cell_ids_large)} cells >= {MIN_CELL_VOXELS} voxels "
          f"(of {len(cell_ids)} total)")

    for cid, n_voxels in cell_ids_large:
        cell_vol_nm3 = n_voxels * voxel_vol

        # SA/V: count ECS-facing faces
        ecs_faces, total_faces = count_boundary_faces(ecs_binary, cell_data, cid)
        # Average face area (approximate for isotropic, exact calc for anisotropic)
        avg_face_area = sum(face_areas) / 3.0  # For isotropic this is exact
        ecs_sa_nm2 = ecs_faces * avg_face_area
        total_sa_nm2 = total_faces * avg_face_area
        sa_v = ecs_sa_nm2 / cell_vol_nm3 if cell_vol_nm3 > 0 else 0

        # Sphericity: SA of equivalent sphere / actual SA
        r_equiv = (3 * cell_vol_nm3 / (4 * np.pi)) ** (1/3)
        sa_sphere = 4 * np.pi * r_equiv ** 2
        sphericity = sa_sphere / total_sa_nm2 if total_sa_nm2 > 0 else 0

        per_cell_rows.append({
            "dataset": dataset,
            "crop": crop_name,
            "tissue": tissue,
            "prep": prep,
            "cell_id": int(cid),
            "voxels": n_voxels,
            "volume_nm3": round(cell_vol_nm3, 1),
            "volume_um3": round(cell_vol_nm3 / 1e9, 4),
            "ecs_faces": ecs_faces,
            "total_faces": total_faces,
            "ecs_sa_nm2": round(ecs_sa_nm2, 1),
            "total_sa_nm2": round(total_sa_nm2, 1),
            "sa_v_ratio": round(sa_v, 8),
            "sphericity": round(sphericity, 4),
        })

    cell_time = time.time() - t3
    print(f"  Per-cell metrics: {len(per_cell_rows)} cells in {cell_time:.1f}s")
    if per_cell_rows:
        sav_vals = [r["sa_v_ratio"] for r in per_cell_rows]
        sph_vals = [r["sphericity"] for r in per_cell_rows]
        print(f"    SA/V: mean={np.mean(sav_vals):.6f}, median={np.median(sav_vals):.6f}")
        print(f"    Sphericity: mean={np.mean(sph_vals):.4f}, median={np.median(sph_vals):.4f}")

    # Crop-level summaries
    if per_cell_rows:
        sav_vals = [r["sa_v_ratio"] for r in per_cell_rows]
        sph_vals = [r["sphericity"] for r in per_cell_rows]
        crop_result["n_cells"] = len(per_cell_rows)
        crop_result["mean_sa_v"] = round(float(np.mean(sav_vals)), 8)
        crop_result["median_sa_v"] = round(float(np.median(sav_vals)), 8)
        crop_result["mean_sphericity"] = round(float(np.mean(sph_vals)), 4)
        crop_result["median_sphericity"] = round(float(np.median(sph_vals)), 4)
    else:
        crop_result["n_cells"] = 0
        crop_result["mean_sa_v"] = None
        crop_result["median_sa_v"] = None
        crop_result["mean_sphericity"] = None
        crop_result["median_sphericity"] = None

    return crop_result, per_cell_rows, contact_results


def main():
    base_dir = os.path.dirname(__file__)
    crop_csv = os.path.join(base_dir, "cell_morphology_crops.csv")
    cell_csv = os.path.join(base_dir, "cell_morphology_per_cell.csv")
    contact_csv = os.path.join(base_dir, "cell_morphology_contacts.csv")

    all_crop_results = []
    all_cell_rows = []
    all_contact_rows = []

    for dataset, crop, tissue, prep, local in CROPS:
        print(f"\nProcessing {dataset}/{crop} ({tissue}, {prep})...")
        crop_result, cell_rows, contact_results = analyze_crop(
            local, dataset, crop, tissue, prep
        )
        all_crop_results.append(crop_result)
        all_cell_rows.extend(cell_rows)

        # Flatten contact results into rows
        if contact_results:
            for T in CONTACT_THRESHOLDS:
                cr = contact_results[T]
                all_contact_rows.append({
                    "tissue": tissue,
                    "dataset": dataset,
                    "crop": crop,
                    "prep": prep,
                    "threshold_nm": T,
                    "contact_voxels": cr["contact_voxels"],
                    "total_boundary_voxels": crop_result.get("total_boundary_voxels", 0),
                    "contact_fraction": cr["contact_fraction"],
                })

        if crop_result["status"] != "OK":
            print(f"  -> {crop_result['status']}")

    # Write crop-level CSV
    crop_fields = [
        "tissue", "dataset", "crop", "prep", "status", "voxel_size_nm",
        "n_cells", "mean_sa_v", "median_sa_v", "mean_sphericity", "median_sphericity",
        "narrow_ecs_median_nm", "narrow_ecs_mean_nm", "narrow_ecs_p25_nm", "narrow_ecs_p75_nm",
        "narrow_ecs_voxels", "total_ecs_voxels", "total_boundary_voxels",
    ]
    # Add contact columns
    for T in CONTACT_THRESHOLDS:
        crop_fields.append(f"contact_frac_{T}nm")

    with open(crop_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=crop_fields)
        writer.writeheader()
        for cr in all_crop_results:
            row = {k: cr.get(k) for k in crop_fields if not k.startswith("contact_frac_")}
            contact = cr.get("contact_results", {})
            for T in CONTACT_THRESHOLDS:
                if T in contact:
                    row[f"contact_frac_{T}nm"] = contact[T]["contact_fraction"]
                else:
                    row[f"contact_frac_{T}nm"] = None
            writer.writerow(row)
    print(f"\nCrop results saved to {crop_csv}")

    # Write per-cell CSV
    if all_cell_rows:
        cell_fields = [
            "tissue", "dataset", "crop", "prep", "cell_id",
            "voxels", "volume_nm3", "volume_um3",
            "ecs_faces", "total_faces", "ecs_sa_nm2", "total_sa_nm2",
            "sa_v_ratio", "sphericity",
        ]
        with open(cell_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cell_fields)
            writer.writeheader()
            writer.writerows(all_cell_rows)
        print(f"Per-cell results saved to {cell_csv} ({len(all_cell_rows)} cells)")

    # Write contact CSV
    if all_contact_rows:
        contact_fields = [
            "tissue", "dataset", "crop", "prep",
            "threshold_nm", "contact_voxels", "total_boundary_voxels", "contact_fraction",
        ]
        with open(contact_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=contact_fields)
            writer.writeheader()
            writer.writerows(all_contact_rows)
        print(f"Contact results saved to {contact_csv}")


if __name__ == "__main__":
    main()
