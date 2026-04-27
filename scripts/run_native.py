"""
Run all Phase 2 metrics at NATIVE resolution on every active crop.

Output: results/native_<metric>.csv (long-format, one row per crop for
crop-level metrics; nested dict fields are exploded to named columns).

Usage:
    python -m scripts.run_native [--only cropXXXX,cropYYYY ...] [--metrics a,b,c]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

# Allow `python -m scripts.run_native` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from ecs.io import load_crop
from ecs.metrics import (
    volume_fraction,
    ecs_width,
    voronoi_gap,
    sa_v,
    topology,
)


METRICS = {
    "volume_fraction": ("from_metadata_or_load", volume_fraction.compute),
    "ecs_width":       ("requires_data",        ecs_width.compute),
    "voronoi_gap":     ("requires_data",        voronoi_gap.compute),
    "sa_v":            ("requires_data",        sa_v.compute),
    "topology":        ("requires_data",        topology.compute),
}


def _flatten(obj) -> dict:
    """Flatten a dataclass instance to a flat {column: scalar} dict.
    Dict-valued fields like `percentiles_nm={25: 12.5, ...}` become columns
    like `percentiles_nm_p25=12.5`."""
    if hasattr(obj, "__dataclass_fields__"):
        raw = asdict(obj)
    elif isinstance(obj, dict):
        raw = obj
    else:
        raise TypeError(f"Cannot flatten {type(obj)}")
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                if isinstance(sk, (int, float)):
                    # percentile or threshold key
                    out[f"{k}_p{int(sk)}"] = sv if not isinstance(sv, float) or sv == sv else None
                else:
                    out[f"{k}_{sk}"] = sv
        else:
            out[k] = v
    return out


def _read_existing(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with open(path) as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        return list(rdr.fieldnames or []), rows


def write_csv(path: Path, rows: list[dict], append: bool = False):
    """Write rows to CSV. If append=True, merge with existing rows
    (replacing rows for the same `crop` if already present)."""
    if not rows and not append:
        print(f"  (no new rows for {path.name})")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if append:
        existing_fields, existing = _read_existing(path)
        # Replace any rows whose crop matches a new row.
        new_keys = {r.get("crop") for r in rows}
        merged = [r for r in existing if r.get("crop") not in new_keys] + rows
    else:
        existing_fields = []
        merged = rows
    if not merged:
        print(f"  (still no rows for {path.name})")
        return
    fields: list[str] = list(existing_fields)
    seen = set(fields)
    for r in merged:
        for k in r:
            if k not in seen:
                fields.append(k)
                seen.add(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in merged:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"  wrote {len(merged)} rows -> {path} ({len(rows)} new)")


def run(crops, metric_names, out_dir: Path, append: bool = False):
    """Run metrics on each crop, writing per-crop incrementally so an
    interruption preserves completed work. Returns the accumulated rows."""
    results: dict[str, list[dict]] = {m: [] for m in metric_names}

    need_data = [m for m in metric_names if METRICS[m][0] == "requires_data"]
    skip_data = [m for m in metric_names if METRICS[m][0] == "from_metadata_or_load"]

    for crop in crops:
        print(f"\n=== {crop.crop}  ({crop.tissue}, {crop.prep})  voxel={crop.zarr_path.name} ===")
        per_crop: dict[str, dict] = {}

        for m in skip_data:
            fn = METRICS[m][1]
            t0 = time.time()
            try:
                out = fn(crop)
                row = _flatten(out)
                results[m].append(row)
                per_crop[m] = row
                print(f"  [{m}] ok ({time.time()-t0:.1f}s)")
            except Exception as e:
                print(f"  [{m}] FAILED: {e}")
                traceback.print_exc()

        if need_data:
            t0 = time.time()
            try:
                data = load_crop(crop)
                print(f"  loaded shape={data.shape} voxel={data.voxel_size_nm} ({time.time()-t0:.1f}s)")
            except Exception as e:
                print(f"  LOAD FAILED: {e}")
                # still flush metadata-only metrics for this crop
                for m, row in per_crop.items():
                    write_csv(out_dir / f"native_{m}.csv", [row], append=True)
                continue

            for m in need_data:
                fn = METRICS[m][1]
                t0 = time.time()
                try:
                    out = fn(data)
                    row = _flatten(out)
                    results[m].append(row)
                    per_crop[m] = row
                    print(f"  [{m}] ok ({time.time()-t0:.1f}s)")
                except Exception as e:
                    print(f"  [{m}] FAILED: {e}")
                    traceback.print_exc()

        # Flush this crop's results immediately
        for m, row in per_crop.items():
            write_csv(out_dir / f"native_{m}.csv", [row], append=True)

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None,
                    help="Comma-separated crop IDs to run (default: all active)")
    ap.add_argument("--metrics", type=str, default=",".join(METRICS.keys()),
                    help=f"Comma-separated metric names (default: all)")
    ap.add_argument("--out", type=str, default=str(cfg.RESULTS_DIR),
                    help="Output directory (default: results/)")
    args = ap.parse_args()

    crops = cfg.active_crops()
    if args.only:
        wanted = set(args.only.split(","))
        crops = tuple(c for c in crops if c.crop in wanted)
        if not crops:
            print(f"No active crops matched: {args.only}")
            sys.exit(1)

    metric_names = [m.strip() for m in args.metrics.split(",") if m.strip()]
    for m in metric_names:
        if m not in METRICS:
            print(f"Unknown metric: {m}. Available: {', '.join(METRICS)}")
            sys.exit(1)

    print(f"Running {len(metric_names)} metrics on {len(crops)} crops")
    print(f"  metrics: {', '.join(metric_names)}")
    print(f"  crops: {', '.join(c.crop for c in crops)}")

    out_dir = Path(args.out)
    t0 = time.time()
    run(crops, metric_names, out_dir, append=True)
    print(f"\nTotal runtime: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
