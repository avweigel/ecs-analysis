"""
Phase 5: degradation experiment.

For each Chemical crop, compute the geometric metrics at multiple voxel
sizes >= the native voxel size (default 2, 4, 8, 16 nm). HPF crops are
already at 8 nm and aren't part of this experiment by default.

Output: results/degradation_<metric>.csv with one row per (crop,
analysis_voxel_nm).

Usage:
    python -m scripts.run_degradation [--targets 2,4,8,16] [--only ...]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from ecs.io import load_crop, downsample
from ecs.metrics import (
    ecs_width,
    voronoi_gap,
    sa_v,
    topology,
)

from scripts.run_native import _flatten, write_csv


METRICS = {
    "ecs_width":   ecs_width.compute,
    "voronoi_gap": voronoi_gap.compute,
    "sa_v":        sa_v.compute,
    "topology":    topology.compute,
}


def run(crops, metric_names, targets_nm, out_dir: Path):
    for crop in crops:
        print(f"\n=== {crop.crop}  ({crop.tissue}, {crop.prep}) ===")

        t0 = time.time()
        try:
            base_data = load_crop(crop)
            print(f"  loaded native shape={base_data.shape} voxel={base_data.voxel_size_nm} ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  LOAD FAILED: {e}")
            continue

        native_vx = float(base_data.voxel_size_nm[0])

        for tgt in sorted(targets_nm):
            if tgt < native_vx - 0.1:
                continue  # can't upsample
            if abs(tgt - native_vx) < 0.1:
                data = base_data
                action = "native"
            else:
                t1 = time.time()
                try:
                    data = downsample(base_data, tgt)
                    action = f"downsampled ({time.time()-t1:.1f}s)"
                except Exception as e:
                    print(f"  DOWNSAMPLE FAILED ({tgt} nm): {e}")
                    continue

            print(f"  --- @ {tgt} nm ({action}, shape={data.shape}) ---")

            for m in metric_names:
                fn = METRICS[m]
                t0 = time.time()
                try:
                    out = fn(data)
                    row = _flatten(out)
                    row["native_voxel_nm"] = native_vx
                    row["analysis_voxel_nm"] = float(data.voxel_size_nm[0])
                    write_csv(out_dir / f"degradation_{m}.csv", [row], append=True)
                    print(f"    [{m}] ok ({time.time()-t0:.1f}s)")
                except Exception as e:
                    print(f"    [{m}] FAILED: {e}")
                    traceback.print_exc()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=",".join(str(v) for v in cfg.DEGRADATION_VOXELS_NM),
                    help=f"Comma-separated target voxel sizes nm (default: {cfg.DEGRADATION_VOXELS_NM})")
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--metrics", type=str, default=",".join(METRICS.keys()))
    ap.add_argument("--prep", type=str, default="Chemical",
                    help="Restrict to a single prep type. Use 'all' for both. Default: Chemical")
    ap.add_argument("--out", type=str, default=str(cfg.RESULTS_DIR))
    args = ap.parse_args()

    crops = cfg.active_crops()
    if args.prep != "all":
        crops = tuple(c for c in crops if c.prep == args.prep)
    if args.only:
        wanted = set(args.only.split(","))
        crops = tuple(c for c in crops if c.crop in wanted)
        if not crops:
            print(f"No active crops matched")
            sys.exit(1)

    targets = [float(t) for t in args.targets.split(",")]
    metric_names = [m.strip() for m in args.metrics.split(",") if m.strip()]
    for m in metric_names:
        if m not in METRICS:
            print(f"Unknown metric: {m}")
            sys.exit(1)

    print(f"Degradation: {len(crops)} crops x {len(targets)} resolutions")
    print(f"  metrics: {', '.join(metric_names)}")
    print(f"  targets: {targets}")

    out_dir = Path(args.out)
    t0 = time.time()
    run(crops, metric_names, targets, out_dir)
    print(f"\nTotal runtime: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
