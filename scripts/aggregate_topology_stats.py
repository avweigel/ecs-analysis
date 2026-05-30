#!/usr/bin/env python3
"""
Aggregate per-vertex curvature / protrusion / contact-gap distributions for
each crop from the inspector .bin files, then produce:

  - results/membrane_topology_per_crop.csv       per-crop summary
  - results/membrane_topology_by_tissue.csv      per-tissue x prep aggregate
  - results/membrane_topology_by_region.csv      per-region_group x prep aggregate
  - results/membrane_topology_tables.tex         LaTeX tables for the manuscript

Inputs: figures/membranes/manifest_inspect.json + the per-crop .bin files (which
already have boundary-uncertain vertices NaN'd in the curvature/deviation/gap
channels by build_patch's vis/gap face filters). No new patch builds required.

Usage:
    python scripts/aggregate_topology_stats.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median, quantiles

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
INSPECT_DIR = REPO_ROOT / "figures" / "membranes" / "inspect"
MANIFEST = REPO_ROOT / "figures" / "membranes" / "manifest_inspect.json"
RESULTS_DIR = REPO_ROOT / "results"

CHANNELS = ("curvature", "deviation", "gap")


def per_crop_stats(rec: dict) -> dict:
    """Read the .bin payload for one crop, compute summary stats on the
    boundary-cleaned scalar values (NaN-aware: the bin already has NaN at
    vis-uncertain / gap-uncertain vertices)."""
    bin_path = INSPECT_DIR / rec["bin"]
    nv, nf = rec["nverts"], rec["nfaces"]
    buf = bin_path.read_bytes()
    o = 0
    o += nv * 3 * 4  # positions
    o += nf * 3 * 4  # indices
    cur = np.frombuffer(buf, dtype="<f4", count=nv, offset=o); o += nv * 4
    dev = np.frombuffer(buf, dtype="<f4", count=nv, offset=o); o += nv * 4
    gap = np.frombuffer(buf, dtype="<f4", count=nv, offset=o); o += nv * 4

    def pct(a, q):
        a = a[np.isfinite(a)]
        return float(np.percentile(a, q)) if a.size else float("nan")

    def frac(a, sign):
        a = a[np.isfinite(a)]
        if not a.size:
            return float("nan")
        if sign > 0: return float((a > 0).mean())
        return float((a < 0).mean())

    n_cur = int(np.isfinite(cur).sum())
    n_dev = int(np.isfinite(dev).sum())
    n_gap = int(np.isfinite(gap).sum())

    return {
        "crop": rec["crop"], "tissue": rec["tissue"], "prep": rec["prep"],
        "region_group": rec.get("region_group") or "",
        "anatomy": rec.get("anatomy") or "",
        "voxel_nm": rec["voxel_nm"],
        "patch_faces": rec.get("patch_faces"),
        "ecs_frac": rec.get("ecs_frac"),
        "gap_bounded_frac": rec.get("gap_bounded_frac"),
        # per-vertex effective sample sizes (after boundary cleanup)
        "n_curvature_kept": n_cur,
        "n_deviation_kept": n_dev,
        "n_gap_kept": n_gap,
        # signed percentiles
        "curvature_p10_nm-1": pct(cur, 10),
        "curvature_p50_nm-1": pct(cur, 50),
        "curvature_p90_nm-1": pct(cur, 90),
        "abs_curvature_p50_nm-1": pct(np.abs(cur), 50),
        "abs_curvature_p90_nm-1": pct(np.abs(cur), 90),
        "frac_convex": frac(cur, +1),
        "frac_concave": frac(cur, -1),
        "deviation_p10_nm": pct(dev, 10),
        "deviation_p50_nm": pct(dev, 50),
        "deviation_p90_nm": pct(dev, 90),
        "abs_deviation_p50_nm": pct(np.abs(dev), 50),
        "abs_deviation_p90_nm": pct(np.abs(dev), 90),
        "frac_protrusion": frac(dev, +1),
        "frac_indent": frac(dev, -1),
        "gap_p10_nm": pct(gap, 10),
        "gap_p50_nm": pct(gap, 50),
        "gap_p90_nm": pct(gap, 90),
    }


def aggregate(rows: list[dict], group_keys: tuple[str, ...]) -> list[dict]:
    """Aggregate per-crop stats over a grouping (e.g. ('tissue','prep'))."""
    by: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by[tuple(r[k] for k in group_keys)].append(r)
    agg = []
    for key, group in by.items():
        out = {k: v for k, v in zip(group_keys, key)}
        out["n_crops"] = len(group)
        # Per-crop p50 of each channel — aggregate across crops as median + IQR.
        for col in ("abs_curvature_p50_nm-1", "abs_deviation_p50_nm",
                    "gap_p50_nm", "frac_convex", "frac_protrusion",
                    "gap_bounded_frac"):
            vals = [r[col] for r in group
                    if r.get(col) is not None and np.isfinite(r[col])]
            if not vals:
                out[col + "_median"] = float("nan")
                out[col + "_iqr_lo"] = float("nan")
                out[col + "_iqr_hi"] = float("nan")
                continue
            out[col + "_median"] = float(median(vals))
            if len(vals) >= 4:
                q1, _q2, q3 = quantiles(vals, n=4)
            elif len(vals) >= 2:
                q1, q3 = min(vals), max(vals)
            else:
                q1 = q3 = vals[0]
            out[col + "_iqr_lo"] = float(q1)
            out[col + "_iqr_hi"] = float(q3)
        agg.append(out)
    return agg


def flag_outliers(rows: list[dict],
                  ratio_hi: float = 1.7,
                  ratio_lo: float = 0.6,
                  min_n: int = 3) -> dict:
    """Flag per-crop topology outliers vs their annotated peer group.

    Within each (tissue, region_group, prep) group with at least `min_n`
    crops, compute the median of |H|_p50 and |d|_p50 and flag a crop if
    EITHER metric's ratio to the group median exceeds `ratio_hi` or falls
    below `ratio_lo`. Two channels are independent — a crop can be flagged
    on curvature, deviation, or both. Singleton and N=2 groups are skipped
    (the median is ill-defined for a peer group of one or two).

    Output schema (one entry per flagged crop):
        {
          \"<crop>\": {
            \"reason\": str,           # human-readable summary for the tooltip
            \"channel\": \"H\"|\"d\"|\"both\",
            \"H_ratio\": float|None,  # observed / group_median
            \"d_ratio\": float|None,
            \"group_median_H\": float, # of all in-group crops
            \"group_median_d\": float,
            \"group_n\": int,
            \"region_group\": str,
            \"tissue\": str, \"prep\": str,
          }, ...
        }

    Re-annotation decisions belong to the annotator; this just surfaces
    candidates so they aren't forgotten.
    """
    by_group: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        h = r.get("abs_curvature_p50_nm-1")
        d = r.get("abs_deviation_p50_nm")
        if h is None or d is None or not np.isfinite(h) or not np.isfinite(d):
            continue
        by_group[(r["tissue"], r["region_group"], r["prep"])].append(r)
    out: dict[str, dict] = {}
    for (tissue, region, prep), group in by_group.items():
        if not region or len(group) < min_n:
            continue
        H = [g["abs_curvature_p50_nm-1"] for g in group]
        D = [g["abs_deviation_p50_nm"] for g in group]
        medH, medD = median(H), median(D)
        if medH <= 0 or medD <= 0:
            continue
        for g in group:
            rh = g["abs_curvature_p50_nm-1"] / medH
            rd = g["abs_deviation_p50_nm"] / medD
            H_out = rh > ratio_hi or rh < ratio_lo
            d_out = rd > ratio_hi or rd < ratio_lo
            if not (H_out or d_out):
                continue
            ch = "both" if (H_out and d_out) else ("H" if H_out else "d")
            # Reason text drives the tooltip on the gallery card.
            bits = []
            if H_out:
                bits.append(f"|H| {g['abs_curvature_p50_nm-1']:.4f} is "
                            f"{rh:.2f}× the {region} {prep} median "
                            f"({medH:.4f}, n={len(group)})")
            if d_out:
                bits.append(f"|d| {g['abs_deviation_p50_nm']:.2f} nm is "
                            f"{rd:.2f}× the {region} {prep} median "
                            f"({medD:.2f} nm, n={len(group)})")
            out[g["crop"]] = {
                "reason": "; ".join(bits),
                "channel": ch,
                "H_ratio": rh, "d_ratio": rd,
                "group_median_H": medH, "group_median_d": medD,
                "group_n": len(group),
                "tissue": tissue, "prep": prep, "region_group": region,
            }
    return out


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _fmt(v, fmt=".3g"):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "---"
    return format(v, fmt)


def latex_table_tissue(by_tissue: list[dict]) -> str:
    """LaTeX longtable summarizing per-tissue x prep medians of the per-crop
    median |H|, |d|, and gap, plus the bd-clip distribution."""
    by_tissue = sorted(by_tissue, key=lambda r: (r["tissue"], r["prep"]))
    rows = []
    for r in by_tissue:
        rows.append(" & ".join([
            r["tissue"], r["prep"], str(r["n_crops"]),
            f'{_fmt(r["abs_curvature_p50_nm-1_median"])} '
            f'[{_fmt(r["abs_curvature_p50_nm-1_iqr_lo"])}, '
            f'{_fmt(r["abs_curvature_p50_nm-1_iqr_hi"])}]',
            f'{_fmt(r["abs_deviation_p50_nm_median"])} '
            f'[{_fmt(r["abs_deviation_p50_nm_iqr_lo"])}, '
            f'{_fmt(r["abs_deviation_p50_nm_iqr_hi"])}]',
            f'{_fmt(r["gap_p50_nm_median"])} '
            f'[{_fmt(r["gap_p50_nm_iqr_lo"])}, '
            f'{_fmt(r["gap_p50_nm_iqr_hi"])}]',
            f'{_fmt(r["gap_bounded_frac_median"], ".2f")}',
        ]) + r" \\")
    return r"""\begin{table}[h]
\centering
\small
\caption{Per-tissue, per-fixation aggregate of the mesh-based membrane topology
metrics. Each cell reports the median across crops of the per-crop median
of the absolute scalar value, with [Q1, Q3] across crops; n is the number
of crops in that (tissue, prep) cell. bd-clip is the median across crops of
the boundary-uncertain fraction (see Methods).}
\label{tab:membrane-topology-tissue}
\begin{tabular}{llrcccc}
\hline
Tissue & Fixation & n & $|H|$ (1/nm) & $|d|$ (nm) & $g$ (nm) & bd-clip \\
\hline
""" + "\n".join(rows) + r"""
\hline
\end{tabular}
\end{table}"""


def latex_table_region(by_region: list[dict]) -> str:
    """LaTeX table for region-matched (Chem vs HPF) comparisons. Only region
    groups with at least one crop in each prep are included."""
    # Group by tissue+region, then split prep into columns.
    grouped: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for r in by_region:
        if not r["region_group"]:
            continue
        grouped[(r["tissue"], r["region_group"])][r["prep"]] = r
    rows = []
    for (tissue, region), preps in sorted(grouped.items()):
        chem, hpf = preps.get("Chemical"), preps.get("Rapid HPF")
        if not (chem and hpf):
            continue

        def cell(r, col):
            if r is None:
                return "---"
            return (f'{_fmt(r[col + "_median"])} '
                    f'[{_fmt(r[col + "_iqr_lo"])}, '
                    f'{_fmt(r[col + "_iqr_hi"])}]')
        rows.append(" & ".join([
            tissue, region,
            f"{chem['n_crops']}\\,/\\,{hpf['n_crops']}",
            cell(chem, "abs_curvature_p50_nm-1"),
            cell(hpf, "abs_curvature_p50_nm-1"),
            cell(chem, "abs_deviation_p50_nm"),
            cell(hpf, "abs_deviation_p50_nm"),
            cell(chem, "gap_p50_nm"),
            cell(hpf, "gap_p50_nm"),
        ]) + r" \\")
    return r"""\begin{table}[h]
\centering
\scriptsize
\caption{Region-matched Chemical vs Rapid-HPF comparison of the mesh-based
membrane topology metrics. Each entry reports the median across crops of the
per-crop median absolute scalar value, with [Q1, Q3] across crops; n shows
Chem/HPF crop counts. Region groups represented in only one prep are
omitted from this table (see per-tissue table for the full set).}
\label{tab:membrane-topology-region}
\begin{tabular}{llcccccc}
\hline
& & & \multicolumn{2}{c}{$|H|$ (1/nm)} & \multicolumn{2}{c}{$|d|$ (nm)} & \multicolumn{2}{c}{$g$ (nm)} \\
Tissue & Region group & n & Chem & HPF & Chem & HPF & Chem & HPF \\
\hline
""" + "\n".join(rows) + r"""
\hline
\end{tabular}
\end{table}"""


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    rows = [per_crop_stats(r) for r in manifest if "bin" in r]
    print(f"per-crop stats: {len(rows)} crops")

    by_tissue = aggregate(rows, ("tissue", "prep"))
    by_region = aggregate(rows, ("tissue", "region_group", "prep"))

    outliers = flag_outliers(rows)

    RESULTS_DIR.mkdir(exist_ok=True)
    write_csv(rows, RESULTS_DIR / "membrane_topology_per_crop.csv")
    write_csv(by_tissue, RESULTS_DIR / "membrane_topology_by_tissue.csv")
    write_csv(by_region, RESULTS_DIR / "membrane_topology_by_region.csv")
    (RESULTS_DIR / "topology_outliers.json").write_text(
        json.dumps(outliers, indent=1))

    tex_path = RESULTS_DIR / "membrane_topology_tables.tex"
    tex_path.write_text(
        "% Auto-generated by scripts/aggregate_topology_stats.py — do not edit.\n\n"
        + latex_table_tissue(by_tissue) + "\n\n"
        + latex_table_region(by_region) + "\n"
    )
    print(f"wrote: {tex_path}")
    # Also emit json for the HTML methods page to consume.
    (RESULTS_DIR / "membrane_topology_aggregates.json").write_text(
        json.dumps({"per_crop": rows, "by_tissue": by_tissue,
                    "by_region": by_region}, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
