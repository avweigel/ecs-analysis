"""
Formal statistical comparison of Chemical vs Rapid HPF preparations,
per-metric, grouped by tissue and by anatomy region_group.

For each (metric, group_type, group_value, column) where both Chemical and
HPF have n>=2 crops, compute:
  - Two-sided Mann-Whitney U test
  - Cliff's delta effect size (signed: positive => Chem > HPF)
  - Bootstrap 95% CI for each group's median (5000 resamples)
  - Bootstrap 95% CI for the difference in medians (Chem - HPF)

Reads results/native_*.csv. Writes results/stats_native.csv.

Usage:
    python -m scripts.stats
"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from scripts.summarize import COLUMNS, read_csv, safe_float


# Topology is now fully computed across all crops, so include it in the
# stat comparisons (curvature, multi-scale roughness, protrusion/indentation
# density) — these are the candidate "correlate of difference" metrics.
SKIP_METRICS: set[str] = set()

N_BOOT = 5000
RNG_SEED = 1234
ALPHA = 0.05


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    """Cliff's delta in [-1, 1]. Positive => x stochastically larger than y."""
    if len(x) == 0 or len(y) == 0:
        return float("nan")
    # Pairwise comparison via broadcasting.
    diff = x[:, None] - y[None, :]
    gt = np.sum(diff > 0)
    lt = np.sum(diff < 0)
    n = x.size * y.size
    return (gt - lt) / n


def bootstrap_median_ci(values: np.ndarray, rng: np.random.Generator,
                        n_boot: int = N_BOOT, alpha: float = ALPHA
                        ) -> tuple[float, float, float]:
    """Return (median, ci_lo, ci_hi) for the median via percentile bootstrap."""
    if values.size == 0:
        return float("nan"), float("nan"), float("nan")
    obs_median = float(np.median(values))
    if values.size == 1:
        return obs_median, obs_median, obs_median
    n = values.size
    idx = rng.integers(0, n, size=(n_boot, n))
    samples = values[idx]
    boot_medians = np.median(samples, axis=1)
    lo = float(np.percentile(boot_medians, 100 * alpha / 2))
    hi = float(np.percentile(boot_medians, 100 * (1 - alpha / 2)))
    return obs_median, lo, hi


def bootstrap_diff_median_ci(x: np.ndarray, y: np.ndarray,
                             rng: np.random.Generator,
                             n_boot: int = N_BOOT, alpha: float = ALPHA
                             ) -> tuple[float, float, float]:
    """Return (median(x)-median(y), ci_lo, ci_hi) by independent bootstrap."""
    if x.size == 0 or y.size == 0:
        return float("nan"), float("nan"), float("nan")
    obs = float(np.median(x) - np.median(y))
    if x.size == 1 and y.size == 1:
        return obs, obs, obs
    nx, ny = x.size, y.size
    ix = rng.integers(0, nx, size=(n_boot, nx))
    iy = rng.integers(0, ny, size=(n_boot, ny))
    diffs = np.median(x[ix], axis=1) - np.median(y[iy], axis=1)
    lo = float(np.percentile(diffs, 100 * alpha / 2))
    hi = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    return obs, lo, hi


def direction(delta: float, eps: float = 0.147) -> str:
    """Vargha-Delaney style threshold for 'negligible' is |delta|<0.147."""
    if math.isnan(delta) or abs(delta) < eps:
        return "approx"
    return "Chem>HPF" if delta > 0 else "HPF>Chem"


def load_crop_records(prefix: str = "native") -> dict[str, dict]:
    """Merge per-metric CSVs into one dict keyed by crop."""
    results_dir = cfg.RESULTS_DIR
    crop_records: dict[str, dict] = {}
    for metric, cols in COLUMNS.items():
        if metric in SKIP_METRICS:
            continue
        path = results_dir / f"{prefix}_{metric}.csv"
        rows = read_csv(path)
        if not rows:
            print(f"  [warn] missing {path.name}", file=sys.stderr)
            continue
        for r in rows:
            crop = r.get("crop")
            if not crop:
                continue
            rec = crop_records.setdefault(crop, {
                "crop": crop,
                "tissue": r.get("tissue"),
                "prep": r.get("prep"),
                "region_group": r.get("region_group"),
            })
            for col, _label in cols:
                rec[col] = r.get(col)
    return crop_records


def collect_values(rows: list[dict], group_key: str, group_value: str,
                   prep: str, column: str) -> np.ndarray:
    out = []
    for r in rows:
        if (r.get(group_key) or "") != group_value:
            continue
        if (r.get("prep") or "") != prep:
            continue
        v = safe_float(r.get(column))
        if v is not None:
            out.append(v)
    return np.asarray(out, dtype=float)


def compare_groups(rows: list[dict], group_key: str, group_values: list[str],
                   metric: str, column: str, label: str,
                   rng: np.random.Generator) -> list[dict]:
    out_rows: list[dict] = []
    for gv in group_values:
        chem = collect_values(rows, group_key, gv, "Chemical", column)
        hpf = collect_values(rows, group_key, gv, "Rapid HPF", column)
        if chem.size < 2 or hpf.size < 2:
            continue

        # Mann-Whitney U (two-sided)
        try:
            mw = sps.mannwhitneyu(chem, hpf, alternative="two-sided")
            mw_u = float(mw.statistic)
            mw_p = float(mw.pvalue)
        except ValueError:
            mw_u = float("nan")
            mw_p = float("nan")

        delta = cliffs_delta(chem, hpf)

        chem_med, chem_lo, chem_hi = bootstrap_median_ci(chem, rng)
        hpf_med, hpf_lo, hpf_hi = bootstrap_median_ci(hpf, rng)
        diff_med, diff_lo, diff_hi = bootstrap_diff_median_ci(chem, hpf, rng)

        out_rows.append({
            "metric": metric,
            "column": column,
            "label": label,
            "group_type": group_key,
            "group_value": gv,
            "n_chem": int(chem.size),
            "n_hpf": int(hpf.size),
            "chem_median": chem_med,
            "chem_ci_lo": chem_lo,
            "chem_ci_hi": chem_hi,
            "hpf_median": hpf_med,
            "hpf_ci_lo": hpf_lo,
            "hpf_ci_hi": hpf_hi,
            "diff_median": diff_med,
            "diff_ci_lo": diff_lo,
            "diff_ci_hi": diff_hi,
            "mw_u": mw_u,
            "mw_p": mw_p,
            "cliff_delta": delta,
            "direction": direction(delta),
        })
    return out_rows


def fmt(v: float, p: int = 3) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "  nan"
    if abs(v) >= 1000 or (0 < abs(v) < 1e-3):
        return f"{v:.{p}e}"
    return f"{v:.{p}f}"


def main():
    rng = np.random.default_rng(RNG_SEED)

    crop_records = load_crop_records("native")
    rows = list(crop_records.values())
    print(f"Loaded {len(rows)} crops from results/native_*.csv\n")

    # Tissues present
    tissues = sorted({r["tissue"] for r in rows if r.get("tissue")})
    # Anatomy-matched region_groups (where both preps exist)
    matched = sorted(cfg.anatomy_matched_groups().keys())

    all_results: list[dict] = []
    for metric, cols in COLUMNS.items():
        if metric in SKIP_METRICS:
            continue
        for col, label in cols:
            all_results.extend(
                compare_groups(rows, "tissue", tissues,
                               metric, col, label, rng)
            )
            all_results.extend(
                compare_groups(rows, "region_group", matched,
                               metric, col, label, rng)
            )

    # Write CSV
    out_path = cfg.RESULTS_DIR / "stats_native.csv"
    fieldnames = [
        "metric", "column", "label", "group_type", "group_value",
        "n_chem", "n_hpf",
        "chem_median", "chem_ci_lo", "chem_ci_hi",
        "hpf_median", "hpf_ci_lo", "hpf_ci_hi",
        "diff_median", "diff_ci_lo", "diff_ci_hi",
        "mw_u", "mw_p", "cliff_delta", "direction",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_results:
            w.writerow(r)
    print(f"Wrote {out_path} ({len(all_results)} comparisons)\n")

    # Print sorted by |cliff_delta| descending
    sorted_rows = sorted(all_results,
                         key=lambda r: abs(r["cliff_delta"])
                         if not math.isnan(r["cliff_delta"]) else -1,
                         reverse=True)
    print("=== Comparisons sorted by |Cliff's delta| (desc) ===")
    print(f"{'metric':18s} {'column':30s} {'group':28s} "
          f"{'nC':>3s} {'nH':>3s} {'chem_med':>10s} {'hpf_med':>10s} "
          f"{'delta':>7s} {'p':>9s}  dir")
    for r in sorted_rows:
        gv = r["group_value"]
        gtag = "T" if r["group_type"] == "tissue" else "A"
        gv_disp = f"[{gtag}] {gv}"
        print(f"{r['metric']:18s} {r['column']:30s} {gv_disp:28s} "
              f"{r['n_chem']:>3d} {r['n_hpf']:>3d} "
              f"{fmt(r['chem_median']):>10s} {fmt(r['hpf_median']):>10s} "
              f"{r['cliff_delta']:>+7.3f} {fmt(r['mw_p']):>9s}  "
              f"{r['direction']}")

    # Highlight strongest signals
    strong = [r for r in all_results
              if not math.isnan(r["cliff_delta"])
              and abs(r["cliff_delta"]) > 0.5
              and not math.isnan(r["mw_p"])
              and r["mw_p"] < 0.05]
    print(f"\n=== {len(strong)} comparisons with |delta|>0.5 AND p<0.05 ===")
    for r in sorted(strong, key=lambda r: abs(r["cliff_delta"]), reverse=True):
        gtag = "tissue" if r["group_type"] == "tissue" else "anatomy"
        print(f"  {r['label']:18s} {gtag}={r['group_value']:24s} "
              f"delta={r['cliff_delta']:+.3f} p={r['mw_p']:.4f} "
              f"({r['direction']}) "
              f"chem={fmt(r['chem_median'])} hpf={fmt(r['hpf_median'])}")


if __name__ == "__main__":
    main()
