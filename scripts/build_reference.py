#!/usr/bin/env python3
"""Build docs/reference.html — study design, how to read the charts, and the
full metric dictionary generated from docs/data/metrics.json."""
from __future__ import annotations

import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

ROOT = Path(__file__).resolve().parent.parent
DOC = json.loads((ROOT / "docs" / "data" / "metrics.json").read_text())

EXTRA = """<style>
 .toc{position:sticky;top:64px;align-self:start}
 .toc a{display:block;padding:3px 0;font-size:13.5px;color:var(--text-secondary);text-decoration:none}
 .toc a:hover{color:var(--text-primary)}
 .layout{display:grid;grid-template-columns:190px 1fr;gap:34px}
 @media(max-width:900px){.layout{grid-template-columns:1fr}.toc{position:static}}
 .fam{border:1px solid var(--line);border-radius:10px;background:var(--surface-1);
      padding:16px 18px;margin:14px 0}
 .fam h3{margin:0 0 4px;font-size:15px}
 .fam .short{color:var(--text-muted);font-size:13px;margin:0 0 9px}
 .mrow{display:grid;grid-template-columns:230px 92px 1fr;gap:12px;padding:7px 0;
       border-top:1px solid var(--line-soft);font-size:13.5px;align-items:baseline}
 @media(max-width:760px){.mrow{grid-template-columns:1fr}}
 .mrow code{font-size:11.5px;color:var(--text-muted);display:block;
            font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
 .mrow .u{color:var(--text-muted);font-size:12.5px}
 dl.runs{margin:0}
 dl.runs dt{font-weight:640;margin-top:13px}
 dl.runs dd{margin:2px 0 0;color:var(--text-secondary)}
</style>"""


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;")


def main():
    fams, mets, runs = DOC["families"], DOC["metrics"], DOC["runs"]
    order = ["volume_fraction", "ecs_width", "voronoi_gap", "sa_v",
             "topology", "membrane_topology", "bm_sensitivity"]

    toc = "".join(f'<a href="#{k}">{esc(fams[k]["label"])}</a>' for k in order if k in fams)

    body = ""
    for k in order:
        if k not in fams:
            continue
        f = fams[k]
        cols = sorted([c for c, v in mets.items() if k in v["families"]],
                      key=lambda c: mets[c]["label"])
        rows = "".join(
            f'<div class="mrow"><div>{esc(mets[c]["label"])}<code>{esc(c)}</code></div>'
            f'<div class="u">{esc(mets[c]["unit"]) or "&mdash;"}</div>'
            f'<div>{esc(mets[c]["blurb"])}</div></div>' for c in cols)
        body += (f'<div class="fam" id="{k}"><h3>{esc(f["label"])}</h3>'
                 f'<p class="short">{esc(f["short"])} · {len(cols)} metrics</p>'
                 f'<p style="margin:0 0 4px">{esc(f["blurb"])}</p>'
                 f'<div class="callout warn"><b>Read with care.</b> {esc(f["caveat"])}</div>'
                 f'{rows}</div>')

    runs_html = "".join(
        f'<dt>{esc(v["label"])}</dt><dd>{esc(v["blurb"])} <span class="muted">'
        f'{esc(v["caveat"])}</span></dd>' for v in runs.values())

    html = sh.head("Reference — ECS preservation", 0, EXTRA)
    html += sh.nav("reference.html", 0)
    html += f"""<main>
<h1>Reference</h1>
<p class="lede">What the study is, how to read the charts, and what every metric on this
site actually measures. If a number here surprises you, the caveat under its family is
usually the reason.</p>

<h2 id="design">The study</h2>
<div class="two">
  <div class="card">
    <h3 style="margin-top:0">The question</h3>
    <p style="margin:0;color:var(--text-secondary)">Chemical fixation is the standard way to
    preserve tissue for electron microscopy, and it is known to distort the extracellular
    space. Rapid high-pressure freezing should distort it less. This dataset measures how
    much the two differ, tissue by tissue and region by region.</p>
  </div>
  <div class="card">
    <h3 style="margin-top:0">The unit</h3>
    <p style="margin:0;color:var(--text-secondary)">A <b>crop</b> is a small annotated cube of
    volume EM in which every cell and the extracellular space between them has been
    segmented. There are 55, across cortex, heart, kidney and liver, roughly half from each
    preparation. Each is measured independently; no crop appears in both arms.</p>
  </div>
</div>

<h3>The two preparations</h3>
{sh.PREP_LEGEND}
<p class="muted" style="margin-top:-4px;max-width:74ch">These two colours mean the same thing
on every chart on this site. Orange is always chemical fixation, blue is always rapid
high-pressure freezing.</p>

<h3>The three runs</h3>
<p class="lede" style="margin-bottom:6px">Every metric family is computed three ways. Which
one you should look at depends on what you are asking.</p>
<div class="card"><dl class="runs">{runs_html}</dl></div>

<h2 id="reading">How to read the charts</h2>
<div class="card">
  <div class="legend">
    <span class="item"><i class="sw" style="background:var(--chem)"></i>one chemical crop</span>
    <span class="item"><i class="sw" style="background:var(--hpf)"></i>one HPF crop</span>
    <span class="item"><i class="sw line" style="background:var(--chem)"></i>group median</span>
    <span class="item"><b class="flag">1</b>&nbsp;an arm with one crop or none</span>
  </div>
  <p style="color:var(--text-secondary);margin:10px 0 0">In the
  <a href="explore.html">explorer</a>, every dot is one crop and every row is a group of
  crops sharing a tissue, region or anatomy. Chemical sits above the line, HPF below.
  Groups share one horizontal scale so they can be compared against each other, not just
  within themselves. A vertical rule marks the median, and is omitted where a group has
  only one crop, because the median of one crop is that crop.</p>
  <div class="callout warn"><b>The n matters more than usual here.</b> Five of the eleven
  region groups have one arm with a single crop or none at all, so no comparison is possible
  in them however clean the dots look. Those counts are shown in orange at the right of every
  row, and the <a href="index.html#coverage">coverage table</a> lists them.</div>
</div>

<h2 id="metrics">Metric dictionary</h2>
<p class="lede">{len(mets)} metrics in {len(order)} families. The name in grey under each
entry is the column name in the CSVs.</p>
<div class="layout"><div class="toc">{toc}</div><div>{body}</div></div>
"""
    html += sh.tail(0)
    (ROOT / "docs" / "reference.html").write_text(html)
    print(f"built docs/reference.html ({len(mets)} metrics)")


if __name__ == "__main__":
    main()
