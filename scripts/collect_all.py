#!/usr/bin/env python3
"""
Collect every per-crop metric the pipeline has produced into two tables:

  results/all_metrics_long.csv   tidy: one row per (crop, run, analysis voxel, metric)
  results/all_metrics_wide.csv   one row per (crop, run, analysis voxel), metrics as columns

Sources: native/matched/degradation runs for volume_fraction, ecs_width, sa_v,
voronoi_gap, topology; plus the mesh-based membrane_topology_per_crop.

Crop metadata (tissue, prep, region_group, anatomy, native voxel size) is taken
from the per-crop rows themselves and reconciled against crop_annotations.csv.

    python scripts/collect_all.py
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"

# (filename, run label, metric family)
SOURCES = [
    ("native_volume_fraction.csv",   "native",      "volume_fraction"),
    ("native_ecs_width.csv",         "native",      "ecs_width"),
    ("native_sa_v.csv",              "native",      "sa_v"),
    ("native_voronoi_gap.csv",       "native",      "voronoi_gap"),
    ("native_topology.csv",          "native",      "topology"),
    ("matched_ecs_width.csv",        "matched",     "ecs_width"),
    ("matched_sa_v.csv",             "matched",     "sa_v"),
    ("matched_voronoi_gap.csv",      "matched",     "voronoi_gap"),
    ("matched_topology.csv",         "matched",     "topology"),
    ("degradation_ecs_width.csv",    "degradation", "ecs_width"),
    ("degradation_sa_v.csv",         "degradation", "sa_v"),
    ("degradation_voronoi_gap.csv",  "degradation", "voronoi_gap"),
    ("degradation_topology.csv",     "degradation", "topology"),
    ("membrane_topology_per_crop.csv", "native",    "membrane_topology"),
    ("kidney_bm_sensitivity.csv",    "native",      "bm_sensitivity"),
]

# columns that describe the crop rather than measure it
META = {"crop", "tissue", "prep", "region_group", "anatomy",
        "voxel_nm", "native_voxel_nm", "analysis_voxel_nm", "method"}


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_annotations():
    """crop -> anatomy, from the annotation table."""
    out = {}
    f = ROOT / "crop_annotations.csv"
    if not f.exists():
        return out
    for row in csv.DictReader(f.open()):
        c = row.get("crop") or row.get("crop_name")
        if not c:
            continue
        out[c] = row.get("anatomy") or row.get("region") or ""
    return out


def main():
    anno = load_annotations()
    long_rows = []
    wide = {}   # (crop, run, analysis_voxel) -> dict
    meta_seen = {}

    for fname, run, family in SOURCES:
        path = RES / fname
        if not path.exists():
            print(f"  skip (missing): {fname}")
            continue
        n = 0
        for row in csv.DictReader(path.open()):
            crop = row.get("crop")
            if not crop:
                continue
            native_v = _num(row.get("native_voxel_nm")) or _num(row.get("voxel_nm"))
            anal_v = _num(row.get("analysis_voxel_nm")) or _num(row.get("voxel_nm"))
            meta = {
                "crop": crop,
                "tissue": row.get("tissue", ""),
                "prep": row.get("prep", ""),
                "region_group": row.get("region_group", ""),
                "anatomy": row.get("anatomy") or anno.get(crop, ""),
                "native_voxel_nm": native_v,
                "analysis_voxel_nm": anal_v,
            }
            # remember the richest metadata we have seen for this crop
            prev = meta_seen.get(crop, {})
            for k, v in meta.items():
                if v not in (None, "") and prev.get(k) in (None, ""):
                    prev[k] = v
            meta_seen[crop] = prev

            key = (crop, run, anal_v)
            w = wide.setdefault(key, dict(meta, run=run))
            for col, val in row.items():
                if col in META:
                    continue
                v = _num(val)
                if v is None:
                    continue
                long_rows.append(dict(meta, run=run, metric_family=family,
                                      metric=col, value=v))
                w[f"{family}.{col}"] = v
            n += 1
        print(f"  {fname:44s} {n:4d} rows -> {run}/{family}")

    # backfill metadata onto every row from the richest record per crop
    for r in long_rows:
        best = meta_seen.get(r["crop"], {})
        for k in ("tissue", "prep", "region_group", "anatomy"):
            if not r.get(k):
                r[k] = best.get(k, "")

    RES.mkdir(exist_ok=True)

    lf = RES / "all_metrics_long.csv"
    cols = ["crop", "tissue", "prep", "region_group", "anatomy",
            "native_voxel_nm", "analysis_voxel_nm", "run",
            "metric_family", "metric", "value"]
    with lf.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(long_rows)

    metric_cols = sorted({k for w in wide.values() for k in w
                          if k not in META and k != "run"})
    wfl = RES / "all_metrics_wide.csv"
    head = ["crop", "tissue", "prep", "region_group", "anatomy",
            "native_voxel_nm", "analysis_voxel_nm", "run"] + metric_cols
    with wfl.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=head, extrasaction="ignore")
        wr.writeheader()
        for key in sorted(wide, key=lambda k: (k[0], k[1], k[2] or 0)):
            w = dict(wide[key])
            best = meta_seen.get(key[0], {})
            for k in ("tissue", "prep", "region_group", "anatomy"):
                if not w.get(k):
                    w[k] = best.get(k, "")
            wr.writerow(w)

    print(f"\nwrote {lf.relative_to(ROOT)}  ({len(long_rows)} rows)")
    print(f"wrote {wfl.relative_to(ROOT)}  ({len(wide)} rows x {len(metric_cols)} metrics)")


if __name__ == "__main__":
    main()
