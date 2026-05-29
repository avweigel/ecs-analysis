#!/usr/bin/env python3
"""
Fig 2 showcase: effect-size matrix across the full metric suite.

Reads results/stats_native.csv and renders the anatomy-matched regions
(both arms n>=2) as rows, the headline metric of each analysis family as
columns, cells colored by Cliff's delta (positive = Chem>HPF). Significance
from Mann-Whitney is marked, and the cell text is the delta. This is the
"all the cool stuff in one view" panel: it shows where every metric agrees
(liver) and where they contradict / are underpowered (heart, kidney).

Writes figures/fig2_effect_matrix.png.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "results" / "stats_native.csv"
OUT = REPO_ROOT / "figures" / "fig2_effect_matrix.png"

# (tissue, region_group) rows with usable n on both arms, in display order.
REGIONS = [
    ("Liver", "Bile canaliculus"),
    ("Liver", "Hepatocyte lateral"),
    ("Heart", "Cardiac interstitial"),
    ("Heart", "Intercalated disc"),
    ("Kidney", "Glomerular"),
]

# One representative column per analysis family, grouped by what it measures.
METRICS = [
    ("ecs_fraction", "ECS\nfraction"),
    ("narrow_percentiles_nm_p50", "ECS width\np50"),
    ("percentiles_nm_p50", "Voronoi gap\np50"),
    ("contact_fractions_p40", "Contact\n<40 nm"),
    ("sa_v_ecs_per_nm", "SA:V\n(ECS)"),
    ("cell_density_per_um3", "Cell\ndensity"),
    ("roughness_rms_nm_p60", "Roughness\n60 nm"),
    ("curvature_std_per_nm", "Curvature\nstd"),
    ("fraction_concave", "Fraction\nconcave"),
    ("protrusion_density_per_um2", "Protrusion\ndensity"),
    ("indentation_density_per_um2", "Indentation\ndensity"),
]


def load() -> dict[tuple[str, str], dict]:
    """(region_group, column) -> {delta, p, n_chem, n_hpf}."""
    out: dict[tuple[str, str], dict] = {}
    with open(SRC) as f:
        for r in csv.DictReader(f):
            if r["group_type"] != "region_group":
                continue
            out[(r["group_value"], r["column"])] = {
                "delta": float(r["cliff_delta"]),
                "p": float(r["mw_p"]),
                "n_chem": int(r["n_chem"]),
                "n_hpf": int(r["n_hpf"]),
            }
    return out


def main() -> None:
    data = load()
    nrow, ncol = len(REGIONS), len(METRICS)
    delta = np.full((nrow, ncol), np.nan)
    annot = [["" for _ in range(ncol)] for _ in range(nrow)]
    for i, (_tissue, region) in enumerate(REGIONS):
        for j, (col, _label) in enumerate(METRICS):
            cell = data.get((region, col))
            if cell is None:
                continue
            delta[i, j] = cell["delta"]
            mark = "*" if cell["p"] < 0.05 else ("†" if cell["p"] < 0.1 else "")
            annot[i][j] = f"{cell['delta']:+.2f}{mark}"

    fig, ax = plt.subplots(figsize=(ncol * 0.92 + 1.6, nrow * 0.78 + 1.8))
    im = ax.imshow(delta, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")

    for i in range(nrow):
        for j in range(ncol):
            if annot[i][j]:
                v = delta[i, j]
                tc = "white" if abs(v) > 0.6 else "black"
                ax.text(j, i, annot[i][j], ha="center", va="center",
                        fontsize=8, color=tc)

    row_labels = [f"{t}\n{r}\n(n={data.get((r, 'ecs_fraction'), {}).get('n_chem', '?')}"
                  f"v{data.get((r, 'ecs_fraction'), {}).get('n_hpf', '?')})"
                  for t, r in REGIONS]
    ax.set_yticks(range(nrow))
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.set_xticks(range(ncol))
    ax.set_xticklabels([m[1] for m in METRICS], fontsize=8)

    # tissue separators
    for i in range(1, nrow):
        if REGIONS[i][0] != REGIONS[i - 1][0]:
            ax.axhline(i - 0.5, color="black", lw=1.5)

    ax.set_title("Fig 2 showcase — Cliff's δ (Chem vs HPF) across the metric suite\n"
                 "red = Chem>HPF, blue = HPF>Chem;  * p<0.05, † p<0.1",
                 fontsize=10)
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("Cliff's δ", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
