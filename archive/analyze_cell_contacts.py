"""
Cell-cell contact distance mapping using Voronoi tessellation of ECS.

For each ECS voxel, assigns it to the nearest cell (Voronoi diagram).
At Voronoi boundaries (where adjacent ECS voxels belong to different cells),
the gap width = dt_ecs[V1] + dt_ecs[V2] + inter-voxel distance.

For each distance threshold T, computes what fraction of inter-cell
Voronoi boundary faces have gap < T (i.e., cells are within T nm).
"""
import zarr
import numpy as np
from scipy.ndimage import distance_transform_edt
import csv
import os
import time

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

CONTACT_THRESHOLDS = [10, 20, 40, 80, 160, 320]


def get_voxel_size(zarr_group):
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


def analyze_contacts(local_path, dataset, crop_name, tissue, prep):
    """Analyze cell-cell contact distances using Voronoi tessellation of ECS."""
    result = {
        "tissue": tissue, "dataset": dataset, "crop": crop_name,
        "prep": prep, "status": "OK", "voxel_size_nm": None,
    }

    if not os.path.isdir(local_path):
        result["status"] = "NOT FOUND"
        return result

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        result["status"] = f"ERROR: {e}"
        return result

    has_ecs = "ecs" in z and "s0" in z.get("ecs", {})
    has_cell = "cell" in z and "s0" in z.get("cell", {})
    if not has_ecs or not has_cell:
        result["status"] = "MISSING LABELS"
        return result

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        result["status"] = "NO VOXEL SIZE"
        return result
    result["voxel_size_nm"] = str(voxel_size)
    vx = np.array(voxel_size)

    t0 = time.time()
    ecs_data = z["ecs"]["s0"][:]
    cell_data = z["cell"]["s0"][:]
    load_time = time.time() - t0
    print(f"  Loaded in {load_time:.1f}s, shape={ecs_data.shape}")

    ecs_binary = (ecs_data == 1)

    # Distance transform of ECS (distance from each ECS voxel to nearest cell boundary)
    t1 = time.time()
    dt_ecs = distance_transform_edt(ecs_binary, sampling=voxel_size)

    # Voronoi assignment: assign each ECS voxel to nearest cell
    # distance_transform_edt on (cell_data == 0) gives distance from each
    # non-cell voxel to nearest cell voxel, and return_indices gives the
    # location of that nearest cell voxel
    cell_mask = (cell_data != 0)
    dt_from_cells, nearest_idx = distance_transform_edt(
        ~cell_mask, sampling=voxel_size, return_indices=True
    )
    # For each voxel, the cell ID of its nearest cell
    voronoi_labels = cell_data[nearest_idx[0], nearest_idx[1], nearest_idx[2]]
    dt_time = time.time() - t1
    print(f"  Distance transforms: {dt_time:.1f}s")

    # Find Voronoi boundaries in ECS: adjacent ECS voxels assigned to different cells
    # At each boundary face, gap = dt_ecs[V1] + dt_ecs[V2] + inter-voxel spacing
    t2 = time.time()
    total_voronoi_faces = 0
    gap_widths = []  # gap width at each Voronoi boundary face

    for axis in range(3):
        spacing = vx[axis]
        s1 = [slice(None)] * 3
        s2 = [slice(None)] * 3
        s1[axis] = slice(0, -1)
        s2[axis] = slice(1, None)
        s1 = tuple(s1)
        s2 = tuple(s2)

        # Both voxels must be ECS
        both_ecs = ecs_binary[s1] & ecs_binary[s2]
        # Different Voronoi labels (assigned to different cells)
        diff_label = (voronoi_labels[s1] != voronoi_labels[s2]) & both_ecs

        if np.any(diff_label):
            # Gap width at each boundary face
            gaps = dt_ecs[s1][diff_label] + dt_ecs[s2][diff_label] + spacing
            gap_widths.append(gaps)
            total_voronoi_faces += int(np.count_nonzero(diff_label))

    if gap_widths:
        all_gaps = np.concatenate(gap_widths)
    else:
        all_gaps = np.array([])

    boundary_time = time.time() - t2
    print(f"  Voronoi boundary analysis: {boundary_time:.1f}s, "
          f"{total_voronoi_faces} boundary faces")

    result["total_voronoi_faces"] = total_voronoi_faces

    if len(all_gaps) > 0:
        result["gap_median_nm"] = round(float(np.median(all_gaps)), 2)
        result["gap_mean_nm"] = round(float(np.mean(all_gaps)), 2)
        result["gap_p25_nm"] = round(float(np.percentile(all_gaps, 25)), 2)
        result["gap_p75_nm"] = round(float(np.percentile(all_gaps, 75)), 2)
        result["gap_min_nm"] = round(float(np.min(all_gaps)), 2)
        print(f"  Gap widths: median={result['gap_median_nm']}nm, "
              f"mean={result['gap_mean_nm']}nm, "
              f"min={result['gap_min_nm']}nm")

        for T in CONTACT_THRESHOLDS:
            frac = float(np.count_nonzero(all_gaps < T)) / len(all_gaps)
            result[f"contact_frac_{T}nm"] = round(frac, 4)
            print(f"    T<{T}nm: {frac*100:.1f}%")
    else:
        result["gap_median_nm"] = None
        result["gap_mean_nm"] = None
        result["gap_p25_nm"] = None
        result["gap_p75_nm"] = None
        result["gap_min_nm"] = None
        for T in CONTACT_THRESHOLDS:
            result[f"contact_frac_{T}nm"] = None
        print("  No Voronoi boundary faces found")

    return result


def main():
    base_dir = os.path.dirname(__file__)
    output_csv = os.path.join(base_dir, "cell_contacts.csv")

    fields = [
        "tissue", "dataset", "crop", "prep", "status", "voxel_size_nm",
        "total_voronoi_faces", "gap_median_nm", "gap_mean_nm",
        "gap_p25_nm", "gap_p75_nm", "gap_min_nm",
    ]
    for T in CONTACT_THRESHOLDS:
        fields.append(f"contact_frac_{T}nm")

    results = []
    for dataset, crop, tissue, prep, local in CROPS:
        print(f"\nProcessing {dataset}/{crop} ({tissue}, {prep})...")
        r = analyze_contacts(local, dataset, crop, tissue, prep)
        results.append(r)
        if r["status"] != "OK":
            print(f"  -> {r['status']}")

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            row = {k: r.get(k) for k in fields}
            writer.writerow(row)

    print(f"\nResults saved to {output_csv}")


if __name__ == "__main__":
    main()
