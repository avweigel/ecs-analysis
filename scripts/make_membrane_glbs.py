#!/usr/bin/env python3
"""
Export membrane-patch GLBs (one per scalar) and build an interactive
model-viewer gallery so the patches can be rotated/zoomed in the browser.

For each crop, exports figures/membranes/glb/<crop>_<scalar>.glb for
scalar in {curvature, deviation, gap}, vertex-colored to match the PNG maps,
meshed at a coarse voxel (web-friendly ~1-2 MB each). Builds
figures/membranes/membranes_3d.html (model-viewer, lazy-loaded, with a
per-card scalar toggle) and manifest_3d.json. The existing 3-panel PNG is
used as the poster so each card shows the quantitative maps until interacted.

Usage:
    python scripts/make_membrane_glbs.py                 # bile-canaliculus proof set
    python scripts/make_membrane_glbs.py --all           # every active crop
    python scripts/make_membrane_glbs.py --crops crop1039 crop1072
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
import urllib.parse
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from scripts.render_membrane_patch import SCALARS, build_patch, glb_from_patch

OUT_DIR = Path(__file__).resolve().parents[1] / "figures" / "membranes"
GLB_DIR = OUT_DIR / "glb"
TISSUE_ORDER = ["Liver", "Heart", "Kidney", "Cortex"]
PROOF = ["crop1039", "crop1040", "crop1042", "crop1072", "crop1073", "crop1074", "crop1075"]
SCALAR_LABELS = {"curvature": "Curvature", "deviation": "Protrusion/indent", "gap": "Contact gap"}

# Neuroglancer wiring (mirrors scripts/build_neuroglancer_index.py + the
# user's tuned example state). EM array names + native voxel sizes vary per
# dataset and have to be specified explicitly. Layouts: dimensions go in
# voxel units = dataset voxel size, so position [a,b,c] sits at (a*vx, …) nm.
DATA_BASE_NRS = "https://cellmap-vm1.int.janelia.org/nrs/data"
NG_BASE   = "https://neuroglancer-demo.appspot.com/"
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
# Per-dataset EM shader controls (manually tuned to make features visible).
# Pulled from the user's example state for kidney-4 and from build_neuro-
# glancer_index.py for cortex-3. Datasets without an entry fall back to
# NG's auto-range (which is often dark on uint16 EM).
EM_SHADER_CONTROLS = {
    "jrc_mus-kidney-4": {"normalized": {"range": [34645, 35894],
                                        "window": [34330, 36209]}},
    "jrc_mus-cortex-3": {"normalized": {"range": [1114, 884],
                                        "window": [-281, 1395]}},
}


def _ng_url(dataset: str, crop: str, cell_id: int,
            cell_ids: list[int] | None = None,
            translation_nm: list[float] | None = None,
            crop_shape_vox: list[int] | None = None,
            crop_voxel_nm: float | None = None) -> str:
    """Neuroglancer link tuned to match the user's reference state: white
    annotation chrome, EM contrast adjusted (per dataset), every cell's
    precomputed mesh pre-loaded, ECS shown as a silhouette mesh, camera
    centered on the crop ROI. The cell of interest gets highlighted by being
    listed first in the cell-layer's `segments` array (NG renders the
    layer's segments in list order so this gives the patch's cell a
    consistent visual anchor)."""
    if dataset not in EM_ARRAY:
        return ""
    vx_ng = DATASET_VOXEL_NM.get(dataset, 8)
    base = f"zarr://{DATA_BASE_NRS}/{dataset}/{dataset}.zarr/recon-1"
    gt   = f"{base}/labels/groundtruth/{crop}"
    # Precomputed-mesh URLs follow CellMap's per-dataset convention.
    mesh_root = (f"https://cellmap-vm1.int.janelia.org/nrs/data/{dataset}"
                 f"/neuroglancer/mesh/groundtruth/{crop}")
    cell_mesh = f"{mesh_root}/cell/|neuroglancer-precomputed:"
    ecs_mesh  = f"{mesh_root}/ecs/|neuroglancer-precomputed:"

    em_layer: dict = {
        "type": "image", "source": f"{base}/em/{EM_ARRAY[dataset]}",
        "tab": "annotations", "annotationColor": "#ffffff", "name": "em",
    }
    if dataset in EM_SHADER_CONTROLS:
        em_layer["shaderControls"] = EM_SHADER_CONTROLS[dataset]

    # All cell IDs visible as meshes; the patch's cell goes first so it's
    # the obvious anchor in the segments list.
    ids = list(cell_ids or [cell_id])
    ids_sorted = ([str(int(cell_id))]
                  + [str(int(i)) for i in ids if int(i) != int(cell_id)])

    layers = [
        em_layer,
        {"type": "segmentation", "source": f"{gt}/all",
         "tab": "annotations", "annotationColor": "#ffffff",
         "segments": [], "name": "all", "visible": False},
        {"type": "segmentation",
         "source": [f"{gt}/cell", cell_mesh],
         "tab": "source", "annotationColor": "#ffffff",
         "meshSilhouetteRendering": 3,
         "segments": ids_sorted, "name": "cell", "visible": False},
        {"type": "segmentation",
         "source": [f"{gt}/ecs", ecs_mesh],
         "tab": "rendering", "annotationColor": "#ffffff",
         "meshSilhouetteRendering": 2.2,
         "segments": ["1"], "name": "ecs"},
    ]
    state = {
        "dimensions": {"z": [vx_ng * 1e-9, "m"],
                       "y": [vx_ng * 1e-9, "m"],
                       "x": [vx_ng * 1e-9, "m"]},
        "layers": layers,
        "showSlices": False,
        "selectedLayer": {"visible": True, "layer": "ecs"},
        "layout": "4panel",
    }
    # Camera position centered on the crop ROI, in NG voxel units.
    if translation_nm and crop_shape_vox and crop_voxel_nm:
        center_nm = [translation_nm[i] + crop_shape_vox[i] * crop_voxel_nm / 2
                     for i in range(3)]
        state["position"] = [c / vx_ng for c in center_nm]
    return NG_BASE + "#!" + urllib.parse.quote(
        json.dumps(state, separators=(",", ":")), safe="")

# Shared Methods blurb (kept in sync with scripts/render_all_membranes.py).
METHODS = """
<details class=methods open><summary>Methods — what each analysis shows</summary>
<p>Each card is one representative cell's <b>extracellular-space (ECS)-facing membrane</b>
from a FIB-SEM crop, comparing <b style="color:#d9480f">Chemical</b> fixation vs
<b style="color:#1971c2">Rapid HPF</b> (high-pressure freezing). Per crop the cell with the
most ECS-facing surface is shown.</p>
<ul>
<li><b>Mesh.</b> The cell segmentation is surfaced by marching cubes and smoothed with a
physical-scale Gaussian (&sigma;&nbsp;&asymp;&nbsp;1.5&times;voxel). Surfaces are coarsened to
16&nbsp;nm voxels for the web (manuscript metrics use finer/native resolution). Only membrane
facing ECS is kept (vertices within ~1 voxel of extracellular space); cell&ndash;cell contacts
and crop-boundary cut faces are removed.</li>
<li><b>Signed curvature (1/nm).</b> Mean curvature from the cotangent Laplacian
&mdash; a strictly <i>local</i> 1-ring quantity (depends only on each vertex and its
immediate mesh neighbours, no smoothing scale). Sign is set by the outward normal:
<b style="color:#b2182b">red&nbsp;=&nbsp;convex</b> (membrane bulges into ECS, e.g. microvilli);
<b style="color:#2166ac">blue&nbsp;=&nbsp;concave</b> (invagination).
The numeric value <code>H</code> is the reciprocal of a radius:
the local membrane "fits" a sphere of radius <code>R&nbsp;=&nbsp;1/|H|</code>.
Worked examples &mdash; <code>H&nbsp;=&nbsp;0.005&nbsp;nm<sup>&minus;1</sup></code> &harr; <code>R&nbsp;=&nbsp;200&nbsp;nm</code>
(gentle membrane curvature);
<code>0.02&nbsp;nm<sup>&minus;1</sup></code> &harr; <code>50&nbsp;nm</code> (microvillus shaft);
<code>0.05&nbsp;nm<sup>&minus;1</sup></code> &harr; <code>20&nbsp;nm</code> (sharp microvillus tip);
<code>0.10&nbsp;nm<sup>&minus;1</sup></code> &harr; <code>10&nbsp;nm</code> (very sharp spike).
The colour limits are per&#8209;crop &mdash; the colourbar saturates at the 90th percentile
of <code>|H|</code> in this particular patch, so the brightest reds/blues are the sharpest
features <i>in this crop</i>, not a fixed absolute threshold.</li>
<li><b>Protrusion / indentation (nm).</b> Per-vertex signed displacement of the actual
surface from a Gaussian-smoothed reference of the same surface
(<code>&sigma;&nbsp;&asymp;&nbsp;60&nbsp;nm</code>). Units are <i>nanometres</i>, not
<code>1/nm</code>: the value is literally "how far this vertex sits outside (red)
or inside (blue) its ~60&nbsp;nm smoothed neighbourhood." This makes the channel
<i>scale-aware</i> in a way curvature is not &mdash; a gentle 100&nbsp;nm-tall ridge
shows large positive protrusion but low curvature; a 5&nbsp;nm-tall bump on flat
membrane shows high curvature but tiny protrusion.</li>
<li><b>When the two agree vs. disagree.</b> Curvature answers <i>"is the surface bent
here, and which way?"</i> &mdash; protrusion answers <i>"does this point stick out (or in)
compared to its ~60&nbsp;nm neighbourhood?"</i>. On a microvillus brush both light up
together (sharp tip + reaching shaft). On a slowly undulating surface only protrusion
fires &mdash; the bends are too gentle for curvature to read.</li>
<li><b>Contact gap (nm).</b> Distance from each membrane point to the nearest <i>neighbouring</i>
cell, computed as a 3D Euclidean distance transform. <b>Dark/purple = tight apposition</b>
(close cell&ndash;cell contact);
<b style="color:#b8a000">yellow = open extracellular space</b>.<br>
<i>Boundary handling.</i> The in-volume distance transform can't see neighbours
that lie just outside the crop, so any vertex whose gap exceeds its distance to
the crop face is dropped from the gap channel — silhouette goes missing rather
than getting painted with a fake value. The <code>bd-clip</code> badge reports the
fraction of patch vertices dropped.<br>
<i>Adaptive scale.</i> The colormap is anchored at 0&ndash;120&nbsp;nm so close-contact
crops are mutually comparable, but expands to the 95th percentile of the
kept-vertex gap distribution when a crop's ECS-facing surface genuinely sits
hundreds of nm away from any in-volume neighbour (e.g. a cell whose only contact
with another cell is a small disc and whose remaining surface faces open ECS).
The active upper bound is shown on each card (<code>gap N nm</code>). Curvature
and protrusion are local quantities and are kept everywhere.<br>
Use the per-card <b>Neuroglancer</b> link to inspect the raw EM and verify.</li>
</ul></details>"""


def _load_outliers() -> dict:
    """Load per-crop topology-outlier flags from
    results/topology_outliers.json so the gallery cards can surface them.
    Missing file = no flags (e.g. fresh checkout before running the
    aggregation script)."""
    path = Path(__file__).resolve().parents[1] / "results" / "topology_outliers.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


OUTLIERS = _load_outliers()


def build_html(records: list[dict]) -> str:
    ok = [r for r in records if r.get("glbs")]

    def tkey(r):
        t = r["tissue"]
        return (TISSUE_ORDER.index(t) if t in TISSUE_ORDER else 99, t,
                r.get("region_group") or "~", r.get("prep") or "")
    ok.sort(key=tkey)

    head = """<!doctype html><meta charset=utf-8>
<title>ECS membrane patches — interactive 3D</title>
<script type="module" src="model-viewer.min.js"></script>
<style>
 :root{--bg:#0f1420;--card:#1a2030;--card2:#222b3e;--ink:#e8ecf3;--muted:#8a93a6;
   --line:#2a3346;--accent:#5b9cff;--head:#cfe0ff}
 *{box-sizing:border-box}
 body{font-family:'Segoe UI',Tahoma,sans-serif;margin:24px;background:var(--bg);color:var(--ink);line-height:1.5}
 h1{font-size:22px;margin:0 0 4px;color:var(--ink)}
 h2{margin-top:32px;border-bottom:1px solid var(--line);padding-bottom:4px;color:var(--head);font-size:19px}
 h3{color:var(--accent);margin:18px 0 8px;font-size:15px}
 /* 3-column grid; collapses to 2 then 1 when the viewport gets narrow. */
 .grid{display:grid;grid-template-columns:repeat(3, minmax(0, 1fr));gap:18px}
 @media (max-width:1180px){ .grid{grid-template-columns:repeat(2, minmax(0, 1fr))} }
 @media (max-width: 760px){ .grid{grid-template-columns:1fr} }
 /* Cards fill their grid cell; flex column keeps the action row at the bottom. */
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;
   width:auto;min-width:0;display:flex;flex-direction:column;box-shadow:0 1px 4px rgba(0,0,0,.25)}
 model-viewer{width:100%;height:380px;border-radius:8px;
   background:radial-gradient(circle at 50% 40%,var(--card2),#141a28);--poster-color:transparent}
 .meta{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.45;
   display:flex;flex-direction:column;gap:3px}
 .meta-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0}
 .meta-row.id{font-size:12.5px;color:var(--ink)}
 .meta-row.stats{color:var(--muted);font-variant-numeric:tabular-nums}
 .meta-row.anat{color:var(--ink);font-style:italic}
 .tag{display:inline-block;background:var(--card2);border:1px solid var(--line);border-radius:4px;padding:1px 7px;
   font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#cdd5e2}
 .prep-tag{color:#fff;font-weight:600;border-radius:4px;padding:1px 7px;
   text-transform:uppercase;letter-spacing:.04em;font-size:10.5px}
 .prep-tag.chem{background:#d9480f} .prep-tag.hpf{background:#1971c2}
 .bd-clip{background:#3d3424;color:#f0c870;border:1px solid #6b5a30;border-radius:4px;
   padding:0 6px;font-size:10.5px;font-weight:600}
 .bd-clip.high{background:#4d2e1c;color:#ffa46e;border-color:#7a4628}
 /* Within-region outlier badge — surfaces crops whose |H| or |d| sits far
    from their annotated peer group's median. Hover reveals the reason. */
 .outlier{background:#3a1e1e;color:#ff8585;border:1px solid #6b3030;
   border-radius:4px;padding:0 6px;font-size:10.5px;font-weight:700;
   cursor:help;letter-spacing:.02em}
 .btns{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}
 .btns button{font-size:12px;border:1px solid var(--line);background:var(--card2);color:var(--ink);
   border-radius:4px;padding:3px 8px;cursor:pointer;font-family:inherit}
 .btns button:hover{background:#283250}
 .btns button.active{background:var(--accent);color:#0a0f1c;border-color:var(--accent)}
 .actions{margin-top:8px;display:flex;flex-wrap:wrap;gap:8px;font-size:12px;align-items:center}
 .actions a.ng{display:inline-block;background:#0d9488;color:#fff;padding:3px 9px;
   border-radius:4px;text-decoration:none;font-weight:600}
 .actions a.ng:hover{background:#0b7a70}
 .actions a.maps{color:var(--accent);text-decoration:none}
 .actions a.maps:hover{text-decoration:underline}
 .methods{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 18px;margin:14px 0;max-width:980px}
 .methods summary{font-weight:600;cursor:pointer;color:var(--head);font-size:14px}
 .methods p{font-size:13px;color:#c0c8d6;line-height:1.6}
 .methods ul{margin:8px 0 0;padding-left:18px}
 .methods li{font-size:13px;color:#c0c8d6;line-height:1.65;margin:5px 0}
 .methods code{background:var(--card2);color:#d6deea;border-radius:3px;padding:1px 5px;
   font-family:ui-monospace,Menlo,monospace;font-size:12px}
 a{color:var(--accent)}
 /* Sticky global-control strip so the scalar switcher stays available while
    scrolling through 50+ cards. */
 .global{position:sticky;top:0;z-index:10;background:rgba(15,20,32,.93);
   backdrop-filter:saturate(140%) blur(6px);padding:10px 0;margin:10px 0 6px;
   border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:10px;align-items:center}
 .global label{font-size:13px;color:var(--head);font-weight:600}
 .global button{font-size:13px;border:1px solid var(--accent);background:transparent;
   color:var(--accent);border-radius:5px;padding:4px 12px;cursor:pointer;font-family:inherit;font-weight:600}
 .global button:hover{background:rgba(91,156,255,.12)}
 .global button.active{background:var(--accent);color:#0a0f1c}
 .global .hint{color:var(--muted);font-weight:400;font-size:12px;margin-left:auto}
</style>
<h1>ECS-facing membrane patches — interactive 3D</h1>
<p><a href="../home.html">&larr; project home</a> ·
<b><a href="index.html">static map gallery</a></b> ·
<b><a href="../crops.html">crop page viewer</a></b> &middot;
<b><a href="methods.html">full methods &amp; results</a></b></p>
<p>Drag to rotate, scroll to zoom. Each card loads on scroll (poster = the static maps).
Use the buttons up top to recolor every card at once, or the per-card buttons for one.
Click <b>NG</b> on any card to open the underlying crop in Neuroglancer (cell of interest
is pre-selected; <code>cell</code> / <code>ecs</code> / <code>all</code> layers are wired in).</p>
<div class=global>
  <label>Color all cards by:</label>
  <button class=g-btn data-scalar=curvature onclick="setGlobal('curvature',this)">Curvature</button>
  <button class=g-btn data-scalar=deviation onclick="setGlobal('deviation',this)">Protrusion / indent</button>
  <button class=g-btn data-scalar=gap onclick="setGlobal('gap',this)">Contact gap</button>
  <span class=hint>per-card buttons still work; this just rewires every card in one click</span>
</div>
""" + METHODS + """
"""
    parts = [head]
    last_t = last_r = None
    for r in ok:
        if r["tissue"] != last_t:
            # Close the previous region's grid before starting a new tissue —
            # otherwise the new <h2> becomes a flex item inside the previous
            # tissue's open .grid div and renders alongside the cards.
            if last_r is not None:
                parts.append("</div>")
            parts.append(f"<h2>{escape(r['tissue'])}</h2>")
            last_t, last_r = r["tissue"], None
        rg = r.get("region_group") or "(unassigned)"
        if rg != last_r:
            if last_r is not None:
                parts.append("</div>")
            parts.append(f"<h3>{escape(rg)}</h3><div class='grid'>")
            last_r = rg
        c = r["crop"]
        default = "curvature" if "curvature" in r["glbs"] else next(iter(r["glbs"]))
        prep_cls = "chem" if r["prep"] == "Chemical" else "hpf"
        btns = "".join(
            f"<button data-scalar='{s}' class='{'active' if s == default else ''}' "
            f"onclick=\"pick('{c}','{s}',this)\">{SCALAR_LABELS[s]}</button>"
            for s in r["glbs"])
        ng = (_ng_url(r.get("dataset", ""), c, r["cell"],
                      cell_ids=r.get("cell_ids"),
                      translation_nm=r.get("translation_nm"),
                      crop_shape_vox=r.get("crop_shape_vox"),
                      crop_voxel_nm=r.get("voxel_nm"))
              if r.get("dataset") else "")
        ng_html = (f"<a class=ng href='{ng}' target=_blank "
                   f"title='Open this crop in Neuroglancer with cell {r['cell']} "
                   f"isolated — verify gap readings against the raw EM'>NG ↗</a>")
        bd = r.get("gap_bounded_frac")
        bd_html = ""
        if bd is not None:
            cls = "bd-clip high" if bd >= 0.25 else "bd-clip"
            bd_html = (f"<span class='{cls}' title='Fraction of patch vertices "
                       f"dropped from the gap channel because the in-volume "
                       f"distance transform overstated the gap (true nearest "
                       f"neighbour likely sat outside the crop). High = most of "
                       f"the gap silhouette is missing; treat the gap reading "
                       f"with caution.'>bd-clip {bd:.0%}</span>")
        outlier = OUTLIERS.get(c)
        outlier_html = ""
        if outlier:
            outlier_html = (
                f"<span class=outlier title='Topology outlier vs annotated peer "
                f"group ({escape(outlier['region_group'])} {escape(outlier['prep'])}, "
                f"n={outlier['group_n']}). {escape(outlier['reason'])}. "
                f"Consider re-annotating, splitting the region group, or "
                f"verifying the cell selection.'>⚠ outlier</span>")
        anat_html = (f"<div class='meta-row anat'>{escape(r['anatomy'])}</div>"
                     if r.get("anatomy") else "")
        glbs_attr = escape(json.dumps(r["glbs"]), quote=True)
        parts.append(
            f"<div class=card data-crop='{c}' data-glbs=\"{glbs_attr}\">"
            f"<model-viewer id='mv-{c}' src='glb/{escape(r['glbs'][default])}' "
            f"poster='membrane_{c}.png' camera-controls touch-action='pan-y' "
            f"loading='lazy' shadow-intensity='1' exposure='0.95' "
            f"environment-image='neutral' interaction-prompt='none'></model-viewer>"
            f"<div class=btns>{btns}</div>"
            f"<div class=meta>"
            f"<div class='meta-row id'>"
            f"<span class='prep-tag {prep_cls}'>{escape(r['prep'])}</span>"
            f"<span class=tag>{escape(c)}</span>"
            f"<span>cell {r['cell']}</span>"
            f"{outlier_html}"
            f"{bd_html}"
            f"</div>"
            f"<div class='meta-row stats'>"
            f"ECS frac {r['ecs_frac']} &middot; "
            f"{r['patch_faces']:,} faces &middot; {r['voxel_nm']:.0f} nm"
            f"{(' &middot; gap ' + str(int(r['gap_clim_nm'][1])) + ' nm') if r.get('gap_clim_nm') else ''}"
            f"</div>"
            f"{anat_html}"
            f"<div class='actions'>"
            f"{ng_html}"
            f"<a class=maps href='membrane_{c}.png' target=_blank>static maps ↗</a>"
            f"</div>"
            f"</div></div>")
    if last_r is not None:
        parts.append("</div>")
    parts.append("""
<script>
// Membrane patches are open surfaces; force every material double-sided so
// they don't vanish when viewed from the back. Reapplied on each (re)load.
function makeDoubleSided(mv){
  try { mv.model.materials.forEach(m => m.setDoubleSided(true)); } catch(e){}
}
document.querySelectorAll('model-viewer').forEach(mv => {
  mv.addEventListener('load', () => makeDoubleSided(mv));
});
function pick(crop, scalar, btn){
  document.getElementById('mv-'+crop).src = 'glb/'+crop+'_'+scalar+'.glb';
  btn.parentNode.querySelectorAll('button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}
// Rewire every card's model-viewer + per-card button state to one scalar in
// one click. Cards that don't have that scalar (shouldn't happen — we emit
// all three for every crop) are left alone.
function setGlobal(scalar, btn){
  document.querySelectorAll('.card').forEach(card => {
    const c = card.dataset.crop;
    const glbs = JSON.parse(card.dataset.glbs);
    if (!glbs[scalar]) return;
    const mv = document.getElementById('mv-'+c);
    if (mv.src.split('/').pop() !== glbs[scalar]) mv.src = 'glb/' + glbs[scalar];
    card.querySelectorAll('.btns button').forEach(b => {
      b.classList.toggle('active', b.dataset.scalar === scalar);
    });
  });
  document.querySelectorAll('.g-btn').forEach(b =>
    b.classList.toggle('active', b === btn));
}
</script>""")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--voxel", type=float, default=16.0)
    args = ap.parse_args()

    GLB_DIR.mkdir(parents=True, exist_ok=True)
    crops = list(cfg.active_crops())
    if not args.all:
        wanted = set(args.crops) if args.crops else set(PROOF)
        crops = [c for c in crops if c.crop in wanted]

    records: list[dict] = []
    for i, crop in enumerate(crops, 1):
        try:
            p = build_patch(crop, voxel=args.voxel)  # load + mesh once
            glbs = {}
            meta = None
            for scalar in SCALARS:
                m = glb_from_patch(p, GLB_DIR / f"{crop.crop}_{scalar}.glb", scalar)
                glbs[scalar] = m["glb"]
                meta = m
            rec = dict(meta); rec["glbs"] = glbs; rec.pop("glb", None)
            records.append(rec)
            print(f"[{i}/{len(crops)}] {crop.crop} OK ({meta['patch_faces']:,} faces x3)",
                  flush=True)
        except Exception as e:  # noqa: BLE001
            records.append({"crop": crop.crop, "tissue": crop.tissue,
                            "prep": crop.prep, "region_group": crop.region_group,
                            "error": f"{type(e).__name__}: {e}"})
            print(f"[{i}/{len(crops)}] {crop.crop} FAILED: {e}", flush=True)
            traceback.print_exc()
        (OUT_DIR / "manifest_3d.json").write_text(json.dumps(records, indent=1))
        (OUT_DIR / "membranes_3d.html").write_text(build_html(records))

    print(f"\nDone. Interactive gallery: {OUT_DIR / 'membranes_3d.html'}")


if __name__ == "__main__":
    main()
