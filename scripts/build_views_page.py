#!/usr/bin/env python3
"""
Build docs/membranes/views.html — the quick-look 3D gallery.

One representative crop per tissue x region x preparation, curvature only,
Chemical and Rapid HPF side by side so the pair is the unit of comparison.
This is deliberately a *subset*: the full set of 55 crops with all three
scalars lives in the inspector, which colormaps them live. This page exists
for the reader who will not operate a viewer.

Each view is framed to fill its own panel, so apparent size on screen is not
physical scale — the face count beside each crop is the size cue.

Representatives are the median-patch-size crop in each group (typical, not
largest), recorded in figures/membranes/_curated.json by build_site.py.

    python scripts/build_views_page.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEM = ROOT / "figures" / "membranes"
OUT = ROOT / "docs" / "membranes" / "views.html"

PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>3D views — ECS preservation</title>
<link rel="stylesheet" href="../assets/app.css">
<script type="module" src="model-viewer.min.js"></script>
<style>
  .pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:10px 0 24px}
  @media(max-width:760px){.pair{grid-template-columns:1fr}}
  .vcard{background:var(--surface-1);border:1px solid var(--line);border-radius:9px;overflow:hidden}
  .vcard model-viewer{width:100%;height:290px;background:var(--surface-2);display:block}
  .vhead{display:flex;justify-content:space-between;align-items:baseline;
         padding:9px 12px;border-bottom:1px solid var(--line-soft)}
  .vhead .c{font-size:12px;color:var(--text-muted);font-variant-numeric:tabular-nums}
  .vfoot{padding:7px 12px;font-size:11px;color:var(--text-muted)}
  .empty{display:flex;align-items:center;justify-content:center;height:290px;
         color:var(--text-muted);font-size:13px;background:var(--surface-2);text-align:center;padding:20px}
  h2.reg{font-size:15px;margin:26px 0 0}
  h2.reg small{color:var(--text-muted);font-weight:400;margin-left:8px}
  .tis{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);
       margin:34px 0 0;padding-top:14px;border-top:1px solid var(--line)}
</style></head><body>
<header class="top"><div class="wrap">
  <span class="brand">ECS preservation</span>
  <nav>
    <a href="../index.html">Overview</a>
    <a href="../explore.html">Metric explorer</a>
    <a href="../crops.html">Crops</a>
    <a href="../figures.html">Figures</a>
    <a href="views.html" aria-current="page">3D views</a>
    <a href="inspector.html">Membrane inspector</a>
  </nav>
</div></header>
<main>
  <h1>3D views</h1>
  <p class="lede">One representative crop per region and preparation, membrane surface
  colored by curvature. Drag to rotate, scroll to zoom. These are pre-rendered for a quick
  look; the <a href="inspector.html">inspector</a> has all 55 crops, all three scalars, and
  live control of the color range.</p>
  <p class="note" style="margin-bottom:22px">Representatives are the median-sized patch in
  each group, so they are typical rather than the most impressive. Where a cell is empty,
  that arm has no crops — see the <a href="../index.html">coverage table</a>.</p>
  <!--BODY-->
</main></body></html>"""


def main():
    rows = json.loads((MEM / "manifest_inspect.json").read_text())
    if not isinstance(rows, list):
        rows = next(v for v in rows.values() if isinstance(v, list))
    picked = set(json.loads((MEM / "_curated.json").read_text()))
    by = {}
    for e in rows:
        if e["crop"] in picked:
            by[(e.get("tissue"), e.get("region_group") or "(no region assigned)",
                e.get("prep"))] = e

    groups = defaultdict(list)
    for (t, r, p), e in by.items():
        groups[t].append((r, p, e))

    body = ""
    for tissue in sorted(groups):
        body += f'<div class="tis">{tissue}</div>'
        regions = sorted({r for r, _, _ in groups[tissue]})
        for reg in regions:
            entries = {p: e for r, p, e in groups[tissue] if r == reg}
            body += f'<h2 class="reg">{reg}</h2><div class="pair">'
            for prep, cls in (("Chemical", "chem"), ("Rapid HPF", "hpf")):
                e = entries.get(prep)
                if not e:
                    body += ('<div class="vcard"><div class="vhead">'
                             f'<span class="tag {cls}">{prep}</span></div>'
                             '<div class="empty">no crops in this arm</div></div>')
                    continue
                c = e["crop"]
                body += (
                    '<div class="vcard"><div class="vhead">'
                    f'<span class="tag {cls}">{prep}</span>'
                    f'<span class="c">{c} · {e.get("patch_faces",0):,} faces</span></div>'
                    f'<model-viewer src="glb/{c}_curvature.glb" camera-controls '
                    'touch-action="pan-y" interaction-prompt="none" exposure="1.1" '
                    'camera-orbit="auto auto 88%" min-field-of-view="8deg" '
                    f'alt="Membrane surface of {c} colored by curvature" '
                    'shadow-intensity="0" loading="lazy"></model-viewer>'
                    f'<div class="vfoot">{e.get("anatomy") or reg} · '
                    f'{e.get("voxel_nm","?")} nm · curvature</div></div>')
            body += "</div>"

    OUT.write_text(PAGE.replace("<!--BODY-->", body))
    print(f"built {OUT.relative_to(ROOT)} ({len(by)} views)")


if __name__ == "__main__":
    main()
