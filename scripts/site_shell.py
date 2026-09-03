"""Shared page chrome for the docs site: one head, one nav, one footer.

Every builder imports from here so the pages cannot drift apart again.
`depth` is how many directories deep the page sits (0 for docs/, 1 for
docs/membranes/) and fixes up the relative asset paths.
"""
from __future__ import annotations

NAV = [
    ("index.html",              "Overview"),
    ("explore.html",            "Explorer"),
    ("crops.html",              "Crops"),
    ("figures.html",            "Figures"),
    ("membranes/views.html",    "3D views"),
    ("membranes/inspector.html", "Inspector"),
    ("reference.html",          "Reference"),
]


def _rel(depth: int) -> str:
    return "../" * depth


def head(title: str, depth: int = 0, extra: str = "", wide: bool = False) -> str:
    r = _rel(depth)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{r}assets/app.css">
<script src="{r}assets/site.js"></script>
{extra}</head><body>"""


def nav(active: str, depth: int = 0) -> str:
    """`active` is the NAV href of the current page."""
    r = _rel(depth)
    cur = ' aria-current="page"'
    items = "".join(
        '<a href="%s%s"%s>%s</a>' % (r, href, cur if href == active else "", label)
        for href, label in NAV)
    return (f'<header class="top"><div class="wrap">'
            f'<a class="brand" href="{r}index.html">ECS preservation</a>'
            f'<nav>{items}</nav>'
            f'<button id="themetog" type="button">Auto</button>'
            f'</div></header>')


def footer(depth: int = 0) -> str:
    r = _rel(depth)
    return (f'<footer class="site">'
            f'<span>Chemical fixation vs rapid high-pressure freezing · 55 crops</span>'
            f'<a href="{r}reference.html">How to read this</a>'
            f'<a href="{r}data/all_metrics_long.csv">Download the data</a>'
            f'<a href="https://github.com/avweigel/ecs-analysis">Source</a>'
            f'</footer>')


def tail(depth: int = 0) -> str:
    return f'{footer(depth)}</main><div id="tip"></div></body></html>'


PREP_LEGEND = (
    '<div class="legend">'
    '<span class="item"><i class="sw" style="background:var(--chem)"></i>Chemical fixation</span>'
    '<span class="item"><i class="sw" style="background:var(--hpf)"></i>Rapid high-pressure freezing</span>'
    '</div>')
