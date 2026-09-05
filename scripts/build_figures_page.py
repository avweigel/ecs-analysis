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

# The page is organised by the QUESTION each panel answers, not by the run it
# came from. The old order listed every metric once at native resolution and
# again at 8 nm, in two separate blocks, so ECS width appeared twice in two
# different places and looked like the site could not make up its mind. A
# metric's two resolutions are one row now, side by side, which is the only
# way to read them anyway: the matched panel exists to be compared against the
# native one.
FAMILIES = [
    ("volume_fraction", "Volume fraction",
     "ECS and cell volume fractions per crop. The most resolution-robust family, so the "
     "native panel can be read fairly directly.",
     "native_volume_fraction.png", None),
    ("ecs_width", "ECS width",
     "Distance from each extracellular voxel to the nearest cell. Distance to the wall, not "
     "channel width &mdash; roughly a quarter of it.",
     "native_ecs_width.png", "matched_ecs_width.png"),
    ("voronoi_gap", "Cell-to-cell gap",
     "Gap between neighbouring cells. Hard floor of three voxels, so the left tail is the "
     "measurement, not the tissue; at 8 nm that floor is 24 nm.",
     "native_voronoi_gap.png", "matched_voronoi_gap.png"),
    ("sa_v", "Surface area to volume",
     "ECS-facing membrane per unit cell volume, pooled across the cells in each crop.",
     "native_sa_v.png", "matched_sa_v.png"),
    ("topology", "Membrane shape",
     "Curvature, roughness and protrusion density on the ECS-facing membrane. The 30 nm "
     "roughness scale is not honestly resolvable in the matched panel.",
     "native_topology.png", "matched_topology.png"),
]

SECTIONS = [
    ("Every metric at once", [
        ("native_anatomy_matched.png", "Anatomy-matched summary",
         "Every metric, restricted to the region groups where both preparations have crops. "
         "Native resolution."),
        ("matched_anatomy_matched.png", "Anatomy-matched, at 8 nm",
         "The same again with every crop downsampled to 8 nm first &mdash; the most "
         "conservative view on the site: same regions, same voxel size."),
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
        # generated in August and never copied into docs/: the site showed five
        # vignettes for the six regions the effect matrix scores
        ("vignette_tubule_basal.png", "Tubule basal",
         "Kidney, DCT base and PCT base pooled &mdash; the pooling is what gives this region "
         "an arm on both sides."),
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


def family_block():
    """One metric family per row: native beside matched, and a link to the same
    family in the explorer, which draws it live for any metric in the family."""
    out, n = "", 0
    for fam, label, blurb, native, matched in FAMILIES:
        pair = ""
        for fn, tag in ((native, "Native resolution"),
                        (matched, "Matched to 8 nm")):
            if not fn or not (FIGDIR / fn).exists():
                continue
            n += 1
            pair += (f'<figure class="fig"><a href="figures/{fn}" target="_blank" rel="noopener">'
                     f'<img src="figures/{fn}" loading="lazy" alt="{label}, {tag.lower()}"></a>'
                     f'<figcaption><b>{tag}</b></figcaption></figure>')
        if not pair:
            continue
        live = (f'<a href="explore.html?fam={fam}&amp;run=native">Draw this live</a> '
                "&mdash; any metric in the family, any grouping, one dot per crop."
                if fam else
                '<a href="explore.html?grp=region_group">Draw this live</a> '
                "&mdash; the explorer groups by region by default.")
        only = ("" if matched else
                '<span class="note"> Native only: the matched run reads zarr metadata that is '
                'valid at native resolution alone.</span>')
        out += (f'<section class="fam" data-fam="{fam or ""}"><div class="famhead">'
                f'<h3>{label}</h3>'
                f'<p>{blurb}{only}</p><p class="note">{live}</p></div>'
                f'<div class="figs pair">{pair}</div></section>')
    return out, n


FIG_STYLE = """<style>
 .figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
 .fig{margin:0;background:var(--raise);border:1px solid var(--rule);border-radius:10px;
      overflow:hidden;display:flex;flex-direction:column}
 .fig img{width:100%;display:block;background:#fff}
 .fig figcaption{padding:11px 14px;font-size:13px;color:var(--ink-2);
                 border-top:1px solid var(--rule)}
 .fig figcaption b{display:block;color:var(--ink);margin-bottom:2px;font-size:13.5px}
 /* the standing panels for the family you are looking at, under the live plot */
 .fampanels{border-top:1px solid var(--rule);margin-top:var(--s5);padding-top:var(--s4)}
 .fampanels > h3{margin:0 0 var(--s2);font-size:var(--t3)}
 .fampanels .note{margin:0 0 var(--s4)}
 .fam[hidden]{display:none!important}
 .onpage{display:flex;gap:var(--s4);align-items:baseline;flex-wrap:wrap;
   padding:0 0 var(--s4);margin-bottom:var(--s5);border-bottom:1px solid var(--rule);
   font-size:var(--t4)}
 .onpage span{font-size:var(--t5);text-transform:uppercase;letter-spacing:.07em;
   color:var(--ink-3)}
 h2.sec-first{margin-top:0}
 /* a family is one row: the words on the left, the two resolutions on the right */
 .fam{display:grid;grid-template-columns:300px 1fr;gap:var(--s5);align-items:start;
   padding:var(--s5) 0;border-top:1px solid var(--rule)}
 .fam:first-of-type{border-top:0}
 .famhead h3{margin:0 0 var(--s2)}
 .famhead p{color:var(--ink-2);font-size:var(--t4);margin:0 0 var(--s3)}
 .famhead .note{margin:0}
 /* always two slots, so the one family with a native panel only does not
    stretch to twice the width of everything else */
 .figs.pair{grid-template-columns:repeat(2,minmax(0,1fr))}
 @media(max-width:1100px){.figs.pair{grid-template-columns:1fr}}
 @media(max-width:900px){.fam{grid-template-columns:1fr;gap:var(--s3)}}
</style>"""


VIGNETTE_REGION = {
    "vignette_bile_canaliculus.png": "Bile canaliculus",
    "vignette_hepatocyte_lateral.png": "Hepatocyte lateral",
    "vignette_glomerular.png": "Glomerular",
    "vignette_tubule_basal.png": "Tubule basal",
    "vignette_cardiac_interstitial.png": "Cardiac interstitial",
    "vignette_intercalated_disc.png": "Intercalated disc",
}


def fig_cards(figs, missing=None):
    cards, n = "", 0
    for fn, label, blurb in figs:
        if not (FIGDIR / fn).exists():
            if missing is not None:
                missing.append(fn)
            continue
        n += 1
        reg = VIGNETTE_REGION.get(fn)
        attr = f' data-region="{reg}"' if reg else ""
        cards += (f'<figure class="fig"{attr}><a href="figures/{fn}" target="_blank" rel="noopener">'
                  f'<img src="figures/{fn}" loading="lazy" alt="{label}"></a>'
                  f'<figcaption><b>{label}</b><span>{blurb}</span></figcaption></figure>')
    return cards, n


def sections_html(missing=None):
    """The standing panels, in order, as the analysis page shows them."""
    body, n = "", 0
    for title, figs in SECTIONS:
        cards, k = fig_cards(figs, missing)
        n += k
        if not cards:
            continue
        slug = SLUGS.get(title, "")
        head = f'<h2 id="{slug}">{title}</h2>' if slug else f'<h2>{title}</h2>'
        if slug == "vignettes":
            body += ('<section id="vigsection">' + head +
                     '<p class="note" id="vignote"></p>' +
                     EXTRA_LINE.get(title, "") +
                     f'<div class="figs">{cards}</div></section>')
            continue
        body += head + EXTRA_LINE.get(title, "") + f'<div class="figs">{cards}</div>'
    return body, n


def main():
    """figures.html is a pointer now: its content lives on the analysis page.

    The URL is in notes and links, so it should not 404 -- and someone who
    lands here should be told where each part went rather than redirected
    somewhere they did not ask for.
    """
    html = sh.head("Quantification — moved into Analysis", 0)
    html += sh.nav("figures.html", 0)
    html += sh.pagehead("Quantification moved",
        "It is part of <a href=\"explore.html\">Analysis</a> now. The explorer and these panels "
        "were the same data with and without the controls on, which is a distinction for whoever "
        "built the site and not for anyone reading it.", wide=False)
    html += """<main class="after-head">
<ul class="jump">
  <li><a href="explore.html#live"><span class="t">One metric, live</span>
    <span class="d">Any metric, any grouping, one dot per crop &mdash; with the standing panels
    for that family underneath it.</span></a></li>
  <li><a href="explore.html#matrix"><span class="t">Every metric at once</span>
    <span class="d">The effect-size matrix.</span></a></li>
  <li><a href="explore.html#vignettes"><span class="t">One region, every metric</span>
    <span class="d">The six region vignettes.</span></a></li>
  <li><a href="explore.html#renders"><span class="t">Pictures of the geometry</span>
    <span class="d">Renders, and the paired 3D views.</span></a></li>
</ul>
"""
    html += sh.tail(0)
    (ROOT / "docs" / "figures.html").write_text(html)
    print("built docs/figures.html (pointer into Analysis)")


if __name__ == "__main__":
    main()
