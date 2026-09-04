"""Shared page chrome for the docs site: one head, one nav, one footer.

Every builder imports from here so the pages cannot drift apart again.
`depth` is how many directories deep the page sits (0 for docs/, 1 for
docs/membranes/) and fixes up the relative asset paths.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

NAV = [
    ("explore.html",   "Explore"),
    ("crops.html",     "Crops"),
    ("figures.html",   "Figures"),
    ("reference.html", "Reference"),
]

# pages that live under a nav entry rather than beside it: visiting one of these
# lights up its parent, so the bar always shows where you are
# the membrane pages now live under Crops, which owns the viewer
PARENT = {
    "membranes/views.html":     "crops.html",
    "membranes/inspector.html": "crops.html",
    "membranes/methods.html":   "crops.html",
    "membranes/index.html":     "crops.html",
    "index.html":               None,
}


def _rel(depth: int) -> str:
    return "../" * depth


def _ver() -> str:
    """Short hash of the shared assets.

    Pages are cached for ten minutes by GitHub Pages. Without this, a browser
    can pair freshly-fetched markup with a stale stylesheet and render something
    that looks broken for no visible reason. Stamping the asset URLs means new
    markup always fetches the CSS and JS it was built against.
    """
    here = Path(__file__).resolve().parent.parent / "docs" / "assets"
    h = hashlib.sha1()
    # every shared asset, not just the two the site started with: viewer.js
    # changed once without the hash moving, and a stale viewer against fresh
    # markup is exactly the kind of "broken for no visible reason" this exists
    # to prevent
    for name in ("app.css", "site.js", "viewer.js", "crops.js"):
        f = here / name
        if f.exists():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


VER = _ver()


def head(title: str, depth: int = 0, extra: str = "", wide: bool = False) -> str:
    r = _rel(depth)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{r}assets/app.css?v={VER}">
<script src="{r}assets/site.js?v={VER}"></script>
{extra}</head><body>"""


def nav(active: str, depth: int = 0) -> str:
    """`active` is the NAV href of the current page."""
    r = _rel(depth)
    cur = ' aria-current="page"'
    lit = PARENT.get(active, active)
    items = "".join(
        '<a href="%s%s"%s>%s</a>' % (r, href, cur if href == lit else "", label)
        for href, label in NAV)
    return (f'<header class="top"><div class="wrap">'
            f'<a class="brand" href="{r}index.html">ECS preservation</a>'
            f'<nav>{items}</nav>'
            f'<button id="themetog" type="button">Auto</button>'
            f'</div></header>')


def footer(depth: int = 0) -> str:
    r = _rel(depth)
    return (f'<footer class="site">'
            f'<span>Chemical fixation vs rapid high-pressure freezing &middot; 55 crops</span>'
            f'<a href="{r}index.html">Overview</a>'
            f'<a href="{r}reference.html">How to read this</a>'
            f'<a href="{r}data/all_metrics_long.csv">Download the data</a>'
            f'<a href="https://github.com/avweigel/ecs-analysis">Source</a>'
            f'</footer>')


def tail(depth: int = 0) -> str:
    return f'{footer(depth)}</main><div id="tip"></div></body></html>'


def pagehead(title: str, lede: str = "", wide: bool = False) -> str:
    """Dark title band for the interior pages."""
    cls = "pagehead wide" if wide else "pagehead"
    body = f'<h1>{title}</h1>' + (f'<p>{lede}</p>' if lede else "")
    return f'<div class="{cls}"><div class="inner">{body}</div></div>'


def pagehead_art(title: str, lede: str = "", wide: bool = False,
                 art: str = "assets/art/hero-curv.png", depth: int = 0) -> str:
    """Title band with a render floated on the right."""
    cls = "pagehead wide" if wide else "pagehead"
    r = _rel(depth)
    return (f'<div class="{cls} has-art"><div class="inner">'
            f'<div><h1>{title}</h1>' + (f'<p>{lede}</p>' if lede else "") + '</div>'
            f'<div class="ph-art"><img src="{r}{art}" alt="" loading="eager"></div>'
            f'</div></div>')


PREP_LEGEND = (
    '<div class="legend">'
    '<span class="item"><i class="sw" style="background:var(--chem)"></i>Chemical fixation</span>'
    '<span class="item"><i class="sw" style="background:var(--hpf)"></i>Rapid high-pressure freezing</span>'
    '</div>')
