"""
Measure ECS channel width via distance transform.

For each crop, computes the distance from every ECS voxel to the nearest
cell boundary (non-ECS voxel). The distribution of these distances
characterizes ECS gap width independent of crop placement.

This is more robust to regional bias than volume fraction because it
measures *how thick* the ECS channels are, not how much ECS there is.
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


def get_voxel_size(zarr_group):
    """Get voxel size from ecs multiscales metadata."""
    for label in ["ecs", "cell"]:
        if label not in zarr_group:
            continue
        attrs = dict(zarr_group[label].attrs)
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


def analyze_ecs_width(local_path, dataset, crop_name):
    """Compute ECS width statistics for a single crop."""
    result = {
        "dataset": dataset,
        "crop": crop_name,
        "status": "OK",
        "voxel_size_nm": None,
        "ecs_voxels": None,
        "median_half_width_nm": None,
        "mean_half_width_nm": None,
        "std_half_width_nm": None,
        "p25_half_width_nm": None,
        "p75_half_width_nm": None,
        "max_half_width_nm": None,
    }

    if not os.path.isdir(local_path):
        result["status"] = "NOT FOUND"
        return result

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        result["status"] = f"ERROR: {e}"
        return result

    if "ecs" not in z or "s0" not in z["ecs"]:
        result["status"] = "NO ECS LABEL"
        return result

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        result["status"] = "NO VOXEL SIZE"
        return result
    result["voxel_size_nm"] = str(voxel_size)

    # Load ECS mask
    t0 = time.time()
    ecs = z["ecs"]["s0"][:]
    load_time = time.time() - t0

    ecs_binary = (ecs == 1)
    n_ecs = int(np.count_nonzero(ecs_binary))
    result["ecs_voxels"] = n_ecs

    if n_ecs == 0:
        result["status"] = "NO ECS VOXELS"
        return result

    # Distance transform with physical spacing
    t1 = time.time()
    dt = distance_transform_edt(ecs_binary, sampling=voxel_size)
    dt_time = time.time() - t1

    ecs_distances = dt[ecs_binary]
    result["median_half_width_nm"] = round(float(np.median(ecs_distances)), 2)
    result["mean_half_width_nm"] = round(float(np.mean(ecs_distances)), 2)
    result["std_half_width_nm"] = round(float(np.std(ecs_distances)), 2)
    result["p25_half_width_nm"] = round(float(np.percentile(ecs_distances, 25)), 2)
    result["p75_half_width_nm"] = round(float(np.percentile(ecs_distances, 75)), 2)
    result["max_half_width_nm"] = round(float(np.max(ecs_distances)), 2)

    print(f"    load={load_time:.1f}s, dt={dt_time:.1f}s, "
          f"median={result['median_half_width_nm']}nm, "
          f"mean={result['mean_half_width_nm']}nm")

    return result


def main():
    output_path = os.path.join(os.path.dirname(__file__), "ecs_width.csv")
    results = []

    for dataset, crop, tissue, prep, local in CROPS:
        print(f"Processing {dataset}/{crop}...")
        r = analyze_ecs_width(local, dataset, crop)
        r["tissue"] = tissue
        r["prep"] = prep
        results.append(r)
        if r["status"] != "OK":
            print(f"  -> {r['status']}")

    fields = [
        "tissue", "dataset", "crop", "prep", "status", "voxel_size_nm", "ecs_voxels",
        "median_half_width_nm", "mean_half_width_nm", "std_half_width_nm",
        "p25_half_width_nm", "p75_half_width_nm", "max_half_width_nm",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
