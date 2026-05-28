"""
Single source of truth for the ECS analysis.

Defines:
  - dataset / crop / tissue / prep mappings
  - analysis parameters (filters, thresholds, target resolutions)
  - data paths
  - known exclusions

Anatomy annotations are loaded from crop_annotations.csv at import time and
joined onto the crop list. Crops without annotations (e.g., pending expert
review) get anatomy=None.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field, replace
from pathlib import Path


# ---------- Paths ----------

REPO_ROOT = Path(__file__).resolve().parent.parent
# Override with ECS_DATA_BASE env var when running on the cluster, e.g.
# `export ECS_DATA_BASE=/nrs/cellmap/data` on Janelia.
NRS_BASE = Path(os.environ.get("ECS_DATA_BASE", "/Volumes/cellmap/data"))

# Output destination. Default is `results/` in the repo, but on the cluster
# you may want to write to a shared scratch / lab-space location:
#   export ECS_RESULTS_DIR=/nrs/cellmap/people/<you>/ecs-results
# Same for figures via ECS_FIGURES_DIR.
RESULTS_DIR = Path(os.environ.get("ECS_RESULTS_DIR", str(REPO_ROOT / "results")))
FIGURES_DIR = Path(os.environ.get("ECS_FIGURES_DIR", str(REPO_ROOT / "figures")))
ANNOTATIONS_CSV = REPO_ROOT / "crop_annotations.csv"


# ---------- Analysis parameters ----------

# --- Whole-cell filter (SA:V only) ---
# Per-cell physical volume floor for the crop-level SA:V calculation.
# 2.56e6 nm^3 = 2.56e-3 um^3. Applied uniformly regardless of native voxel
# size so Chemical and HPF cell populations face the same physical criterion.
MIN_CELL_VOL_NM3 = 2_560_000

# --- ECS channel width ---
# Distance-transform cutoff (nm). Values above this are treated as vessel
# lumens / large pools rather than intercellular channels.
ECS_WIDTH_CUTOFF_NM = 200

# --- Curvature ---
# Physical Gaussian smoothing scale before marching-cubes (nm). Sets the
# finest feature size that enters the mesh.
CURVATURE_SIGMA_NM = 16.0

# --- Membrane-topology filter ---
# A cell must contribute at least this much ECS-facing mesh surface area to
# enter the topology metrics. 50,000 nm^2 ~= 225nm x 225nm patch, enough for
# stable percentile stats at scales up to ~60 nm.
MIN_ECS_SURFACE_NM2 = 50_000

# --- Multi-scale roughness ---
# Gaussian-smooth the mesh at each scale; roughness = RMS vertex displacement.
ROUGHNESS_SCALES_NM = (30, 60, 120)

# --- Feature detection (protrusions / indentations) ---
# Smooth the mesh at FEATURE_SMOOTHING_NM; features SMALLER than this scale
# survive as deviations from the smoothed surface. To detect clathrin pits
# (~100 nm diameter) and caveolae (~80 nm), we smooth well above the
# feature size so the smoothed surface doesn't follow the feature.
# 200 nm is a reasonable default — preserves 60-100 nm features as signal.
FEATURE_SMOOTHING_NM = 200

# Minimum feature amplitude (nm) — signed deviation-from-smoothed must
# exceed this to count as a real bump/pit. 10 nm is well above mesh noise
# and below typical caveolae/clathrin pit depth (~50 nm).
FEATURE_AMPLITUDE_NM = 10

# Neighborhood radius (nm) for the "local maximum/minimum" test. A vertex
# must be the extremum of the signed deviation within this radius. Set
# around the expected feature size so two close features aren't merged.
FEATURE_NEIGHBORHOOD_NM = 100

# --- Flat-membrane classification ---
# |H| below this counts as "flat" — corresponds to radius of curvature > 500 nm.
FLAT_CURVATURE_THRESHOLD = 0.002  # 1/nm

# --- Resolution comparisons ---
# Target for the matched-resolution (Phase 4) analysis: everything downsampled
# to this voxel size before geometry metrics are computed.
TARGET_VOXEL_NM = 8.0

# Resolutions scanned in the degradation experiment (Phase 5). Each Chemical
# crop is downsampled to every value >= its native voxel size.
DEGRADATION_VOXELS_NM = (2.0, 4.0, 8.0, 16.0)

# --- Reporting ---
DISTRIBUTION_PERCENTILES = (10, 25, 50, 75, 90)
CONTACT_THRESHOLDS_NM = (20, 40, 80, 160, 320)


# ---------- Crop definitions ----------

@dataclass(frozen=True)
class Crop:
    crop: str                          # e.g. 'crop1026'
    dataset: str                       # e.g. 'jrc_mus-kidney'
    tissue: str                        # 'Kidney' | 'Heart' | 'Liver' | 'Cortex'
    prep: str                          # 'Chemical' | 'Rapid HPF'
    anatomy: str | None = None         # e.g. 'Glomerular interstitium'
    region_group: str | None = None    # e.g. 'Glomerular'
    exclude: bool = False
    exclude_reason: str = ""

    @property
    def zarr_path(self) -> Path:
        return (
            NRS_BASE / self.dataset / f"{self.dataset}.zarr"
            / "recon-1" / "labels" / "groundtruth" / self.crop
        )


# Dataset -> (tissue, prep, [crops]). The crop list here is the authoritative
# inventory of analysable crops. Anatomy is joined in from the CSV.
_DATASET_TABLE: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("jrc_mus-kidney",   "Kidney", "Chemical",
     ("crop1026", "crop1027", "crop1028", "crop1029",
      "crop1030", "crop1031", "crop1032")),
    ("jrc_mus-kidney-4", "Kidney", "Rapid HPF",
     ("crop1134", "crop1135", "crop1136", "crop1137", "crop1138", "crop1144")),

    ("jrc_mus-heart-6",  "Heart",  "Chemical",
     ("crop1145", "crop1146", "crop1147", "crop1148")),
    ("jrc_mus-heart-4",  "Heart",  "Rapid HPF",
     ("crop1149", "crop1150", "crop1151", "crop1152")),

    ("jrc_mus-liver",    "Liver",  "Chemical",
     ("crop1038", "crop1039", "crop1040", "crop1041",
      "crop1042", "crop1043", "crop1044",
      "crop1118", "crop1119", "crop1120", "crop1121", "crop1122")),
    ("jrc_mus-liver-8",  "Liver",  "Rapid HPF",
     ("crop1071", "crop1072", "crop1073", "crop1074", "crop1075",
      "crop1123", "crop1124", "crop1125", "crop1126", "crop1127")),

    ("jrc_mus-cortex-2", "Cortex", "Rapid HPF", ("crop1116", "crop1117")),
    ("jrc_mus-cortex-3", "Cortex", "Chemical",
     ("crop1033", "crop1034", "crop1035", "crop1036", "crop1037",
      "crop1045", "crop1046")),
    ("jrc_mus-cortex-4", "Cortex", "Rapid HPF", ("crop1139", "crop1141")),
)

# Known bad crops. crop1117 has no ECS/cell labels (confirmed empty in zarr).
# crop1139 is dominated by a cortical blood vessel lumen — its ~70% ECS skews
# the cortex Chemical-vs-HPF tissue comparison even though it's not
# parenchyma. Annotated as "Cortex vessel" in crop_annotations.csv; excluded
# here so it doesn't pollute pooled cortex statistics.
_EXCLUSIONS: dict[str, str] = {
    "crop1117": "zarr contains no ECS or cell labels",
    "crop1139": "blood vessel lumen — not representative of cortex parenchyma",
}


def _load_anatomy_csv(path: Path) -> dict[str, tuple[str, str]]:
    """Return {crop: (anatomy, region_group)} from the annotations CSV."""
    if not path.exists():
        return {}
    out: dict[str, tuple[str, str]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            crop = row.get("crop", "").strip()
            if not crop:
                continue
            out[crop] = (
                row.get("anatomical_region", "").strip() or None,
                row.get("region_group", "").strip() or None,
            )
    return out


def _build_crops() -> tuple[Crop, ...]:
    anatomy = _load_anatomy_csv(ANNOTATIONS_CSV)
    crops: list[Crop] = []
    for dataset, tissue, prep, crop_ids in _DATASET_TABLE:
        for cid in crop_ids:
            region, group = anatomy.get(cid, (None, None))
            excl = cid in _EXCLUSIONS
            crops.append(Crop(
                crop=cid, dataset=dataset, tissue=tissue, prep=prep,
                anatomy=region, region_group=group,
                exclude=excl,
                exclude_reason=_EXCLUSIONS.get(cid, ""),
            ))
    return tuple(crops)


CROPS: tuple[Crop, ...] = _build_crops()


# ---------- Query helpers ----------

def active_crops() -> tuple[Crop, ...]:
    """Crops usable for analysis (excludes known-bad)."""
    return tuple(c for c in CROPS if not c.exclude)


def crops_by(tissue: str | None = None, prep: str | None = None,
             region_group: str | None = None) -> tuple[Crop, ...]:
    out = active_crops()
    if tissue is not None:
        out = tuple(c for c in out if c.tissue == tissue)
    if prep is not None:
        out = tuple(c for c in out if c.prep == prep)
    if region_group is not None:
        out = tuple(c for c in out if c.region_group == region_group)
    return out


# Expert-verified anatomy groups that have both Chemical and HPF crops.
# Populated from the CSV at import time so the list auto-updates when the
# pending cortex annotations land.
def anatomy_matched_groups() -> dict[str, dict[str, tuple[Crop, ...]]]:
    """{region_group: {'Chemical': (crops,), 'Rapid HPF': (crops,)}} for
    groups where BOTH preps are present."""
    out: dict[str, dict[str, tuple[Crop, ...]]] = {}
    groups = sorted({c.region_group for c in active_crops() if c.region_group})
    for g in groups:
        chem = crops_by(region_group=g, prep="Chemical")
        hpf = crops_by(region_group=g, prep="Rapid HPF")
        if chem and hpf:
            out[g] = {"Chemical": chem, "Rapid HPF": hpf}
    return out
