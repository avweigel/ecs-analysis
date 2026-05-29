#!/usr/bin/env python3
"""
Batch-render the ECS-facing membrane patch for every active crop and build an
HTML gallery to review them all in one place.

Renders are written to figures/membranes/membrane_<crop>.png, metadata to
figures/membranes/manifest.json, and the gallery to
figures/membranes/index.html (grouped by tissue -> region -> prep). The
manifest + HTML are rewritten after each crop so progress is viewable mid-run.

Usage:
    python scripts/render_all_membranes.py
    python scripts/render_all_membranes.py --crops crop1039 crop1072   # subset
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
from scripts.render_membrane_patch import render_membrane

OUT_DIR = Path(__file__).resolve().parents[1] / "figures" / "membranes"
TISSUE_ORDER = ["Liver", "Heart", "Kidney", "Cortex"]

# Shared Methods blurb (kept in sync with scripts/make_membrane_glbs.py).
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
    ok = [r for r in records if r.get("image")]
    err = [r for r in records if not r.get("image")]

    def tkey(r):
        t = r["tissue"]
        return (TISSUE_ORDER.index(t) if t in TISSUE_ORDER else 99, t,
                r.get("region_group") or "~", r.get("prep") or "")

    ok.sort(key=tkey)
    parts = ["""<!doctype html><meta charset=utf-8>
<title>ECS membrane patches</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;background:#f7f8fa;color:#1a1d21}
 h1{font-size:20px} h2{margin-top:32px;border-bottom:1px solid #d7dbe0;padding-bottom:4px}
 h3{color:#1565c0;margin:18px 0 8px} .grid{display:flex;flex-wrap:wrap;gap:18px}
 .card{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px;width:560px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
 .card img{width:100%;border-radius:4px;background:#fff;cursor:zoom-in}
 .meta{font-size:12px;color:#555b63;margin-top:6px;line-height:1.5}
 .tag{display:inline-block;background:#eef1f5;border-radius:4px;padding:1px 6px;margin-right:4px}
 .chem{color:#d9480f;font-weight:600} .hpf{color:#1971c2;font-weight:600}
 .err{color:#c92a2a} a{color:#1971c2}
 .methods{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px 16px;margin:14px 0;max-width:920px}
 .methods summary{font-weight:600;cursor:pointer;color:#1565c0;font-size:14px}
 .methods p{font-size:13px;color:#333;line-height:1.55} .methods ul{margin:8px 0 0;padding-left:18px}
 .methods li{font-size:13px;color:#333;line-height:1.6;margin:4px 0}
</style>
<h1>ECS-facing membrane patches — all crops</h1>
<p><a href="../home.html">&larr; project home</a> ·
<b><a href="membranes_3d.html">interactive 3D version</a></b> (rotate/zoom each patch)</p>
<p>Each card shows three maps of the same membrane patch: signed curvature, protrusion/indentation,
and gap-to-nearest-cell. Click an image to open full size.</p>
""" + METHODS + """
"""]
    parts.append(f"<p><b>{len(ok)}</b> rendered"
                 + (f", <span class=err>{len(err)} failed</span>" if err else "")
                 + ".</p>")

    last_t = last_r = None
    for r in ok:
        if r["tissue"] != last_t:
            parts.append(f"<h2>{escape(r['tissue'])}</h2>")
            last_t, last_r = r["tissue"], None
        rg = r.get("region_group") or "(unassigned)"
        if rg != last_r:
            parts.append(f"<h3>{escape(rg)}</h3><div class='grid'>")
            if last_r is not None:
                parts.insert(-1, "")  # noop, keep simple
            last_r = rg
        prep_cls = "chem" if r["prep"] == "Chemical" else "hpf"
        parts.append(
            f"<div class=card><a href='{escape(r['image'])}' target=_blank>"
            f"<img src='{escape(r['image'])}'></a>"
            f"<div class=meta>"
            f"<span class='tag {prep_cls}'>{escape(r['prep'])}</span>"
            f"<span class=tag>{escape(r['crop'])}</span>"
            f"cell {r['cell']} &middot; ECS frac {r['ecs_frac']} &middot; "
            f"patch {r['patch_faces']:,}/{r['total_faces']:,} faces "
            f"({int(r['ecs_facing_frac']*100)}% ECS-facing) &middot; "
            f"{r['n_cells']} cells &middot; {r['voxel_nm']:.0f} nm"
            f"{(' &middot; ' + escape(r['anatomy'])) if r.get('anatomy') else ''}"
            f"</div></div>")
    parts.append("</div>")

    if err:
        parts.append("<h2 class=err>Failed</h2><ul>")
        for r in err:
            parts.append(f"<li class=err>{escape(r['crop'])} "
                         f"({escape(r.get('tissue',''))}/{escape(r.get('prep',''))}): "
                         f"{escape(r.get('error',''))}</li>")
        parts.append("</ul>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", nargs="*", default=None)
    ap.add_argument("--voxel", type=float, default=8.0)
    ap.add_argument("--scale", type=float, default=60.0)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    crops = list(cfg.active_crops())
    if args.crops:
        wanted = set(args.crops)
        crops = [c for c in crops if c.crop in wanted]

    records: list[dict] = []
    for i, crop in enumerate(crops, 1):
        img = OUT_DIR / f"membrane_{crop.crop}.png"
        try:
            meta = render_membrane(crop, img, voxel=args.voxel, scale=args.scale)
            records.append(meta)
            print(f"[{i}/{len(crops)}] {crop.crop} OK "
                  f"({meta['patch_faces']:,} faces)", flush=True)
        except Exception as e:  # noqa: BLE001 - keep batch going, record failure
            records.append({"crop": crop.crop, "tissue": crop.tissue,
                            "prep": crop.prep, "region_group": crop.region_group,
                            "error": f"{type(e).__name__}: {e}"})
            print(f"[{i}/{len(crops)}] {crop.crop} FAILED: {e}", flush=True)
            traceback.print_exc()
        (OUT_DIR / "manifest.json").write_text(json.dumps(records, indent=1))
        (OUT_DIR / "index.html").write_text(build_html(records))

    print(f"\nDone. Gallery: {OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
