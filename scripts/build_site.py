#!/usr/bin/env python3
"""
Build the generated pages of the docs site: the overview and the crop table.

    python scripts/collect_all.py            # data first
    python scripts/build_metric_dictionary.py
    python scripts/build_site.py
    python scripts/build_reference.py
    python scripts/build_figures_page.py
    python scripts/build_views_page.py
"""
from __future__ import annotations

import csv, json, shutil, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

ROOT = Path(__file__).resolve().parent.parent
RES, DOCS = ROOT / "results", ROOT / "docs"


# Section icons. Each one draws what the page actually is -- a strip plot, a
# filterable table beside a render, a wall of panels, a cut solid, a dictionary
# page -- rather than a crop thumbnail that says nothing about where the link
# goes. Two colours, both from the palette, so they read in either theme.
_ICO = ('<svg class="ico" viewBox="0 0 44 44" width="46" height="46" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>')

ICO_EXPLORE = _ICO % (
    '<g stroke="currentColor" stroke-width="1.6" opacity=".55">'
    '<path d="M6 8v30h32"/></g>'
    '<g stroke="var(--rule-strong)" stroke-width="1.4" opacity=".8">'
    '<path d="M12 12v22M20 12v22M28 12v22M36 12v22"/></g>'
    '<g fill="var(--chem)"><circle cx="14" cy="15" r="2.4"/><circle cx="22" cy="15" r="2.4"/>'
    '<circle cx="30" cy="15" r="2.4"/></g>'
    '<g fill="var(--hpf)"><circle cx="12" cy="24" r="2.4"/><circle cx="18" cy="24" r="2.4"/>'
    '<circle cx="27" cy="24" r="2.4"/></g>'
    '<g fill="var(--chem)"><circle cx="17" cy="32" r="2.4"/><circle cx="25" cy="32" r="2.4"/>'
    '<circle cx="34" cy="32" r="2.4"/></g>')

ICO_CROPS = _ICO % (
    '<g stroke="currentColor" stroke-width="1.6"><rect x="5" y="8" width="20" height="28" rx="2"/>'
    '<path d="M5 15h20M13 15v21"/></g>'
    '<g stroke="var(--accent)" stroke-width="1.5" opacity=".85">'
    '<path d="M8 20h3M8 26h3M8 32h3"/></g>'
    '<g stroke="currentColor" stroke-width="1.6"><rect x="29" y="8" width="10" height="28" rx="2"/></g>'
    '<path d="M31 30c3-6 2-11 6-14v18h-6z" fill="var(--accent)" opacity=".8"/>')

ICO_QUANT = _ICO % (
    '<g stroke="currentColor" stroke-width="1.5">'
    '<rect x="5" y="6" width="15" height="15" rx="2"/><rect x="24" y="6" width="15" height="15" rx="2"/>'
    '<rect x="5" y="24" width="15" height="14" rx="2"/><rect x="24" y="24" width="15" height="14" rx="2"/></g>'
    '<g stroke="var(--chem)" stroke-width="1.8"><path d="M8 17l3-6 3 4 3-6"/></g>'
    '<g fill="var(--hpf)"><rect x="27" y="12" width="2.6" height="6" rx="1"/>'
    '<rect x="31" y="9" width="2.6" height="9" rx="1"/><rect x="35" y="14" width="2.6" height="4" rx="1"/></g>'
    '<g stroke="var(--hpf)" stroke-width="1.8"><path d="M8 34c4 0 4-7 8-7"/></g>'
    '<g fill="var(--chem)" opacity=".85"><rect x="27" y="28" width="10" height="3" rx="1.5"/>'
    '<rect x="27" y="33" width="6" height="3" rx="1.5"/></g>')

ICO_RENDERS = _ICO % (
    '<g stroke="currentColor" stroke-width="1.6">'
    '<path d="M22 5l15 8v18l-15 8-15-8V13z"/></g>'
    '<path d="M9 15c5 5 8-2 13 2s7-3 13 1v14l-13 7-13-7z" fill="var(--accent)" opacity=".28"/>'
    '<g stroke="var(--accent)" stroke-width="1.6"><path d="M9 15c5 5 8-2 13 2s7-3 13 1"/>'
    '<path d="M9 24c5 5 8-2 13 2s7-3 13 1"/></g>')

ICO_REFERENCE = _ICO % (
    '<g stroke="currentColor" stroke-width="1.6"><path d="M8 7h17a4 4 0 014 4v26H12a4 4 0 01-4-4z"/>'
    '<path d="M12 37a4 4 0 010-8h17"/></g>'
    '<g stroke="var(--accent)" stroke-width="1.5" opacity=".9">'
    '<path d="M13 14h13M13 19h13M13 24h8"/></g>'
    '<g stroke="var(--chem)" stroke-width="1.7"><circle cx="30" cy="26" r="5"/>'
    '<path d="M34 30l4 4"/></g>')


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;")


def build_index(long_rows, wide_rows, mets):
    crops = {r["crop"]: r for r in wide_rows if r["run"] == "native"}
    n_crops, n_meas = len(crops), len(long_rows)
    n_metrics = len({r["metric"] for r in long_rows})
    tissues = Counter(r["tissue"] for r in crops.values())
    preps = Counter(r["prep"] for r in crops.values())

    reg = defaultdict(Counter)
    for r in crops.values():
        reg[(r["tissue"], r["region_group"] or "no region assigned")][r["prep"]] += 1
    rows, thin = [], 0
    for (t, g), c in sorted(reg.items()):
        nc, nh = c.get("Chemical", 0), c.get("Rapid HPF", 0)
        bad = nc <= 1 or nh <= 1
        thin += bad
        rows.append(
            f'<tr><td>{esc(t)}</td><td>{esc(g)}</td>'
            f'<td class="num{" flag" if nc<=1 else ""}">{nc}</td>'
            f'<td class="num{" flag" if nh<=1 else ""}">{nh}</td>'
            f'<td class="wrap">{"<span class=flag>no comparison possible</span>" if bad else ""}</td></tr>')

    fams = Counter(r["metric_family"] for r in long_rows)
    fam_labels = json.loads((DOCS / "data" / "metrics.json").read_text())["families"]
    fam_rows = ""
    for f, n in sorted(fams.items(), key=lambda kv: fam_labels.get(kv[0], {}).get("label", kv[0])):
        cols = {r["metric"] for r in long_rows if r["metric_family"] == f}
        label = fam_labels.get(f, {}).get("label", f.replace("_", " "))
        fam_rows += (f'<tr><td><a href="reference.html#{f}">{esc(label)}</a></td>'
                     f'<td class="num">{len(cols)}</td><td class="num">{n:,}</td></tr>')

    # the hero is a <model-viewer> element, which is inert without its script:
    # the page rendered the caption and nothing above it
    html = sh.head("ECS preservation — data overview", 0,
                   '<script type="module" src="assets/model-viewer.min.js"></script>')
    html += sh.nav("index.html", 0)
    html += f"""
<div class="hero"><div class="inner">
  <div>
    <p class="eyebrow">Volume electron microscopy &middot; mouse tissue</p>
    <h1>What fixation does to the space <em>between</em> cells</h1>
    <p>Chemical fixation is how almost all tissue is preserved for electron
    microscopy, and it is known to distort the extracellular space. Rapid
    high-pressure freezing should distort it less. These are all
    {n_meas:,} measurements behind that comparison.</p>
    <div class="stats">
      <div class="stat"><div class="n">{n_crops}</div><div class="k">crops</div></div>
      <div class="stat"><div class="n">{len(tissues)}</div><div class="k">tissues</div></div>
      <div class="stat"><div class="n">{n_metrics}</div><div class="k">metrics</div></div>
      <div class="stat"><div class="n">{n_meas:,}</div><div class="k">measurements</div></div>
    </div>
  </div>
  <div class="art">
    <model-viewer id="hero" camera-controls auto-rotate
      auto-rotate-delay="1200" rotation-per-second="14deg" interaction-prompt="none"
      touch-action="pan-y" exposure="1.15" shadow-intensity="0"
      camera-orbit="auto auto 88%" min-field-of-view="12deg"
      alt="The extracellular space as a solid object. Drag to rotate."></model-viewer>
    <span class="cap">loading&hellip;</span>
    <script>document.addEventListener('DOMContentLoaded',function(){{
      ECS.mountHero(document.getElementById('hero'),'');}});</script>
  </div>
</div></div>

<main class="after-head">
<p class="lede" style="max-width:64ch">Nothing here is a finished result. This is working
data, published so it can be read from the outside &mdash; every metric, every crop, and the
caveats that go with them.</p>

<ul class="jump">
  <li><a href="explore.html">{ICO_EXPLORE}
    <span class="t">Analysis</span>
    <span class="d">Any metric live, one dot per crop &mdash; and every standing panel the pipeline draws.</span></a></li>
  <li><a href="crops.html">{ICO_CROPS}
    <span class="t">Crops</span>
    <span class="d">All {n_crops} crops, filterable, with the membrane and the space itself in the viewer.</span></a></li>
  <li><a href="reference.html">{ICO_REFERENCE}
    <span class="t">Reference</span>
    <span class="d">What a crop is, how to read the charts, and what all {n_metrics} metrics mean.</span></a></li>
</ul>

<div class="sec">
<h2 style="margin-top:0">What you are looking at</h2>
<div class="grid cols-3">
  <div>
    <h3 style="margin-top:0">A crop</h3>
    <p class="small muted" style="margin:0">A small cube of volume electron microscopy in which
    every cell, and the space between the cells, has been traced by hand. One crop is one piece of
    tissue. There are {n_crops}, and no crop appears in both arms of the comparison.</p>
  </div>
  <div>
    <h3 style="margin-top:0">The two preparations</h3>
    <p class="small muted" style="margin:0 0 var(--s2)">Two ways of preserving tissue before
    imaging. Chemical fixation is standard and is known to distort the extracellular space;
    rapid freezing should distort it less. These colours mean these two things on every chart
    on this site.</p>
    <div class="legend" style="margin:0">
      <span class="item"><i class="sw" style="background:var(--chem)"></i>Chemical</span>
      <span class="item"><i class="sw" style="background:var(--hpf)"></i>Rapid HPF</span>
    </div>
  </div>
  <div>
    <h3 style="margin-top:0">Regions</h3>
    <p class="small muted" style="margin:0">Crops are labelled by where in the tissue they came
    from &mdash; bile canaliculus, glomerulus, intercalated disc. Comparing like with like means
    comparing within a region, which is why the counts below matter.</p>
  </div>
</div>
<p class="note"><a href="reference.html">The reference page</a> goes further: why every metric is
computed three times, and what all {n_metrics} of them measure.</p>
</div>

<div class="sec" id="coverage">
<h2 style="margin-top:0">Where the comparison is supported</h2>
<p class="lede" style="margin-bottom:var(--s4)">A region can only support a comparison if both
preparations have crops in it. <b>{thin} of {len(rows)} do not.</b> Kidney &mdash; where the
direction of the effect splits by region &mdash; is where most of the gaps are, so read kidney
carefully.</p>
<div class="scroll"><table>
  <thead><tr><th>Tissue</th><th>Region</th><th class="num">Chemical</th>
    <th class="num">Rapid HPF</th><th class="wrap"></th></tr></thead>
  <tbody>{"".join(rows)}</tbody></table></div>
</div>

<div class="sec">
<h2 style="margin-top:0">What is measured</h2>
<div class="grid cols-2">
  <div>
    <table>
      <thead><tr><th>Metric family</th><th class="num">Metrics</th><th class="num">Values</th></tr></thead>
      <tbody>{fam_rows}</tbody></table>
    <p class="note">Each family is computed three ways &mdash; at native resolution, matched to
    8&nbsp;nm, and across a degradation series &mdash; so a difference can be checked against what
    resolution alone would produce. <a href="reference.html#design">What the runs mean.</a></p>
  </div>
  <div>
    <table>
      <thead><tr><th>Preparation</th><th class="num">Crops</th></tr></thead>
      <tbody>{"".join(f'<tr><td><span class="tag {"chem" if "Chem" in k else "hpf"}">{esc(k)}</span></td><td class="num">{v}</td></tr>' for k, v in sorted(preps.items()))}</tbody></table>
    <table style="margin-top:var(--s5)">
      <thead><tr><th>Tissue</th><th class="num">Crops</th></tr></thead>
      <tbody>{"".join(f'<tr><td>{esc(k)}</td><td class="num">{v}</td></tr>' for k, v in sorted(tissues.items()))}</tbody></table>
  </div>
</div>
</div>

<div class="sec">
<h2 style="margin-top:0">Data</h2>
<p class="note" style="max-width:76ch">Everything here is generated from
<a href="data/all_metrics_long.csv">all_metrics_long.csv</a> (one row per measurement) and
<a href="data/all_metrics_wide.csv">all_metrics_wide.csv</a> (one row per crop, run and
resolution), with names and units from <a href="data/metrics.json">metrics.json</a>.
Rebuild with <code>python scripts/collect_all.py</code>.</p>
</div>
"""
    html += sh.tail(0)
    (DOCS / "index.html").write_text(html)
    return n_crops


def build_crops(wide_rows, mets):
    native = [r for r in wide_rows if r["run"] == "native"]
    cols = ["volume_fraction.ecs_fraction",
            "ecs_width.narrow_percentiles_nm_p50",
            "ecs_width.narrow_std_nm",
            "voronoi_gap.percentiles_nm_p50",
            "sa_v.sa_v_ecs_per_nm",
            "sa_v.cell_density_per_um3",
            "topology.protrusion_density_per_um2"]

    def meta(k):
        col = k.split(".", 1)[1]
        m = mets.get(col, {})
        return m.get("label", col), m.get("unit", ""), m.get("blurb", "")

    head_cells = ""
    for k in cols:
        label, unit, blurb = meta(k)
        head_cells += (f'<th class="num sortable" title="{esc(blurb)}">{esc(label)}'
                       f'<span class="u">{esc(unit) or "&nbsp;"}</span></th>')

    def cell(r, k):
        v = r.get(k, "")
        if v in ("", None):
            return '<td class="num muted">&mdash;</td>'
        f = float(v)
        s = f"{f:.4g}" if abs(f) < 1000 else f"{f:,.0f}"
        return f'<td class="num">{s}</td>'

    body = ""
    for r in sorted(native, key=lambda x: x["crop"]):
        cls = "chem" if r["prep"] == "Chemical" else "hpf"
        body += (f'<tr><td class="thumbcell">'
                 f'<a href="membranes/membrane_{r["crop"]}.png">'
                 f'<img class="thumb" src="assets/art/thumbs/{r["crop"]}.png" alt="" '
                 f'loading="lazy" width="34" height="34">{r["crop"]}</a></td>'
                 f'<td>{esc(r["tissue"])}</td><td>{esc(r["region_group"])}</td>'
                 f'<td class="wrap">{esc(r["anatomy"])}</td>'
                 f'<td><span class="tag {cls}">{esc(r["prep"])}</span></td>'
                 f'<td class="num">{r["native_voxel_nm"] or ""}</td>'
                 + "".join(cell(r, k) for k in cols) + "</tr>")

    html = sh.head("Crops — ECS preservation", 0,
                   "<style>#q{min-width:250px}th{vertical-align:bottom}</style>")
    html += sh.nav("crops.html", 0)
    html += sh.pagehead("Crops",
        f"All {len(native)} annotated crops at native resolution, with one headline number from "
        "each metric family. Hover a column heading for what it measures; the "
        f'<a href="reference.html#metrics">dictionary</a> has all {len(mets)}. '
        "Crop names link to the membrane render.", wide=True)
    html += f"""<main class="wide after-head">
{sh.PREP_LEGEND}
<div class="controls"><div class="ctl"><label for="q">Filter</label>
  <input type="search" id="q" placeholder="tissue, region, prep, crop&hellip;" style="min-width:260px"></div>
  <div class="ctl"><label>Showing</label><span id="count" class="muted"
   style="font-size:var(--t4);padding:6px 0">{len(native)} crops</span></div></div>
<div class="scroll"><table id="t"><thead><tr>
  <th class="sortable">Crop</th><th class="sortable">Tissue</th><th class="sortable">Region</th>
  <th class="sortable wrap">Anatomy</th><th class="sortable">Prep</th>
  <th class="num sortable">Voxel<span class="u">nm</span></th>
  {head_cells}</tr></thead><tbody>{body}</tbody></table></div>
<p class="note">Values are native resolution, so voxel size differs between rows &mdash; use the
<a href="explore.html">explorer</a>&rsquo;s matched run to compare preparations fairly.</p>
"""
    html += sh.tail(0)
    (DOCS / "crops.html").write_text(html)


CROPS_JS = """
<script>
const t=document.getElementById('t'), q=document.getElementById('q'), cnt=document.getElementById('count');
function refilter(){const v=q.value.toLowerCase();let n=0;
  for(const tr of t.tBodies[0].rows){const show=tr.textContent.toLowerCase().includes(v);
    tr.style.display=show?'':'none'; if(show)n++;}
  cnt.textContent=n+' crop'+(n===1?'':'s');}
q.addEventListener('input',refilter);
t.tHead.addEventListener('click',e=>{
  const th=e.target.closest('th.sortable'); if(!th)return;
  const i=[...th.parentNode.children].indexOf(th), num=th.classList.contains('num');
  const dir=th.dataset.d==='1'?-1:1;
  [...t.tHead.rows[0].cells].forEach(c=>delete c.dataset.d); th.dataset.d=dir===1?'1':'0';
  [...t.tBodies[0].rows].sort((a,b)=>{
    const x=a.cells[i].textContent.trim(), y=b.cells[i].textContent.trim();
    if(num){const nx=parseFloat(x.replace(/,/g,'')),ny=parseFloat(y.replace(/,/g,''));
      if(isNaN(nx))return 1; if(isNaN(ny))return -1; return (nx-ny)*dir;}
    return x.localeCompare(y)*dir;}).forEach(r=>t.tBodies[0].appendChild(r));
});
</script>"""


def main():
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    for f in ("all_metrics_long.csv", "all_metrics_wide.csv", "stats_native.csv",
              "summary_native_anatomy_matched.csv"):
        if (RES / f).exists():
            shutil.copy2(RES / f, DOCS / "data" / f)
    long_rows = list(csv.DictReader((DOCS / "data" / "all_metrics_long.csv").open()))
    wide_rows = list(csv.DictReader((DOCS / "data" / "all_metrics_wide.csv").open()))
    mets = json.loads((DOCS / "data" / "metrics.json").read_text())["metrics"]
    n = build_index(long_rows, wide_rows, mets)
    # crops.html is built by scripts/build_crops.py — it owns the viewer now
    print(f"built docs/index.html ({n} crops)")


if __name__ == "__main__":
    main()
