"""
Build a focused page comparing hepatocyte-lateral and bile-canaliculus
contact-site profiles. Each card shows the contact-distance heatmap
thumbnail plus a Neuroglancer link.

Output: out/ecs-handoff/contacts.html
Thumbnails: /nrs/cellmap/weigela/ecs-handoff/thumbs/contacts/<crop>.png
"""
from __future__ import annotations

import csv
import json
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "out" / "ecs-handoff" / "contacts.html"

DATA_BASE = "https://cellmap-vm1.int.janelia.org/nrs/data"
NG_BASE   = "https://neuroglancer-demo.appspot.com/"
THUMBS    = "thumbs/contacts"

EM_ARRAY = {
    "jrc_mus-liver":   "fibsem-uint8",
    "jrc_mus-liver-8": "fibsem-uint16",
}

from palette import PREP_COLOR


def ng_url(dataset: str, crop: str) -> str:
    base = f"zarr://{DATA_BASE}/{dataset}/{dataset}.zarr/recon-1"
    em = f"{base}/em/{EM_ARRAY[dataset]}"
    gt = f"{base}/labels/groundtruth/{crop}"
    state = {
        "layers": [
            {"type": "image", "source": em, "name": "em"},
            {"type": "segmentation", "source": f"{gt}/all", "name": "all"},
            {"type": "segmentation", "source": f"{gt}/cell", "name": "cell", "visible": False},
            {"type": "segmentation", "source": f"{gt}/ecs",  "name": "ecs",  "visible": False},
        ],
        "selectedLayer": {"layer": "em"}, "layout": "4panel",
    }
    return NG_BASE + "#!" + urllib.parse.quote(json.dumps(state, separators=(",", ":")), safe="")


# Pull per-crop contact fractions for labelling cards
def _load_voronoi():
    d = {}
    with open(REPO_ROOT / "results" / "native_voronoi_gap.csv") as f:
        for r in csv.DictReader(f):
            d[r["crop"]] = r
    return d


SECTIONS = [
    {
        "label": "Hepatocyte–hepatocyte lateral interface",
        "subtitle": (
            "Membranes of two adjacent hepatocytes meeting along their lateral surface. "
            "In vivo these membranes lie within tens of nm of each other; chemical fixation "
            "is thought to pull them apart."
        ),
        "rows": [
            {
                "heading": "Chemical (n=1 in this region group)",
                "crops": [("jrc_mus-liver", "crop1044", "Chemical")],
            },
            {
                "heading": "Rapid HPF (n=6 in this region group; showing three)",
                "crops": [
                    ("jrc_mus-liver-8", "crop1124", "Rapid HPF"),
                    ("jrc_mus-liver-8", "crop1125", "Rapid HPF"),
                    ("jrc_mus-liver-8", "crop1127", "Rapid HPF"),
                ],
            },
        ],
    },
    {
        "label": "Bile canaliculus (control comparison)",
        "subtitle": (
            "Bile canaliculus is a designed-to-be-open lumen between hepatocytes, with "
            "microvilli. No tight membrane apposition to disrupt — Chem and HPF should look similar."
        ),
        "rows": [
            {
                "heading": "Chemical",
                "crops": [("jrc_mus-liver", "crop1040", "Chemical")],
            },
            {
                "heading": "Rapid HPF",
                "crops": [("jrc_mus-liver-8", "crop1073", "Rapid HPF")],
            },
        ],
    },
]


def card(dataset: str, crop: str, prep: str, voronoi: dict) -> str:
    row = voronoi.get(crop, {})
    p20 = float(row.get("contact_fractions_p20", 0) or 0)
    p40 = float(row.get("contact_fractions_p40", 0) or 0)
    p80 = float(row.get("contact_fractions_p80", 0) or 0)
    p160 = float(row.get("contact_fractions_p160", 0) or 0)
    p_color = PREP_COLOR[prep]
    return f"""
<div class="card" style="--prep:{p_color}">
  <a href="{ng_url(dataset, crop)}" target="_blank" rel="noopener" class="thumb-wrap">
    <img class="thumb" src="{THUMBS}/{crop}.png" alt="{crop}" loading="lazy">
    <div class="thumb-overlay">{crop} ↗</div>
  </a>
  <div class="meta">
    <div class="prep-tag" style="background:{p_color}">{prep}</div>
    <div class="dataset">{dataset}</div>
  </div>
  <div class="metrics">
    <div><span class="lbl">p<sub>20</sub></span><span class="val">{p20:.3f}</span></div>
    <div><span class="lbl">p<sub>40</sub></span><span class="val">{p40:.3f}</span></div>
    <div><span class="lbl">p<sub>80</sub></span><span class="val">{p80:.3f}</span></div>
    <div><span class="lbl">p<sub>160</sub></span><span class="val">{p160:.3f}</span></div>
  </div>
</div>"""


def main() -> None:
    voronoi = _load_voronoi()
    sections_html = []
    for sec in SECTIONS:
        rows_html = []
        for row in sec["rows"]:
            cards_html = "".join(card(ds, c, p, voronoi) for ds, c, p in row["crops"])
            rows_html.append(f"""
<div class="row-block">
  <h3 class="row-head">{row['heading']}</h3>
  <div class="card-grid">{cards_html}</div>
</div>""")
        sections_html.append(f"""
<section class="section">
  <h2>{sec['label']}</h2>
  <div class="subtitle">{sec['subtitle']}</div>
  {''.join(rows_html)}
</section>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Liver cell-cell contact sites — Chem vs HPF</title>
<style>
  :root {{
    --bg:#0f1420; --card:#1a2030; --card2:#222b3e;
    --border:#2a3346; --text:#e8ecf3; --muted:#8a93a6;
    --accent:#5b9cff; --head:#cfe0ff;
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); margin: 0; color: var(--text); font-family: 'Segoe UI', Tahoma, sans-serif; line-height: 1.55; }}
  .container {{ max-width: 1500px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }}
  h1 {{ margin: 0 0 0.4rem; font-size: 1.7rem; letter-spacing: -0.01em; color: var(--text); }}
  .page-sub {{ color: #c0c8d6; margin-bottom: 1.5rem; font-size: 0.95rem; }}
  a.back {{ display: inline-block; margin-bottom: 1rem; color: var(--accent); text-decoration: none; font-size: 0.9rem; }}

  .legend {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 1rem 1.2rem; margin-bottom: 1.5rem; color: #c0c8d6;
  }}
  .legend h2 {{ font-size: 1rem; margin: 0 0 0.5rem; color: var(--head); }}
  .legend p {{ margin: 0.35rem 0; font-size: 0.92rem; }}
  .legend em {{ color: var(--text); }}
  .legend code {{
    background: var(--card2); border-radius: 3px; padding: 1px 5px; color: #d6deea;
    font-family: ui-monospace, Menlo, monospace; font-size: 0.85rem;
  }}
  .swatches {{ display: flex; flex-wrap: wrap; gap: 0.8rem; margin-top: 0.6rem; font-size: 0.85rem; }}
  .sw {{ display: inline-flex; align-items: center; gap: 0.35rem; }}
  .sw span.box {{ display: inline-block; width: 14px; height: 14px; border-radius: 3px; }}

  section.section {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 1.1rem 1.3rem 1.4rem; margin-bottom: 1.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.25);
  }}
  section.section h2 {{ margin: 0 0 0.25rem; font-size: 1.2rem; color: var(--head); }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1rem; }}

  .row-block {{ margin-top: 1rem; }}
  .row-head {{
    margin: 0 0 0.6rem; font-size: 0.78rem; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--muted); font-weight: 700;
  }}
  .card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.9rem; }}

  .card {{
    background: var(--card2); border: 1px solid var(--border); border-left: 4px solid var(--prep);
    border-radius: 10px; overflow: hidden;
  }}
  .thumb-wrap {{ display: block; position: relative; text-decoration: none; background: #0a0f1c; aspect-ratio: 1; }}
  .thumb {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .thumb-overlay {{
    position: absolute; bottom: 0.4rem; left: 0.4rem;
    background: rgba(0,0,0,0.7); color: white; padding: 0.15rem 0.5rem;
    border-radius: 4px; font-family: ui-monospace, monospace; font-size: 0.82rem; font-weight: 600;
  }}
  .meta {{ padding: 0.55rem 0.8rem 0.2rem; display: flex; justify-content: space-between; align-items: center; }}
  .prep-tag {{ color: white; padding: 0.1rem 0.55rem; border-radius: 4px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }}
  .dataset {{ font-family: ui-monospace, monospace; font-size: 0.72rem; color: var(--muted); }}
  .metrics {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.35rem;
    padding: 0.45rem 0.8rem 0.75rem;
  }}
  .metrics > div {{ display: flex; flex-direction: column; align-items: center; }}
  .metrics .lbl {{ font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
  .metrics .val {{ font-size: 0.92rem; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); }}
</style>
</head>
<body>
<div class="container">

<a class="back" href="home.html">⌂ Project home</a> &nbsp; <a class="back" href="index.html">← Back to crops index</a>
<h1>Liver cell–cell contact sites</h1>
<div class="page-sub">
  Visual side-by-side of where cell membranes lie close to one another (yellow / orange)
  vs far apart (blue), comparing Chemical fixation against Rapid HPF.
  The hepatocyte–lateral interface is where the largest difference lives;
  bile canaliculus is shown as a control where Chem and HPF should look similar.
</div>

<div class="legend">
  <h2>How to read the thumbnails</h2>
  <p>
    The colored overlay is computed per cell pixel: distance from that pixel to the nearest
    pixel assigned (via Voronoi) to a <em>different</em> cell. Small distance = tight cell-cell
    contact. The bands below the thumbnail are the standard
    <code>contact_fractions_p<sub>T</sub></code> = fraction of cell-cell Voronoi boundary faces
    closer than T nm. Higher = more tightly packed cells.
  </p>
  <div class="swatches">
    <span class="sw"><span class="box" style="background:#ffe600"></span>&lt;40 nm (very close)</span>
    <span class="sw"><span class="box" style="background:#ff8c00"></span>40–80 nm</span>
    <span class="sw"><span class="box" style="background:#d91a8c"></span>80–160 nm</span>
    <span class="sw"><span class="box" style="background:#3366e6"></span>&gt;160 nm (isolated)</span>
  </div>
  <p style="margin-top:0.5rem; font-size:0.85rem; color:var(--muted)">
    The <code>p<sub>20</sub></code> bin (gap &lt; 20 nm) is a metric-level resolution artifact
    on the HPF side — gap estimation has a floor of ~3 × voxel size, which is 24 nm for 8 nm
    voxels. The values you should compare are p<sub>40</sub>, p<sub>80</sub>, p<sub>160</sub>.
  </p>
</div>

{''.join(sections_html)}

</div>
</body>
</html>
"""
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
