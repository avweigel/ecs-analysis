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
<li><b>Signed curvature (1/nm).</b> Mean curvature from the cotangent Laplacian.
<b style="color:#b2182b">Red = convex</b> (membrane bulges into ECS, e.g. microvilli);
<b style="color:#2166ac">blue = concave</b> (invagination). A dense microvillus brush reads
strongly convex.</li>
<li><b>Protrusion / indentation (nm).</b> Per-vertex displacement of the surface from a
~60&nbsp;nm smoothed reference. <b style="color:#b2182b">Red = protrusion</b> (bulges outward
into ECS); <b style="color:#2166ac">blue = indentation</b> (pit). Highlights fine features
relative to the local mean surface.</li>
<li><b>Contact gap (nm).</b> Distance from each membrane point to the nearest <i>neighbouring</i>
cell. <b>Dark/purple = tight apposition</b> (close cell&ndash;cell contact);
<b style="color:#b8a000">yellow = open extracellular space</b>.</li>
</ul></details>"""


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
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;background:#f7f8fa;color:#1a1d21}
 h1{font-size:20px} h2{margin-top:32px;border-bottom:1px solid #d7dbe0;padding-bottom:4px}
 h3{color:#1565c0;margin:18px 0 8px} .grid{display:flex;flex-wrap:wrap;gap:18px}
 .card{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px;width:420px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
 model-viewer{width:100%;height:380px;background:#fff;border-radius:4px;--poster-color:#fff}
 .meta{font-size:12px;color:#555b63;margin-top:6px;line-height:1.5}
 .tag{display:inline-block;background:#eef1f5;border-radius:4px;padding:1px 6px;margin-right:4px}
 .chem{color:#d9480f;font-weight:600} .hpf{color:#1971c2;font-weight:600}
 .btns{margin-top:6px} .btns button{font-size:12px;border:1px solid #cdd3da;background:#fff;
   border-radius:4px;padding:3px 8px;margin-right:4px;cursor:pointer}
 .btns button.active{background:#1565c0;color:#fff;border-color:#1565c0}
 .methods{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px 16px;margin:14px 0;max-width:920px}
 .methods summary{font-weight:600;cursor:pointer;color:#1565c0;font-size:14px}
 .methods p{font-size:13px;color:#333;line-height:1.55} .methods ul{margin:8px 0 0;padding-left:18px}
 .methods li{font-size:13px;color:#333;line-height:1.6;margin:4px 0}
 a{color:#1971c2}
</style>
<h1>ECS-facing membrane patches — interactive 3D</h1>
<p><a href="../home.html">&larr; project home</a> ·
<b><a href="index.html">static map gallery</a></b> ·
<b><a href="inspector.html">adjustable-scale inspector</a></b></p>
<p>Drag to rotate, scroll to zoom. Each card loads on scroll (poster = the static maps).
Toggle the surface coloring with the buttons.</p>
""" + METHODS + """
"""
    parts = [head]
    last_t = last_r = None
    for r in ok:
        if r["tissue"] != last_t:
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
            f"<button class='{'active' if s == default else ''}' "
            f"onclick=\"pick('{c}','{s}',this)\">{SCALAR_LABELS[s]}</button>"
            for s in r["glbs"])
        parts.append(
            f"<div class=card>"
            f"<model-viewer id='mv-{c}' src='glb/{escape(r['glbs'][default])}' "
            f"poster='membrane_{c}.png' camera-controls touch-action='pan-y' "
            f"loading='lazy' shadow-intensity='1' exposure='0.95' "
            f"environment-image='neutral' interaction-prompt='none'></model-viewer>"
            f"<div class=btns>{btns}</div>"
            f"<div class=meta>"
            f"<span class='tag {prep_cls}'>{escape(r['prep'])}</span>"
            f"<span class=tag>{escape(c)}</span>"
            f"cell {r['cell']} &middot; ECS frac {r['ecs_frac']} &middot; "
            f"{r['patch_faces']:,} faces &middot; {r['voxel_nm']:.0f} nm"
            f"{(' &middot; ' + escape(r['anatomy'])) if r.get('anatomy') else ''}"
            f" &middot; <a href='membrane_{c}.png' target=_blank>maps</a>"
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
