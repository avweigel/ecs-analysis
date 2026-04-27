"""
Phase 4: run all metrics with every crop DOWNSAMPLED to a common voxel
size (default 8 nm), so geometry comparisons are not confounded by the
Chemical-vs-HPF resolution difference.

Output: results/matched_<metric>.csv (same schema as native_<metric>.csv,
with an extra column noting the source voxel size before downsampling).

Usage:
    python -m scripts.run_matched [--target 8.0] [--only ...] [--metrics ...]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from ecs.io import load_crop, downsample
from ecs.metrics import (
    volume_fraction,
    ecs_width,
    voronoi_gap,
    sa_v,
    topology,
)

# Reuse helpers from run_native
from scripts.run_native import _flatten, write_csv

METRICS = {
    "ecs_width":   ecs_width.compute,
    "voronoi_gap": voronoi_gap.compute,
    "sa_v":        sa_v.compute,
    "topology":    topology.compute,
}


def run(crops, metric_names, target_nm: float, out_dir: Path):
    for crop in crops:
        print(f"\n=== {crop.crop}  ({crop.tissue}, {crop.prep})  target={target_nm}nm ===")
        t0 = time.time()
        try:
            data = load_crop(crop)
            print(f"  loaded native shape={data.shape} voxel={data.voxel_size_nm} ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  LOAD FAILED: {e}")
            continue

        if data.voxel_size_nm[0] > target_nm + 0.1:
            print(f"  SKIP: native voxel {data.voxel_size_nm[0]} nm exceeds target {target_nm} nm")
            continue

        if data.voxel_size_nm[0] < target_nm - 0.1:
            t1 = time.time()
            data = downsample(data, target_nm)
            print(f"  downsampled to shape={data.shape} voxel={data.voxel_size_nm} ({time.time()-t1:.1f}s)")
        else:
            print(f"  already at target")

        for m in metric_names:
            fn = METRICS[m]
            t0 = time.time()
            try:
                out = fn(data)
                row = _flatten(out)
                row["native_voxel_nm"] = float(data.native_voxel_size_nm[0]) \
                    if data.native_voxel_size_nm else None
                row["analysis_voxel_nm"] = float(data.voxel_size_nm[0])
                write_csv(out_dir / f"matched_{m}.csv", [row], append=True)
                print(f"  [{m}] ok ({time.time()-t0:.1f}s)")
            except Exception as e:
                print(f"  [{m}] FAILED: {e}")
                traceback.print_exc()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, default=cfg.TARGET_VOXEL_NM,
                    help=f"Target voxel size in nm (default: {cfg.TARGET_VOXEL_NM})")
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--metrics", type=str, default=",".join(METRICS.keys()))
    ap.add_argument("--out", type=str, default=str(cfg.RESULTS_DIR))
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
            print(f"Unknown metric: {m}")
            sys.exit(1)

    print(f"Running matched-resolution at {args.target} nm on {len(crops)} crops")
    print(f"  metrics: {', '.join(metric_names)}")

    out_dir = Path(args.out)
    t0 = time.time()
    run(crops, metric_names, args.target, out_dir)
    print(f"\nTotal runtime: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
