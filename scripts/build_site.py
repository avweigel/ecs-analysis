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
    fam_rows = ""
    for f, n in sorted(fams.items()):
        cols = {r["metric"] for r in long_rows if r["metric_family"] == f}
        label = f.replace("_", " ")
        fam_rows += (f'<tr><td><a href="reference.html#{f}">{esc(label)}</a></td>'
                     f'<td class="num">{len(cols)}</td><td class="num">{n:,}</td></tr>')

    html = sh.head("ECS preservation — data overview", 0,
                   "<style>.tile .n{font-variant-numeric:tabular-nums}</style>")
    html += sh.nav("index.html", 0)
    html += f"""<main>
<h1>Extracellular space across fixation methods</h1>
<p class="lede">Every measurement from the chemical-fixation versus rapid high-pressure
freezing comparison, browsable rather than filed away in CSVs. Nothing here is a finished
result &mdash; this is working data, published so it can be looked at from the outside.</p>

<div class="grid tiles">
  <div class="card tile"><div class="n">{n_crops}</div><div class="k">annotated crops</div></div>
  <div class="card tile"><div class="n">{n_metrics}</div><div class="k">distinct metrics</div></div>
  <div class="card tile"><div class="n">{n_meas:,}</div><div class="k">measurements</div></div>
  <div class="card tile"><div class="n">{len(tissues)}</div><div class="k">tissues</div></div>
</div>

<div class="callout"><b>New here?</b> The <a href="reference.html">reference page</a> explains
what a crop is, what the two preparations are, why every metric is computed three times, and
what each of the {n_metrics} metrics measures.</div>

<h2>Start here</h2>
<div class="two">
  <div class="card"><h3 style="margin-top:0"><a href="explore.html">Metric explorer</a></h3>
    <p class="muted" style="margin:0">Any of the {n_metrics} metrics, grouped by tissue, region
    or anatomy, both preparations on one scale. One dot per crop.</p></div>
  <div class="card"><h3 style="margin-top:0"><a href="crops.html">Crop table</a></h3>
    <p class="muted" style="margin:0">All {n_crops} crops with their metadata and headline
    numbers, sortable and filterable.</p></div>
  <div class="card"><h3 style="margin-top:0"><a href="figures.html">Figure gallery</a></h3>
    <p class="muted" style="margin:0">Every plot the analysis pipeline produces.</p></div>
  <div class="card"><h3 style="margin-top:0"><a href="membranes/views.html">3D views</a> and
    <a href="membranes/inspector.html">inspector</a></h3>
    <p class="muted" style="margin:0">Membrane surfaces in 3D &mdash; a quick paired gallery,
    and a viewer with all 55 crops and live control of the colour range.</p></div>
</div>

<h2>What is measured</h2>
<div class="two">
  <div class="card scroll"><table>
    <thead><tr><th>Metric family</th><th class="num">Metrics</th><th class="num">Values</th></tr></thead>
    <tbody>{fam_rows}</tbody></table>
    <p class="note">Each family is computed three ways &mdash; at native resolution, matched to
    8&nbsp;nm, and across a degradation series &mdash; so a difference can be checked against
    what resolution alone would produce. <a href="reference.html#design">What the runs mean.</a></p>
  </div>
  <div class="card">
    <h3 style="margin-top:0">Preparation</h3>
    {"".join(f'<p class="muted" style="margin:2px 0"><span class="tag {"chem" if "Chem" in k else "hpf"}">{esc(k)}</span> {v} crops</p>' for k, v in sorted(preps.items()))}
    <h3>Tissue</h3>
    {"".join(f'<p class="muted" style="margin:2px 0">{esc(k)} &mdash; {v} crops</p>' for k, v in sorted(tissues.items()))}
  </div>
</div>

<h2 id="coverage">Where the comparison is supported</h2>
<p class="lede" style="margin-bottom:12px">A region can only support a chemical-vs-HPF
comparison if both arms have crops in it. <b>{thin} of {len(rows)} do not.</b> Kidney, where the
direction of the effect splits by region, is where most of the gaps are.</p>
<div class="card scroll"><table>
  <thead><tr><th>Tissue</th><th>Region</th><th class="num">Chemical</th>
    <th class="num">Rapid HPF</th><th class="wrap"></th></tr></thead>
  <tbody>{"".join(rows)}</tbody></table></div>

<h2>Data</h2>
<p class="muted">Everything on this site is generated from
<a href="data/all_metrics_long.csv">all_metrics_long.csv</a> (one row per measurement) and
<a href="data/all_metrics_wide.csv">all_metrics_wide.csv</a> (one row per crop, run and
resolution), with names and units from <a href="data/metrics.json">metrics.json</a>.
Rebuild with <code>python scripts/collect_all.py</code>.</p>
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
                       f'<br><span style="font-weight:400;text-transform:none;letter-spacing:0">'
                       f'{esc(unit)}</span></th>')

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
        body += (f'<tr><td><a href="membranes/membrane_{r["crop"]}.png">{r["crop"]}</a></td>'
                 f'<td>{esc(r["tissue"])}</td><td>{esc(r["region_group"])}</td>'
                 f'<td class="wrap">{esc(r["anatomy"])}</td>'
                 f'<td><span class="tag {cls}">{esc(r["prep"])}</span></td>'
                 f'<td class="num">{r["native_voxel_nm"] or ""}</td>'
                 + "".join(cell(r, k) for k in cols) + "</tr>")

    html = sh.head("Crops — ECS preservation", 0,
                   "<style>#q{min-width:250px}th{vertical-align:bottom}</style>")
    html += sh.nav("crops.html", 0)
    html += f"""<main class="wide">
<h1>Crops</h1>
<p class="lede">All {len(native)} annotated crops at native resolution, with one headline number
from each metric family. Hover a column heading for what it measures; the
<a href="reference.html#metrics">dictionary</a> has all {len(mets)}. Crop names link to the
membrane render.</p>
{sh.PREP_LEGEND}
<div class="controls"><div class="ctl"><label for="q">Filter</label>
  <input type="search" id="q" placeholder="tissue, region, prep, crop&hellip;"></div>
  <div class="ctl"><label>Showing</label><span id="count" class="muted"
   style="font-size:13.5px;padding:6px 0">{len(native)} crops</span></div></div>
<div class="card scroll"><table id="t"><thead><tr>
  <th class="sortable">Crop</th><th class="sortable">Tissue</th><th class="sortable">Region</th>
  <th class="sortable wrap">Anatomy</th><th class="sortable">Prep</th>
  <th class="num sortable">Voxel<br><span style="font-weight:400;text-transform:none">nm</span></th>
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
    build_crops(wide_rows, mets)
    p = DOCS / "crops.html"
    p.write_text(p.read_text().replace("</body></html>", CROPS_JS + "</body></html>"))
    print(f"built docs/index.html and docs/crops.html ({n} crops)")


if __name__ == "__main__":
    main()
