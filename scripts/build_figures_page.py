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
    ("Effect sizes at a glance", [
        ("fig2_effect_matrix.png", "Effect-size matrix",
         "Cliff's delta for every metric family across the region-matched comparison. "
         "Delta runs from -1 to 1; zero means the two preparations are indistinguishable. "
         "This is a summary of direction and size, not of significance — read it "
         "alongside the group sizes, because several regions have an arm of one."),
    ]),
    ("Per metric, native resolution", [
        ("native_volume_fraction.png", "Volume fraction",
         "ECS and cell volume fractions per crop. The most resolution-robust family, so this "
         "is the one native-resolution panel that can be read fairly directly."),
        ("native_ecs_width.png", "ECS width",
         "Distance from each extracellular voxel to the nearest cell. Remember this is "
         "distance to the wall, not channel width — roughly a quarter of it."),
        ("native_voronoi_gap.png", "Cell-to-cell gap",
         "Gap between neighbouring cells. Has a hard floor of three voxels, so the left tail "
         "is a property of the measurement rather than the tissue."),
        ("native_sa_v.png", "Surface area to volume",
         "ECS-facing membrane per unit cell volume, pooled across cells in each crop."),
        ("native_topology.png", "Membrane shape",
         "Curvature, roughness and protrusion density on the ECS-facing membrane."),
        ("native_anatomy_matched.png", "Anatomy-matched summary",
         "The same metrics restricted to region groups where both preparations have crops."),
    ]),
    ("Resolution-controlled, matched to 8 nm", [
        ("matched_ecs_width.png", "ECS width, matched",
         "Every crop downsampled to 8 nm before measuring. Differences that survive here are "
         "not explained by voxel size."),
        ("matched_voronoi_gap.png", "Cell-to-cell gap, matched",
         "At 8 nm the gap floor is 24 nm, so anything below that is measurement, not biology."),
        ("matched_sa_v.png", "Surface area to volume, matched", "Pooled SA:V at common resolution."),
        ("matched_topology.png", "Membrane shape, matched",
         "Shape statistics at 8 nm. The 30 nm roughness scale is not honestly resolvable here."),
        ("matched_anatomy_matched.png", "Anatomy-matched, matched resolution",
         "Both controls at once: same regions, same voxel size. The most conservative view."),
    ]),
    ("Region vignettes", [
        ("vignette_bile_canaliculus.png", "Bile canaliculus", "Liver, chemical vs HPF."),
        ("vignette_hepatocyte_lateral.png", "Hepatocyte lateral", "Liver, the largest matched group."),
        ("vignette_glomerular.png", "Glomerular", "Kidney."),
        ("vignette_cardiac_interstitial.png", "Cardiac interstitial", "Heart."),
        ("vignette_intercalated_disc.png", "Intercalated disc", "Heart."),
    ]),
    ("3D renders", [
        ("ecs3d_bile_canaliculus.png", "Extracellular space in 3D",
         "The space itself rendered as a solid, rather than the membranes around it."),
        ("cellsurf_crop1039_cell1.png", "Cell surface", "A single segmented cell."),
        ("membrane_crop1039_cell1.png", "Membrane patch, crop1039", "Curvature on one ECS-facing patch."),
        ("membrane_crop1072_cell1.png", "Membrane patch, crop1072", "The same view in another crop."),
    ]),
]


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
            body += f'<h2>{title}</h2><div class="figs">{cards}</div>'

    extra = """<style>
 .figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
 .fig{margin:0;background:var(--raise);border:1px solid var(--rule);border-radius:10px;
      overflow:hidden;display:flex;flex-direction:column}
 .fig img{width:100%;display:block;background:#fff}
 .fig figcaption{padding:11px 14px;font-size:13px;color:var(--ink-2);
                 border-top:1px solid var(--rule)}
 .fig figcaption b{display:block;color:var(--ink);margin-bottom:2px;font-size:13.5px}
</style>"""
    html = sh.head("Figures — ECS preservation", 0, extra)
    html += sh.nav("figures.html", 0)
    html += sh.pagehead("Figure gallery",
        "Every plot the analysis pipeline produces, with what it shows and the caveat that goes "
        "with it. Click any figure for the full-resolution version. These are generated output, "
        'not final figures &mdash; the <a href="explore.html">explorer</a> is the better place to '
        "interrogate a specific number.", wide=True)
    html += f"""<main class="wide after-head">
{sh.PREP_LEGEND}
{body}
"""
    html += sh.tail(0)
    (ROOT / "docs" / "figures.html").write_text(html)
    print(f"built docs/figures.html ({n} figures)"
          + (f", {len(missing)} missing: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
