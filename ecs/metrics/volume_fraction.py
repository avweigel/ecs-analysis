"""
Crop-level ECS and cell volume fractions.

Purely voxel-count ratios — the most resolution-robust of our metrics.

ECS accounting: the `ecs` label is the primary extracellular mask, but
certain crops annotate basement membrane (`bm`) separately. Per the user,
`bm` is a structural sub-part of the extracellular compartment, so we sum
`ecs + bm` for the ECS count. Without this correction the 4 Kidney-Chemical
crops with bm annotation (glomerular interstitium, DCT base) under-report
ECS by 2.7-10.3 percentage points each.

Uses cellmap complement_counts metadata when available; falls back to
counting the loaded array.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Crop
from ..io import CropData, load_crop, get_complement_counts


# Labels that should be pooled with `ecs` for the ECS voxel count.
# Basement membrane is structurally part of the extracellular compartment
# in the tissues we're analysing (it's the scaffold produced by cells but
# not part of any cell). Crops without this annotation have it as 0 or
# missing — handled gracefully below.
ECS_SUBPART_LABELS = ("bm",)


@dataclass
class VolumeFraction:
    crop: str
    tissue: str
    prep: str
    region_group: str | None
    native_voxel_nm: float
    analysis_voxel_nm: float
    total_voxels: int
    ecs_voxels: int               # ecs + ecs-subparts (e.g. bm)
    ecs_primary_voxels: int       # just `ecs` label, for transparency
    ecs_bm_voxels: int            # just `bm` label (0 for most crops)
    cell_voxels: int
    ecs_fraction: float
    cell_fraction: float
    ecs_volume_um3: float
    cell_volume_um3: float
    total_volume_um3: float
    method: str                   # 'metadata' or 'computed'


def _subpart_voxel_count(crop: Crop) -> int:
    """Sum of `present` counts across ECS sub-part labels (bm, etc.).
    Labels absent from a crop contribute 0."""
    total = 0
    for lbl in ECS_SUBPART_LABELS:
        cc = get_complement_counts(crop, lbl)
        if cc is None:
            continue
        total += int(cc.get("present", 0))
    return total


def from_metadata(crop: Crop) -> VolumeFraction | None:
    """Compute volume fractions from zarr metadata without loading arrays."""
    ecs_cc = get_complement_counts(crop, "ecs")
    cell_cc = get_complement_counts(crop, "cell")
    if not ecs_cc or not cell_cc:
        return None
    total = ecs_cc.get("present", 0) + ecs_cc.get("absent", 0) + ecs_cc.get("unknown", 0)
    if total <= 0:
        return None
    ecs_primary = int(ecs_cc.get("present", 0))
    bm_voxels = _subpart_voxel_count(crop)
    ecs_voxels = ecs_primary + bm_voxels
    cell_voxels = total - int(cell_cc.get("absent", 0))

    from ..io import get_voxel_size
    vs = get_voxel_size(crop)
    if vs is None:
        return None
    voxel_vol_nm3 = float(np.prod(vs))
    vx = float(vs[0])

    return VolumeFraction(
        crop=crop.crop, tissue=crop.tissue, prep=crop.prep,
        region_group=crop.region_group,
        native_voxel_nm=vx, analysis_voxel_nm=vx,
        total_voxels=total,
        ecs_voxels=ecs_voxels,
        ecs_primary_voxels=ecs_primary,
        ecs_bm_voxels=bm_voxels,
        cell_voxels=cell_voxels,
        ecs_fraction=ecs_voxels / total,
        cell_fraction=cell_voxels / total,
        ecs_volume_um3=ecs_voxels * voxel_vol_nm3 / 1e9,
        cell_volume_um3=cell_voxels * voxel_vol_nm3 / 1e9,
        total_volume_um3=total * voxel_vol_nm3 / 1e9,
        method="metadata",
    )


def from_data(data: CropData) -> VolumeFraction:
    """Compute volume fractions by counting the loaded arrays. Used when
    the data has been transformed (downsampled) and metadata counts no
    longer apply."""
    total = int(np.prod(data.shape))
    ecs_voxels = int(data.ecs.sum())
    cell_voxels = int((data.cell > 0).sum())
    vv = data.voxel_volume_nm3
    vx = float(data.voxel_size_nm[0])
    native_vx = float((data.native_voxel_size_nm or data.voxel_size_nm)[0])
    return VolumeFraction(
        crop=data.crop.crop,
        tissue=data.crop.tissue,
        prep=data.crop.prep,
        region_group=data.crop.region_group,
        native_voxel_nm=native_vx,
        analysis_voxel_nm=vx,
        total_voxels=total,
        ecs_voxels=ecs_voxels,
        cell_voxels=cell_voxels,
        ecs_fraction=ecs_voxels / total,
        cell_fraction=cell_voxels / total,
        ecs_volume_um3=ecs_voxels * vv / 1e9,
        cell_volume_um3=cell_voxels * vv / 1e9,
        total_volume_um3=total * vv / 1e9,
        method="computed",
    )


def compute(crop: Crop, prefer_metadata: bool = True) -> VolumeFraction:
    """Public entry point: try metadata first (fast), fall back to loading."""
    if prefer_metadata:
        vf = from_metadata(crop)
        if vf is not None:
            return vf
    return from_data(load_crop(crop))
