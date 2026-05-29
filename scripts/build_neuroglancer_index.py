"""
Build a self-contained HTML index of all ECS-analysis crops with embedded
Neuroglancer viewer-state links.

Produces:
  out/index.html          -- table of crops with metadata + NG link
  out/states/<crop>.json  -- per-crop neuroglancer viewer state

Designed to be rsync'd to /nrs/cellmap/weigela/ecs-handoff/ on the cluster,
which is served at https://cellmap-vm1.int.janelia.org/nrs/cellmap/weigela/ecs-handoff/.

Usage:
    python scripts/build_neuroglancer_index.py
"""
from __future__ import annotations

import csv
import json
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from ecs.config import active_crops, CROPS

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "out" / "ecs-handoff"
STATES_DIR = OUT_DIR / "states"

# cellmap-vm1 strips a leading `cellmap/` from `/nrs/cellmap/<X>` filesystem
# paths and serves them at URL `/nrs/<X>`. So filesystem path
# `/nrs/cellmap/weigela/ecs-handoff/...` is served at
# `https://cellmap-vm1.int.janelia.org/nrs/weigela/ecs-handoff/...`.
WEB_BASE = "https://cellmap-vm1.int.janelia.org/nrs/weigela/ecs-handoff"
DATA_BASE = "https://cellmap-vm1.int.janelia.org/nrs/data"

NEUROGLANCER_BASE = "https://neuroglancer-demo.appspot.com/"

# EM array name per dataset (varies: uint8, uint16, int16).
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

# Native voxel size per dataset (nm).
DATASET_VOXEL_NM = {
    "jrc_mus-kidney":   4,
    "jrc_mus-kidney-4": 8,
    "jrc_mus-heart-6":  8,
    "jrc_mus-heart-4":  8,
    "jrc_mus-liver":    4,
    "jrc_mus-liver-8":  8,
    "jrc_mus-cortex-2": 8,
    "jrc_mus-cortex-3": 2,
    "jrc_mus-cortex-4": 8,
}

# Display order for dataset sections.
DATASET_ORDER = [
    "jrc_mus-cortex-3",   # Cortex Chem 2nm
    "jrc_mus-cortex-2",   # Cortex HPF 8nm
    "jrc_mus-cortex-4",   # Cortex HPF 8nm
    "jrc_mus-heart-6",    # Heart Chem 8nm
    "jrc_mus-heart-4",    # Heart HPF 8nm
    "jrc_mus-kidney",     # Kidney Chem 4nm
    "jrc_mus-kidney-4",   # Kidney HPF 8nm
    "jrc_mus-liver",      # Liver Chem 4nm
    "jrc_mus-liver-8",    # Liver HPF 8nm
]

# Per-dataset EM rendering / LUT overrides. Values supplied by AW after
# tuning in neuroglancer. If a dataset isn't listed, no shaderControls
# are injected and NG picks its own auto-range.
EM_SHADER_CONTROLS: dict[str, dict] = {
    "jrc_mus-cortex-3": {
        "normalized": {"range": [1114, 884], "window": [-281, 1395]},
    },
}

# Per-tissue accent color (used for dataset header band and tissue chip).
TISSUE_COLOR = {
    "Cortex": "#3b82f6",   # blue
    "Heart":  "#ef4444",   # red
    "Kidney": "#f59e0b",   # amber
    "Liver":  "#84cc16",   # green
}

# Per-prep chip color.
PREP_COLOR = {
    "Chemical":  "#f97316",  # orange (warm = chemical fixation)
    "Rapid HPF": "#0ea5e9",  # cyan  (cool = freezing)
}

# Crops on the zarr filesystem but not yet in ecs/config.py — surfaced in
# this session. Tissue + prep guessed from dataset name; anatomy left blank
# pending KP annotation.
NEW_CROPS: list[tuple[str, str, str, str]] = [
    # (dataset, crop, tissue, prep)
    ("jrc_mus-kidney-4", "crop1135", "Kidney", "Rapid HPF"),
    ("jrc_mus-heart-6",  "crop1148", "Heart",  "Chemical"),
    ("jrc_mus-liver",    "crop1118", "Liver",  "Chemical"),
    ("jrc_mus-liver",    "crop1119", "Liver",  "Chemical"),
    ("jrc_mus-liver",    "crop1120", "Liver",  "Chemical"),
    ("jrc_mus-liver",    "crop1121", "Liver",  "Chemical"),
    ("jrc_mus-liver",    "crop1122", "Liver",  "Chemical"),
    ("jrc_mus-cortex-4", "crop1140", "Cortex", "Rapid HPF"),
    ("jrc_mus-cortex-4", "crop1142", "Cortex", "Rapid HPF"),
    ("jrc_mus-cortex-4", "crop1143", "Cortex", "Rapid HPF"),
]


@dataclass
class CropEntry:
    crop: str
    dataset: str
    tissue: str
    prep: str
    anatomy: str | None
    region_group: str | None
    annotation: str | None
    is_new: bool
    excluded: bool = False
    exclude_reason: str = ""


def _load_annotations() -> dict[str, dict]:
    """Return {crop: full_row_dict} from crop_annotations.csv."""
    out = {}
    path = REPO_ROOT / "crop_annotations.csv"
    if not path.exists():
        return out
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            crop = row.get("crop", "").strip()
            if crop:
                out[crop] = row
    return out


def _build_entries() -> list[CropEntry]:
    """Compile the full crop list: active crops from config + any filesystem-only NEW_CROPS."""
    anno = _load_annotations()
    entries: list[CropEntry] = []
    seen: set[str] = set()
    for c in CROPS:  # all crops; we visually mark excluded ones
        row = anno.get(c.crop, {})
        entries.append(CropEntry(
            crop=c.crop, dataset=c.dataset, tissue=c.tissue, prep=c.prep,
            anatomy=row.get("anatomical_region") or None,
            region_group=row.get("region_group") or None,
            annotation=row.get("annotation") or None,
            is_new=False,
            excluded=c.exclude,
            exclude_reason=c.exclude_reason,
        ))
        seen.add(c.crop)
    for dataset, crop, tissue, prep in NEW_CROPS:
        if crop in seen:
            continue
        row = anno.get(crop, {})
        entries.append(CropEntry(
            crop=crop, dataset=dataset, tissue=tissue, prep=prep,
            anatomy=row.get("anatomical_region") or None,
            region_group=row.get("region_group") or None,
            annotation=row.get("annotation") or None,
            is_new=True,
        ))
    # Sort by tissue, prep, crop id (numeric tail)
    def _key(e: CropEntry):
        try:
            num = int("".join(ch for ch in e.crop if ch.isdigit()))
        except ValueError:
            num = 0
        return (e.tissue, e.prep, num)
    entries.sort(key=_key)
    return entries


def _viewer_state(e: CropEntry) -> dict:
    """Build a Neuroglancer viewer-state dict for one crop."""
    base = f"zarr://{DATA_BASE}/{e.dataset}/{e.dataset}.zarr/recon-1"
    em_url = f"{base}/em/{EM_ARRAY[e.dataset]}"
    gt_base = f"{base}/labels/groundtruth/{e.crop}"
    em_layer: dict = {
        "type": "image",
        "source": em_url,
        "name": "em",
    }
    if e.dataset in EM_SHADER_CONTROLS:
        em_layer["shaderControls"] = EM_SHADER_CONTROLS[e.dataset]
        em_layer["tab"] = "rendering"
    return {
        "layers": [
            em_layer,
            {
                "type": "segmentation",
                "source": f"{gt_base}/all",
                "name": "all",
            },
            {
                "type": "segmentation",
                "source": f"{gt_base}/cell",
                "name": "cell",
                "visible": False,
            },
            {
                "type": "segmentation",
                "source": f"{gt_base}/ecs",
                "name": "ecs",
                "visible": False,
            },
            {
                "type": "segmentation",
                "source": f"{gt_base}/bm",
                "name": "bm",
                "visible": False,
            },
        ],
        "selectedLayer": {"layer": "em"},
        "layout": "4panel",
    }


def _attr_escape(s: str) -> str:
    """Minimal HTML attribute escape for data-* values."""
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _cell_render(s: str) -> str:
    """Render an editable-cell body: text or em-dash placeholder."""
    if not s:
        return '<span class="missing">—</span>'
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _neuroglancer_url_inline(state: dict) -> str:
    """Build an NG URL with the state inlined as URL-encoded JSON in the
    fragment. Robust across NG instances; works without a state server."""
    # Compact JSON keeps the URL short.
    s = json.dumps(state, separators=(",", ":"))
    # Quote everything except a small safe set — NG handles standard escapes.
    return NEUROGLANCER_BASE + "#!" + urllib.parse.quote(s, safe="")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATES_DIR.mkdir(parents=True, exist_ok=True)

    entries = _build_entries()
    print(f"Building index for {len(entries)} crops ({sum(e.is_new for e in entries)} new)")

    # Write per-crop state JSONs
    for e in entries:
        state = _viewer_state(e)
        (STATES_DIR / f"{e.crop}.json").write_text(json.dumps(state, indent=2))

    # Group entries by dataset, in the configured display order. Dataset
    # ordering puts each tissue's Chemical → HPF datasets together.
    by_dataset: dict[str, list[CropEntry]] = {}
    for e in entries:
        by_dataset.setdefault(e.dataset, []).append(e)

    ordered_datasets = [d for d in DATASET_ORDER if d in by_dataset]
    # Anything not in the predefined order, append at the end (future-proof).
    for d in by_dataset:
        if d not in ordered_datasets:
            ordered_datasets.append(d)

    sections_html: list[str] = []
    for dataset in ordered_datasets:
        es = by_dataset[dataset]
        tissue = es[0].tissue
        prep = es[0].prep
        voxel = DATASET_VOXEL_NM.get(dataset, "?")
        t_color = TISSUE_COLOR.get(tissue, "#888")
        p_color = PREP_COLOR.get(prep, "#888")
        n_needs = sum(1 for e in es if not e.anatomy)
        n_done = len(es) - n_needs
        count_html = f"{len(es)} crops"
        if n_needs:
            count_html += f' &middot; <span class="needs-count">{n_needs} need annotation</span>'

        rows_html: list[str] = []
        for e in es:
            state = _viewer_state(e)
            ng = _neuroglancer_url_inline(state)
            anatomy = e.anatomy or ''
            region = e.region_group or ''
            annotation = e.annotation or ''
            needs = not anatomy
            tr_classes = "needs-annotation" if needs else ""
            rows_html.append(f"""
            <tr class="{tr_classes}" data-tissue="{e.tissue}" data-prep="{e.prep}" data-crop="{e.crop}" data-tissue-name="{e.tissue}" data-prep-name="{e.prep}">
                <td class="crop"><a href="{ng}" target="_blank" rel="noopener">{e.crop}</a></td>
                <td class="editable region" data-field="anatomical_region" data-orig="{_attr_escape(anatomy)}">{_cell_render(anatomy)}</td>
                <td class="editable region-group" data-field="region_group" data-orig="{_attr_escape(region)}">{_cell_render(region)}</td>
                <td class="editable desc" data-field="annotation" data-orig="{_attr_escape(annotation)}">{_cell_render(annotation)}</td>
            </tr>""")

        sections_html.append(f"""
<section class="dataset" data-tissue="{tissue}" data-prep="{prep}" style="--tissue: {t_color}; --prep: {p_color};">
  <header class="dataset-header">
    <div class="dataset-title">
      <span class="tissue-chip">{tissue}</span>
      <span class="prep-chip">{prep}</span>
      <span class="voxel-chip">{voxel}&nbsp;nm</span>
      <code class="dataset-id">{dataset}</code>
    </div>
    <div class="dataset-count">{count_html}</div>
  </header>
  <table class="crops-table">
    <thead>
      <tr><th class="col-crop">Crop</th><th>Anatomical region</th><th>Region group</th><th>Description</th></tr>
    </thead>
    <tbody>{''.join(rows_html)}
    </tbody>
  </table>
</section>""")

    n_crops = len(entries)
    n_annotated = sum(1 for e in entries if e.anatomy)
    n_needs = n_crops - n_annotated

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ECS analysis crops — Neuroglancer links</title>
<style>
  :root {{
    --bg: #fafafa;
    --card: #ffffff;
    --border: #e5e7eb;
    --text: #1f2937;
    --muted: #6b7280;
    --accent: #2563eb;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ background: var(--bg); margin: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
    color: var(--text);
    line-height: 1.5;
  }}
  .container {{ max-width: 1280px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }}

  header.page-header {{ margin-bottom: 1.5rem; }}
  header.page-header h1 {{ font-size: 1.75rem; font-weight: 700; margin: 0 0 0.35rem; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); font-size: 0.95rem; }}

  .summary-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem; margin: 1.25rem 0 1.5rem;
  }}
  .summary-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 0.65rem 0.9rem;
  }}
  .summary-card .num {{ font-size: 1.5rem; font-weight: 700; line-height: 1; }}
  .summary-card .lbl {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 0.2rem; }}

  .controls {{
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 0.7rem 1rem; margin-bottom: 1.5rem;
    display: flex; flex-wrap: wrap; gap: 1rem; align-items: center;
  }}
  .controls label {{ font-size: 0.85rem; color: var(--muted); display: flex; align-items: center; gap: 0.45rem; }}
  .controls select {{
    padding: 0.3rem 0.5rem; border: 1px solid var(--border); border-radius: 5px;
    background: white; font-size: 0.9rem; font-family: inherit;
  }}
  .controls .checkbox {{ display: flex; align-items: center; gap: 0.35rem; cursor: pointer; }}

  section.dataset {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    overflow: hidden; margin-bottom: 1.25rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  }}
  .dataset-header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.75rem 1rem;
    border-left: 4px solid var(--tissue);
    background: linear-gradient(to right, color-mix(in srgb, var(--tissue) 8%, white), white 60%);
    border-bottom: 1px solid var(--border);
  }}
  .dataset-title {{ display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }}
  .tissue-chip, .prep-chip, .voxel-chip {{
    font-size: 0.72rem; font-weight: 600; padding: 0.18rem 0.55rem;
    border-radius: 999px; text-transform: uppercase; letter-spacing: 0.04em;
    color: white;
  }}
  .tissue-chip {{ background: var(--tissue); }}
  .prep-chip   {{ background: var(--prep); }}
  .voxel-chip  {{ background: #475569; }}
  .dataset-id  {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.82rem; color: var(--muted); }}
  .dataset-count {{ color: var(--muted); font-size: 0.85rem; }}
  .needs-count {{ color: #b45309; font-weight: 600; }}

  table.crops-table {{ width: 100%; border-collapse: collapse; }}
  table.crops-table th {{
    text-align: left; padding: 0.55rem 1rem; background: #f9fafb;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--border);
  }}
  table.crops-table td {{
    padding: 0.55rem 1rem; border-bottom: 1px solid #f1f3f5;
    font-size: 0.9rem; vertical-align: top;
  }}
  table.crops-table tr:last-child td {{ border-bottom: none; }}
  table.crops-table tr:hover td {{ background: #f9fafb; }}

  td.crop {{ width: 9rem; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.88rem; }}
  td.crop a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
  td.crop a:hover {{ text-decoration: underline; }}
  td.region {{ width: 18rem; font-weight: 500; }}
  td.region-group {{ width: 11rem; color: var(--muted); font-size: 0.85rem; }}
  td.desc {{ color: #374151; }}

  .missing {{
    display: inline-block; color: #b45309; font-style: italic;
    font-weight: 600; font-size: 0.82rem;
  }}
  .missing::before {{ content: "✎ needs annotation"; }}

  /* Row-level "needs annotation" highlighting. The class is added in
     server-rendered HTML when the original anatomical_region is empty,
     and removed by JS once the user fills it in. */
  tr.needs-annotation td.crop {{ position: relative; }}
  tr.needs-annotation td.crop::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: #f59e0b;
  }}
  tr.needs-annotation td {{ background: #fffbeb; }}
  tr.needs-annotation:hover td {{ background: #fef3c7; }}

  /* Editable cells */
  td.editable {{ cursor: text; position: relative; }}
  td.editable:hover {{ background: #f0f9ff; }}
  td.editable:hover::after {{
    content: "✎"; position: absolute; top: 0.4rem; right: 0.5rem;
    font-size: 0.75rem; color: #94a3b8;
  }}
  td.editable.edited {{ background: #fef3c7; }}
  td.editable.edited::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: #f59e0b;
  }}
  td.editable textarea {{
    width: 100%; min-height: 2.2rem; padding: 0.35rem 0.5rem;
    border: 1px solid #94a3b8; border-radius: 4px;
    font-family: inherit; font-size: 0.88rem; line-height: 1.4;
    background: white; resize: vertical;
  }}
  td.editable textarea:focus {{ outline: 2px solid #2563eb; outline-offset: -1px; border-color: #2563eb; }}

  /* Editor toolbar */
  .editor-bar {{
    background: linear-gradient(to right, #ecfdf5, #f0fdf4);
    border: 1px solid #a7f3d0; border-radius: 8px;
    padding: 0.7rem 1rem; margin-bottom: 1.25rem;
    display: flex; flex-wrap: wrap; align-items: center; gap: 0.9rem;
  }}
  .editor-bar .note {{ flex: 1 1 14rem; color: #047857; font-size: 0.86rem; }}
  .editor-bar input[type=text] {{
    padding: 0.3rem 0.55rem; border: 1px solid #cbd5e1; border-radius: 5px;
    font-size: 0.9rem; font-family: inherit; min-width: 12rem; background: white;
  }}
  .editor-bar button {{
    padding: 0.4rem 0.85rem; border-radius: 6px; font-size: 0.88rem; font-weight: 600;
    border: 1px solid #059669; background: #10b981; color: white; cursor: pointer;
    font-family: inherit;
  }}
  .editor-bar button:disabled {{ background: #cbd5e1; border-color: #94a3b8; cursor: not-allowed; }}
  .editor-bar button:hover:not(:disabled) {{ background: #059669; }}
  .editor-bar button.secondary {{ background: white; color: #047857; border-color: #6ee7b7; }}
  .editor-bar button.secondary:hover {{ background: #ecfdf5; }}
  .editor-bar .pending-count {{ font-weight: 700; color: #047857; }}

  /* How-to-use panel */
  .howto {{
    background: #fffbeb; border: 2px solid #fbbf24; border-radius: 10px;
    padding: 1.1rem 1.4rem; margin-bottom: 1.5rem;
  }}
  .howto-header {{
    display: flex; justify-content: space-between; align-items: center;
    cursor: pointer; user-select: none;
  }}
  .howto h2 {{
    margin: 0; font-size: 1.1rem; color: #78350f;
    display: flex; align-items: center; gap: 0.5rem;
  }}
  .howto h2::before {{ content: "👋"; }}
  .howto-toggle {{
    background: transparent; border: 1px solid #d97706; color: #78350f;
    padding: 0.2rem 0.6rem; border-radius: 5px;
    font-size: 0.8rem; font-weight: 600; cursor: pointer; font-family: inherit;
  }}
  .howto-body {{ margin-top: 1rem; }}
  .howto.collapsed .howto-body {{ display: none; }}
  .howto p {{ margin: 0.4rem 0 0.7rem; line-height: 1.6; }}
  .howto .step-list {{ list-style: none; padding: 0; margin: 0.8rem 0; counter-reset: stp; }}
  .howto .step-list > li {{
    counter-increment: stp; padding: 0.6rem 0 0.6rem 2.6rem;
    position: relative; border-top: 1px dashed #fde68a;
  }}
  .howto .step-list > li:first-child {{ border-top: none; }}
  .howto .step-list > li::before {{
    content: counter(stp); position: absolute; left: 0; top: 0.55rem;
    width: 1.8rem; height: 1.8rem; line-height: 1.8rem; text-align: center;
    background: #f59e0b; color: white; border-radius: 999px;
    font-weight: 700; font-size: 0.95rem;
  }}
  .howto .step-title {{ font-weight: 700; color: #78350f; display: block; margin-bottom: 0.2rem; }}
  .howto kbd {{
    background: white; border: 1px solid #d97706; border-bottom-width: 2px;
    border-radius: 3px; padding: 0.05rem 0.4rem; font-size: 0.82rem;
    font-family: ui-monospace, monospace; color: #78350f;
  }}
  .howto .warn {{
    background: #fef2f2; border-left: 4px solid #ef4444;
    padding: 0.7rem 1rem; margin-top: 1rem; border-radius: 6px;
  }}
  .howto .warn strong {{ color: #991b1b; }}
  .howto .demo-pill {{
    display: inline-block; background: #fef3c7; border: 1px solid #fcd34d;
    padding: 0.05rem 0.45rem; border-radius: 4px; font-size: 0.82rem;
  }}

  footer {{ margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }}
  footer code {{ background: #f3f4f6; padding: 0.05rem 0.3rem; border-radius: 3px; font-size: 0.8rem; }}

  @media (max-width: 720px) {{
    .container {{ padding: 1.25rem 1rem 3rem; }}
    .dataset-header {{ flex-direction: column; align-items: flex-start; gap: 0.5rem; }}
    td.region, td.region-group {{ width: auto; }}
  }}
</style>
</head>
<body>
<div class="container">

<header class="page-header">
  <h1>ECS analysis crops</h1>
  <div class="subtitle">CellMap groundtruth crops used in the Chemical vs Rapid HPF extracellular-space morphology study. Use this page to (a) view each crop in Neuroglancer and (b) fill in what anatomical structure the crop is showing.</div>
  <div style="margin-top: 0.75rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
    <a href="home.html" style="display:inline-block; padding: 0.4rem 0.9rem; background:#111827; color:white; border-radius:6px; text-decoration:none; font-size:0.9rem; font-weight:600;">⌂ Project home</a>
    <a href="sanity-check.html" style="display:inline-block; padding: 0.4rem 0.9rem; background:#2563eb; color:white; border-radius:6px; text-decoration:none; font-size:0.9rem; font-weight:600;">→ Sanity check: matched-region comparison</a>
    <a href="contacts.html" style="display:inline-block; padding: 0.4rem 0.9rem; background:#7c3aed; color:white; border-radius:6px; text-decoration:none; font-size:0.9rem; font-weight:600;">→ Liver cell-cell contact sites</a>
    <a href="membranes/membranes_3d.html" style="display:inline-block; padding: 0.4rem 0.9rem; background:#0d9488; color:white; border-radius:6px; text-decoration:none; font-size:0.9rem; font-weight:600;">→ Membrane topology (3D)</a>
  </div>
</header>

<div class="howto" id="howto">
  <div class="howto-header" onclick="document.getElementById('howto').classList.toggle('collapsed')">
    <h2>How to use this page</h2>
    <button class="howto-toggle" type="button">Show / hide</button>
  </div>
  <div class="howto-body">
    <p>
      Each row below is one EM crop. Two things you can do.
      Rows with a <strong style="color:#b45309">yellow background</strong> still need
      an anatomical region — those are the ones we'd most like you to fill in.
    </p>

    <ol class="step-list">
      <li>
        <span class="step-title">View a crop in Neuroglancer</span>
        Click the blue crop ID in the left column (e.g. <span class="demo-pill">crop1033</span>).
        A new tab opens in Neuroglancer with five layers: <kbd>em</kbd> (raw image, on by default),
        <kbd>all</kbd> (color-coded full segmentation, on by default), and
        <kbd>cell</kbd> / <kbd>ecs</kbd> / <kbd>bm</kbd> (off by default — click the eye in
        Neuroglancer's left panel to toggle).
      </li>
      <li>
        <span class="step-title">Add or edit an anatomical region / description</span>
        Click any cell in the <strong>Anatomical region</strong>, <strong>Region group</strong>,
        or <strong>Description</strong> column. The cell turns into a text box. Type, then click
        outside (or press <kbd>Enter</kbd> for short fields). Press <kbd>Esc</kbd> to cancel an edit
        without saving. <strong>Edited cells get a yellow background</strong> so you can see what
        you've changed.
        <br><br>
        Use these guidelines:
        <ul>
          <li><strong>Anatomical region</strong> — the specific structure shown
          (e.g. <em>"Bile canaliculus between hepatocytes"</em>).</li>
          <li><strong>Region group</strong> — a short category that groups similar crops
          (e.g. <em>"Bile canaliculus"</em>). Match the existing values where possible so
          we can compare Chemical vs HPF crops with the same group label.</li>
          <li><strong>Description</strong> — a longer free-text note about what's notable
          (cell types present, orientation, anything unusual).</li>
        </ul>
      </li>
      <li>
        <span class="step-title">Send your edits back</span>
        Type your name in the <strong>Annotator</strong> box up top (this gets attached to each row
        in the export). Then click <strong>Download CSV</strong>. A file named
        <code>crop_annotations_edits_…csv</code> downloads to your computer. <strong>Email or
        Slack that file to Aubrey</strong> — she'll merge it into the master annotation list.
      </li>
    </ol>

    <div class="warn">
      <strong>⚠️ Important:</strong> your edits live in <em>this browser only</em>. They aren't
      synced anywhere. Two consequences:
      <ul>
        <li>If you clear browser data, use private/incognito mode, or switch to a different
        computer, your edits will not be there.</li>
        <li>Two people editing simultaneously will not see each other's edits — each sends
        their own CSV and Aubrey merges them.</li>
      </ul>
      <strong>Best practice:</strong> hit <strong>Download CSV</strong> when you finish a
      batch, even if you plan to come back — it's a backup.
    </div>
  </div>
</div>

<div class="summary-grid">
  <div class="summary-card"><div class="num">{n_crops}</div><div class="lbl">Crops total</div></div>
  <div class="summary-card"><div class="num">{n_annotated}</div><div class="lbl">Annotated</div></div>
  <div class="summary-card"><div class="num" style="color:#b45309">{n_needs}</div><div class="lbl">Need annotation</div></div>
  <div class="summary-card"><div class="num">{len(ordered_datasets)}</div><div class="lbl">Datasets</div></div>
</div>

<div class="editor-bar">
  <label><strong>Your name:</strong> <input type="text" id="annotator-name" placeholder="e.g. KP"></label>
  <span><span class="pending-count" id="pending-count">0</span> edits pending in this browser</span>
  <button id="download-edits" disabled title="Download a CSV of just the rows you've edited">⬇ Download CSV</button>
  <button id="clear-edits" class="secondary" title="Wipe all your unsent edits from this browser">Clear edits</button>
</div>

<div class="controls">
  <label>Tissue
    <select id="tissue-filter">
      <option value="">All</option>
      <option>Cortex</option><option>Heart</option><option>Kidney</option><option>Liver</option>
    </select>
  </label>
  <label>Prep
    <select id="prep-filter">
      <option value="">All</option>
      <option>Chemical</option><option>Rapid HPF</option>
    </select>
  </label>
  <label class="checkbox"><input type="checkbox" id="needs-only"> Only show crops needing annotation</label>
</div>

{''.join(sections_html)}

<footer>
  Click a crop ID to open it in Neuroglancer (em + all-labels + per-label segmentations: cell / ecs / bm).
  Click any region/description cell to edit; edits live in your browser's localStorage and can be exported as CSV with the <strong>Download CSV</strong> button.
  <br>
  Rows with a <strong style="color:#b45309">yellow background and orange left bar</strong> are crops that still need an anatomical region. The "Need annotation" count in the summary updates as you fill these in.
</footer>

</div>

<script>
const sections = document.querySelectorAll('section.dataset');
function applyFilters() {{
  const t = document.getElementById('tissue-filter').value;
  const p = document.getElementById('prep-filter').value;
  const needsOnly = document.getElementById('needs-only').checked;
  sections.forEach(sec => {{
    const sectionTissueOk = !t || sec.dataset.tissue === t;
    const sectionPrepOk = !p || sec.dataset.prep === p;
    let visibleRows = 0;
    sec.querySelectorAll('tbody tr').forEach(tr => {{
      const needsAnnotation = tr.classList.contains('needs-annotation');
      const ok = sectionTissueOk && sectionPrepOk && (!needsOnly || needsAnnotation);
      tr.style.display = ok ? '' : 'none';
      if (ok) visibleRows++;
    }});
    sec.style.display = visibleRows ? '' : 'none';
  }});
}}
['tissue-filter', 'prep-filter', 'needs-only'].forEach(id => document.getElementById(id).addEventListener('change', applyFilters));

/* ============================================================
   Inline annotation editor — edits persist in localStorage so a
   user can come back to the page and continue annotating without
   losing work, then export a CSV of just the rows they touched.
   ============================================================ */
const STORAGE_KEY = 'ecs-handoff-edits-v1';
const NAME_KEY = 'ecs-handoff-annotator';

function loadEdits() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}'); }}
  catch (e) {{ return {{}}; }}
}}
function saveEdits(e) {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(e)); }}

const annotatorInput = document.getElementById('annotator-name');
annotatorInput.value = localStorage.getItem(NAME_KEY) || '';
annotatorInput.addEventListener('input', () => localStorage.setItem(NAME_KEY, annotatorInput.value));

function renderCellText(text) {{
  if (!text) return '<span class="missing">—</span>';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}}

function paintEditedState() {{
  const edits = loadEdits();
  document.querySelectorAll('td.editable').forEach(td => {{
    const crop = td.closest('tr').dataset.crop;
    const field = td.dataset.field;
    const orig = td.dataset.orig || '';
    const editedVal = edits[crop] && edits[crop][field];
    if (editedVal !== undefined && editedVal !== orig) {{
      td.classList.add('edited');
      td.innerHTML = renderCellText(editedVal);
    }} else {{
      td.classList.remove('edited');
      td.innerHTML = renderCellText(orig);
    }}
  }});
  // Re-evaluate "needs annotation" per row based on the live value of
  // anatomical_region (original + any edit).
  document.querySelectorAll('tr[data-crop]').forEach(tr => {{
    const crop = tr.dataset.crop;
    const td = tr.querySelector('td[data-field="anatomical_region"]');
    const orig = td.dataset.orig || '';
    const edit = edits[crop] && edits[crop].anatomical_region;
    const live = edit !== undefined ? edit : orig;
    tr.classList.toggle('needs-annotation', !live);
  }});
  refreshCount();
  // Filters depend on the needs-annotation class; re-apply.
  if (typeof applyFilters === 'function') applyFilters();
}}

function refreshCount() {{
  const edits = loadEdits();
  const n = Object.values(edits).reduce((sum, fields) => sum + Object.keys(fields).length, 0);
  document.getElementById('pending-count').textContent = n;
  document.getElementById('download-edits').disabled = n === 0;
}}

function beginEdit(td) {{
  if (td.querySelector('textarea')) return;
  const edits = loadEdits();
  const crop = td.closest('tr').dataset.crop;
  const field = td.dataset.field;
  const orig = td.dataset.orig || '';
  const current = (edits[crop] && edits[crop][field] !== undefined) ? edits[crop][field] : orig;

  const ta = document.createElement('textarea');
  ta.value = current;
  ta.rows = field === 'annotation' ? 3 : 1;
  td.innerHTML = '';
  td.appendChild(ta);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);

  function commit() {{
    const v = ta.value.trim();
    const edits = loadEdits();
    if (v === (td.dataset.orig || '')) {{
      // Equal to original → remove any stored edit.
      if (edits[crop]) {{
        delete edits[crop][field];
        if (!Object.keys(edits[crop]).length) delete edits[crop];
      }}
    }} else {{
      edits[crop] = edits[crop] || {{}};
      edits[crop][field] = v;
    }}
    saveEdits(edits);
    paintEditedState();
  }}

  ta.addEventListener('blur', commit);
  ta.addEventListener('keydown', (ev) => {{
    if (ev.key === 'Escape') {{ ev.preventDefault(); ta.value = current; ta.blur(); }}
    if (ev.key === 'Enter' && !ev.shiftKey && field !== 'annotation') {{ ev.preventDefault(); ta.blur(); }}
  }});
}}

document.querySelectorAll('td.editable').forEach(td => {{
  td.addEventListener('click', (ev) => {{
    if (ev.target.tagName === 'TEXTAREA') return;
    beginEdit(td);
  }});
}});

function csvEscape(s) {{
  s = s == null ? '' : String(s);
  return /[,"\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}}

document.getElementById('download-edits').addEventListener('click', () => {{
  const edits = loadEdits();
  const annotator = annotatorInput.value.trim();
  const cropMeta = {{}};
  document.querySelectorAll('tr[data-crop]').forEach(tr => {{
    cropMeta[tr.dataset.crop] = {{
      tissue: tr.dataset.tissueName,
      prep: tr.dataset.prepName,
    }};
  }});
  const headers = ['crop','tissue','prep','anatomical_region','region_group','annotation','annotator'];
  const lines = [headers.join(',')];
  Object.keys(edits).sort().forEach(crop => {{
    const e = edits[crop];
    const tds = document.querySelector('tr[data-crop="' + crop + '"]');
    const orig = (field) => tds.querySelector('td[data-field="' + field + '"]').dataset.orig || '';
    const get = (field) => e[field] !== undefined ? e[field] : orig(field);
    lines.push([
      crop,
      cropMeta[crop].tissue,
      cropMeta[crop].prep,
      get('anatomical_region'),
      get('region_group'),
      get('annotation'),
      annotator,
    ].map(csvEscape).join(','));
  }});
  const blob = new Blob([lines.join('\\n') + '\\n'], {{ type: 'text/csv;charset=utf-8' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.download = `crop_annotations_edits_${{stamp}}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}});

document.getElementById('clear-edits').addEventListener('click', () => {{
  if (!Object.keys(loadEdits()).length) return;
  if (!confirm('Clear all pending edits in this browser?')) return;
  saveEdits({{}});
  paintEditedState();
}});

paintEditedState();
</script>
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(html)
    print(f"Wrote {OUT_DIR / 'index.html'} ({len(html)} bytes)")
    print(f"Wrote {len(entries)} state files to {STATES_DIR}")


if __name__ == "__main__":
    main()
