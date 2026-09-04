#!/usr/bin/env python3
"""
Build the project landing/hub page (out/ecs-handoff/home.html) that links and
sorts every hosted page for the ECS preservation project. Static content; run
after adding or refreshing any page.

    PYTHONPATH=. python scripts/build_landing.py
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out" / "ecs-handoff" / "home.html"

# (section title, blurb, [(href, title, desc, badge)])
SECTIONS = [
    ("Crops & quality control", "Browse the FIB-SEM crops and check region-matched ECS summaries.", [
        ("index.html", "Crop directory",
         "All active crops with anatomical annotations, prep/tissue metadata, and "
         "click-through Neuroglancer viewer states. Inline annotation editing.", ""),
        ("sanity-check.html", "Matched-region sanity check",
         "Per-region and tissue-level ECS% summary tables, plus matched-region "
         "thumbnail grids with Chemical-vs-HPF dot plots.", ""),
        ("figures.html", "Figures gallery",
         "Every quantitative graph: per-metric Chemical-vs-HPF strip plots (native and "
         "resolution-matched), the effect-size matrix, region vignettes, and 3D renders.", ""),
    ]),
    ("Membrane topology — 3D", "The ECS-facing membrane of one representative cell per crop, "
     "characterized by curvature, protrusion/indentation, and contact gap.", [
        ("membranes/membranes_3d.html", "Interactive 3D gallery",
         "Rotate/zoom every crop's membrane patch; toggle the surface coloring "
         "between curvature, protrusion-indentation, and contact gap.", "recommended"),
        ("membranes/index.html", "Static map gallery",
         "Three quantitative maps per crop as images (curvature / protrusion-indentation "
         "/ contact gap), grouped tissue → region → prep.", ""),
        ("membranes/inspector.html", "Adjustable-scale inspector",
         "Single-mesh viewer with live colormap min/max sliders and a colorbar legend "
         "for rescaling any scalar in real time.", ""),
        ("membranes/methods.html", "Full methods &amp; results",
         "Long-form methods page mirroring the manuscript: pipeline, sign-convention "
         "calibration, boundary handling, per-tissue and region-matched result tables, "
         "and a comparison vs Metric 5 (Voronoi).", ""),
    ]),
    ("Contact sites", "Cell–cell apposition analysis.", [
        ("contacts.html", "Liver cell–cell contacts",
         "Hepatocyte-lateral cell–cell contact-site visualizations.", ""),
    ]),
]


def main() -> None:
    today = _dt.date.today().isoformat()
    cards = []
    for title, blurb, items in SECTIONS:
        rows = []
        for href, name, desc, badge in items:
            b = f"<span class=badge>{badge}</span>" if badge else ""
            rows.append(
                f"<a class=card href='{href}'><div class=ct>{name}{b}</div>"
                f"<div class=cd>{desc}</div><div class=cl>{href}</div></a>")
        cards.append(f"<section><h2>{title}</h2><p class=blurb>{blurb}</p>"
                     f"<div class=grid>{''.join(rows)}</div></section>")

    html = f"""<!doctype html><meta charset=utf-8>
<title>ECS preservation project — pages</title>
<style>
 :root{{--bg:#0f1420;--card:#1a2030;--card2:#222b3e;--ink:#e8ecf3;--muted:#8a93a6;
   --line:#2a3346;--accent:#5b9cff;--head:#cfe0ff}}
 *{{box-sizing:border-box}}
 body{{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:var(--bg);color:var(--ink);line-height:1.5}}
 header{{background:linear-gradient(135deg,#16243f,#1d3a33);border-bottom:1px solid var(--line);padding:30px 32px}}
 header h1{{margin:0 0 6px;font-size:24px;color:var(--ink)}}
 header p{{margin:0;color:#c4ccda;font-size:14px;max-width:760px;line-height:1.5}}
 main{{padding:8px 32px 40px}} section{{margin-top:28px}}
 h2{{font-size:17px;color:var(--head);border-bottom:1px solid var(--line);padding-bottom:6px}}
 .blurb{{color:var(--muted);font-size:13px;margin:6px 0 12px}}
 .grid{{display:flex;flex-wrap:wrap;gap:16px}}
 .card{{display:block;width:340px;background:var(--card);border:1px solid var(--line);border-radius:12px;
   padding:14px 16px;text-decoration:none;color:inherit;box-shadow:0 1px 4px rgba(0,0,0,.25);
   transition:box-shadow .15s,transform .15s,border-color .15s}}
 .card:hover{{box-shadow:0 6px 18px rgba(0,0,0,.35);transform:translateY(-1px);border-color:var(--accent)}}
 .ct{{font-weight:600;font-size:15px;color:var(--accent)}}
 .cd{{font-size:13px;color:#c0c8d6;margin:6px 0;line-height:1.55}}
 .cl{{font-size:11px;color:var(--muted);font-family:ui-monospace,Menlo,monospace}}
 .badge{{font-size:10px;background:var(--accent);color:#0a0f1c;border-radius:4px;padding:2px 6px;margin-left:8px;
   text-transform:uppercase;letter-spacing:.04em;font-weight:700}}
 footer{{padding:0 32px 32px;color:var(--muted);font-size:12px}}
</style>
<header>
 <h1>Extracellular space preservation — Chemical vs Rapid HPF</h1>
 <p>FIB-SEM analysis comparing extracellular space (ECS) and membrane morphology between
 chemical fixation and rapid high-pressure freezing across liver, heart, kidney, and cortex.
 Hosted pages for browsing crops, region-matched summaries, and 3D membrane topology.</p>
</header>
<main>{''.join(cards)}</main>
<footer>Last updated {today}</footer>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
