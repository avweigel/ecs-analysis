"""
Crop-level membrane topology metrics, pooled across cells.

For each cell fragment in a crop that has enough ECS-facing surface:
  - Extract a triangulated mesh via marching cubes on a physically-scaled
    Gaussian-smoothed binary mask.
  - Compute signed mean curvature H at each mesh vertex (sign convention
    validated on synthetic spheres: convex -> positive H).
  - Restrict to ECS-facing vertices.
  - Compute local-plane deviation at each ROUGHNESS_SCALES_NM scale.
  - Find protrusions (local maxima) and indentations (local minima) of
    the FEATURE_SMOOTHING_NM deviation field that exceed
    FEATURE_AMPLITUDE_NM.

All per-vertex quantities from all cells in a crop are POOLED (with their
per-vertex barycentric areas as weights for roughness and feature
density). The pool is the crop's "membrane sample" — one set of
distribution statistics per crop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import (
    CURVATURE_SIGMA_NM,
    FEATURE_AMPLITUDE_NM,
    FEATURE_NEIGHBORHOOD_NM,
    FEATURE_SMOOTHING_NM,
    FLAT_CURVATURE_THRESHOLD,
    MIN_ECS_SURFACE_NM2,
    ROUGHNESS_SCALES_NM,
)
from ..geometry import (
    CellMesh,
    classify_ecs_facing_vertices,
    local_extrema_on_mesh,
    rms_roughness,
    signed_mean_curvature,
    smoothed_surface_deviation,
)
from ..io import CropData, iter_cells


@dataclass
class CropTopology:
    crop: str
    tissue: str
    prep: str
    region_group: str | None
    voxel_nm: float

    # Inclusion bookkeeping
    n_cells_considered: int
    n_cells_included: int
    total_ecs_surface_nm2: float   # pooled vertex-area over included cells

    # Curvature distribution (over ECS-facing vertices, weighted by vertex area)
    curvature_abs_median_per_nm: float
    curvature_abs_p25_per_nm: float
    curvature_abs_p75_per_nm: float
    curvature_signed_median_per_nm: float
    curvature_signed_p10_per_nm: float
    curvature_signed_p90_per_nm: float
    curvature_std_per_nm: float
    curvature_iqr_per_nm: float
    fraction_convex: float          # H > +FLAT
    fraction_concave: float         # H < -FLAT
    fraction_flat: float            # |H| <= FLAT

    # Multi-scale roughness: RMS(deviation) per scale (nm)
    roughness_rms_nm: dict[float, float]

    # Feature density per um^2 of ECS-facing surface
    protrusion_density_per_um2: float
    indentation_density_per_um2: float
    protrusion_count: int
    indentation_count: int


def _vertex_area_weighted_percentile(values, weights, p_list):
    """Compute weighted percentiles. `values` and `weights` are 1-D arrays;
    `p_list` is an iterable of percentile points in [0, 100].
    Returns a dict {p: value}."""
    if len(values) == 0:
        return {p: float("nan") for p in p_list}
    order = np.argsort(values)
    v = values[order]
    w = weights[order]
    cum = np.cumsum(w)
    total = cum[-1]
    if total <= 0:
        return {p: float("nan") for p in p_list}
    out = {}
    for p in p_list:
        target = (p / 100.0) * total
        idx = int(np.searchsorted(cum, target, side="left"))
        idx = min(idx, len(v) - 1)
        out[p] = float(v[idx])
    return out


def compute(data: CropData) -> CropTopology:
    voxel_size = data.voxel_size_nm
    vs = float(voxel_size[0])
    face_area = (vs ** 2)  # isotropic

    pooled_H = []
    pooled_area = []
    pooled_verts = []
    pooled_deviations = {float(s): [] for s in ROUGHNESS_SCALES_NM}

    n_considered = 0
    n_included = 0
    feature_pool_dev = []
    feature_pool_verts = []
    feature_pool_areas = []
    total_area = 0.0

    # For each cell with >= MIN_ECS_SURFACE_NM2 ECS-facing surface, extract
    # its mesh and pool vertex-level values.
    for cid, n_voxels in iter_cells(data, min_voxels=1):
        n_considered += 1
        cell_mask = (data.cell == cid)

        mesh = CellMesh.from_mask(cell_mask, voxel_size, sigma_nm=CURVATURE_SIGMA_NM)
        if mesh is None:
            continue

        # Classify ECS-facing vertices using the effective ECS mask.
        ecs_facing = classify_ecs_facing_vertices(
            mesh.verts_nm, voxel_size, data.ecs
        )
        if int(ecs_facing.sum()) < 10:
            continue

        H_signed, vert_area = signed_mean_curvature(mesh.trimesh)
        area_ecs = float(vert_area[ecs_facing].sum())
        if area_ecs < MIN_ECS_SURFACE_NM2:
            continue

        n_included += 1
        total_area += area_ecs
        pooled_H.append(H_signed[ecs_facing])
        pooled_area.append(vert_area[ecs_facing])
        pooled_verts.append(mesh.verts_nm[ecs_facing])

        verts_ecs = mesh.verts_nm[ecs_facing]
        for scale in ROUGHNESS_SCALES_NM:
            dev_full, _ = smoothed_surface_deviation(mesh.trimesh, float(scale))
            pooled_deviations[float(scale)].append(dev_full[ecs_facing])

        # Feature detection at FEATURE_SMOOTHING_NM scale
        feat_dev_full, _ = smoothed_surface_deviation(mesh.trimesh, FEATURE_SMOOTHING_NM)
        feat_dev = feat_dev_full[ecs_facing]
        feature_pool_dev.append(feat_dev)
        feature_pool_verts.append(verts_ecs)
        feature_pool_areas.append(vert_area[ecs_facing])

    # If no cells passed inclusion, return a row of NaNs (still useful as a
    # placeholder so the crop isn't silently dropped downstream).
    if n_included == 0:
        nan_pct = lambda: float("nan")
        return CropTopology(
            crop=data.crop.crop, tissue=data.crop.tissue, prep=data.crop.prep,
            region_group=data.crop.region_group, voxel_nm=vs,
            n_cells_considered=n_considered, n_cells_included=0,
            total_ecs_surface_nm2=0.0,
            curvature_abs_median_per_nm=nan_pct(),
            curvature_abs_p25_per_nm=nan_pct(),
            curvature_abs_p75_per_nm=nan_pct(),
            curvature_signed_median_per_nm=nan_pct(),
            curvature_signed_p10_per_nm=nan_pct(),
            curvature_signed_p90_per_nm=nan_pct(),
            curvature_std_per_nm=nan_pct(),
            curvature_iqr_per_nm=nan_pct(),
            fraction_convex=nan_pct(),
            fraction_concave=nan_pct(),
            fraction_flat=nan_pct(),
            roughness_rms_nm={float(s): nan_pct() for s in ROUGHNESS_SCALES_NM},
            protrusion_density_per_um2=nan_pct(),
            indentation_density_per_um2=nan_pct(),
            protrusion_count=0, indentation_count=0,
        )

    H_all = np.concatenate(pooled_H)
    A_all = np.concatenate(pooled_area)

    # Area-weighted curvature percentiles
    abs_pct = _vertex_area_weighted_percentile(np.abs(H_all), A_all, [25, 50, 75])
    signed_pct = _vertex_area_weighted_percentile(H_all, A_all, [10, 50, 90])

    total_weight = float(A_all.sum())
    mean_H = float(np.average(H_all, weights=A_all))
    var_H = float(np.average((H_all - mean_H) ** 2, weights=A_all))
    std_H = float(np.sqrt(var_H))
    iqr_H = float(abs_pct[75] - abs_pct[25]) if np.isfinite(abs_pct[75]) else float("nan")

    # Area-weighted sign-class fractions
    convex_mask = H_all > FLAT_CURVATURE_THRESHOLD
    concave_mask = H_all < -FLAT_CURVATURE_THRESHOLD
    flat_mask = np.abs(H_all) <= FLAT_CURVATURE_THRESHOLD
    frac_convex = float(A_all[convex_mask].sum() / total_weight)
    frac_concave = float(A_all[concave_mask].sum() / total_weight)
    frac_flat = float(A_all[flat_mask].sum() / total_weight)

    # Multi-scale roughness: RMS of deviation, weighted by vertex area, pooled
    roughness = {}
    for scale_key, devs in pooled_deviations.items():
        dev_all = np.concatenate(devs)
        roughness[scale_key] = float(rms_roughness(dev_all, vert_area=A_all))

    # Feature detection - per cell (local extrema), then pooled count
    protrusions = 0
    indentations = 0
    for dev, verts_ecs in zip(feature_pool_dev, feature_pool_verts):
        maxima, minima = local_extrema_on_mesh(
            dev, verts_ecs,
            radius_nm=FEATURE_NEIGHBORHOOD_NM,
            amplitude_threshold=FEATURE_AMPLITUDE_NM,
        )
        protrusions += int(len(maxima))
        indentations += int(len(minima))

    area_um2 = total_area / 1e6
    prot_density = protrusions / area_um2 if area_um2 > 0 else float("nan")
    ind_density = indentations / area_um2 if area_um2 > 0 else float("nan")

    return CropTopology(
        crop=data.crop.crop,
        tissue=data.crop.tissue,
        prep=data.crop.prep,
        region_group=data.crop.region_group,
        voxel_nm=vs,
        n_cells_considered=n_considered,
        n_cells_included=n_included,
        total_ecs_surface_nm2=total_area,
        curvature_abs_median_per_nm=abs_pct[50],
        curvature_abs_p25_per_nm=abs_pct[25],
        curvature_abs_p75_per_nm=abs_pct[75],
        curvature_signed_median_per_nm=signed_pct[50],
        curvature_signed_p10_per_nm=signed_pct[10],
        curvature_signed_p90_per_nm=signed_pct[90],
        curvature_std_per_nm=std_H,
        curvature_iqr_per_nm=iqr_H,
        fraction_convex=frac_convex,
        fraction_concave=frac_concave,
        fraction_flat=frac_flat,
        roughness_rms_nm=roughness,
        protrusion_density_per_um2=prot_density,
        indentation_density_per_um2=ind_density,
        protrusion_count=protrusions,
        indentation_count=indentations,
    )
