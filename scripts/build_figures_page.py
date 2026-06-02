#!/usr/bin/env python3
"""
Build the figures gallery page (out/ecs-handoff/figures.html) — a dark-theme
gallery of every analysis graph the pipeline produces (per-metric strip plots,
the region-matched panels, the Fig 2 effect-size matrix, region vignettes, and
3D renders). Copies the referenced PNGs from figures/ into
out/ecs-handoff/figures/ so the page is self-contained for deployment.

    PYTHONPATH=. python scripts/build_figures_page.py
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "figures"
OUT_DIR = REPO / "out" / "ecs-handoff"
IMG_DIR = OUT_DIR / "figures"
OUT = OUT_DIR / "figures.html"

# (section title, blurb, [(filename, caption)])
SECTIONS = [
    ("Effect-size summary",
     "The headline results graphic: Cliff's δ for every metric family across the "
     "region-matched Chemical-vs-HPF comparisons.",
     [("fig2_effect_matrix.png",
       "Fig 2 — Cliff's δ effect-size matrix (region-matched comparisons × metric families). "
       "Warm = Chemical &gt; HPF, cool = HPF &gt; Chemical.")]),
    ("Per-metric, native resolution",
     "Chemical-vs-HPF strip plots, one dot per crop, grouped by tissue, at each crop's "
     "native voxel size.",
     [("native_volume_fraction.png", "ECS &amp; cell volume fraction, per tissue."),
      ("native_ecs_width.png", "ECS width — narrow-band percentiles (p25/p50/p75) and fraction &lt;200 nm."),
      ("native_voronoi_gap.png", "Voronoi gap percentiles and close-contact fractions (&lt;40 / &lt;80 nm)."),
      ("native_sa_v.png", "ECS surface-area-to-volume ratio and cell density."),
      ("native_topology.png", "Membrane topology — curvature, roughness, protrusion/indentation density."),
      ("native_anatomy_matched.png", "Region-matched comparison across the full metric suite.")]),
    ("Resolution-controlled (downsampled to 8 nm)",
     "The same comparisons after downsampling every crop to a common 8 nm voxel, to rule out "
     "resolution as a confounder.",
     [("matched_ecs_width.png", "ECS width at matched 8 nm."),
      ("matched_voronoi_gap.png", "Voronoi gap &amp; contact fractions at matched 8 nm."),
      ("matched_sa_v.png", "SA:V &amp; cell density at matched 8 nm."),
      ("matched_topology.png", "Membrane topology at matched 8 nm."),
      ("matched_anatomy_matched.png", "Region-matched comparison at matched 8 nm.")]),
    ("Region vignettes",
     "Per-region example panels for the anatomy-matched comparisons.",
     [("vignette_bile_canaliculus.png", "Liver — bile canaliculus."),
      ("vignette_hepatocyte_lateral.png", "Liver — hepatocyte lateral."),
      ("vignette_glomerular.png", "Kidney — glomerular interstitium."),
      ("vignette_cardiac_interstitial.png", "Heart — cardiac interstitial."),
      ("vignette_intercalated_disc.png", "Heart — intercalated disc.")]),
    ("3D renders",
     "Example ECS, cell-surface, and membrane-patch renders.",
     [("ecs3d_bile_canaliculus.png", "ECS volume — bile canaliculus."),
      ("cellsurf_crop1039_cell1.png", "Cell surface — crop1039 cell 1."),
      ("membrane_crop1039_cell1.png", "Membrane patch — crop1039 cell 1."),
      ("membrane_crop1072_cell1.png", "Membrane patch — crop1072 cell 1.")]),
]


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()

    sections_html = []
    missing = []
    for title, blurb, items in SECTIONS:
        figs = []
        for fname, caption in items:
            src = SRC / fname
            if not src.exists():
                missing.append(fname)
                continue
            shutil.copy2(src, IMG_DIR / fname)
            # Content-hash query string so browsers re-fetch when a render
            # changes (filenames are stable, so without this the old image
            # stays cached).
            ver = hashlib.md5(src.read_bytes()).hexdigest()[:8]
            figs.append(
                f"<figure><a href='figures/{fname}?v={ver}' target=_blank>"
                f"<img src='figures/{fname}?v={ver}' loading=lazy alt='{caption}'></a>"
                f"<figcaption>{caption}</figcaption></figure>")
        if figs:
            sections_html.append(
                f"<section><h2>{title}</h2><p class=blurb>{blurb}</p>"
                f"<div class=grid>{''.join(figs)}</div></section>")

    html = f"""<!doctype html><meta charset=utf-8>
<title>ECS preservation — figures</title>
<style>
 :root{{--bg:#0f1420;--card:#1a2030;--card2:#222b3e;--ink:#e8ecf3;--muted:#8a93a6;
   --line:#2a3346;--accent:#5b9cff;--head:#cfe0ff}}
 *{{box-sizing:border-box}}
 body{{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:var(--bg);color:var(--ink);line-height:1.5}}
 nav.bar{{background:linear-gradient(135deg,#16243f,#1d3a33);border-bottom:1px solid var(--line);
   padding:12px 32px;font-size:13px;display:flex;gap:14px}}
 nav.bar a{{color:var(--accent);text-decoration:none;font-weight:600}}
 nav.bar a:hover{{text-decoration:underline}}
 header{{padding:22px 32px 4px}} header h1{{margin:0 0 6px;font-size:23px}}
 header p{{margin:0;color:#c4ccda;font-size:14px;max-width:820px}}
 main{{padding:8px 32px 48px}} section{{margin-top:30px}}
 h2{{font-size:17px;color:var(--head);border-bottom:1px solid var(--line);padding-bottom:6px}}
 .blurb{{color:var(--muted);font-size:13px;margin:6px 0 14px;max-width:820px}}
 .grid{{display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start}}
 figure{{margin:0;width:420px;max-width:100%;background:var(--card);border:1px solid var(--line);
   border-radius:12px;padding:12px;box-shadow:0 1px 4px rgba(0,0,0,.25)}}
 figure img{{width:100%;height:auto;border-radius:8px;background:#fff;display:block}}
 figcaption{{font-size:12.5px;color:#c0c8d6;margin-top:9px;line-height:1.5}}
 footer{{padding:0 32px 32px;color:var(--muted);font-size:12px}}
</style>
<nav class=bar>
 <a href='home.html'>⌂ project home</a>
 <a href='index.html'>crop directory</a>
 <a href='sanity-check.html'>sanity check</a>
 <a href='membranes/methods.html'>methods &amp; results</a>
</nav>
<header>
 <h1>Analysis figures</h1>
 <p>Every quantitative graph the pipeline produces: per-metric Chemical-vs-HPF strip plots
 (native and resolution-matched), the region-matched effect-size matrix, region vignettes,
 and example 3D renders. Click any figure to open it full-size.</p>
</header>
<main>{''.join(sections_html)}</main>
<footer>Last updated {today}{' · missing: ' + ', '.join(missing) if missing else ''}</footer>
"""
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(html):,} bytes); copied {sum(len(s[2]) for s in SECTIONS) - len(missing)} figures"
          + (f"; MISSING {missing}" if missing else ""))


if __name__ == "__main__":
    main()
