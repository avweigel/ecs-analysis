"""
Produce a panel of per-metric figures from the native CSVs.

Each metric column is rendered as a strip-plot: tissue on x-axis, value on
y-axis, dots colored by prep and shape-coded by anatomy-matched group
when applicable.

Usage:
    python -m scripts.make_figures [--prefix native]
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ecs import config as cfg


COLUMNS = {
    "volume_fraction": [("ecs_fraction", "ECS fraction", "fraction")],
    "ecs_width": [
        ("narrow_percentiles_nm_p25", "ECS width p25", "nm"),
        ("narrow_percentiles_nm_p50", "ECS width p50", "nm"),
        ("narrow_percentiles_nm_p75", "ECS width p75", "nm"),
    ],
    "voronoi_gap": [
        ("percentiles_nm_p50", "Voronoi gap p50", "nm"),
        ("contact_fractions_p40", "Contact fraction <40 nm", "fraction"),
        ("contact_fractions_p80", "Contact fraction <80 nm", "fraction"),
    ],
    "sa_v": [
        ("sa_v_ecs_per_nm", "ECS-facing SA / cell vol", "1/nm"),
        ("cell_density_per_um3", "Cell density", "cells/um^3"),
    ],
    "topology": [
        ("fraction_convex", "Fraction convex", "fraction"),
        ("fraction_concave", "Fraction concave", "fraction"),
        ("fraction_flat", "Fraction flat", "fraction"),
        ("curvature_std_per_nm", "|H| std", "1/nm"),
        ("roughness_rms_nm_p30", "Roughness @ 30 nm", "nm"),
        ("roughness_rms_nm_p60", "Roughness @ 60 nm", "nm"),
        ("roughness_rms_nm_p120", "Roughness @ 120 nm", "nm"),
        ("protrusion_density_per_um2", "Protrusion density", "/um^2"),
        ("indentation_density_per_um2", "Indentation density", "/um^2"),
    ],
}

TISSUE_ORDER = ["Kidney", "Heart", "Liver", "Cortex"]
try:                                   # `python -m scripts.make_figures`
    from scripts.palette import PREP_COLORS
except ImportError:                     # `python scripts/make_figures.py`
    from palette import PREP_COLORS


def safe_float(v):
    try:
        if v is None or v == "" or v == "nan":
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def strip_plot(ax, rows, value_col, title, ylabel):
    """Plot tissue x-axis, value y-axis, dots colored by prep."""
    by_group = defaultdict(list)  # (tissue, prep) -> [(crop, value, region_group)]
    for r in rows:
        v = safe_float(r.get(value_col))
        if v is None:
            continue
        t = r.get("tissue", "")
        p = r.get("prep", "")
        by_group[(t, p)].append((r.get("crop", ""), v, r.get("region_group") or ""))

    x_positions = []
    x_labels = []
    handled_legend = set()
    for i, t in enumerate(TISSUE_ORDER):
        for j, p in enumerate(["Chemical", "Rapid HPF"]):
            xc = i * 3 + (0 if p == "Chemical" else 1)
            entries = by_group.get((t, p), [])
            for _, v, _grp in entries:
                jitter = (np.random.rand() - 0.5) * 0.4
                label = p if p not in handled_legend else None
                ax.scatter(xc + jitter, v, color=PREP_COLORS[p],
                           edgecolor="black", linewidth=0.4, s=40, alpha=0.85,
                           label=label)
                handled_legend.add(p)
        x_positions.append(i * 3 + 0.5)
        x_labels.append(t)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels)
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    if title.endswith("p50") or "fraction" in title.lower() or "density" in title.lower():
        # one of the columns we want the legend on
        ax.legend(fontsize=8, loc="best", frameon=True)


def render_metric_panel(prefix: str, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    for metric, cols in COLUMNS.items():
        path = cfg.RESULTS_DIR / f"{prefix}_{metric}.csv"
        rows = read_csv(path)
        if not rows:
            print(f"  skip {metric}: no rows in {path.name}")
            continue
        n = len(cols)
        ncols = 3 if n >= 3 else n
        nrows = (n + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4.5, nrows * 3.6),
                                 squeeze=False)
        for k, (col, title, ylabel) in enumerate(cols):
            ax = axes[k // ncols][k % ncols]
            strip_plot(ax, rows, col, title, ylabel)
        for k in range(n, nrows * ncols):
            axes[k // ncols][k % ncols].axis("off")
        fig.suptitle(f"{metric} — by tissue x prep ({prefix})", fontsize=12, y=0.99)
        fig.tight_layout()
        out = out_dir / f"{prefix}_{metric}.png"
        fig.savefig(out, dpi=160, bbox_inches="tight")
        plt.close(fig)
        print(f"  wrote {out}")


def render_anatomy_matched(prefix: str, out_dir: Path):
    """Side-by-side Chemical vs HPF strip plots, one per anatomy-matched group."""
    matched = cfg.anatomy_matched_groups()
    if not matched:
        print("  no anatomy-matched groups defined yet")
        return

    # Pick a few key columns to visualize across all matched groups
    headline_columns = [
        ("volume_fraction", "ecs_fraction", "ECS fraction"),
        ("ecs_width", "narrow_percentiles_nm_p50", "ECS width p50 (nm)"),
        ("voronoi_gap", "percentiles_nm_p50", "Voronoi gap p50 (nm)"),
        ("sa_v", "sa_v_ecs_per_nm", "ECS-facing SA / cell vol (1/nm)"),
        ("topology", "fraction_convex", "Fraction convex"),
        ("topology", "roughness_rms_nm_p60", "Roughness @ 60 nm"),
        ("topology", "protrusion_density_per_um2", "Protrusion density (/um^2)"),
        ("topology", "indentation_density_per_um2", "Indentation density (/um^2)"),
    ]

    rows_by_metric = {}
    for metric, _col, _title in headline_columns:
        if metric not in rows_by_metric:
            rows_by_metric[metric] = read_csv(cfg.RESULTS_DIR / f"{prefix}_{metric}.csv")

    groups = sorted(matched.keys())
    fig, axes = plt.subplots(len(groups), len(headline_columns),
                             figsize=(len(headline_columns) * 2.4, len(groups) * 2.0),
                             squeeze=False)
    for i, group in enumerate(groups):
        for j, (metric, col, title) in enumerate(headline_columns):
            ax = axes[i][j]
            rows = [r for r in rows_by_metric.get(metric, [])
                    if r.get("region_group") == group]
            data_chem = [safe_float(r.get(col)) for r in rows if r.get("prep") == "Chemical"]
            data_hpf = [safe_float(r.get(col)) for r in rows if r.get("prep") == "Rapid HPF"]
            data_chem = [v for v in data_chem if v is not None]
            data_hpf = [v for v in data_hpf if v is not None]
            xs_c = np.zeros(len(data_chem)) + np.random.rand(len(data_chem)) * 0.3 - 0.15
            xs_h = np.ones(len(data_hpf)) + np.random.rand(len(data_hpf)) * 0.3 - 0.15
            ax.scatter(xs_c, data_chem, color=PREP_COLORS["Chemical"], s=40,
                       edgecolor="black", linewidth=0.4)
            ax.scatter(xs_h, data_hpf, color=PREP_COLORS["Rapid HPF"], s=40,
                       edgecolor="black", linewidth=0.4)
            if data_chem:
                ax.plot([-0.25, 0.25], [np.mean(data_chem)] * 2,
                        color=PREP_COLORS["Chemical"], linewidth=2)
            if data_hpf:
                ax.plot([0.75, 1.25], [np.mean(data_hpf)] * 2,
                        color=PREP_COLORS["Rapid HPF"], linewidth=2)
            ax.set_xticks([0, 1])
            ax.set_xticklabels(["Chem", "HPF"], fontsize=8)
            if i == 0:
                ax.set_title(title, fontsize=8)
            if j == 0:
                ax.set_ylabel(group, fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(True, alpha=0.3, axis="y")
    fig.suptitle(f"Anatomy-matched comparisons ({prefix})", fontsize=11, y=0.995)
    fig.tight_layout()
    out = out_dir / f"{prefix}_anatomy_matched.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="native")
    ap.add_argument("--out", default=str(cfg.FIGURES_DIR))
    args = ap.parse_args()

    out_dir = Path(args.out)
    print(f"Rendering figures from {args.prefix}_*.csv into {out_dir}")
    render_metric_panel(args.prefix, out_dir)
    render_anatomy_matched(args.prefix, out_dir)


if __name__ == "__main__":
    main()
