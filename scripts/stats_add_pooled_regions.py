#!/usr/bin/env python3
"""
Append pooled-anatomy stat rows to results/stats_native.csv.

Fig 2 wants two regions per tissue, but no single kidney tubule region_group
has n>=2 on both arms (DCT base is 1 Chem / 3 HPF, PCT base is 1 Chem only).
Pooling the two *basal* tubule groups gives a usable "Tubule basal" arm
(2 Chem vs 3 HPF) that matches the anatomy being compared: tubule epithelium
basal infolding ECS, DCT and PCT together.

Reuses the exact machinery from scripts.stats (same exact Mann-Whitney,
Cliff's delta, bootstrap CIs, same RNG seed) so the appended rows are
methodologically identical to the rest of the table. Idempotent: existing
rows for these pooled groups are replaced on re-run.

Usage:
    python scripts/stats_add_pooled_regions.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from scripts.summarize import COLUMNS
from scripts.stats import (RNG_SEED, SKIP_METRICS, compare_groups,
                           load_crop_records)

# pooled_name -> set of constituent region_group values
POOLED_REGIONS: dict[str, set[str]] = {
    "Tubule basal": {"DCT base", "PCT base"},
}

STATS_PATH = cfg.RESULTS_DIR / "stats_native.csv"


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)

    rows = list(load_crop_records("native").values())

    # Relabel constituent crops with the pooled name, in a copy.
    pooled_rows = []
    for r in rows:
        for name, members in POOLED_REGIONS.items():
            if (r.get("region_group") or "") in members:
                rr = dict(r)
                rr["region_group"] = name
                pooled_rows.append(rr)

    new_results: list[dict] = []
    for metric, cols in COLUMNS.items():
        if metric in SKIP_METRICS:
            continue
        for col, label in cols:
            new_results.extend(
                compare_groups(pooled_rows, "region_group",
                               list(POOLED_REGIONS), metric, col, label, rng)
            )

    with open(STATS_PATH) as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        existing = [r for r in reader
                    if not (r["group_type"] == "region_group"
                            and r["group_value"] in POOLED_REGIONS)]

    with open(STATS_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in existing:
            w.writerow(r)
        for r in new_results:
            w.writerow(r)

    for name, members in POOLED_REGIONS.items():
        n = [r for r in new_results if r["group_value"] == name]
        if n:
            print(f"{name} (= {' + '.join(sorted(members))}): "
                  f"{len(n)} comparisons, n={n[0]['n_chem']}v{n[0]['n_hpf']}")
        else:
            print(f"{name}: no usable comparisons (n<2 on an arm)")
    print(f"Wrote {STATS_PATH} ({len(existing)} kept + {len(new_results)} pooled)")


if __name__ == "__main__":
    main()
