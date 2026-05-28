#!/usr/bin/env python3
"""
Fig 1G: Cortex % ECS, Chemical vs Rapid HPF.

A single strip/box panel of per-crop ECS volume fraction for the cortex
(brain) crops — the analysis contribution to Figure 1's brain-benchmarking
panel. Reads results/native_volume_fraction.csv. Writes
figures/fig1g_cortex_ecs.png.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "results" / "native_volume_fraction.csv"
OUT = REPO_ROOT / "figures" / "fig1g_cortex_ecs.png"

PREP_ORDER = ["Chemical", "Rapid HPF"]
PREP_COLOR = {"Chemical": "#f97316", "Rapid HPF": "#0ea5e9"}


def main() -> None:
    by_prep: dict[str, list[float]] = {p: [] for p in PREP_ORDER}
    with open(SRC) as f:
        for r in csv.DictReader(f):
            if r["tissue"] != "Cortex":
                continue
            try:
                by_prep[r["prep"]].append(float(r["ecs_fraction"]) * 100.0)
            except (KeyError, ValueError):
                continue

    fig, ax = plt.subplots(figsize=(3.2, 4.0))
    for i, prep in enumerate(PREP_ORDER):
        vals = by_prep[prep]
        if not vals:
            continue
        x = [i + (j - len(vals) / 2) * 0.04 for j in range(len(vals))]
        ax.scatter(x, vals, s=45, color=PREP_COLOR[prep], alpha=0.85,
                   edgecolor="white", linewidth=0.6, zorder=3,
                   label=f"{prep} (n={len(vals)})")
        med = sorted(vals)[len(vals) // 2] if len(vals) % 2 else \
            sum(sorted(vals)[len(vals) // 2 - 1:len(vals) // 2 + 1]) / 2
        ax.plot([i - 0.18, i + 0.18], [med, med], color="black", lw=2, zorder=4)

    ax.set_xticks(range(len(PREP_ORDER)))
    ax.set_xticklabels(PREP_ORDER)
    ax.set_ylabel("ECS volume fraction (%)")
    ax.set_title("Cortex % ECS")
    ax.set_ylim(bottom=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT, dpi=200)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
