"""
Read per-metric CSVs from results/ and print tissue x prep summaries and
anatomy-matched comparisons. Also writes results/summary_tissue_prep.csv
and results/summary_anatomy_matched.csv.

Usage:
    python -m scripts.summarize [--prefix native]
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics as stat
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg


# Which numeric columns per metric CSV to summarise, with short display names.
COLUMNS = {
    "volume_fraction": [
        ("ecs_fraction", "ECS frac"),
        ("cell_fraction", "cell frac"),
    ],
    "ecs_width": [
        ("narrow_percentiles_nm_p25", "width p25 nm"),
        ("narrow_percentiles_nm_p50", "width p50 nm"),
        ("narrow_percentiles_nm_p75", "width p75 nm"),
        ("narrow_fraction", "frac <200nm"),
    ],
    "voronoi_gap": [
        ("percentiles_nm_p25", "gap p25 nm"),
        ("percentiles_nm_p50", "gap p50 nm"),
        ("percentiles_nm_p75", "gap p75 nm"),
        ("contact_fractions_p40", "contact<40nm"),
        ("contact_fractions_p80", "contact<80nm"),
    ],
    "sa_v": [
        ("sa_v_ecs_per_nm", "SA:V /nm"),
        ("cell_density_per_um3", "cells/um3"),
    ],
    "topology": [
        ("fraction_convex", "frac convex"),
        ("fraction_concave", "frac concave"),
        ("fraction_flat", "frac flat"),
        ("curvature_std_per_nm", "|H| std /nm"),
        ("roughness_rms_nm_p30", "rough 30nm"),
        ("roughness_rms_nm_p60", "rough 60nm"),
        ("roughness_rms_nm_p120", "rough 120nm"),
        ("protrusion_density_per_um2", "prot/um2"),
        ("indentation_density_per_um2", "ind/um2"),
    ],
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def safe_float(v):
    try:
        if v is None or v == "" or v == "nan":
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def summarise_by_group(rows: list[dict], column: str, group_keys: list[str]):
    """Returns {group_key_tuple: (n, mean, median)}."""
    buckets = defaultdict(list)
    for r in rows:
        key = tuple(r.get(k) or "" for k in group_keys)
        v = safe_float(r.get(column))
        if v is not None:
            buckets[key].append(v)
    out = {}
    for key, vals in buckets.items():
        n = len(vals)
        out[key] = (n, stat.mean(vals) if n else float("nan"),
                    stat.median(vals) if n else float("nan"))
    return out


def fmt(v, precision=3):
    if v is None:
        return "-"
    if abs(v) >= 1000 or (0 < abs(v) < 1e-3):
        return f"{v:.{precision}e}"
    return f"{v:.{precision}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="native",
                    help="Filename prefix (default: native)")
    args = ap.parse_args()

    results_dir = cfg.RESULTS_DIR
    print(f"Reading {args.prefix}_*.csv from {results_dir}\n")

    combined_rows = []  # flatten one row per crop from all metric CSVs
    crop_records: dict[str, dict] = {}

    for metric, cols in COLUMNS.items():
        path = results_dir / f"{args.prefix}_{metric}.csv"
        rows = read_csv(path)
        if not rows:
            print(f"  {metric}: (missing {path.name})")
            continue
        print(f"  {metric}: {len(rows)} rows")
        # Accumulate into crop records
        for r in rows:
            crop = r.get("crop")
            rec = crop_records.setdefault(crop, {
                "crop": crop, "tissue": r.get("tissue"),
                "prep": r.get("prep"), "region_group": r.get("region_group"),
                "voxel_nm": r.get("voxel_nm"),
            })
            for col, _label in cols:
                rec[col] = r.get(col)

    all_rows = list(crop_records.values())

    # --- Tissue x Prep summary ---
    print("\n=== Tissue x Prep summaries ===")
    summary_rows = []
    for metric, cols in COLUMNS.items():
        for col, label in cols:
            grouped = summarise_by_group(all_rows, col, ["tissue", "prep"])
            if not grouped:
                continue
            print(f"\n  [{label}]   ({metric}.{col})")
            header = f"    {'tissue':8s} {'prep':12s} {'n':>4s} {'mean':>12s} {'median':>12s}"
            print(header)
            for (tissue, prep), (n, m, md) in sorted(grouped.items()):
                print(f"    {tissue:8s} {prep:12s} {n:>4d} {fmt(m):>12s} {fmt(md):>12s}")
                summary_rows.append({
                    "metric": metric, "column": col, "label": label,
                    "tissue": tissue, "prep": prep, "n": n,
                    "mean": m, "median": md,
                })

    out_path = results_dir / f"summary_{args.prefix}_tissue_prep.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric","column","label","tissue","prep","n","mean","median"])
        w.writeheader()
        w.writerows(summary_rows)
    print(f"\n  wrote {out_path}")

    # --- Anatomy-matched comparisons ---
    print("\n=== Anatomy-matched comparisons (region_group x prep) ===")
    anatomy_rows = []
    matched = cfg.anatomy_matched_groups()
    for metric, cols in COLUMNS.items():
        for col, label in cols:
            grouped = summarise_by_group(all_rows, col, ["region_group", "prep"])
            for group in matched:
                chem = grouped.get((group, "Chemical"))
                hpf = grouped.get((group, "Rapid HPF"))
                if chem is None or hpf is None:
                    continue
                n_c, m_c, md_c = chem
                n_h, m_h, md_h = hpf
                print(f"  [{label:14s}]  {group:25s}  "
                      f"Chem n={n_c} mean={fmt(m_c)}  HPF n={n_h} mean={fmt(m_h)}")
                anatomy_rows.append({
                    "metric": metric, "column": col, "label": label,
                    "region_group": group,
                    "chem_n": n_c, "chem_mean": m_c, "chem_median": md_c,
                    "hpf_n": n_h, "hpf_mean": m_h, "hpf_median": md_h,
                })

    out_path = results_dir / f"summary_{args.prefix}_anatomy_matched.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "metric","column","label","region_group",
            "chem_n","chem_mean","chem_median",
            "hpf_n","hpf_mean","hpf_median",
        ])
        w.writeheader()
        w.writerows(anatomy_rows)
    print(f"\n  wrote {out_path}")


if __name__ == "__main__":
    main()
