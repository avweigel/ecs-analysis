"""
Analyze ECS and cell voxel volumes from CellMap zarr groundtruth crops.

Reads metadata (complement_counts) from zarr attrs when available,
falls back to loading the actual array data when metadata is missing.

Outputs results to CSV.
"""
import zarr
import numpy as np
import csv
import os
import sys

# Path mappings:
# /nrs/data/... -> /Volumes/cellmap/data/...

NRS_BASE = "/Volumes/cellmap/data"

# Dataset definitions: (dataset, tissue, prep, [crops])
# Only includes crops with /nrs/ paths (skipping prfs-only crops)
DATASETS = [
    # Kidney
    ("jrc_mus-kidney", "Kidney", "Chemical",
     ["crop1026", "crop1027", "crop1028", "crop1029", "crop1030", "crop1031", "crop1032"]),
    ("jrc_mus-kidney-4", "Kidney", "Rapid HPF",
     ["crop1134", "crop1136", "crop1137", "crop1144"]),
    # Heart
    ("jrc_mus-heart-6", "Heart", "Chemical",
     ["crop1145", "crop1146", "crop1147"]),
    # jrc_mus-heart-4: all crops are on prfs, skipped
    # Liver
    ("jrc_mus-liver", "Liver", "Chemical",
     ["crop1038", "crop1039", "crop1040", "crop1041", "crop1042", "crop1043", "crop1044"]),
    ("jrc_mus-liver-8", "Liver", "Rapid HPF",
     ["crop1123", "crop1124", "crop1125", "crop1126", "crop1127",
      "crop1071", "crop1072", "crop1073", "crop1074", "crop1075"]),
    # Cortex
    ("jrc_mus-cortex-2", "Cortex", "Rapid HPF",
     ["crop1116", "crop1117"]),
    ("jrc_mus-cortex-3", "Cortex", "Chemical",
     ["crop1033", "crop1034", "crop1035", "crop1036", "crop1037", "crop1045", "crop1046"]),
    ("jrc_mus-cortex-4", "Cortex", "Rapid HPF",
     ["crop1139", "crop1141"]),
]

# Build flat crop list: (dataset, crop, tissue, prep, local_path)
CROPS = []
for dataset, tissue, prep, crop_list in DATASETS:
    for crop in crop_list:
        local = f"{NRS_BASE}/{dataset}/{dataset}.zarr/recon-1/labels/groundtruth/{crop}"
        CROPS.append((dataset, crop, tissue, prep, local))


def get_complement_counts(zarr_group, label_name):
    """Get voxel counts from zarr metadata (complement_counts in s0 attrs)."""
    if label_name not in zarr_group:
        return None
    label = zarr_group[label_name]
    if "s0" not in label:
        return None
    attrs = dict(label["s0"].attrs)
    return (
        attrs.get("cellmap", {})
        .get("annotation", {})
        .get("complement_counts", None)
    )


def get_annotation_type(zarr_group, label_name):
    """Get annotation type (semantic_segmentation or instance_segmentation)."""
    if label_name not in zarr_group:
        return None
    label = zarr_group[label_name]
    if "s0" not in label:
        return None
    attrs = dict(label["s0"].attrs)
    return (
        attrs.get("cellmap", {})
        .get("annotation", {})
        .get("annotation_type", {})
        .get("type", None)
    )


def get_voxel_size(zarr_group, label_name):
    """Get voxel size in nm from multiscales metadata."""
    if label_name not in zarr_group:
        return None
    attrs = dict(zarr_group[label_name].attrs)
    multiscales = attrs.get("cellmap", {}).get("multiscales") or attrs.get("multiscales")
    if not multiscales:
        return None
    datasets = multiscales[0].get("datasets", [])
    if not datasets:
        return None
    for t in datasets[0].get("coordinateTransformations", []):
        if t.get("type") == "scale":
            return t["scale"]
    return None


def get_shape(zarr_group):
    """Get the s0 shape from any available label."""
    for key in zarr_group.keys():
        sub = zarr_group[key]
        if hasattr(sub, "keys") and "s0" in sub:
            return sub["s0"].shape
    return None


def count_nonzero_from_data(zarr_group, label_name):
    """Fallback: load the actual array and count nonzero voxels."""
    if label_name not in zarr_group:
        return None
    label = zarr_group[label_name]
    if "s0" not in label:
        return None
    print(f"    Loading {label_name}/s0 data (no metadata available)...")
    data = label["s0"][:]
    nonzero = int(np.count_nonzero(data))
    total = int(data.size)
    return {"nonzero": nonzero, "zero": total - nonzero, "total": total}


def analyze_crop(local_path, dataset, crop_name):
    """Analyze a single crop and return a results dict."""
    result = {
        "dataset": dataset,
        "crop": crop_name,
        "status": "OK",
        "shape": None,
        "voxel_size_nm": None,
        "total_voxels": None,
        "total_volume_um3": None,
        "ecs_voxels": None,
        "ecs_pct": None,
        "ecs_volume_um3": None,
        "cell_voxels": None,
        "cell_pct": None,
        "cell_volume_um3": None,
        "ecs_method": None,
        "cell_method": None,
    }

    if not os.path.isdir(local_path):
        result["status"] = "NOT FOUND"
        return result

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        result["status"] = f"ERROR: {e}"
        return result

    shape = get_shape(z)
    result["shape"] = str(shape) if shape else None
    total = int(np.prod(shape)) if shape else None
    result["total_voxels"] = total

    # Voxel size (from zarr metadata)
    voxel_size = None
    for label in ["ecs", "cell"]:
        vs = get_voxel_size(z, label)
        if vs:
            voxel_size = vs
            result["voxel_size_nm"] = str(vs)
            break

    # Voxel volume in µm³: (nm³) / (1000³ nm³/µm³)
    voxel_vol_um3 = None
    if voxel_size:
        voxel_vol_um3 = (voxel_size[0] * voxel_size[1] * voxel_size[2]) / 1e9

    if total is not None and voxel_vol_um3 is not None:
        result["total_volume_um3"] = round(total * voxel_vol_um3, 4)

    has_ecs = "ecs" in z
    has_cell = "cell" in z

    # --- ECS ---
    if has_ecs:
        cc = get_complement_counts(z, "ecs")
        if cc and "present" in cc:
            result["ecs_voxels"] = cc["present"]
            result["ecs_method"] = "metadata"
        else:
            # Fallback to loading data
            counts = count_nonzero_from_data(z, "ecs")
            if counts:
                result["ecs_voxels"] = counts["nonzero"]
                result["ecs_method"] = "computed"
    else:
        result["ecs_method"] = "no_label"

    # --- Cell ---
    if has_cell:
        cc = get_complement_counts(z, "cell")
        ann_type = get_annotation_type(z, "cell")
        if cc and "absent" in cc and total:
            # For instance segmentation: nonzero = total - absent
            result["cell_voxels"] = total - cc["absent"]
            result["cell_method"] = "metadata"
        else:
            counts = count_nonzero_from_data(z, "cell")
            if counts:
                result["cell_voxels"] = counts["nonzero"]
                result["cell_method"] = "computed"
    else:
        result["cell_method"] = "no_label"

    # Percentages and physical volumes
    if total and result["ecs_voxels"] is not None:
        result["ecs_pct"] = round(100 * result["ecs_voxels"] / total, 2)
        if voxel_vol_um3:
            result["ecs_volume_um3"] = round(result["ecs_voxels"] * voxel_vol_um3, 4)
    if total and result["cell_voxels"] is not None:
        result["cell_pct"] = round(100 * result["cell_voxels"] / total, 2)
        if voxel_vol_um3:
            result["cell_volume_um3"] = round(result["cell_voxels"] * voxel_vol_um3, 4)

    return result


def main():
    output_path = os.path.join(os.path.dirname(__file__), "ecs_cell_volumes.csv")
    results = []

    for dataset, crop, tissue, prep, local in CROPS:
        print(f"Processing {dataset}/{crop}...")
        r = analyze_crop(local, dataset, crop)
        r["tissue"] = tissue
        r["prep"] = prep
        results.append(r)
        if r["status"] != "OK":
            print(f"  -> {r['status']}")
        else:
            print(f"  ECS: {r['ecs_voxels']} ({r['ecs_pct']}%)  Cell: {r['cell_voxels']} ({r['cell_pct']}%)")

    # Write CSV
    fields = [
        "tissue", "dataset", "crop", "prep", "status", "shape", "voxel_size_nm",
        "total_voxels", "total_volume_um3",
        "ecs_voxels", "ecs_pct", "ecs_volume_um3",
        "cell_voxels", "cell_pct", "cell_volume_um3",
        "ecs_method", "cell_method",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
