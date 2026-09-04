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
 .toc{position:sticky;top:72px;align-self:start}
 #mq{width:100%;margin-bottom:var(--s3)}
 .toc a{display:block;padding:3px 0;font-size:13.5px;color:var(--ink-2);text-decoration:none}
 .toc a:hover{color:var(--ink)}
 .layout{display:grid;grid-template-columns:190px 1fr;gap:34px}
 @media(max-width:900px){.layout{grid-template-columns:1fr}.toc{position:static}}
 .fam{border-top:1px solid var(--rule);padding:var(--s5) 0 var(--s4);margin:0}
 .fam details{margin-top:var(--s3)}
 .fam summary{cursor:pointer;font-size:var(--t4);color:var(--accent);list-style:none;
   display:inline-flex;gap:6px;align-items:center}
 .fam summary::-webkit-details-marker{display:none}
 .fam summary::before{content:"▸";transition:transform .15s;display:inline-block}
 .fam details[open] summary::before{transform:rotate(90deg)}
 .fam h3{margin:0 0 4px;font-size:15px}
 .fam .short{color:var(--ink-3);font-size:13px;margin:0 0 9px}
 .mrow{display:grid;grid-template-columns:250px 96px 1fr;gap:var(--s3);padding:7px 0;
       border-top:1px solid var(--rule);font-size:var(--t4);align-items:baseline}
 .mrow:hover{background:var(--sunk)}
 @media(max-width:760px){.mrow{grid-template-columns:1fr}}
 .mrow code{font-size:var(--t5);color:var(--ink-3);display:block;
            font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
 .mrow .u{color:var(--ink-3);font-size:var(--t4)}
 dl.runs{margin:0}
 dl.runs dt{font-weight:600;margin-top:var(--s4)}
 dl.runs dd{margin:2px 0 0;color:var(--ink-2)}
</style>"""


DATASET_JS = """<script>
/* The dataset table is built in the browser from the same neuroglancer.json the
   crop page uses, so the two can never disagree about what exists where. */
(function () {
  const TISSUE = { cortex: 'Cortex', heart: 'Heart', kidney: 'Kidney', liver: 'Liver' };
  fetch('data/neuroglancer.json').then(r => r.json()).then(NG => {
    const tb = document.querySelector('#dstable tbody'); if (!tb) return;
    const rowsFor = ds => NG.datasets[ds];
    const names = Object.keys(NG.datasets).sort();
    tb.innerHTML = names.map(ds => {
      const d = rowsFor(ds);
      const tissue = TISSUE[Object.keys(TISSUE).find(k => ds.includes(k))] || '';
      const ready = d.s3_ready ? '<span class="tag hpf">public</span>'
        : `<span class="muted">${d.s3_note || 'not yet'}</span>`;
      const first = d.crops[0];
      return `<tr><td><code>${ds}</code></td><td>${tissue}</td>
        <td>${/-(2|4|6|8)$/.test(ds) && !/kidney$|liver$/.test(ds) ? '' : ''}</td>
        <td class="num">${d.voxel_nm ?? ''}</td><td class="num">${d.crops.length}</td>
        <td><code>${d.em || ''}</code></td><td>${ready}</td>
        <td><a class="nglink" href="#" data-ds="${first}">NG</a></td></tr>`;
    }).join('');
    // reuse the crop page's URL builder if it is present; otherwise build here
    document.querySelectorAll('#dstable a.nglink').forEach(a => {
      a.target = '_blank'; a.rel = 'noopener';
      a.href = ngURLLocal(NG, a.dataset.ds);
    });
    document.getElementById('dsnote').innerHTML =
      'Links open the whole volume with every annotated crop in it as a layer. ' +
      'Each link carries only the crops used in this analysis, not every crop in the volume. ' +
      'Where the public OpenOrganelle copy holds the image <em>and</em> all of those crops, ' +
      'links use it and need no VPN; otherwise they fall back to Janelia. That is ' +
      Object.values(NG.datasets).filter(d => d.s3_ready).length +
      ' of ' + names.length + ' volumes today.';
  }).catch(() => {});

  function ngURLLocal(NG, crop) {
    const dsName = NG.crop_dataset[crop], d = NG.datasets[dsName];
    const base = `zarr://${NG.sources.nrs.base}/${dsName}/${dsName}.zarr/recon-1`;
    const em = { type: 'image', source: `${base}/em/${d.em}`, name: 'em' };
    if (d.shader) { em.shaderControls = d.shader; em.tab = 'rendering'; }
    const layers = [em].concat(d.crops.map(c => ({ type: 'segmentation',
      source: `${base}/labels/groundtruth/${c}/all`, name: c, visible: true })));
    const s = { layers, layout: '4panel' };
    const c = NG.centre_nm[crop], v = d.voxel_nm || 8;
    if (c) { s.dimensions = { x: [v*1e-9,'m'], y: [v*1e-9,'m'], z: [v*1e-9,'m'] };
             s.position = c.map(x => +(x / v).toFixed(1)); }
    return 'https://neuroglancer-demo.appspot.com/#!' + encodeURIComponent(JSON.stringify(s));
  }
})();
</script>"""

DICT_JS = """<script>
const mq=document.getElementById('mq');
mq.addEventListener('input',()=>{
  const v=mq.value.toLowerCase().trim();
  document.querySelectorAll('.fam').forEach(fam=>{
    let hits=0;
    fam.querySelectorAll('.mrow').forEach(r=>{
      const on=!v||r.textContent.toLowerCase().includes(v);
      r.style.display=on?'':'none'; if(on)hits++;});
    fam.style.display=(v&&!hits)?'none':'';
    const d=fam.querySelector('details');
    if(d) d.open = !!v;
  });
});
</script>"""


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;")


def main():
    fams, mets, runs = DOC["families"], DOC["metrics"], DOC["runs"]
    order = ["volume_fraction", "ecs_width", "voronoi_gap", "sa_v",
             "topology", "membrane_topology", "bm_sensitivity"]

    toc = ('<a href="#datasets">The datasets</a>'
           + "".join(f'<a href="#{k}">{esc(fams[k]["label"])}</a>' for k in order if k in fams))

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
                 f'<details><summary>{len(cols)} metrics</summary>{rows}</details></div>')

    runs_html = "".join(
        f'<dt>{esc(v["label"])}</dt><dd>{esc(v["blurb"])} <span class="muted">'
        f'{esc(v["caveat"])}</span></dd>' for v in runs.values())

    html = sh.head("Reference — ECS preservation", 0, EXTRA)
    html += sh.nav("reference.html", 0)
    html += sh.pagehead("Reference",
        "What the study is, how to read the charts, and what every metric on this site "
        "actually measures. If a number here surprises you, the caveat under its family is "
        "usually the reason.")
    html += f"""<main class="after-head">

<h2 id="design">The study</h2>
<div class="two">
  <div class="card">
    <h3 style="margin-top:0">The question</h3>
    <p style="margin:0;color:var(--ink-2)">Chemical fixation is the standard way to
    preserve tissue for electron microscopy, and it is known to distort the extracellular
    space. Rapid high-pressure freezing should distort it less. This dataset measures how
    much the two differ, tissue by tissue and region by region.</p>
  </div>
  <div class="card">
    <h3 style="margin-top:0">The unit</h3>
    <p style="margin:0;color:var(--ink-2)">A <b>crop</b> is a small annotated cube of
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
  <p style="color:var(--ink-2);margin:10px 0 0">In the
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

<h2 id="surfaces">The two surfaces in the viewer</h2>
<p class="lede">The <a href="crops.html">crop page</a> can show either side of the same
boundary. They are built differently, and the difference matters when you compare them.</p>
<div class="grid cols-2">
  <div class="card">
    <h3 style="margin-top:0">Membrane</h3>
    <p style="color:var(--ink-2)">One cell's ECS-facing skin, in the crop's own frame. The
    cell with the most ECS-facing surface is meshed at 16 nm, and the patch is the part of it
    that faces extracellular space. Coloured by signed curvature, protrusion / indentation
    against a 60 nm smoothed reference, or the gap to the nearest neighbouring cell.</p>
    <p class="note" style="margin:0">Faces at the crop wall are trimmed: marching cubes caps
    the volume there, and the cap is not membrane.</p>
  </div>
  <div class="card">
    <h3 style="margin-top:0">ECS</h3>
    <p style="color:var(--ink-2)">The space itself, meshed at 8 nm from an 800 nm cube of
    every crop &mdash; equal volume, so two crops can be compared with a shared camera. The
    cube is not the middle of the crop: it is the position whose ECS fraction is closest to
    the whole crop's, because the middle of a liver crop can sit inside one hepatocyte and
    hold no ECS at all. Coloured by curvature, protrusion / indentation, or local channel
    width.</p>
    <p class="note" style="margin:0">Width is the diameter of the largest ball that fits in
    the channel, found by walking the surface normal into the space &mdash; an estimate, and
    it saturates in open pools. Where a channel leaves the cube the reading would be a guess,
    so those vertices are grey rather than wrong.</p>
  </div>
</div>
<p class="note">Both surfaces use one sign convention: positive curvature and positive
deviation mean the membrane bulges <b>into</b> the extracellular space. The shared geometry
code is calibrated on a cell mask, so the ECS values are negated to put them on that scale.</p>

<h2 id="datasets">The datasets</h2>
<p class="lede">The 55 crops come from nine imaged volumes. A crop is a hand-annotated cube
inside one of these; the volume itself is the raw electron microscopy it was cut from.</p>
<div class="scroll"><table id="dstable">
  <thead><tr><th>Dataset</th><th>Tissue</th><th>Preparation</th>
    <th class="num">Voxel<span class="u">nm</span></th><th class="num">Crops</th>
    <th>EM array</th><th>OpenOrganelle</th><th>Open</th></tr></thead>
  <tbody></tbody></table></div>
<p class="note" id="dsnote"></p>

<h2 id="metrics">Metric dictionary</h2>
<p class="lede">{len(mets)} metrics in {len(order)} families. The grey name under each entry is
its column name in the CSVs. Use the filter to find one by name, unit or wording.</p>
<div class="layout"><div class="toc">
  <input type="search" id="mq" placeholder="Filter metrics&hellip;">{toc}</div>
  <div id="dict">{body}</div></div>
<!--DICTJS-->
"""
    html = html.replace("<!--DICTJS-->", DICT_JS + DATASET_JS)
    html += sh.tail(0)
    (ROOT / "docs" / "reference.html").write_text(html)
    print(f"built docs/reference.html ({len(mets)} metrics)")


if __name__ == "__main__":
    main()
