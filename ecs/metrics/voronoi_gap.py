"""
Inter-cell gap distribution via Voronoi tessellation of the ECS.

Each ECS voxel is assigned to its nearest cell (Euclidean). At Voronoi
boundary faces - adjacent ECS voxels that belong to different cells - the
gap width is estimated as the sum of both voxels' distances to their
respective cells plus the inter-voxel spacing along the axis:

    gap = dt_ecs[V1] + spacing + dt_ecs[V2]

Known caveats (both inherited from the estimator):
  - This is the length of a kinked path V1 -> cell_A -> V1 -> V2 -> cell_B,
    i.e. an UPPER BOUND on the true straight-line cell-to-cell gap.
  - Resolution floor: at isotropic voxel size v, the minimum possible gap
    is 3v (both dt_ecs values >= v and the step >= v). So e.g. 8 nm voxels
    cannot produce a gap below 24 nm even if the true gap is smaller.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt

from ..config import CONTACT_THRESHOLDS_NM, DISTRIBUTION_PERCENTILES
from ..io import CropData


@dataclass
class VoronoiGap:
    crop: str
    tissue: str
    prep: str
    region_group: str | None
    voxel_nm: float
    n_boundary_faces: int
    gap_min_nm: float
    gap_mean_nm: float
    gap_std_nm: float
    percentiles_nm: dict[int, float]              # distribution percentiles
    contact_fractions: dict[int, float]           # T -> fraction with gap < T


def compute(data: CropData) -> VoronoiGap:
    vs = np.asarray(data.voxel_size_nm, dtype=float)
    ecs_mask = data.ecs
    cell_mask = (data.cell != 0)

    # Distance from each ECS voxel to the nearest cell surface.
    dt_ecs = distance_transform_edt(ecs_mask, sampling=data.voxel_size_nm)

    # Voronoi assignment: id of the nearest cell for each voxel.
    _, idx = distance_transform_edt(
        ~cell_mask, sampling=data.voxel_size_nm, return_indices=True
    )
    voronoi = data.cell[idx[0], idx[1], idx[2]]

    gaps_parts = []
    n_faces = 0
    for axis in range(3):
        spacing = float(vs[axis])
        s1 = [slice(None)] * 3
        s2 = [slice(None)] * 3
        s1[axis] = slice(0, -1)
        s2[axis] = slice(1, None)
        s1 = tuple(s1); s2 = tuple(s2)

        both_ecs = ecs_mask[s1] & ecs_mask[s2]
        different_owner = (voronoi[s1] != voronoi[s2]) & both_ecs
        both_have_owner = (voronoi[s1] != 0) & (voronoi[s2] != 0)
        boundary = different_owner & both_have_owner
        if not boundary.any():
            continue
        gaps = dt_ecs[s1][boundary] + dt_ecs[s2][boundary] + spacing
        gaps_parts.append(gaps)
        n_faces += int(boundary.sum())

    if gaps_parts:
        gaps = np.concatenate(gaps_parts)
    else:
        gaps = np.empty(0, dtype=float)

    if gaps.size > 0:
        pct = {int(p): float(np.percentile(gaps, p)) for p in DISTRIBUTION_PERCENTILES}
        contacts = {
            int(T): float((gaps < T).mean()) for T in CONTACT_THRESHOLDS_NM
        }
        g_min = float(gaps.min())
        g_mean = float(gaps.mean())
        g_std = float(gaps.std())
    else:
        pct = {int(p): float("nan") for p in DISTRIBUTION_PERCENTILES}
        contacts = {int(T): float("nan") for T in CONTACT_THRESHOLDS_NM}
        g_min = g_mean = g_std = float("nan")

    return VoronoiGap(
        crop=data.crop.crop,
        tissue=data.crop.tissue,
        prep=data.crop.prep,
        region_group=data.crop.region_group,
        voxel_nm=float(data.voxel_size_nm[0]),
        n_boundary_faces=n_faces,
        gap_min_nm=g_min,
        gap_mean_nm=g_mean,
        gap_std_nm=g_std,
        percentiles_nm=pct,
        contact_fractions=contacts,
    )
