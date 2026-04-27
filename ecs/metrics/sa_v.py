"""
Crop-level SA:V (ECS-facing surface area per unit cell volume).

For each cell in the crop that passes a physical-volume filter, count the
voxel faces on its boundary that face ECS. Pool numerator and denominator
across all passing cells in the crop and report a single ratio per crop:

    crop_sa_v = sum(ECS-facing surface area) / sum(cell volume)

This is a descriptive summary of how much ECS-adjacent membrane the
tissue has per unit cell volume, aggregated at the crop level. It
deliberately does NOT compute per-cell SA:V means — that introduced
fragment-truncation bias in the old pipeline. Here, large fragments and
small fragments all contribute proportionally to their true physical
contribution.

Cell volume filter (MIN_CELL_VOL_NM3) still applies: very small
fragments are excluded to avoid letting digitisation noise dominate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import MIN_CELL_VOL_NM3
from ..geometry import count_cell_boundary_faces
from ..io import CropData


@dataclass
class CropSAV:
    crop: str
    tissue: str
    prep: str
    region_group: str | None
    voxel_nm: float
    n_cells_total: int            # instance IDs > 0 in the crop
    n_cells_passing: int          # after MIN_CELL_VOL_NM3 filter
    total_cell_volume_nm3: float
    total_ecs_facing_sa_nm2: float
    total_cell_cell_sa_nm2: float
    total_outer_sa_nm2: float     # at crop boundary
    cell_density_per_um3: float   # passing cells per um^3 of crop volume
    sa_v_ecs_per_nm: float        # (ECS-facing SA) / (cell volume)


def compute(data: CropData) -> CropSAV:
    voxel_vol_nm3 = data.voxel_volume_nm3
    # For isotropic voxels (all CellMap data is isotropic) face area is
    # simply vx^2. For generality we take any face as (vy*vz + vx*vz +
    # vx*vy) / 3, which equals vx^2 for isotropic.
    vs = data.voxel_size_nm
    face_area = (vs[1] * vs[2] + vs[0] * vs[2] + vs[0] * vs[1]) / 3.0

    ids, counts = np.unique(data.cell, return_counts=True)
    mask = ids != 0
    ids = ids[mask]
    counts = counts[mask]

    n_cells_total = int(len(ids))
    cell_volumes_nm3 = counts.astype(np.int64) * int(voxel_vol_nm3)

    passing = cell_volumes_nm3 >= MIN_CELL_VOL_NM3
    passing_ids = ids[passing]
    passing_volumes = cell_volumes_nm3[passing]

    total_vol = int(passing_volumes.sum())
    total_ecs_faces = 0
    total_cc_faces = 0
    total_outer_faces = 0

    for cid in passing_ids:
        bf = count_cell_boundary_faces(data.cell, data.ecs, int(cid))
        total_ecs_faces += bf.ecs_faces
        total_cc_faces += bf.cell_cell_faces
        total_outer_faces += bf.outer_faces

    ecs_sa_nm2 = total_ecs_faces * face_area
    cc_sa_nm2 = total_cc_faces * face_area
    outer_sa_nm2 = total_outer_faces * face_area

    sa_v = ecs_sa_nm2 / total_vol if total_vol > 0 else float("nan")

    crop_vol_um3 = data.total_volume_nm3 / 1e9
    density = len(passing_ids) / crop_vol_um3 if crop_vol_um3 > 0 else float("nan")

    return CropSAV(
        crop=data.crop.crop,
        tissue=data.crop.tissue,
        prep=data.crop.prep,
        region_group=data.crop.region_group,
        voxel_nm=float(vs[0]),
        n_cells_total=n_cells_total,
        n_cells_passing=int(len(passing_ids)),
        total_cell_volume_nm3=float(total_vol),
        total_ecs_facing_sa_nm2=float(ecs_sa_nm2),
        total_cell_cell_sa_nm2=float(cc_sa_nm2),
        total_outer_sa_nm2=float(outer_sa_nm2),
        cell_density_per_um3=float(density),
        sa_v_ecs_per_nm=float(sa_v),
    )
