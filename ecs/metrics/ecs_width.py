"""
ECS channel width from the distance transform of the ECS mask.

For each ECS voxel, computes the Euclidean distance to the nearest cell
voxel (the 'half-width at that point'). Reports the full distribution and
the filtered distribution restricted to values < ECS_WIDTH_CUTOFF_NM
(excludes vessel lumens and large pools).

Caveat on interpretation: the value at an ECS voxel is the distance from
that voxel to the NEAREST cell surface, not the channel-width at the
center of the gap. For a uniform channel of width W, the distribution of
voxel-wise dt values runs from 0 (at the walls) up to W/2 (centerline),
with the voxel-count-weighted median at approximately W/4. Convert
reported percentiles to channel widths with that in mind.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import (
    ECS_WIDTH_CUTOFF_NM, DISTRIBUTION_PERCENTILES,
)
from ..geometry import ecs_distance_nm
from ..io import CropData


@dataclass
class ECSWidth:
    crop: str
    tissue: str
    prep: str
    region_group: str | None
    voxel_nm: float
    n_ecs_voxels: int
    n_narrow_voxels: int
    narrow_fraction: float
    full_percentiles_nm: dict[int, float]      # p -> distance in nm, unfiltered
    narrow_percentiles_nm: dict[int, float]    # p -> distance in nm, <CUTOFF
    narrow_mean_nm: float
    narrow_std_nm: float


def compute(data: CropData) -> ECSWidth:
    dt = ecs_distance_nm(data.ecs, data.voxel_size_nm)
    ecs_mask = data.ecs
    d_all = dt[ecs_mask]

    n_ecs = int(d_all.size)
    full_pct = {int(p): float(np.percentile(d_all, p)) for p in DISTRIBUTION_PERCENTILES} \
               if n_ecs > 0 else {int(p): float("nan") for p in DISTRIBUTION_PERCENTILES}

    narrow = d_all[(d_all > 0) & (d_all < ECS_WIDTH_CUTOFF_NM)]
    n_narrow = int(narrow.size)
    if n_narrow > 0:
        narrow_pct = {int(p): float(np.percentile(narrow, p)) for p in DISTRIBUTION_PERCENTILES}
        narrow_mean = float(narrow.mean())
        narrow_std = float(narrow.std())
    else:
        narrow_pct = {int(p): float("nan") for p in DISTRIBUTION_PERCENTILES}
        narrow_mean = float("nan")
        narrow_std = float("nan")

    return ECSWidth(
        crop=data.crop.crop,
        tissue=data.crop.tissue,
        prep=data.crop.prep,
        region_group=data.crop.region_group,
        voxel_nm=float(data.voxel_size_nm[0]),
        n_ecs_voxels=n_ecs,
        n_narrow_voxels=n_narrow,
        narrow_fraction=n_narrow / n_ecs if n_ecs > 0 else float("nan"),
        full_percentiles_nm=full_pct,
        narrow_percentiles_nm=narrow_pct,
        narrow_mean_nm=narrow_mean,
        narrow_std_nm=narrow_std,
    )
