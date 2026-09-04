#!/usr/bin/env python3
"""
Build docs/crops.html — the crop hub.

Everything that used to live under "Membranes" is folded in here: the table,
the interactive membrane viewer, and a linked two-panel comparison. The table
and the viewer talk to each other, which is the point: you filter down to the
crops you care about and look at them without changing pages.

Data is embedded as JSON so the page needs one request, not three.
"""
from __future__ import annotations

import csv, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# columns offered in the picker, in a sensible reading order; the first six are on by default
DEFAULT_COLS = [
    "volume_fraction.ecs_fraction",
    "ecs_width.narrow_percentiles_nm_p50",
    "ecs_width.narrow_std_nm",
    "voronoi_gap.percentiles_nm_p50",
    "sa_v.sa_v_ecs_per_nm",
    "topology.protrusion_density_per_um2",
]

EXTRA = """<script src="membranes/three.min.js"></script>
<script src="membranes/OrbitControls.js"></script>
<script src="membranes/colormaps.js"></script>
<script src="assets/viewer.js?v=__VER__"></script>
<style>
 /* Layout tiers.
    Wide: table | A | B in three columns, divider draggable.
    Medium: the old breakpoint was 1000px, which is exactly the width of a
    half-screen window on a laptop -- it collapsed all three to one column and
    put B a screen and a half below the fold. Instead the table moves to a
    capped strip on top and the two viewers stay side by side, because seeing
    two patches at once is the whole point of the page.
    Narrow: everything stacks. */
 .hub{display:grid;grid-template-columns:var(--tablew,460px) 6px 1fr 1fr;
   grid-template-rows:auto 1fr;
   grid-template-areas:"bar bar bar bar"
                       "tbl gut a   b";
   gap:0;height:calc(100vh - 230px);min-height:400px;
   border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden;
   background:var(--bg)}
 .hub.solo{grid-template-columns:var(--tablew,460px) 6px 1fr;
   grid-template-areas:"bar bar bar"
                       "tbl gut a"}
 .tablecol{grid-area:tbl;overflow:auto;background:var(--bg);min-width:0;min-height:0}
 .tablecol table{font-size:12.5px}
 /* the header row is as tall as its tallest cell, and a wrapped metric label
    three columns off to the right left a blank band above the visible ones --
    the column scrolls horizontally anyway, so let the labels run */
 .tablecol th{position:sticky;top:0;background:var(--bg);z-index:4;
   white-space:nowrap;vertical-align:bottom;box-shadow:0 1px 0 var(--rule-strong)}
 .tablecol th,.tablecol td{padding:6px 10px 6px 0}
 .tablecol td:first-child,.tablecol th:first-child{padding-left:10px}
 .gutter{grid-area:gut;background:var(--rule);cursor:col-resize;position:relative}
 .gutter:hover,.gutter.drag{background:var(--accent)}
 .gutter::after{content:"";position:absolute;inset:0 -5px;cursor:col-resize}

 /* the panels: a header that says which slot and which crop, the render
    filling everything left over, and one line of provenance underneath */
 #pA{grid-area:a} #pB{grid-area:b}
 .vpanel{display:flex;flex-direction:column;min-width:0;min-height:0;
   border-left:1px solid var(--rule);background:var(--raise)}
 .vhead{display:flex;gap:7px;align-items:center;padding:5px 8px;
   border-bottom:1px solid var(--rule)}
 .vpanel.active .vhead{background:color-mix(in srgb,var(--accent) 9%,transparent)}
 .vhead .slot{font-size:10.5px;letter-spacing:.09em;color:var(--ink-3);
   border:1px solid var(--rule-strong);border-radius:4px;padding:1px 7px}
 .vpanel.active .vhead .slot{background:var(--accent);border-color:var(--accent);color:#fff}
 .vhead .pick{flex:1;min-width:0;font:inherit;font-size:var(--t5);padding:3px 6px;
   background:var(--bg);color:var(--ink);border:1px solid var(--rule-strong);border-radius:5px}
 .vhead .btn{padding:2px 8px}
 .stage{flex:1;min-height:0;position:relative;overflow:hidden;
   background:radial-gradient(115% 85% at 50% 0%,var(--sunk),var(--bg))}
 .stage canvas{display:block;width:100%;height:100%}
 .vfoot{padding:4px 9px;font-size:10.5px;color:var(--ink-3);
   border-top:1px solid var(--rule);
   white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

 /* between about 940 and 1180 the three columns still fit -- the table just
    gives up width first. Collapsing this range was what put panel B a screen
    below the fold on a half-width laptop window. */
 @media(max-width:1180px){
   .hub{grid-template-columns:clamp(240px,var(--tablew,460px),38vw) 6px 1fr 1fr}
   .hub.solo{grid-template-columns:clamp(240px,var(--tablew,460px),38vw) 6px 1fr}
 }
 @media(max-width:940px){
   .hub,.hub.solo{grid-template-columns:1fr 1fr;
     grid-template-rows:auto minmax(120px,22vh) 1fr;
     grid-template-areas:"bar bar" "tbl tbl" "a b";min-height:460px}
   .hub.solo{grid-template-areas:"bar bar" "tbl tbl" "a a"}
   .gutter{display:none}
   .tablecol{border-bottom:1px solid var(--rule)}
   #pA{border-left:0}
 }
 @media(max-width:720px){
   .hub,.hub.solo{grid-template-columns:1fr;grid-template-rows:auto;
     grid-template-areas:"bar" "tbl" "a" "b";height:auto!important;min-height:0}
   .hub.solo{grid-template-areas:"bar" "tbl" "a"}
   .tablecol{max-height:300px}
   .vpanel{min-height:330px;border-left:0;border-top:1px solid var(--rule)}
 }
 /* the viewer controls sit inside the hub, directly over the panels they
    act on, instead of floating above the whole page */
 .vbar{grid-area:bar;display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap;
   padding:6px 10px;border-bottom:1px solid var(--rule);background:var(--raise)}
 .vbar select,.vbar input[type=number]{font:inherit;font-size:var(--t5);padding:3px 6px;
   background:var(--bg);color:var(--ink);border:1px solid var(--rule-strong);border-radius:5px}
 .vbar input[type=number]{width:76px}
 .vbar .rng{display:flex;gap:var(--s3);align-items:center}
 .vbar .rng[hidden]{display:none!important}
 .vbar select{max-width:none}
 /* the surface is a two-button segment, not a line in a menu */
 .seggroup{display:inline-flex}
 .seggroup .seg{border-radius:0;margin-left:-1px;position:relative}
 .seggroup .seg:first-child{border-radius:6px 0 0 6px;margin-left:0}
 .seggroup .seg:last-child{border-radius:0 6px 6px 0}
 .seggroup .seg.on{z-index:1}
 .seggroup .seg[disabled]{opacity:.4;cursor:not-allowed}
 .vbar optgroup{font-style:normal}
 .vbar .key{font-size:10.5px}
 .grow{flex:1 1 auto}
 .swatchbar{display:inline-flex;flex-direction:column;gap:2px}
 .swatchbar canvas{border-radius:3px;width:140px;height:11px;display:block}
 .swatchbar .ends{display:flex;justify-content:space-between;font-size:10px;color:var(--ink-3)}
 .btn{background:var(--raise);border:1px solid var(--rule-strong);color:var(--ink);
   border-radius:6px;padding:5px 11px;font:inherit;font-size:var(--t5);cursor:pointer}
 .btn:hover{border-color:var(--ink-3)}
 .btn.on{background:var(--accent);border-color:var(--accent);color:#fff}
 /* one line of page chrome. Everything that used to stack above the table --
    three rows of facet chips, a control row, two disclosure rows -- cost about
    620px before you saw a single render. It now opens on demand. */
 .toolbar{display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap;
   padding:0 0 var(--s3)}
 .toolbar input[type=search]{font:inherit;font-size:var(--t4);padding:5px 9px;min-width:240px;
   background:var(--raise);color:var(--ink);border:1px solid var(--rule-strong);border-radius:6px}
 .toolbar .tcount{font-size:var(--t4);color:var(--ink-3);font-variant-numeric:tabular-nums}
 .drawer{border:1px solid var(--rule);border-radius:var(--radius);
   background:var(--raise);margin:0 0 var(--s3);padding:var(--s3) var(--s4)}
 summary .n{margin-left:6px;font-variant-numeric:tabular-nums;opacity:.75}
 .facets{display:flex;gap:var(--s4);flex-wrap:wrap}
 .fgroup{display:flex;gap:5px;align-items:center;flex-wrap:wrap}
 .fgroup .flabel{font-size:var(--t5);color:var(--ink-3);text-transform:uppercase;
   letter-spacing:.07em;margin-right:2px}
 .chip{border:1px solid var(--rule-strong);background:var(--raise);color:var(--ink-2);
   border-radius:99px;padding:3px 10px;font-size:var(--t5);cursor:pointer;white-space:nowrap}
 .chip:hover{color:var(--ink)}
 .chip.on{background:var(--ink);border-color:var(--ink);color:var(--bg)}
 .chip .c{opacity:.55;margin-left:5px;font-variant-numeric:tabular-nums}
 details.tools{margin:var(--s3) 0}
 details.tools summary{cursor:pointer;font-size:var(--t4);color:var(--accent);list-style:none;
   display:inline-flex;gap:6px;align-items:center}
 details.tools summary::-webkit-details-marker{display:none}
 details.tools summary::before{content:"▸";transition:transform .15s;display:inline-block}
 details.tools[open] summary::before{transform:rotate(90deg)}
 .ranges{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
   gap:var(--s3) var(--s5)}
 .rrow label{display:block;font-size:var(--t5);color:var(--ink-3);margin-bottom:2px}
 .rrow .pair{display:flex;gap:6px;align-items:center}
 .rrow input[type=range]{flex:1;min-width:60px}
 .rrow .val{font-size:10.5px;color:var(--ink-3);font-variant-numeric:tabular-nums;min-width:96px}
 .colpick{display:flex;flex-wrap:wrap;gap:5px}
 /* a shallower title band: this page is a tool, not a piece of writing */
 .pagehead .inner{padding-top:var(--s4);padding-bottom:var(--s4)}
 .pagehead h1{font-size:26px;margin-bottom:4px}
 .pagehead p{font-size:var(--t4);max-width:80ch}
 main.after-head{padding-top:var(--s4)}
 #ngnote{margin:0 0 var(--s3)}
 tbody tr.sel{background:color-mix(in srgb,var(--accent) 14%,transparent)}
 tbody tr{cursor:pointer}
 td .cmp{opacity:0;font-size:10px;border:1px solid var(--rule-strong);border-radius:4px;
   padding:1px 6px;margin-left:8px;color:var(--ink-3)}
 tr:hover td .cmp{opacity:1}
 .ngcell{width:1%}
 a.nglink{display:inline-block;border:1px solid var(--rule-strong);border-radius:5px;
   padding:1px 7px;font-size:10.5px;letter-spacing:.06em;color:var(--ink-2)}
 a.nglink:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
 a.nglink[aria-disabled]{opacity:.35;pointer-events:none}
</style>"""


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def main():
    wide = [r for r in csv.DictReader((DOCS / "data" / "all_metrics_wide.csv").open())
            if r["run"] == "native"]
    mets = json.loads((DOCS / "data" / "metrics.json").read_text())["metrics"]
    manifest = json.loads((DOCS / "membranes" / "manifest_inspect.json").read_text())
    if not isinstance(manifest, list):
        manifest = next(v for v in manifest.values() if isinstance(v, list))
    mani = {e["crop"]: e for e in manifest}

    # the ECS surfaces, built by scripts/make_ecs_surfaces.py. Optional: the
    # page still builds without them, it just has no ECS views.
    ecs_path = DOCS / "membranes" / "manifest_ecs.json"
    ecs_mani = ({e["crop"]: e for e in json.loads(ecs_path.read_text())}
                if ecs_path.exists() else {})

    metric_cols = sorted(
        {k for r in wide for k, v in r.items() if "." in k and v not in ("", None)},
        key=lambda c: (mets.get(c.split(".", 1)[1], {}).get("label", c)))

    rows = []
    for r in sorted(wide, key=lambda x: x["crop"]):
        e = mani.get(r["crop"], {})
        rec = {
            "crop": r["crop"], "tissue": r["tissue"], "region": r["region_group"],
            "anatomy": r["anatomy"], "prep": r["prep"],
            "voxel": r["analysis_voxel_nm"],
            "hasMesh": bool(e),
            "m": {c: (float(r[c]) if r.get(c) not in ("", None) else None) for c in metric_cols},
        }
        rows.append(rec)

    cols_meta = {c: {"label": mets.get(c.split(".", 1)[1], {}).get("label", c),
                     "unit": mets.get(c.split(".", 1)[1], {}).get("unit", ""),
                     "blurb": mets.get(c.split(".", 1)[1], {}).get("blurb", "")}
                 for c in metric_cols}

    payload = json.dumps({"rows": rows, "cols": cols_meta,
                          "defaults": DEFAULT_COLS,
                          "mani": {k: {kk: v[kk] for kk in
                                       ("crop", "bin", "nverts", "nfaces", "ranges",
                                        "tissue", "prep", "region_group", "anatomy", "voxel_nm")
                                       if kk in v}
                                   for k, v in mani.items()},
                          "ecs": {k: {kk: v[kk] for kk in
                                      ("crop", "bin", "nverts", "nfaces", "ranges",
                                       "tissue", "prep", "region_group", "anatomy",
                                       "voxel_nm", "cube_nm", "box_nm", "ecs_frac")
                                      if kk in v}
                                  for k, v in ecs_mani.items()}}, separators=(",", ":"))

    html = sh.head("Crops — ECS preservation", 0, EXTRA.replace("__VER__", sh.VER))
    html += sh.nav("crops.html", 0)
    html += sh.pagehead("Crops",
        f"All {len(rows)} annotated crops, with the viewer alongside. Pick a view — the "
        "membrane, or the extracellular space itself — filter the table, click a row to load "
        "it, and compare two crops with the same colour range and a shared camera. "
        '<a href="reference.html#surfaces">How the two surfaces are built.</a> '
        '<a href="reference.html#metrics">What the metrics mean.</a>',
        wide=True)

    html += """<main class="wide after-head">
<div class="toolbar">
  <input type="search" id="q" placeholder="Search crop, tissue, region, anatomy…">
  <span class="tcount" id="count"></span>
  <details class="tools" data-panel="facets"><summary>Filters<span class="n" id="nfilt"></span></summary></details>
  <details class="tools" data-panel="ranges"><summary>Numeric ranges</summary></details>
  <details class="tools" data-panel="colpick"><summary>Columns</summary></details>
  <button class="btn" id="reset" type="button">Reset</button>
</div>
<div class="facets drawer" id="facets" hidden></div>
<div class="ranges drawer" id="ranges" hidden></div>
<div class="colpick drawer" id="colpick" hidden></div>
<div class="hub" id="hub">
  <div class="tablecol" id="tablecol">
    <table id="t"><thead></thead><tbody></tbody></table>
  </div>
  <div class="gutter" id="gutter" title="Drag to resize the table"></div>
  <div class="vbar">
    <span class="seggroup" id="vsurface" title="Which surface to show"></span>
    <select id="vview" title="What colours the surface"></select>
    <span class="rng" id="vrange"><input type="number" id="vlo" step="any" title="Colour range, low">
      <input type="number" id="vhi" step="any" title="Colour range, high">
      <button class="btn" id="vauto" type="button">Auto</button>
      <span class="swatchbar"><canvas id="vbar"></canvas>
        <span class="ends"><span id="vlolab"></span><span id="vhilab"></span></span></span></span>
    <span class="grow"></span>
    <button class="btn on" id="vcaps" type="button"
      title="The flat faces where the crop was cut. Solid shows the object; open lets you see in.">Cut faces solid</button>
    <button class="btn on" id="vlink" type="button"
      title="Both patches share one camera, so they stay at the same scale">Linked</button>
    <button class="btn" id="vswap" type="button" title="Swap the two panels">Swap</button>
    <button class="btn" id="vcompare" type="button">Single</button>
  </div>
  <div class="vpanel active" id="pA">
    <div class="vhead"><span class="slot">A</span><select class="pick"></select><button class="btn fit" type="button" title="Recentre this patch">Fit</button></div>
    <div class="stage"></div><div class="vfoot"></div>
  </div>
  <div class="vpanel" id="pB">
    <div class="vhead"><span class="slot">B</span><select class="pick"></select><button class="btn fit" type="button" title="Recentre this patch">Fit</button></div>
    <div class="stage"></div><div class="vfoot"></div>
  </div>
</div>
<p class="note" id="ngnote"></p>
<p class="note">Grey on a surface means the reading there is uncertain — a value whose
kernel reached the crop wall, or a channel that leaves the box. The ECS views are an 800 nm
cube of each crop at 8 nm, chosen to match the crop's own ECS fraction; the membrane views are
one cell's ECS-facing patch at 16 nm, in the crop's frame. Click a row to load it into the highlighted panel; <b>compare →</b> on a row sends
it to B. Drag the divider to widen the table. While the cameras are linked both patches are drawn
at the <b>same scale</b>, so a patch that looks smaller really is smaller — that is the point of
linking them. <b>Fit</b> recentres a patch; double-clicking a panel does the same.</p>
"""
    html += sh.footer(0) + '</main><div id="tip"></div>'
    html += '<script>const DATA=' + payload + ';</script>\n'
    html += '<script src="assets/crops.js?v=' + sh.VER + '"></script>\n'
    html += "</body></html>"
    (DOCS / "crops.html").write_text(html)
    print(f"built docs/crops.html ({len(rows)} crops, {len(metric_cols)} columns available)")


if __name__ == "__main__":
    main()
