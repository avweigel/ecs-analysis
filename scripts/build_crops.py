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
<script src="assets/viewer.js"></script>
<style>
 /* three columns: table, then the two viewers. The divider between the table
    and the viewers is draggable, and the width is remembered. */
 .hub{display:grid;grid-template-columns:var(--tablew,460px) 6px 1fr 1fr;
   gap:0;height:calc(100vh - 210px);min-height:520px;
   border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden}
 .hub.solo{grid-template-columns:var(--tablew,460px) 6px 1fr}
 .tablecol{overflow:auto;background:var(--bg);min-width:0}
 .tablecol table{font-size:12.5px}
 .tablecol th{position:sticky;top:0;background:var(--bg);z-index:4;
   box-shadow:0 1px 0 var(--rule-strong)}
 .tablecol th,.tablecol td{padding:6px 10px 6px 0}
 .tablecol td:first-child,.tablecol th:first-child{padding-left:10px}
 .gutter{background:var(--rule);cursor:col-resize;position:relative}
 .gutter:hover,.gutter.drag{background:var(--accent)}
 .gutter::after{content:"";position:absolute;inset:0 -5px;cursor:col-resize}
 @media(max-width:1000px){
   .hub,.hub.solo{grid-template-columns:1fr;height:auto}
   .gutter{display:none}
   .tablecol{max-height:420px}
   .vpanel{min-height:340px}
 }
 .vbar{display:flex;gap:var(--s4);align-items:center;flex-wrap:wrap;
   padding:var(--s3) 0;border-bottom:1px solid var(--rule);margin-bottom:var(--s3)}
 .vbar label{font-size:var(--t5);color:var(--ink-3);text-transform:uppercase;letter-spacing:.07em}
 .vbar .rng{display:flex;gap:6px;align-items:center}
 .vbar input[type=number]{width:78px;font-size:var(--t5);padding:4px 6px;
   background:var(--raise);color:var(--ink);border:1px solid var(--rule-strong);border-radius:5px}
 .swatchbar{display:flex;flex-direction:column;gap:2px}
 .swatchbar canvas{border-radius:3px;width:190px;height:12px}
 .swatchbar .ends{display:flex;justify-content:space-between;font-size:10.5px;color:var(--ink-3)}
 .btn{background:var(--raise);border:1px solid var(--rule-strong);color:var(--ink);
   border-radius:6px;padding:5px 11px;font:inherit;font-size:var(--t5);cursor:pointer}
 .btn:hover{border-color:var(--ink-3)}
 .btn.on{background:var(--accent);border-color:var(--accent);color:#fff}
 .facets{display:flex;gap:var(--s4);flex-wrap:wrap;padding:var(--s3) 0}
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
   gap:var(--s3) var(--s5);padding:var(--s3) 0}
 .rrow label{display:block;font-size:var(--t5);color:var(--ink-3);margin-bottom:2px}
 .rrow .pair{display:flex;gap:6px;align-items:center}
 .rrow input[type=range]{flex:1;min-width:60px}
 .rrow .val{font-size:10.5px;color:var(--ink-3);font-variant-numeric:tabular-nums;min-width:96px}
 .colpick{display:flex;flex-wrap:wrap;gap:5px;padding:var(--s3) 0}
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
                                   for k, v in mani.items()}}, separators=(",", ":"))

    html = sh.head("Crops — ECS preservation", 0, EXTRA)
    html += sh.nav("crops.html", 0)
    html += sh.pagehead("Crops",
        f"All {len(rows)} annotated crops, with the membrane viewer alongside. Filter the table, "
        "click a row to load it, and use compare to put two crops side by side with the same "
        'colour range and a shared camera. <a href="reference.html#metrics">What the metrics mean.</a>',
        wide=True)

    html += """<main class="wide after-head">
<div class="facets" id="facets"></div>
<div class="controls" style="border:0;padding:0 0 var(--s3)">
  <div class="ctl"><label for="q">Search</label>
    <input type="search" id="q" placeholder="crop, tissue, region, anatomy…" style="min-width:230px"></div>
  <div class="ctl"><label>Showing</label>
    <span id="count" class="muted" style="font-size:var(--t4);padding:6px 0"></span></div>
  <div class="ctl"><label>&nbsp;</label><button class="btn" id="reset" type="button">Reset</button></div>
  <div class="ctl"><label>&nbsp;</label>
    <details class="tools" style="margin:0"><summary>Numeric ranges</summary></details></div>
  <div class="ctl"><label>&nbsp;</label>
    <details class="tools" style="margin:0"><summary>Columns</summary></details></div>
  <div class="ctl"><label>Neuroglancer source</label>
    <span id="ngsource" style="display:flex;gap:5px;padding:3px 0"></span></div>
</div>
<p class="note" id="ngnote" style="margin-top:0"></p>
<div class="ranges" id="ranges" hidden></div>
<div class="colpick" id="colpick" hidden></div>

<div class="vbar">
  <div class="ctl"><label for="vscalar">Scalar</label>
    <select id="vscalar">
      <option value="gap">Gap to nearest cell</option>
      <option value="curvature">Signed curvature</option>
      <option value="deviation">Protrusion / indentation</option>
    </select></div>
  <div class="rng"><label for="vlo">Range</label>
    <input type="number" id="vlo" step="any"><input type="number" id="vhi" step="any">
    <button class="btn" id="vauto" type="button">Auto</button></div>
  <div class="swatchbar"><canvas id="vbar"></canvas>
    <div class="ends"><span id="vlolab"></span><span id="vhilab"></span></div></div>
  <button class="btn on" id="vlink" type="button">Cameras linked</button>
  <button class="btn" id="vcompare" type="button">Single view</button>
  <span class="muted" style="font-size:var(--t5)">grey = boundary-uncertain</span>
</div>

<div class="hub" id="hub">
  <div class="tablecol" id="tablecol">
    <table id="t"><thead></thead><tbody></tbody></table>
  </div>
  <div class="gutter" id="gutter" title="Drag to resize the table"></div>
  <div class="vpanel active" id="pA">
    <div class="vhead"><span class="slot">A</span><select class="pick"></select></div>
    <div class="stage"></div><div class="vfoot"></div>
  </div>
  <div class="vpanel" id="pB">
    <div class="vhead"><span class="slot">B</span><select class="pick"></select></div>
    <div class="stage"></div><div class="vfoot"></div>
  </div>
</div>
<p class="note">Click a row to load it into the highlighted panel; <b>compare →</b> on a row sends
it to B. Drag the divider to widen the table. While the cameras are linked both patches are drawn
at the <b>same scale</b>, so a patch that looks smaller really is smaller — that is the point of
linking them.</p>
"""
    html += sh.footer(0) + '</main><div id="tip"></div>'
    html += '<script>const DATA=' + payload + ';</script>\n'
    html += '<script src="assets/crops.js?v=' + sh.VER + '"></script>\n'
    html += "</body></html>"
    (DOCS / "crops.html").write_text(html)
    print(f"built docs/crops.html ({len(rows)} crops, {len(metric_cols)} columns available)")


if __name__ == "__main__":
    main()
