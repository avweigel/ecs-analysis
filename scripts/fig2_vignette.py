#!/usr/bin/env python3
"""
Fig 2 vignette: one anatomy-matched region, the full metric smorgasbord.

Each region is a little descriptive vignette of how ECS and membrane
morphology differ between Chemical and Rapid HPF. This renders one region
as a row of per-metric dot-plots (one metric per analysis family), with
per-crop points, a median bar, n per arm, and Cliff's delta pulled from
stats_native.csv so the annotation matches the stats table.

Usage:
    python scripts/fig2_vignette.py "Bile canaliculus"
Writes figures/vignette_<slug>.png.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS = REPO_ROOT / "results"
PREP_ORDER = ["Chemical", "Rapid HPF"]
PREP_COLOR = {"Chemical": "#d62728", "Rapid HPF": "#1f77b4"}

# (metric_file, column, short label) — one representative per analysis family.
PANELS = [
    ("volume_fraction", "ecs_fraction", "ECS fraction"),
    ("ecs_width", "narrow_percentiles_nm_p50", "ECS width p50 (nm)"),
    ("voronoi_gap", "contact_fractions_p40", "Contact <40 nm"),
    ("sa_v", "sa_v_ecs_per_nm", "SA:V ECS (1/nm)"),
    ("sa_v", "cell_density_per_um3", "Cell density (/µm³)"),
    ("topology", "roughness_rms_nm_p60", "Roughness 60 nm"),
    ("topology", "indentation_density_per_um2", "Indentation (/µm²)"),
]


def read_rows(metric: str) -> list[dict]:
    with open(RESULTS / f"native_{metric}.csv") as f:
        return list(csv.DictReader(f))


def stats_lookup() -> dict[tuple[str, str], dict]:
    out = {}
    with open(RESULTS / "stats_native.csv") as f:
        for r in csv.DictReader(f):
            if r["group_type"] == "region_group":
                out[(r["group_value"], r["column"])] = r
    return out


def median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main() -> None:
    region = sys.argv[1] if len(sys.argv) > 1 else "Bile canaliculus"
    stats = stats_lookup()

    tissue = ""
    fig, axes = plt.subplots(1, len(PANELS), figsize=(len(PANELS) * 2.0 + 0.5, 3.2))
    for ax, (metric, col, label) in zip(axes, PANELS):
        rows = [r for r in read_rows(metric) if r.get("region_group") == region]
        if rows and not tissue:
            tissue = rows[0].get("tissue", "")
        for i, prep in enumerate(PREP_ORDER):
            vals = []
            for r in rows:
                if r.get("prep") != prep:
                    continue
                try:
                    vals.append(float(r[col]))
                except (KeyError, ValueError):
                    pass
            if not vals:
                continue
            n = len(vals)
            xs = [i + (j - (n - 1) / 2) * 0.06 for j in range(n)]
            ax.scatter(xs, vals, s=42, color=PREP_COLOR[prep], alpha=0.85,
                       edgecolor="white", linewidth=0.6, zorder=3)
            ax.plot([i - 0.22, i + 0.22], [median(vals)] * 2, color="black",
                    lw=2, zorder=4)
        st = stats.get((region, col))
        sub = ""
        if st:
            p = float(st["mw_p"])
            mark = "*" if p < 0.05 else ("†" if p < 0.1 else "")
            sub = (f"δ={float(st['cliff_delta']):+.2f}{mark}  "
                   f"n={st['n_chem']}v{st['n_hpf']}")
        ax.set_title(f"{label}\n{sub}", fontsize=8)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Chem", "HPF"], fontsize=8)
        ax.set_ylim(bottom=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=7)

    fig.suptitle(f"{tissue}  —  {region}", fontsize=12, y=1.02)
    fig.tight_layout()
    slug = region.lower().replace(" ", "_")
    out = REPO_ROOT / "figures" / f"vignette_{slug}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
