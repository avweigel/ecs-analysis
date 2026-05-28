"""
Build a side-by-side sanity-check page for the anatomy-matched groups.

For each region group with both Chemical and HPF crops, lay out the Chem
crops in one column and the HPF crops in another. Each card has a small
EM/ECS thumbnail and a Neuroglancer link. Above each group is a summary
panel showing the effect sizes per metric, and a button to load all the
group's crops in one Neuroglancer view as togglable layers.

Output: out/ecs-handoff/sanity-check.html
Thumbnails: /nrs/cellmap/weigela/ecs-handoff/thumbs/<crop>.png (generated
separately on the cluster by tools/gen_thumbs.py).
"""
from __future__ import annotations

import csv
import json
import statistics
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "out" / "ecs-handoff" / "sanity-check.html"

DATA_BASE = "https://cellmap-vm1.int.janelia.org/nrs/data"
NG_BASE = "https://neuroglancer-demo.appspot.com/"
THUMBS_URL = "thumbs"  # relative to page

EM_ARRAY = {
    "jrc_mus-kidney":   "fibsem-uint8",
    "jrc_mus-kidney-4": "fibsem-uint16",
    "jrc_mus-heart-6":  "fibsem-uint16",
    "jrc_mus-heart-4":  "fibsem-uint16",
    "jrc_mus-liver":    "fibsem-uint8",
    "jrc_mus-liver-8":  "fibsem-uint16",
    "jrc_mus-cortex-2": "fibsem-uint16",
    "jrc_mus-cortex-3": "fibsem-int16",
    "jrc_mus-cortex-4": "fibsem-uint16",
}
EM_SHADER = {
    "jrc_mus-cortex-3": {"normalized": {"range": [1114, 884], "window": [-281, 1395]}},
}

GROUPS = [
    {
        "label": "Liver — Bile canaliculus",
        "subtitle": "Bile canaliculus between 2–3 hepatocytes",
        "crops": {
            "Chemical":  [("jrc_mus-liver", "crop1039"), ("jrc_mus-liver", "crop1040"), ("jrc_mus-liver", "crop1042")],
            "Rapid HPF": [("jrc_mus-liver-8", "crop1072"), ("jrc_mus-liver-8", "crop1073"),
                          ("jrc_mus-liver-8", "crop1074"), ("jrc_mus-liver-8", "crop1075")],
        },
    },
    {
        "label": "Liver — Hepatocyte lateral",
        "subtitle": "Intercellular space between hepatocyte lateral membranes",
        "crops": {
            "Chemical":  [("jrc_mus-liver", "crop1044")],
            "Rapid HPF": [("jrc_mus-liver-8", "crop1071"), ("jrc_mus-liver-8", "crop1124"),
                          ("jrc_mus-liver-8", "crop1125"), ("jrc_mus-liver-8", "crop1127")],
        },
    },
    {
        "label": "Kidney — Glomerular interstitium",
        "subtitle": "Interstitial space among fenestrated endothelium, podocytes, and basal membrane",
        "note": "crop1135 was newly annotated (KP) and is not yet in the analysis pipeline — its metric cells will show '—' until a cluster re-run picks it up.",
        "crops": {
            "Chemical":  [("jrc_mus-kidney", "crop1026"), ("jrc_mus-kidney", "crop1027")],
            "Rapid HPF": [("jrc_mus-kidney-4", "crop1134"), ("jrc_mus-kidney-4", "crop1135")],
        },
    },
    {
        "label": "Kidney — DCT base",
        "subtitle": "Base of distal convoluted tubule epithelium with basement lamina",
        "note": "Underpowered as of 2026-05-14: crop1032 was reclassified PCT base per the WP/KP annotation doc, so the Chemical side now has only crop1030. Comparable stats are not computed for n=1.",
        "crops": {
            "Chemical":  [("jrc_mus-kidney", "crop1030")],
            "Rapid HPF": [("jrc_mus-kidney-4", "crop1136"), ("jrc_mus-kidney-4", "crop1137"),
                          ("jrc_mus-kidney-4", "crop1144")],
        },
    },
    {
        "label": "Kidney — PCT lateral",
        "subtitle": "Lateral space between two apical epithelia of proximal convoluted tubule",
        "note": "n=1 vs n=1 — too few crops for formal stats; shown because the direction is unusual (HPF appears to have more ECS than Chem here, opposite to Liver).",
        "crops": {
            "Chemical":  [("jrc_mus-kidney", "crop1031")],
            "Rapid HPF": [("jrc_mus-kidney-4", "crop1138")],
        },
    },
]

PREP_COLOR = {"Chemical": "#f97316", "Rapid HPF": "#0ea5e9"}
PREP_LIGHT = {"Chemical": "#fed7aa", "Rapid HPF": "#bae6fd"}

# Headline metrics to show in the summary + per-crop card.
KEY_METRICS = [
    ("ECS %",        "volume_fraction", "ecs_fraction",         lambda v: f"{v*100:.1f}%",   100.0,  "higher = more extracellular space"),
    ("SA:V (1/nm)", "sa_v",            "sa_v_ecs_per_nm",      lambda v: f"{v:.4f}",        1.0,    "higher = more membrane per unit cell volume"),
    ("cells/μm³",    "sa_v",            "cell_density_per_um3", lambda v: f"{v:.2f}",        1.0,    "higher = denser packing of cells"),
    ("gap p50 (nm)", "voronoi_gap",     "percentiles_nm_p50",   lambda v: f"{v:.1f} nm",     1.0,    "median nearest-neighbor gap"),
]


def _load_csv(path: str, key: str = "crop") -> dict[str, dict]:
    with open(path) as f:
        return {r[key]: r for r in csv.DictReader(f)}


def _f(d: dict, k: str) -> float | None:
    v = d.get(k, "")
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def ng_url(dataset: str, crop: str) -> str:
    base = f"zarr://{DATA_BASE}/{dataset}/{dataset}.zarr/recon-1"
    em = f"{base}/em/{EM_ARRAY[dataset]}"
    gt = f"{base}/labels/groundtruth/{crop}"
    em_layer = {"type": "image", "source": em, "name": "em"}
    if dataset in EM_SHADER:
        em_layer["shaderControls"] = EM_SHADER[dataset]
        em_layer["tab"] = "rendering"
    state = {
        "layers": [em_layer,
            {"type": "segmentation", "source": f"{gt}/all", "name": "all"},
            {"type": "segmentation", "source": f"{gt}/cell", "name": "cell", "visible": False},
            {"type": "segmentation", "source": f"{gt}/ecs",  "name": "ecs",  "visible": False},
            {"type": "segmentation", "source": f"{gt}/bm",   "name": "bm",   "visible": False},
        ],
        "selectedLayer": {"layer": "em"}, "layout": "4panel",
    }
    return NG_BASE + "#!" + urllib.parse.quote(json.dumps(state, separators=(",", ":")), safe="")


def ng_url_group(group_label: str, crops_by_prep: dict[str, list[tuple[str, str]]]) -> str:
    """All crops in one viewer. Each crop becomes its own ecs+cell layer pair,
    prefixed with prep + crop ID so it's clear which is which."""
    # Use first crop's EM as the base image. Different crops in the same group
    # share a coordinate system only within their own dataset; this is just for
    # quick visual cycling so we accept some misalignment.
    layers: list[dict] = []
    first_added = False
    for prep, crops in crops_by_prep.items():
        for dataset, crop in crops:
            base = f"zarr://{DATA_BASE}/{dataset}/{dataset}.zarr/recon-1"
            em = f"{base}/em/{EM_ARRAY[dataset]}"
            gt = f"{base}/labels/groundtruth/{crop}"
            short = "Chem" if prep == "Chemical" else "HPF"
            em_layer = {"type": "image", "source": em, "name": f"em_{short}_{crop}", "visible": not first_added}
            if dataset in EM_SHADER:
                em_layer["shaderControls"] = EM_SHADER[dataset]
                em_layer["tab"] = "rendering"
            layers.append(em_layer)
            layers.append({"type": "segmentation", "source": f"{gt}/ecs",
                           "name": f"ecs_{short}_{crop}", "visible": not first_added})
            first_added = True
    state = {"layers": layers, "selectedLayer": {"layer": layers[0]["name"]}, "layout": "4panel"}
    return NG_BASE + "#!" + urllib.parse.quote(json.dumps(state, separators=(",", ":")), safe="")


def _dot_plot_svg(values_chem: list[float], values_hpf: list[float],
                  highlight_value: float | None = None,
                  highlight_prep: str | None = None) -> str:
    """Inline SVG: horizontal axis showing values, Chem dots above HPF dots
    (or all together), the highlighted crop is bigger and ringed."""
    all_vals = [v for v in values_chem + values_hpf if v is not None]
    if not all_vals:
        return ""
    lo, hi = min(all_vals), max(all_vals)
    if hi == lo:
        hi = lo + 1
    width = 240
    height = 38
    pad = 8
    axis_y = height - 12

    def x_of(v):
        return pad + (v - lo) / (hi - lo) * (width - 2 * pad)

    parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" class="dot-plot">']
    parts.append(f'<line x1="{pad}" y1="{axis_y}" x2="{width - pad}" y2="{axis_y}" stroke="#cbd5e1" stroke-width="1"/>')
    # Chem dots (above axis)
    for v in values_chem:
        if v is None:
            continue
        is_hi = (highlight_value is not None and abs(v - highlight_value) < 1e-9 and highlight_prep == "Chemical")
        r = 4 if is_hi else 3
        stroke = '#7c2d12' if is_hi else 'none'
        parts.append(f'<circle cx="{x_of(v):.1f}" cy="{axis_y - 6}" r="{r}" fill="{PREP_COLOR["Chemical"]}" stroke="{stroke}" stroke-width="1.5"/>')
    # HPF dots (below axis)
    for v in values_hpf:
        if v is None:
            continue
        is_hi = (highlight_value is not None and abs(v - highlight_value) < 1e-9 and highlight_prep == "Rapid HPF")
        r = 4 if is_hi else 3
        stroke = '#0c4a6e' if is_hi else 'none'
        parts.append(f'<circle cx="{x_of(v):.1f}" cy="{axis_y + 6}" r="{r}" fill="{PREP_COLOR["Rapid HPF"]}" stroke="{stroke}" stroke-width="1.5"/>')
    parts.append(f'<text x="{pad}" y="{height - 1}" font-size="9" fill="#9ca3af">{lo:.3g}</text>')
    parts.append(f'<text x="{width - pad}" y="{height - 1}" font-size="9" fill="#9ca3af" text-anchor="end">{hi:.3g}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def _summary_panel(label: str, metric_col: str, metric_table: str,
                   chem_vals: list[float], hpf_vals: list[float],
                   higher_better_desc: str) -> str:
    """Per-metric mini comparison block: medians, ratio, dot plot."""
    if not chem_vals or not hpf_vals:
        return ""
    c_med = statistics.median(chem_vals)
    h_med = statistics.median(hpf_vals)
    ratio = c_med / h_med if h_med else float("inf")
    direction = "C&gt;H" if c_med > h_med else "H&gt;C"
    arrow_color = "#16a34a" if c_med > h_med else "#0284c7"
    return f"""
<div class="metric-summary">
  <div class="ms-name">{label}</div>
  <div class="ms-medians">
    <span class="med-chem">Chem {c_med:.4g}</span>
    <span class="med-arrow" style="color:{arrow_color}">{direction}</span>
    <span class="med-hpf">HPF {h_med:.4g}</span>
    <span class="med-ratio">×{ratio:.2f}</span>
  </div>
  {_dot_plot_svg(chem_vals, hpf_vals)}
  <div class="ms-note">{higher_better_desc}</div>
</div>"""


def _build_overview_tables(volume_fraction: dict) -> str:
    """Build the per-region / per-tissue ECS% summary tables that go at the
    top of the page. Pulls from crop_annotations.csv and the
    native_volume_fraction.csv results dict."""
    import statistics
    from collections import defaultdict

    anno = {}
    with open(REPO_ROOT / "crop_annotations.csv", newline="") as f:
        for row in csv.DictReader(f):
            anno[row["crop"]] = row

    ecs_by_crop = {c: float(r["ecs_fraction"]) for c, r in volume_fraction.items()}

    groups: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(lambda: {"Chemical": [], "Rapid HPF": []})
    tissue_of_region: dict[str, str] = {}
    for crop, frac in ecs_by_crop.items():
        r = anno.get(crop, {})
        rg = (r.get("region_group") or "").strip()
        prep = (r.get("prep") or "").strip()
        tissue = (r.get("tissue") or "").strip()
        if rg and prep:
            groups[rg][prep].append((crop, frac))
            tissue_of_region[rg] = tissue

    tissue_groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"Chemical": [], "Rapid HPF": []})
    for crop, frac in ecs_by_crop.items():
        prep = (anno.get(crop, {}).get("prep") or "").strip()
        # Pull tissue directly from the volume_fraction row, since some
        # excluded-but-still-rendered crops may not have annotations.
        t = volume_fraction[crop].get("tissue", "")
        if prep and t:
            tissue_groups[t][prep].append(frac)

    matched_rows = []
    chem_only_rows = []
    for rg, d in groups.items():
        c, h = d["Chemical"], d["Rapid HPF"]
        t = tissue_of_region[rg]
        if c and h:
            cm = statistics.median(v for _, v in c) * 100
            hm = statistics.median(v for _, v in h) * 100
            ratio = cm / hm if hm > 0 else float("inf")
            direction = "Chem > HPF" if cm > hm else ("HPF > Chem" if hm > cm else "tie")
            matched_rows.append((t, rg, len(c), len(h), cm, hm, ratio, direction))
        elif c:
            cm = statistics.median(v for _, v in c) * 100
            chem_only_rows.append((t, rg, len(c), cm))

    # Sort: matched by direction (Chem>HPF first) then tissue/region for readability
    matched_rows.sort(key=lambda r: (r[0], r[1]))
    chem_only_rows.sort(key=lambda r: (r[0], r[1]))

    def fmt_ratio(c, h):
        if h == 0: return "—"
        return f"{c/h:.2f}x" if c >= h else f"{c/h:.2f}x"

    def direction_class(d):
        if "Chem > HPF" in d or "Chem >> HPF" in d: return "chem-dir"
        if "HPF > Chem" in d or "HPF >> Chem" in d: return "hpf-dir"
        return ""

    matched_html = "".join(
        f'<tr class="{direction_class(direction)}">'
        f'<td class="rg">{rg}</td><td>{t}</td>'
        f'<td class="num">{nc}</td><td class="num">{nh}</td>'
        f'<td class="num">{cm:.1f}%</td><td class="num">{hm:.1f}%</td>'
        f'<td class="num">{ratio:.2f}×</td>'
        f'<td>{direction}{" (n=1)" if (nc==1 or nh==1) else ""}</td>'
        f'</tr>'
        for t, rg, nc, nh, cm, hm, ratio, direction in matched_rows
    )

    chem_html = "".join(
        f'<tr><td class="rg">{rg}</td><td>{t}</td><td class="num">{n}</td><td class="num">{cm:.1f}%</td></tr>'
        for t, rg, n, cm in chem_only_rows
    )

    tissue_html_rows = []
    for t in ["Liver", "Kidney", "Cortex", "Heart"]:
        c = tissue_groups[t]["Chemical"]; h = tissue_groups[t]["Rapid HPF"]
        if not c:
            continue
        cm = statistics.median(c) * 100
        if h:
            hm = statistics.median(h) * 100
            ratio = cm / hm if hm > 0 else float("inf")
            direction = "Chem > HPF" if cm > hm else "HPF > Chem"
            cls = direction_class(direction)
            tissue_html_rows.append(
                f'<tr class="{cls}"><td class="rg">{t}</td>'
                f'<td class="num">{len(c)}</td><td class="num">{len(h)}</td>'
                f'<td class="num">{cm:.1f}%</td><td class="num">{hm:.1f}%</td>'
                f'<td class="num">{ratio:.2f}×</td><td>{direction}</td></tr>'
            )
        else:
            tissue_html_rows.append(
                f'<tr><td class="rg">{t}</td>'
                f'<td class="num">{len(c)}</td><td class="num">0</td>'
                f'<td class="num">{cm:.1f}%</td><td class="num">—</td>'
                f'<td class="num">—</td><td>(no HPF data)</td></tr>'
            )
    tissue_html = "".join(tissue_html_rows)

    return f"""
<section class="overview">
  <h2>ECS % at a glance</h2>
  <p class="overview-sub">
    Each table shows median ECS volume fraction. Rows are colored by direction:
    <span class="legend-pill chem-dir">Chem &gt; HPF</span>
    <span class="legend-pill hpf-dir">HPF &gt; Chem</span>
  </p>

  <h3>Matched anatomy — both Chemical and Rapid HPF crops available</h3>
  <table class="overview-tbl">
    <thead><tr><th>Region</th><th>Tissue</th><th>n_C</th><th>n_H</th><th>Chem ECS%</th><th>HPF ECS%</th><th>Ratio</th><th>Direction</th></tr></thead>
    <tbody>{matched_html}</tbody>
  </table>

  <h3>Chemical-only regions <span class="dim">(no HPF crop annotated yet for these regions)</span></h3>
  <table class="overview-tbl">
    <thead><tr><th>Region</th><th>Tissue</th><th>n</th><th>Chem ECS%</th></tr></thead>
    <tbody>{chem_html}</tbody>
  </table>

  <h3>Tissue-level pooled <span class="dim">(all crops in that tissue, regardless of region)</span></h3>
  <table class="overview-tbl">
    <thead><tr><th>Tissue</th><th>n_C</th><th>n_H</th><th>Chem ECS%</th><th>HPF ECS%</th><th>Ratio</th><th>Direction</th></tr></thead>
    <tbody>{tissue_html}</tbody>
  </table>

  <p class="takeaway">
    <strong>One-paragraph read:</strong>
    In <strong>Liver</strong>, Chem leans toward more ECS (tissue ECS ~4.6×, but
    only borderline: Cliff +0.47, p=0.07; SA:V stays significant, +0.55, p=0.03).
    The bile canaliculus matched comparison is the cleanest signal (Chem &gt; HPF
    cell density, p≈0.05). Note: hepatocyte lateral is now 6-vs-6 and null —
    the earlier strong lateral result rested on a single Chemical crop.
    In <strong>Kidney</strong>, the tissue-level Chem &gt; HPF holds (2.8×),
    but the matched anatomy splits: DCT base goes Chem &gt; HPF; Glomerular and
    PCT lateral go the opposite direction (HPF more ECS).
    In <strong>Cortex</strong>, both the tissue level and the matched signal lean HPF &gt; Chem,
    though sample sizes are small (only 2 HPF crops).
    <strong>Heart</strong> now has an HPF arm (4 vs 4): no significant Chem-vs-HPF
    difference at tissue level, and region-matched groups are only 2-vs-2
    (underpowered). The clearest, best-powered story is Liver bile canaliculus.
  </p>
</section>"""


def main() -> None:
    csvs = {
        "volume_fraction": _load_csv("results/native_volume_fraction.csv"),
        "sa_v":            _load_csv("results/native_sa_v.csv"),
        "ecs_width":       _load_csv("results/native_ecs_width.csv"),
        "voronoi_gap":     _load_csv("results/native_voronoi_gap.csv"),
    }

    def get(crop: str, table: str, col: str) -> float | None:
        return _f(csvs[table].get(crop, {}), col)

    def group_summary(grp: dict) -> str:
        chem_crops = [c for _, c in grp["crops"]["Chemical"]]
        hpf_crops  = [c for _, c in grp["crops"]["Rapid HPF"]]
        panels = []
        for name, table, col, fmt, mul, note in KEY_METRICS:
            cv = [get(c, table, col) for c in chem_crops]
            cv = [v for v in cv if v is not None]
            hv = [get(c, table, col) for c in hpf_crops]
            hv = [v for v in hv if v is not None]
            panels.append(_summary_panel(name, col, table, cv, hv, note))
        return f'<div class="summary-row">{"".join(panels)}</div>'

    def crop_card(dataset: str, crop: str, prep: str, group_crops: dict) -> str:
        prep_color = PREP_COLOR[prep]
        # Per-metric mini values + position of this crop in dot plot
        chem_crops = [c for _, c in group_crops["Chemical"]]
        hpf_crops  = [c for _, c in group_crops["Rapid HPF"]]

        metric_rows = []
        for name, table, col, fmt, mul, note in KEY_METRICS:
            this_val = get(crop, table, col)
            cv = [get(c, table, col) for c in chem_crops]
            hv = [get(c, table, col) for c in hpf_crops]
            cv = [v for v in cv if v is not None]
            hv = [v for v in hv if v is not None]
            val_str = fmt(this_val) if this_val is not None else "—"
            dot = _dot_plot_svg(cv, hv, highlight_value=this_val, highlight_prep=prep)
            metric_rows.append(f"""
<div class="crop-metric">
  <div class="cm-name">{name}</div>
  <div class="cm-value">{val_str}</div>
  <div class="cm-dot">{dot}</div>
</div>""")

        return f"""
<div class="crop-card" style="--prep:{prep_color}">
  <a class="thumb-link" href="{ng_url(dataset, crop)}" target="_blank" rel="noopener" title="Open in Neuroglancer">
    <img class="thumb" src="{THUMBS_URL}/{crop}.png" alt="{crop} thumbnail" loading="lazy"
         onerror="this.style.display='none'; this.nextElementSibling.style.display='block'">
    <div class="thumb-placeholder">(thumbnail rendering on cluster — refresh in a minute)</div>
    <div class="thumb-overlay">{crop} ↗</div>
  </a>
  <div class="crop-meta">{dataset}</div>
  <div class="crop-metrics">{"".join(metric_rows)}</div>
</div>"""

    def _sorted_crops(crops: list[tuple[str, str]]) -> list[tuple[float, str, str]]:
        out = []
        for ds, c in crops:
            v = get(c, "volume_fraction", "ecs_fraction") or 0
            out.append((v, ds, c))
        out.sort(key=lambda x: -x[0])
        return out

    def _empty_card(prep: str, reason: str) -> str:
        prep_color = PREP_COLOR[prep]
        return f"""
<div class="crop-card empty-card" style="--prep:{prep_color}">
  <div class="empty-msg">No {prep} crop<br>at this rank</div>
</div>"""

    def pair_rows(grp: dict) -> str:
        chem_sorted = _sorted_crops(grp["crops"]["Chemical"])
        hpf_sorted  = _sorted_crops(grp["crops"]["Rapid HPF"])
        n_rows = max(len(chem_sorted), len(hpf_sorted))
        rows = []
        for i in range(n_rows):
            rank_label = f"Pair {i + 1}"
            if i == 0:
                rank_label += " · highest ECS"
            elif i == n_rows - 1 and n_rows > 1:
                rank_label += " · lowest ECS"
            if i < len(chem_sorted):
                _, ds, c = chem_sorted[i]
                chem_html = crop_card(ds, c, "Chemical", grp["crops"])
            else:
                chem_html = _empty_card("Chemical", "no match")
            if i < len(hpf_sorted):
                _, ds, c = hpf_sorted[i]
                hpf_html = crop_card(ds, c, "Rapid HPF", grp["crops"])
            else:
                hpf_html = _empty_card("Rapid HPF", "no match")
            rows.append(f"""
<div class="pair-row">
  <div class="pair-label">{rank_label}</div>
  <div class="pair-side">{chem_html}</div>
  <div class="pair-vs">vs</div>
  <div class="pair-side">{hpf_html}</div>
</div>""")
        return "".join(rows)

    def group_section(grp: dict) -> str:
        all_ng = ng_url_group(grp["label"], grp["crops"])
        n_chem = len(grp["crops"]["Chemical"])
        n_hpf  = len(grp["crops"]["Rapid HPF"])
        note_html = ""
        if grp.get("note"):
            note_html = f'<div class="group-note">⚠ {grp["note"]}</div>'
        return f"""
<section class="group">
  <header class="group-header">
    <div class="gh-left">
      <h2>{grp['label']}</h2>
      <div class="group-sub">{grp['subtitle']}</div>
    </div>
    <a class="all-in-one" href="{all_ng}" target="_blank" rel="noopener" title="Open all crops in this group as togglable layers in a single Neuroglancer viewer">↗ All crops in one viewer</a>
  </header>
  {note_html}
  {group_summary(grp)}
  <div class="pair-header">
    <div class="ph-label">Rank</div>
    <div class="ph-chem" style="color:{PREP_COLOR['Chemical']}">Chemical · n = {n_chem}</div>
    <div class="ph-vs"></div>
    <div class="ph-hpf"  style="color:{PREP_COLOR['Rapid HPF']}">Rapid HPF · n = {n_hpf}</div>
  </div>
  {pair_rows(grp)}
</section>"""

    sections_html = "\n".join(group_section(g) for g in GROUPS)
    overview_html = _build_overview_tables(csvs["volume_fraction"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ECS sanity check — Chem vs HPF, matched regions</title>
<style>
  :root {{ --bg: #fafafa; --card: white; --border: #e5e7eb; --text: #1f2937; --muted: #6b7280; }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); margin: 0; color: var(--text); font-family: -apple-system, system-ui, sans-serif; line-height: 1.5; }}
  .container {{ max-width: 1500px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 0.3rem; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); font-size: 0.95rem; margin-bottom: 1.25rem; }}
  .back {{ display: inline-block; margin-bottom: 1rem; color: #2563eb; text-decoration: none; font-size: 0.9rem; }}
  .back:hover {{ text-decoration: underline; }}

  .legend {{
    background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px;
    padding: 0.9rem 1.1rem; margin-bottom: 1.5rem; font-size: 0.9rem;
    display: flex; flex-wrap: wrap; gap: 1.2rem; align-items: center;
  }}
  .legend .swatch {{
    display: inline-block; width: 12px; height: 12px; border-radius: 50%;
    margin-right: 0.4rem; vertical-align: middle;
  }}

  section.group {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    margin-bottom: 1.8rem; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .group-header {{
    padding: 0.95rem 1.2rem; border-bottom: 1px solid var(--border);
    background: linear-gradient(to right, #f9fafb, white 60%);
    display: flex; justify-content: space-between; align-items: center; gap: 1rem;
  }}
  .group-header h2 {{ margin: 0; font-size: 1.15rem; }}
  .group-sub {{ color: var(--muted); font-size: 0.86rem; margin-top: 0.15rem; }}
  .group-note {{
    background: #fef3c7; border-left: 4px solid #f59e0b;
    padding: 0.55rem 1rem; font-size: 0.85rem; color: #78350f;
    border-bottom: 1px solid var(--border);
  }}
  .all-in-one {{
    background: #1f2937; color: white; padding: 0.45rem 0.85rem; border-radius: 6px;
    text-decoration: none; font-size: 0.85rem; font-weight: 600; white-space: nowrap;
  }}
  .all-in-one:hover {{ background: #111827; }}

  /* Summary panel */
  .summary-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.75rem; padding: 1rem 1.2rem; background: #f9fafb;
    border-bottom: 1px solid var(--border);
  }}
  .metric-summary {{
    background: white; border: 1px solid var(--border); border-radius: 6px;
    padding: 0.6rem 0.7rem;
  }}
  .ms-name {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }}
  .ms-medians {{ display: flex; align-items: baseline; gap: 0.4rem; flex-wrap: wrap; font-size: 0.85rem; margin: 0.25rem 0 0.25rem; }}
  .med-chem {{ color: {PREP_COLOR['Chemical']}; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .med-hpf  {{ color: {PREP_COLOR['Rapid HPF']}; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .med-arrow {{ font-size: 0.78rem; font-weight: 600; }}
  .med-ratio {{ margin-left: auto; color: #4b5563; font-weight: 600; }}
  .dot-plot {{ display: block; margin: 0.1rem 0; }}
  .ms-note {{ color: var(--muted); font-size: 0.75rem; }}

  /* Paired-row layout: [rank label] [Chem card] [vs] [HPF card] */
  .pair-header {{
    display: grid; grid-template-columns: 5rem 1fr 2.5rem 1fr; gap: 0.8rem;
    padding: 0.7rem 1.2rem; background: #f3f4f6; border-bottom: 1px solid var(--border);
    font-size: 0.78rem; letter-spacing: 0.05em; text-transform: uppercase; font-weight: 700;
  }}
  .ph-label {{ color: var(--muted); }}
  .ph-chem, .ph-hpf {{ text-align: center; }}
  .pair-row {{
    display: grid; grid-template-columns: 5rem 1fr 2.5rem 1fr; gap: 0.8rem;
    padding: 0.85rem 1.2rem; align-items: stretch;
    border-bottom: 1px solid #f1f5f9;
  }}
  .pair-row:last-child {{ border-bottom: none; }}
  .pair-label {{
    display: flex; align-items: center; color: var(--muted);
    font-size: 0.8rem; font-weight: 600; line-height: 1.3;
  }}
  .pair-side {{ display: flex; }}
  .pair-side .crop-card {{ flex: 1; margin-bottom: 0; }}
  .pair-vs {{
    display: flex; align-items: center; justify-content: center;
    color: #94a3b8; font-weight: 700; font-size: 0.95rem;
  }}
  .empty-card {{
    flex: 1; min-height: 200px;
    background: #f9fafb; border: 1px dashed #d1d5db; border-left: 3px dashed var(--prep);
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }}
  .empty-msg {{ color: #9ca3af; font-size: 0.85rem; text-align: center; line-height: 1.4; }}

  /* Crop card */
  .crop-card {{
    background: white; border: 1px solid var(--border); border-left: 3px solid var(--prep);
    border-radius: 6px; padding: 0; margin-bottom: 0.8rem; overflow: hidden;
  }}
  .thumb-link {{ display: block; position: relative; text-decoration: none; background: #111; aspect-ratio: 1; }}
  .thumb {{ width: 100%; height: 100%; display: block; object-fit: cover; }}
  .thumb-placeholder {{
    display: none; position: absolute; inset: 0; align-items: center; justify-content: center;
    background: #f3f4f6; color: var(--muted); font-size: 0.8rem; text-align: center; padding: 1rem;
  }}
  .thumb-overlay {{
    position: absolute; bottom: 0.4rem; left: 0.4rem;
    background: rgba(0,0,0,0.7); color: white; padding: 0.15rem 0.5rem;
    border-radius: 4px; font-family: ui-monospace, monospace; font-size: 0.82rem; font-weight: 600;
  }}
  .crop-meta {{
    font-family: ui-monospace, monospace; font-size: 0.7rem; color: var(--muted);
    padding: 0.35rem 0.7rem 0; text-align: right;
  }}
  .crop-metrics {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; padding: 0.45rem 0.7rem 0.6rem;
  }}
  .crop-metric {{ font-size: 0.8rem; line-height: 1.2; }}
  .cm-name {{ color: var(--muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  .cm-value {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
  .cm-dot {{ height: 18px; }}
  .cm-dot svg {{ width: 100%; height: 18px; }}

  @media (max-width: 900px) {{
    .pair-header {{ grid-template-columns: 4rem 1fr 1.5rem 1fr; padding: 0.5rem 0.8rem; font-size: 0.7rem; }}
    .pair-row    {{ grid-template-columns: 4rem 1fr 1.5rem 1fr; gap: 0.4rem; padding: 0.6rem 0.8rem; }}
    .pair-label  {{ font-size: 0.72rem; }}
  }}

  /* Overview tables */
  section.overview {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 1.2rem 1.4rem 1.3rem; margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  section.overview h2 {{ margin: 0 0 0.3rem; font-size: 1.25rem; }}
  section.overview h3 {{
    margin: 1.2rem 0 0.5rem; font-size: 0.9rem;
    color: var(--text); font-weight: 700;
  }}
  section.overview h3 .dim {{ color: var(--muted); font-weight: 500; font-size: 0.85rem; }}
  .overview-sub {{ color: var(--muted); margin: 0 0 0.6rem; font-size: 0.9rem; }}
  .legend-pill {{
    display: inline-block; padding: 0.05rem 0.5rem; border-radius: 4px;
    font-size: 0.78rem; font-weight: 700; margin-left: 0.3rem;
  }}
  .legend-pill.chem-dir {{ background: #fed7aa; color: #9a3412; }}
  .legend-pill.hpf-dir  {{ background: #bae6fd; color: #075985; }}
  .overview-tbl {{
    width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-bottom: 0.7rem;
  }}
  .overview-tbl th {{
    text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--muted); padding: 0.45rem 0.7rem; border-bottom: 1px solid var(--border);
    background: #f9fafb;
  }}
  .overview-tbl td {{
    padding: 0.5rem 0.7rem; border-bottom: 1px solid #f1f3f5;
  }}
  .overview-tbl tr:last-child td {{ border-bottom: none; }}
  .overview-tbl tr.chem-dir td {{ background: #fff7ed; }}
  .overview-tbl tr.hpf-dir  td {{ background: #f0f9ff; }}
  .overview-tbl td.rg {{ font-weight: 600; }}
  .overview-tbl td.num {{ font-variant-numeric: tabular-nums; }}
  .takeaway {{
    background: #f3f4f6; border-left: 4px solid #6b7280;
    padding: 0.7rem 1rem; margin-top: 1rem; border-radius: 6px;
    font-size: 0.92rem; line-height: 1.6;
  }}
</style>
</head>
<body>
<div class="container">
<a class="back" href="index.html">← Back to crops index</a>
<h1>Sanity check — anatomy-matched Chem vs HPF</h1>
<div class="subtitle">Side-by-side images, numbers and Neuroglancer links so you can visually verify whether the Chem &gt; HPF finding survives at the per-crop level.</div>

{overview_html}

<div class="legend">
  <span><span class="swatch" style="background:{PREP_COLOR['Chemical']}"></span><strong>Chemical</strong> (orange)</span>
  <span><span class="swatch" style="background:{PREP_COLOR['Rapid HPF']}"></span><strong>Rapid HPF</strong> (cyan)</span>
  <span>Each <strong>thumbnail</strong> is a mid-Z slice: <span style="background:rgba(0,217,242,0.55); padding:0 0.4rem;">cyan tint</span> = ECS overlay.</span>
  <span><strong>Dot plot</strong> = all crops in the group along the metric axis (Chem on top, HPF on bottom).</span>
  <span><strong>↗ All crops in one viewer</strong> loads every crop of the group as togglable layers in a single Neuroglancer tab.</span>
  <span>Crops are paired by <strong>rank within their prep</strong> (sorted by ECS%): the rank-1 Chem crop sits next to the rank-1 HPF crop, etc. Pairing is by rank, not by anatomical sub-feature.</span>
</div>

{sections_html}

</div>
</body>
</html>
"""
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
