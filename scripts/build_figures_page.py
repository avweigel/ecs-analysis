#!/usr/bin/env python3
"""Build docs/figures.html — the plot gallery, on the shared site shell.
Each figure is captioned with what it shows and how to read it."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

ROOT = Path(__file__).resolve().parent.parent
FIGDIR = ROOT / "docs" / "figures"

SECTIONS = [
    # What the explorer cannot be. Twelve per-metric panels used to sit here
    # (native_* and matched_*) and every one of them was a worse version of a
    # dot plot the explorer draws live, for any metric, at any grouping. They
    # are gone. What is left is the three things one dot plot cannot do: all
    # the metrics at once, all the metrics for one region at once, and a
    # picture of the geometry itself.
    ("Every metric at once", [
        ("effect_matrix.png", "Effect-size matrix",
         "Cliff's delta for every metric family across the region-matched comparison. "
         "Delta runs from -1 to 1; zero means the two preparations are indistinguishable. "
         "Direction and size, not significance &mdash; several regions have an arm of one, "
         "so read the effect, not the p."),
    ]),
    ("One region, every metric", [
        ("vignette_bile_canaliculus.png", "Bile canaliculus", "Liver, chemical vs HPF."),
        ("vignette_hepatocyte_lateral.png", "Hepatocyte lateral", "Liver, the largest matched group."),
        ("vignette_glomerular.png", "Glomerular", "Kidney."),
        ("vignette_cardiac_interstitial.png", "Cardiac interstitial", "Heart."),
        ("vignette_intercalated_disc.png", "Intercalated disc", "Heart."),
    ]),
    ("Pictures of the geometry", [
        ("ecs3d_bile_canaliculus.png", "Extracellular space in 3D",
         "The space itself rendered as a solid, rather than the membranes around it."),
        ("cellsurf_crop1039_cell1.png", "Cell surface", "A single segmented cell."),
        ("membrane_crop1039_cell1.png", "Membrane patch, crop1039", "Curvature on one ECS-facing patch."),
        ("membrane_crop1072_cell1.png", "Membrane patch, crop1072", "The same view in another crop."),
    ]),
]


EXTRA_LINE = {
    "Pictures of the geometry":
        '<p class="lede" style="margin-bottom:var(--s4)">These are stills. '
        '<a href="membranes/views.html">Paired 3D views</a> puts one crop of each '
        'preparation side by side per region, and the <a href="crops.html">crop page</a> '
        'will load any two of the 55 into a viewer you can turn.</p>',
}

SLUGS = {"Every metric at once": "matrix",
         "One region, every metric": "vignettes",
         "Pictures of the geometry": "renders"}


def main():
    body, missing, n = "", [], 0
    for title, figs in SECTIONS:
        cards = ""
        for fn, label, blurb in figs:
            if not (FIGDIR / fn).exists():
                missing.append(fn)
                continue
            n += 1
            cards += (f'<figure class="fig"><a href="figures/{fn}" target="_blank" rel="noopener">'
                      f'<img src="figures/{fn}" loading="lazy" alt="{label}"></a>'
                      f'<figcaption><b>{label}</b><span>{blurb}</span></figcaption></figure>')
        if cards:
            slug = SLUGS.get(title, "")
            head = f'<h2 id="{slug}">{title}</h2>' if slug else f'<h2>{title}</h2>'
            body += head + EXTRA_LINE.get(title, "") + f'<div class="figs">{cards}</div>'

    extra = """<style>
 .figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
 .fig{margin:0;background:var(--raise);border:1px solid var(--rule);border-radius:10px;
      overflow:hidden;display:flex;flex-direction:column}
 .fig img{width:100%;display:block;background:#fff}
 .fig figcaption{padding:11px 14px;font-size:13px;color:var(--ink-2);
                 border-top:1px solid var(--rule)}
 .fig figcaption b{display:block;color:var(--ink);margin-bottom:2px;font-size:13.5px}
</style>"""
    html = sh.head("Quantification — ECS preservation", 0, extra)
    html += sh.nav("figures.html", 0)
    html += sh.pagehead("Quantification",
        "Every plot the pipeline draws, with what it shows and the caveat that goes with it. "
        "Click any panel for the full-resolution version. These are pipeline output, not "
        "assembled figures &mdash; nothing here is numbered and nothing is final. For one "
        'metric at a time, per crop, the <a href="explore.html">explorer</a> does it live and '
        "does it better; this page is for what a single dot plot cannot show &mdash; every "
        "metric at once, the paired region vignettes, and the 3D renders.", wide=True)
    html += f"""<main class="wide after-head">
{sh.PREP_LEGEND}
{body}
"""
    html += sh.tail(0)
    (ROOT / "docs" / "figures.html").write_text(html)
    print(f"built docs/figures.html ({n} panels)"
          + (f", {len(missing)} missing: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
