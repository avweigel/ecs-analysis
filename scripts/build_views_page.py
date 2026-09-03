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

import json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

ROOT = Path(__file__).resolve().parent.parent
MEM = ROOT / "figures" / "membranes"
OUT = ROOT / "docs" / "membranes" / "views.html"

EXTRA = """<style>
  .pair{display:grid;grid-template-columns:1fr 1fr;gap:13px;margin:10px 0 26px}
  @media(max-width:780px){.pair{grid-template-columns:1fr}}
  .vcard{background:var(--surface-1);border:1px solid var(--line);border-radius:10px;overflow:hidden}
  .vcard model-viewer{width:100%;height:300px;background:var(--surface-2);display:block}
  .vhead{display:flex;justify-content:space-between;align-items:baseline;
         padding:10px 13px;border-bottom:1px solid var(--line-soft)}
  .vhead .c{font-size:12px;color:var(--text-muted);font-variant-numeric:tabular-nums}
  .vfoot{padding:8px 13px;font-size:11.5px;color:var(--text-muted)}
  .empty{display:flex;align-items:center;justify-content:center;height:300px;
         color:var(--text-muted);font-size:13px;background:var(--surface-2);
         text-align:center;padding:22px}
  h2.reg{font-size:15px;margin:26px 0 0}
  .tis{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--text-muted);
       margin:36px 0 0;padding-top:15px;border-top:1px solid var(--line)}
</style>
<script type="module" src="model-viewer.min.js"></script>"""

INTRO = """<main class="wide">
  <h1>3D views</h1>
  <p class="lede">One representative crop per region and preparation, membrane surface coloured
  by curvature. Drag to rotate, scroll to zoom. These are pre-rendered for a quick look; the
  <a href="inspector.html">inspector</a> has all 55 crops, all three scalars, and live control
  of the colour range.</p>
  <div class="legend">
    <span class="item"><i class="sw" style="background:var(--chem)"></i>Chemical fixation</span>
    <span class="item"><i class="sw" style="background:var(--hpf)"></i>Rapid high-pressure freezing</span>
  </div>
  <div class="callout"><b>Curvature colouring.</b> Warm is convex, membrane bulging out toward
  the extracellular space; cool is concave, curving away. Pale is flat. Each view is framed to
  fill its own panel, so apparent size on screen is not physical scale &mdash; the face count
  beside each crop is the size cue. Where a panel is empty, that arm has no crops; see the
  <a href="../index.html#coverage">coverage table</a>.</div>
  <!--BODY-->
"""

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

    html = sh.head("3D views — ECS preservation", 1, EXTRA)
    html += sh.nav("membranes/views.html", 1)
    html += INTRO.replace("<!--BODY-->", body)
    html += sh.tail(1)
    OUT.write_text(html)
    print(f"built {OUT.relative_to(ROOT)} ({len(by)} views)")


if __name__ == "__main__":
    main()
