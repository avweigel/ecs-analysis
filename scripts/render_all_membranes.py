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
of <code>|H|</code> in this particular patch.</li>
<li><b>Protrusion / indentation (nm).</b> Per-vertex signed displacement of the actual
surface from a Gaussian-smoothed reference of the same surface
(<code>&sigma;&nbsp;&asymp;&nbsp;60&nbsp;nm</code>). Units are <i>nanometres</i>, not
<code>1/nm</code>: the value is literally "how far this vertex sits outside (red)
or inside (blue) its ~60&nbsp;nm smoothed neighbourhood." Scale-aware where curvature
isn't &mdash; a gentle 100&nbsp;nm-tall ridge shows large positive protrusion but low
curvature; a 5&nbsp;nm bump on flat membrane shows high curvature but tiny protrusion.</li>
<li><b>When the two agree vs. disagree.</b> Curvature answers <i>"is the surface bent
here, and which way?"</i> &mdash; protrusion answers <i>"does this point stick out (or in)
compared to its ~60&nbsp;nm neighbourhood?"</i>. On a microvillus brush both light up
together. On a slowly undulating surface only protrusion fires &mdash; the bends are
too gentle for curvature to read.</li>
<li><b>Contact gap (nm).</b> Distance from each membrane point to the nearest <i>neighbouring</i>
cell. <b>Dark/purple = tight apposition</b> (close cell&ndash;cell contact);
<b style="color:#b8a000">yellow = open extracellular space</b>. The in-volume distance
transform can't see neighbours that lie just outside the crop, so any vertex whose
reading exceeds its distance to the crop face is dropped from the gap panel — the
silhouette goes missing rather than getting painted with a fake "far" value. The
<code>bd-clip</code> badge on each card reports the fraction of patch vertices dropped.</li>
</ul></details>"""


def _load_outliers() -> dict:
    path = Path(__file__).resolve().parents[1] / "results" / "topology_outliers.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


OUTLIERS = _load_outliers()


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
 :root{--bg:#0f1420;--card:#1a2030;--card2:#222b3e;--ink:#e8ecf3;--muted:#8a93a6;
   --line:#2a3346;--accent:#5b9cff;--head:#cfe0ff}
 *{box-sizing:border-box}
 body{font-family:'Segoe UI',Tahoma,sans-serif;margin:24px;background:var(--bg);color:var(--ink);line-height:1.5}
 h1{font-size:22px;margin:0 0 6px}
 h2{margin-top:32px;border-bottom:1px solid var(--line);padding-bottom:4px;color:var(--head);font-size:19px}
 h3{color:var(--accent);margin:18px 0 8px;font-size:15px}
 .grid{display:flex;flex-wrap:wrap;gap:18px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;width:560px;
   box-shadow:0 1px 4px rgba(0,0,0,.25)}
 .card img{width:100%;border-radius:8px;background:#0a0f1c;cursor:zoom-in}
 .meta{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5}
 .tag{display:inline-block;background:var(--card2);border:1px solid var(--line);border-radius:4px;
   padding:1px 7px;margin-right:4px;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#cdd5e2}
 .chem{color:#ff8b4a;font-weight:600} .hpf{color:#7ec0ff;font-weight:600}
 .bd-clip{display:inline-block;background:#3d3424;color:#f0c870;border:1px solid #6b5a30;
   border-radius:4px;padding:0 6px;font-size:11px;font-weight:600;margin-right:4px}
 .bd-clip.high{background:#4d2e1c;color:#ffa46e;border-color:#7a4628}
 .outlier{display:inline-block;background:#3a1e1e;color:#ff8585;border:1px solid #6b3030;
   border-radius:4px;padding:0 6px;font-size:11px;font-weight:700;margin-right:4px;cursor:help}
 .err{color:#ff8585} a{color:var(--accent)}
 .methods{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 18px;margin:14px 0;max-width:980px}
 .methods summary{font-weight:600;cursor:pointer;color:var(--head);font-size:14px}
 .methods p{font-size:13px;color:#c0c8d6;line-height:1.6}
 .methods ul{margin:8px 0 0;padding-left:18px}
 .methods li{font-size:13px;color:#c0c8d6;line-height:1.65;margin:5px 0}
 .methods code{background:var(--card2);color:#d6deea;border-radius:3px;padding:1px 5px;
   font-family:ui-monospace,Menlo,monospace;font-size:12px}
</style>
<h1>ECS-facing membrane patches — all crops</h1>
<p><a href="../home.html">&larr; project home</a> ·
<b><a href="membranes_3d.html">interactive 3D version</a></b> (rotate/zoom each patch) ·
<b><a href="methods.html">full methods &amp; results</a></b></p>
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
        bd = r.get("gap_bounded_frac")
        bd_html = ""
        if bd is not None:
            cls = "bd-clip high" if bd >= 0.25 else "bd-clip"
            bd_html = (f"<span class='{cls}' title='Patch vertices dropped from "
                       f"the gap panel because the in-volume distance transform "
                       f"overstated the gap (true nearest neighbour likely sat "
                       f"outside the crop). High = most of the gap silhouette is "
                       f"missing.'>bd-clip {bd:.0%}</span>")
        outlier = OUTLIERS.get(r["crop"])
        outlier_html = ""
        if outlier:
            outlier_html = (
                f"<span class=outlier title='Topology outlier vs annotated peer "
                f"group ({escape(outlier['region_group'])} "
                f"{escape(outlier['prep'])}, n={outlier['group_n']}). "
                f"{escape(outlier['reason'])}.'>⚠ outlier</span>")
        parts.append(
            f"<div class=card><a href='{escape(r['image'])}' target=_blank>"
            f"<img src='{escape(r['image'])}'></a>"
            f"<div class=meta>"
            f"<span class='tag {prep_cls}'>{escape(r['prep'])}</span>"
            f"<span class=tag>{escape(r['crop'])}</span>"
            f"{outlier_html}"
            f"{bd_html}"
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
