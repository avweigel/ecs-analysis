"""
Zarr I/O and resolution handling.

All heavy lifting (distance transforms, meshing, curvature) happens in
ecs.geometry on arrays loaded here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import zarr
from scipy.ndimage import zoom

from .config import Crop


@dataclass
class CropData:
    """Loaded ECS analysis arrays for a single crop.

    `ecs` is the effective extracellular mask used by downstream geometric
    analyses. It is the union of the primary `ecs` label and any ECS
    sub-part labels (currently only `bm`, basement membrane). `ecs_primary`
    is the `ecs`-label-only mask for transparency; `bm` is kept as its own
    boolean when present so it can be reported separately.
    """
    crop: Crop
    ecs: np.ndarray              # bool: effective ECS (ecs | bm)
    cell: np.ndarray             # int instance labels; 0 = not-cell
    voxel_size_nm: tuple[float, float, float]
    ecs_primary: np.ndarray | None = None  # bool: just the `ecs` label
    bm: np.ndarray | None = None           # bool: basement membrane, if annotated
    is_downsampled: bool = False
    native_voxel_size_nm: tuple[float, float, float] | None = None

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.ecs.shape

    @property
    def voxel_volume_nm3(self) -> float:
        return float(np.prod(self.voxel_size_nm))

    @property
    def total_volume_nm3(self) -> float:
        return self.voxel_volume_nm3 * int(np.prod(self.shape))


def _read_voxel_size(label_group) -> tuple[float, float, float] | None:
    """Extract scale from OME-NGFF multiscales metadata."""
    attrs = dict(label_group.attrs)
    ms = attrs.get("cellmap", {}).get("multiscales") or attrs.get("multiscales")
    if not ms:
        return None
    datasets = ms[0].get("datasets", [])
    if not datasets:
        return None
    for t in datasets[0].get("coordinateTransformations", []):
        if t.get("type") == "scale":
            scale = t["scale"]
            return (float(scale[0]), float(scale[1]), float(scale[2]))
    return None


def get_voxel_size(crop: Crop) -> tuple[float, float, float] | None:
    """Read voxel size in nm from zarr metadata without loading data."""
    if not crop.zarr_path.is_dir():
        return None
    z = zarr.open(str(crop.zarr_path), mode="r")
    for label in ("ecs", "cell"):
        if label in z:
            vs = _read_voxel_size(z[label])
            if vs is not None:
                return vs
    return None


def get_complement_counts(crop: Crop, label: str) -> dict[str, int] | None:
    """Return the cellmap annotation complement_counts block for a label,
    or None if not available."""
    if not crop.zarr_path.is_dir():
        return None
    z = zarr.open(str(crop.zarr_path), mode="r")
    if label not in z or "s0" not in z[label]:
        return None
    attrs = dict(z[label]["s0"].attrs)
    cc = attrs.get("cellmap", {}).get("annotation", {}).get("complement_counts")
    return dict(cc) if cc else None


# Labels that are structural sub-parts of the extracellular compartment and
# should be unioned into the `ecs` mask for geometric analyses. Kept in sync
# with ecs.metrics.volume_fraction.ECS_SUBPART_LABELS.
_ECS_SUBPART_LABELS = ("bm",)


def load_crop(crop: Crop) -> CropData:
    """Load ECS (binary), cell (instance), and any ECS sub-part arrays
    (currently `bm`) from a crop's zarr group.

    The returned `CropData.ecs` mask is `ecs | bm` — the effective ECS for
    distance-transform and mesh analyses. Primary `ecs` and `bm` are also
    retained individually for transparency (bm as None if not annotated or
    all-zero).

    Raises FileNotFoundError if the zarr is missing, ValueError if required
    labels are absent.
    """
    if not crop.zarr_path.is_dir():
        raise FileNotFoundError(f"Zarr not found: {crop.zarr_path}")

    z = zarr.open(str(crop.zarr_path), mode="r")
    if "ecs" not in z or "s0" not in z["ecs"]:
        raise ValueError(f"{crop.crop}: missing ecs/s0")
    if "cell" not in z or "s0" not in z["cell"]:
        raise ValueError(f"{crop.crop}: missing cell/s0")

    vs = _read_voxel_size(z["ecs"]) or _read_voxel_size(z["cell"])
    if vs is None:
        raise ValueError(f"{crop.crop}: missing voxel-size metadata")

    ecs_primary = (z["ecs"]["s0"][:] == 1)
    cell = np.asarray(z["cell"]["s0"][:])
    if ecs_primary.shape != cell.shape:
        raise ValueError(
            f"{crop.crop}: ecs shape {ecs_primary.shape} != cell shape {cell.shape}"
        )

    # Pool ECS sub-parts (currently only `bm`). Skip if label is missing or
    # has no present voxels to avoid wasted I/O.
    ecs_effective = ecs_primary.copy()
    bm_mask = None
    for lbl in _ECS_SUBPART_LABELS:
        if lbl not in z or "s0" not in z[lbl]:
            continue
        cc = dict(z[lbl]["s0"].attrs).get("cellmap", {}).get("annotation", {}).get("complement_counts", {})
        if cc.get("present", 0) == 0:
            continue
        sub = (z[lbl]["s0"][:] == 1)
        if sub.shape != ecs_effective.shape:
            raise ValueError(
                f"{crop.crop}: {lbl} shape {sub.shape} != ecs shape {ecs_effective.shape}"
            )
        ecs_effective |= sub
        if lbl == "bm":
            bm_mask = sub

    return CropData(
        crop=crop, ecs=ecs_effective, cell=cell,
        voxel_size_nm=vs,
        ecs_primary=ecs_primary,
        bm=bm_mask,
        is_downsampled=False,
        native_voxel_size_nm=vs,
    )


def downsample(data: CropData, target_voxel_nm: float,
               tolerance_nm: float = 0.1) -> CropData:
    """Downsample to isotropic target voxel size via nearest-neighbor.

    Nearest-neighbor preserves label identities (cell IDs, binary ECS).
    If the source is already within `tolerance_nm` of the target, returns
    the input unchanged.

    Raises ValueError if attempting to upsample.
    """
    src = data.voxel_size_nm
    if any(v > target_voxel_nm + tolerance_nm for v in ()) or \
       any(v > target_voxel_nm + tolerance_nm for v in src):
        # Strictly: we allow downsampling (src < target) or equal; upsampling
        # is only allowed when already at target (no-op).
        pass  # fall through to factor check below

    # Zoom factor along each axis = src / target (<1 for downsampling).
    factors = tuple(v / target_voxel_nm for v in src)
    if any(f > 1.0 + 1e-6 for f in factors):
        raise ValueError(
            f"Cannot upsample from {src} nm to {target_voxel_nm} nm"
        )

    if all(abs(f - 1.0) < 1e-3 for f in factors):
        return data  # already at target

    ecs_ds = zoom(data.ecs.astype(np.uint8), factors, order=0, mode="nearest") > 0
    cell_ds = zoom(data.cell, factors, order=0, mode="nearest")
    ecs_primary_ds = None
    bm_ds = None
    if data.ecs_primary is not None:
        ecs_primary_ds = zoom(data.ecs_primary.astype(np.uint8), factors, order=0, mode="nearest") > 0
    if data.bm is not None:
        bm_ds = zoom(data.bm.astype(np.uint8), factors, order=0, mode="nearest") > 0

    new_vs = (target_voxel_nm, target_voxel_nm, target_voxel_nm)
    return CropData(
        crop=data.crop, ecs=ecs_ds, cell=cell_ds,
        voxel_size_nm=new_vs,
        ecs_primary=ecs_primary_ds, bm=bm_ds,
        is_downsampled=True,
        native_voxel_size_nm=data.native_voxel_size_nm or src,
    )


def iter_cells(data: CropData, min_voxels: int = 1):
    """Yield (cell_id, voxel_count) for each cell >= min_voxels, background
    (0) excluded. Uses np.unique with return_counts for speed."""
    ids, counts = np.unique(data.cell, return_counts=True)
    for cid, n in zip(ids, counts):
        if cid == 0:
            continue
        if n < min_voxels:
            continue
        yield int(cid), int(n)
