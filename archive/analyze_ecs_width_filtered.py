"""
ECS channel width analysis with upper cutoff to exclude vessel lumens.

Filters to ECS voxels with half-width < CUTOFF_NM, then reports
distribution statistics within that filtered set.
"""
import zarr
import numpy as np
from scipy.ndimage import distance_transform_edt
import csv
import os
import time

NRS_BASE = "/Volumes/cellmap/data"
CUTOFF_NM = 200  # Exclude ECS voxels with half-width >= this

# Thresholds for "fraction of narrow ECS below X nm"
FRAC_THRESHOLDS = [10, 20, 30, 50, 75, 100]

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


def analyze_crop(local_path, dataset, crop_name, tissue, prep):
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

    if "ecs" not in z or "s0" not in z["ecs"]:
        result["status"] = "NO ECS LABEL"
        return result

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        result["status"] = "NO VOXEL SIZE"
        return result
    result["voxel_size_nm"] = str(voxel_size)

    t0 = time.time()
    ecs = z["ecs"]["s0"][:]
    load_time = time.time() - t0

    ecs_binary = (ecs == 1)
    total_ecs = int(np.count_nonzero(ecs_binary))
    result["total_ecs_voxels"] = total_ecs

    if total_ecs == 0:
        result["status"] = "NO ECS VOXELS"
        return result

    t1 = time.time()
    dt = distance_transform_edt(ecs_binary, sampling=voxel_size)
    dt_time = time.time() - t1

    # Full distribution stats (for reference)
    ecs_distances = dt[ecs_binary]
    result["full_median_nm"] = round(float(np.median(ecs_distances)), 2)
    result["full_mean_nm"] = round(float(np.mean(ecs_distances)), 2)

    # Filtered: only ECS voxels with half-width < CUTOFF_NM
    narrow_mask = (dt > 0) & (dt < CUTOFF_NM) & ecs_binary
    narrow_distances = dt[narrow_mask]
    n_narrow = len(narrow_distances)
    result["narrow_voxels"] = n_narrow
    result["narrow_fraction"] = round(n_narrow / total_ecs, 4) if total_ecs > 0 else 0

    if n_narrow > 0:
        result["narrow_p10_nm"] = round(float(np.percentile(narrow_distances, 10)), 2)
        result["narrow_p25_nm"] = round(float(np.percentile(narrow_distances, 25)), 2)
        result["narrow_median_nm"] = round(float(np.median(narrow_distances)), 2)
        result["narrow_mean_nm"] = round(float(np.mean(narrow_distances)), 2)
        result["narrow_p75_nm"] = round(float(np.percentile(narrow_distances, 75)), 2)
        result["narrow_p90_nm"] = round(float(np.percentile(narrow_distances, 90)), 2)
        result["narrow_std_nm"] = round(float(np.std(narrow_distances)), 2)

        # Fraction of narrow ECS below each threshold
        for T in FRAC_THRESHOLDS:
            frac = float(np.count_nonzero(narrow_distances < T)) / n_narrow
            result[f"frac_below_{T}nm"] = round(frac, 4)
    else:
        for key in ["narrow_p10_nm", "narrow_p25_nm", "narrow_median_nm",
                     "narrow_mean_nm", "narrow_p75_nm", "narrow_p90_nm", "narrow_std_nm"]:
            result[key] = None
        for T in FRAC_THRESHOLDS:
            result[f"frac_below_{T}nm"] = None

    print(f"  load={load_time:.1f}s, dt={dt_time:.1f}s")
    print(f"  Full: median={result['full_median_nm']}nm, "
          f"Narrow(<{CUTOFF_NM}nm): {n_narrow}/{total_ecs} voxels "
          f"({result['narrow_fraction']*100:.1f}%)")
    if n_narrow > 0:
        print(f"  Narrow dist: p10={result['narrow_p10_nm']}, "
              f"p25={result['narrow_p25_nm']}, "
              f"median={result['narrow_median_nm']}, "
              f"p75={result['narrow_p75_nm']}, "
              f"p90={result['narrow_p90_nm']}nm")
        fracs_str = ", ".join(f"<{T}nm:{result[f'frac_below_{T}nm']*100:.1f}%"
                              for T in FRAC_THRESHOLDS)
        print(f"  Fraction: {fracs_str}")

    return result


def main():
    output_path = os.path.join(os.path.dirname(__file__), "ecs_width_filtered.csv")

    fields = [
        "tissue", "dataset", "crop", "prep", "status", "voxel_size_nm",
        "total_ecs_voxels", "full_median_nm", "full_mean_nm",
        "narrow_voxels", "narrow_fraction",
        "narrow_p10_nm", "narrow_p25_nm", "narrow_median_nm", "narrow_mean_nm",
        "narrow_p75_nm", "narrow_p90_nm", "narrow_std_nm",
    ]
    for T in FRAC_THRESHOLDS:
        fields.append(f"frac_below_{T}nm")

    results = []
    for dataset, crop, tissue, prep, local in CROPS:
        print(f"\nProcessing {dataset}/{crop} ({tissue}, {prep})...")
        r = analyze_crop(local, dataset, crop, tissue, prep)
        results.append(r)
        if r["status"] != "OK":
            print(f"  -> {r['status']}")

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            row = {k: r.get(k) for k in fields}
            writer.writerow(row)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
