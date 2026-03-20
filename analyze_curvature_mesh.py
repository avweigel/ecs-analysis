"""
Mesh-based surface curvature analysis of cell membranes at ECS-facing surfaces.

For each cell:
  1. Gaussian-smooth the binary mask (fixed physical scale SIGMA_NM)
  2. Extract isosurface mesh via marching cubes at the 0.5 level
  3. Compute discrete mean curvature via the cotangent Laplacian
  4. Identify ECS-facing vertices (within 1 voxel of ECS)
  5. Report curvature statistics at ECS-facing vertices

Advantages over voxel-based level-set curvature:
  - Sub-voxel vertex interpolation naturally smooths voxel staircasing
  - Cotangent Laplacian is the standard for discrete differential geometry
  - Curvature is defined per-vertex on a proper manifold, not on a grid

Curvature in units of 1/nm. Positive = convex (bulging into ECS),
negative = concave (invagination).
"""
import zarr
import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes
import trimesh
import csv
import os
import time

NRS_BASE = "/Volumes/cellmap-1/data"
SIGMA_NM = 16.0  # Physical smoothing scale (nm)
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
        local = "{}/{}/{}.zarr/recon-1/labels/groundtruth/{}".format(
            NRS_BASE, dataset, dataset, crop)
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


def compute_mesh_curvature(cell_mask, voxel_size_nm):
    """Extract mesh from smoothed binary mask and compute discrete mean curvature.

    Returns (vertices_nm, faces, curvature_per_vertex) or None if mesh extraction fails.
    Vertices are in physical (nm) coordinates.
    """
    # Gaussian smooth the binary mask
    sigma_voxels = [SIGMA_NM / v for v in voxel_size_nm]
    phi = gaussian_filter(cell_mask.astype(np.float32), sigma=sigma_voxels)

    # Extract isosurface at 0.5 level
    try:
        verts_voxel, faces, _, _ = marching_cubes(phi, level=0.5,
                                                   spacing=tuple(voxel_size_nm))
    except (ValueError, RuntimeError):
        return None

    if len(verts_voxel) < 10 or len(faces) < 10:
        return None

    # verts_voxel is already in physical nm coordinates (due to spacing param)
    mesh = trimesh.Trimesh(vertices=verts_voxel, faces=faces, process=False)

    # Compute discrete mean curvature via trimesh
    # trimesh.curvature.discrete_mean_curvature_measure uses the angle deficit method
    # For better results, use the cotangent Laplacian approach
    H = _cotangent_mean_curvature(mesh)

    return verts_voxel, faces, H


def _cotangent_mean_curvature(mesh):
    """Compute mean curvature at each vertex using the cotangent Laplacian.

    Vectorized implementation for performance on large meshes.

    Returns signed mean curvature per vertex (positive = convex outward).
    """
    verts = mesh.vertices  # (V, 3)
    faces = mesh.faces     # (F, 3)
    n_verts = len(verts)
    n_faces = len(faces)

    # Get triangle vertex positions: (F, 3, 3) -> v0, v1, v2
    v0 = verts[faces[:, 0]]  # (F, 3)
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]

    # Edge vectors
    e01 = v1 - v0  # (F, 3)
    e02 = v2 - v0
    e12 = v2 - v1

    # Cross products and triangle areas
    cross012 = np.cross(e01, e02)  # (F, 3)
    tri_area = 0.5 * np.linalg.norm(cross012, axis=1)  # (F,)
    cross_mag = 2.0 * tri_area  # magnitude of cross product

    # Skip degenerate triangles
    valid = tri_area > 1e-20
    eps = 1e-30

    # Cotangents at each vertex of each triangle
    # cot(angle at v0) = dot(e01, e02) / |cross(e01, e02)|
    cot0 = np.zeros(n_faces)
    cot1 = np.zeros(n_faces)
    cot2 = np.zeros(n_faces)

    cot0[valid] = (np.sum(e01[valid] * e02[valid], axis=1) /
                   (cross_mag[valid] + eps))
    cot1[valid] = (np.sum(-e01[valid] * e12[valid], axis=1) /
                   (np.linalg.norm(np.cross(-e01[valid], e12[valid]), axis=1) + eps))
    cot2[valid] = (np.sum(-e02[valid] * -e12[valid], axis=1) /
                   (np.linalg.norm(np.cross(-e02[valid], -e12[valid]), axis=1) + eps))

    # Per-vertex area (1/3 of each adjacent triangle)
    area = np.zeros(n_verts)
    a3 = tri_area / 3.0
    np.add.at(area, faces[:, 0], a3)
    np.add.at(area, faces[:, 1], a3)
    np.add.at(area, faces[:, 2], a3)

    # Cotangent Laplacian accumulation
    laplacian = np.zeros((n_verts, 3))

    # Edge (v1, v2) opposite v0 -> weight cot0
    diff_12 = v2 - v1  # v2 - v1
    diff_21 = -diff_12
    for d in range(3):
        np.add.at(laplacian[:, d], faces[:, 1], cot0 * diff_12[:, d])
        np.add.at(laplacian[:, d], faces[:, 2], cot0 * diff_21[:, d])

    # Edge (v0, v2) opposite v1 -> weight cot1
    diff_02 = v2 - v0
    diff_20 = -diff_02
    for d in range(3):
        np.add.at(laplacian[:, d], faces[:, 0], cot1 * diff_02[:, d])
        np.add.at(laplacian[:, d], faces[:, 2], cot1 * diff_20[:, d])

    # Edge (v0, v1) opposite v2 -> weight cot2
    diff_01 = v1 - v0
    diff_10 = -diff_01
    for d in range(3):
        np.add.at(laplacian[:, d], faces[:, 0], cot2 * diff_01[:, d])
        np.add.at(laplacian[:, d], faces[:, 1], cot2 * diff_10[:, d])

    # Mean curvature normal: Hn = laplacian / (2 * area)
    safe_area = np.maximum(area, 1e-20)
    Hn = laplacian / (2.0 * safe_area[:, np.newaxis])

    # Mean curvature magnitude
    H_mag = np.linalg.norm(Hn, axis=1)

    # Sign convention: positive = convex (bulging outward into ECS)
    # Vertex normals point outward from the mesh surface
    normals = mesh.vertex_normals
    # For convex regions, Hn points inward (toward center of curvature)
    # so dot(Hn, outward_normal) < 0 means convex
    sign = np.sign(np.sum(Hn * normals, axis=1))
    H_signed = -sign * H_mag

    return H_signed


def find_ecs_facing_vertices(verts_nm, voxel_size_nm, ecs_mask, sub_origin):
    """Identify mesh vertices that are near ECS voxels.

    verts_nm: vertex positions in nm (relative to sub-volume origin)
    voxel_size_nm: voxel size in nm
    ecs_mask: binary ECS mask for the sub-volume
    sub_origin: not used (vertices are already relative to sub-volume)

    Returns boolean mask over vertices.
    """
    # Convert vertex positions back to voxel coordinates
    vx = np.array(voxel_size_nm)
    verts_voxel = verts_nm / vx[np.newaxis, :]

    # Round to nearest voxel
    vi = np.round(verts_voxel).astype(int)

    # Clamp to volume bounds
    for dim in range(3):
        vi[:, dim] = np.clip(vi[:, dim], 0, ecs_mask.shape[dim] - 1)

    # Check if nearest voxel or any 6-neighbor is ECS
    ecs_facing = np.zeros(len(verts_nm), dtype=bool)

    # Check the vertex voxel itself
    ecs_facing |= ecs_mask[vi[:, 0], vi[:, 1], vi[:, 2]]

    # Check 6-connected neighbors
    for axis in range(3):
        for delta in [-1, 1]:
            shifted = vi.copy()
            shifted[:, axis] += delta
            shifted[:, axis] = np.clip(shifted[:, axis], 0, ecs_mask.shape[axis] - 1)
            ecs_facing |= ecs_mask[shifted[:, 0], shifted[:, 1], shifted[:, 2]]

    return ecs_facing


def analyze_crop(local_path, dataset, crop_name, tissue, prep):
    """Analyze mesh-based curvature for all cells in a crop."""
    if not os.path.isdir(local_path):
        print("  NOT FOUND")
        return []

    try:
        z = zarr.open(local_path, mode="r")
    except Exception as e:
        print("  ERROR: {}".format(e))
        return []

    has_ecs = "ecs" in z and "s0" in z.get("ecs", {})
    has_cell = "cell" in z and "s0" in z.get("cell", {})
    if not has_ecs or not has_cell:
        print("  MISSING LABELS")
        return []

    voxel_size = get_voxel_size(z)
    if not voxel_size:
        print("  NO VOXEL SIZE")
        return []

    vx = [float(v) for v in voxel_size]
    voxel_vol = vx[0] * vx[1] * vx[2]

    t0 = time.time()
    ecs_data = z["ecs"]["s0"][:]
    cell_data = z["cell"]["s0"][:]
    print("  Loaded in {:.1f}s, shape={}, voxel={}nm".format(
        time.time() - t0, ecs_data.shape, vx[0]))

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

    print("  {} cells above volume threshold".format(len(cell_ids_large)))

    per_cell_rows = []
    t1 = time.time()
    n_skipped_mesh = 0

    for i, (cid, n_voxels) in enumerate(cell_ids_large):
        # Extract bounding box with padding for smoothing
        coords = np.argwhere(cell_data == cid)
        pad = max(int(SIGMA_NM / min(vx) * 3), 4)
        slices = []
        for dim in range(3):
            lo = max(0, coords[:, dim].min() - pad)
            hi = min(cell_data.shape[dim], coords[:, dim].max() + pad + 1)
            slices.append(slice(lo, hi))

        sub_cell = cell_data[slices[0], slices[1], slices[2]]
        sub_ecs = ecs_binary[slices[0], slices[1], slices[2]]
        cell_mask = (sub_cell == cid)

        # Extract mesh and compute curvature
        result = compute_mesh_curvature(cell_mask, vx)
        if result is None:
            n_skipped_mesh += 1
            continue

        verts_nm, faces, H_per_vertex = result

        # Identify ECS-facing vertices
        ecs_facing = find_ecs_facing_vertices(verts_nm, vx, sub_ecs, None)
        n_ecs_verts = int(np.count_nonzero(ecs_facing))

        if n_ecs_verts < 10:
            continue

        # Curvature at ECS-facing vertices
        curv_ecs = H_per_vertex[ecs_facing]

        abs_curv = np.abs(curv_ecs)
        median_abs_H = float(np.median(abs_curv))
        mean_abs_H = float(np.mean(abs_curv))
        std_H = float(np.std(curv_ecs))
        p25_H = float(np.percentile(curv_ecs, 25))
        p75_H = float(np.percentile(curv_ecs, 75))

        frac_convex = float(np.mean(curv_ecs > 0))
        frac_concave = float(np.mean(curv_ecs < 0))

        median_radius_nm = 1.0 / median_abs_H if median_abs_H > 1e-10 else float('inf')

        per_cell_rows.append({
            "tissue": tissue,
            "dataset": dataset,
            "crop": crop_name,
            "prep": prep,
            "cell_id": int(cid),
            "n_voxels": n_voxels,
            "volume_nm3": round(n_voxels * voxel_vol, 1),
            "n_mesh_verts": len(verts_nm),
            "n_mesh_faces": len(faces),
            "n_ecs_verts": n_ecs_verts,
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
    print("  Mesh curvature: {} cells in {:.1f}s ({} skipped)".format(
        len(per_cell_rows), elapsed, n_skipped_mesh))

    if per_cell_rows:
        abs_h = [r['median_abs_H'] for r in per_cell_rows]
        radii = [r['median_radius_nm'] for r in per_cell_rows if r['median_radius_nm'] < 1e6]
        convex = [r['frac_convex'] for r in per_cell_rows]
        print("    Median |H|: {:.6f} 1/nm".format(np.median(abs_h)))
        if radii:
            print("    Median radius of curvature: {:.1f} nm".format(np.median(radii)))
        print("    Fraction convex: {:.3f}".format(np.mean(convex)))

    return per_cell_rows


def main():
    base_dir = os.path.dirname(__file__)
    out_csv = os.path.join(base_dir, "cell_curvature_mesh.csv")

    all_rows = []

    for dataset, crop, tissue, prep, local in CROPS:
        print("\nProcessing {}/{} ({}, {})...".format(dataset, crop, tissue, prep))
        rows = analyze_crop(local, dataset, crop, tissue, prep)
        all_rows.extend(rows)

    if all_rows:
        fields = [
            "tissue", "dataset", "crop", "prep", "cell_id",
            "n_voxels", "volume_nm3", "n_mesh_verts", "n_mesh_faces",
            "n_ecs_verts",
            "median_abs_H", "mean_abs_H", "std_H", "p25_H", "p75_H",
            "frac_convex", "frac_concave", "median_radius_nm",
        ]
        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(all_rows)
        print("\nMesh curvature results saved to {} ({} cells)".format(
            out_csv, len(all_rows)))

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

    print("\n=== Mesh Mean Curvature |H| (1/nm) by group ===")
    for (tissue, prep), vals in sorted(groups.items()):
        h = vals["abs_h"]
        n = len(h)
        m = stat.mean(h)
        sem = stat.stdev(h) / n**0.5 if n > 1 else 0
        print("  {:8s} {:12s}  n={:>4}  mean={:.6f} +/- {:.6f}".format(
            tissue, prep, n, m, sem))

    print("\n=== Median Radius of Curvature (nm) by group ===")
    for (tissue, prep), vals in sorted(groups.items()):
        r = vals["radius"]
        n = len(r)
        if n > 0:
            m = stat.mean(r)
            md = stat.median(r)
            sem = stat.stdev(r) / n**0.5 if n > 1 else 0
            print("  {:8s} {:12s}  n={:>4}  mean={:.1f} +/- {:.1f}  median={:.1f}".format(
                tissue, prep, n, m, sem, md))

    print("\n=== Fraction Convex Surface by group ===")
    for (tissue, prep), vals in sorted(groups.items()):
        c = vals["convex"]
        n = len(c)
        m = stat.mean(c)
        sem = stat.stdev(c) / n**0.5 if n > 1 else 0
        print("  {:8s} {:12s}  n={:>4}  mean={:.3f} +/- {:.3f}".format(
            tissue, prep, n, m, sem))


if __name__ == "__main__":
    main()
