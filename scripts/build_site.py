#!/usr/bin/env python3
"""
Build the static docs/ site published at https://avweigel.github.io/ecs-analysis/

Regenerates the overview and crop table from results/. The metric explorer
(docs/explore.html) is hand-written and reads docs/data/*.csv at runtime, so it
needs no regeneration; this script refreshes the data copies it reads.

    python scripts/build_site.py
"""
from __future__ import annotations

import csv, shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES, DOCS = ROOT / "results", ROOT / "docs"

NAV = """<header class="top"><div class="wrap">
  <span class="brand">ECS preservation</span>
  <nav>
    <a href="index.html"{a_home}>Overview</a>
    <a href="explore.html"{a_exp}>Metric explorer</a>
    <a href="crops.html"{a_crop}>Crops</a>
    <a href="figures.html">Figures</a>
    <a href="membranes/views.html">3D views</a>
    <a href="membranes/inspector.html">Membrane inspector</a>
  </nav>
</div></header>"""

HEAD = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="assets/app.css">{extra}</head><body>"""

CUR = ' aria-current="page"'


def read(name):
    p = RES / name
    return list(csv.DictReader(p.open())) if p.exists() else []


def build_index(long_rows, wide_rows):
    crops = {r["crop"]: r for r in wide_rows if r["run"] == "native"}
    n_crops = len(crops)
    n_meas = len(long_rows)
    n_metrics = len({(r["metric_family"], r["metric"]) for r in long_rows})
    tissues = Counter(r["tissue"] for r in crops.values())
    preps = Counter(r["prep"] for r in crops.values())

    # region coverage, both arms
    reg = defaultdict(Counter)
    for r in crops.values():
        reg[(r["tissue"], r["region_group"] or "(unassigned)")][r["prep"]] += 1
    rows = []
    for (t, g), c in sorted(reg.items()):
        nc, nh = c.get("Chemical", 0), c.get("Rapid HPF", 0)
        thin = nc <= 1 or nh <= 1
        rows.append(
            f'<tr><td>{t}</td><td>{g}</td>'
            f'<td class="num">{nc}</td><td class="num">{nh}</td>'
            f'<td>{"<span class=thin-flag>one arm too thin</span>" if thin else ""}</td></tr>')

    fams = Counter(r["metric_family"] for r in long_rows)
    fam_rows = "".join(
        f'<tr><td>{f.replace("_"," ")}</td><td class="num">'
        f'{len({(r["metric"]) for r in long_rows if r["metric_family"]==f})}</td>'
        f'<td class="num">{n:,}</td></tr>' for f, n in sorted(fams.items()))

    extra = """<style>
      .thin-flag{color:var(--chem);font-size:12px;font-weight:600}
      td.num{font-variant-numeric:tabular-nums}
      .two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
      @media(max-width:820px){.two{grid-template-columns:1fr}}
    </style>"""
    html = HEAD.format(title="ECS preservation — data overview", extra=extra)
    html += NAV.format(a_home=CUR, a_exp="", a_crop="")
    html += f"""<main>
  <h1>Extracellular space across fixation methods</h1>
  <p class="lede">Every measurement from the chemical-fixation versus rapid high-pressure-freezing
  comparison, browsable rather than filed away in CSVs. Nothing here is a finished result — this is
  the working data, published so it can be looked at from the outside.</p>

  <div class="grid tiles">
    <div class="card tile"><div class="n">{n_crops}</div><div class="k">annotated crops</div></div>
    <div class="card tile"><div class="n">{n_metrics}</div><div class="k">distinct metrics</div></div>
    <div class="card tile"><div class="n">{n_meas:,}</div><div class="k">measurements</div></div>
    <div class="card tile"><div class="n">{len(tissues)}</div><div class="k">tissues</div></div>
  </div>

  <h2>What is measured</h2>
  <div class="two">
    <div class="card scroll"><table>
      <thead><tr><th>Metric family</th><th class="num">Metrics</th><th class="num">Values</th></tr></thead>
      <tbody>{fam_rows}</tbody></table>
      <p class="note">Each family runs three ways: <b>native</b> resolution, <b>matched</b> to 8&nbsp;nm
      so preps are compared on equal footing, and a <b>degradation</b> series that downsamples
      chemical crops to 2/4/8/16&nbsp;nm to separate real differences from resolution effects.</p>
    </div>
    <div class="card">
      <p style="margin-top:0"><b>Preparation</b></p>
      {"".join(f'<p class="muted" style="margin:2px 0">{k} — {v} crops</p>' for k,v in sorted(preps.items()))}
      <p style="margin-top:16px"><b>Tissue</b></p>
      {"".join(f'<p class="muted" style="margin:2px 0">{k} — {v} crops</p>' for k,v in sorted(tissues.items()))}
    </div>
  </div>

  <h2>Where the comparison is actually supported</h2>
  <p class="lede" style="margin-bottom:12px">A region only supports a chemical-vs-HPF comparison
  if both arms have crops in it. Several do not — worth knowing before reading any difference
  in that region as real.</p>
  <div class="card scroll"><table>
    <thead><tr><th>Tissue</th><th>Region</th><th class="num">Chemical</th>
      <th class="num">Rapid HPF</th><th></th></tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>

  <h2>Browse</h2>
  <div class="two">
    <div class="card"><p style="margin-top:0"><b><a href="explore.html">Metric explorer</a></b></p>
      <p class="muted">Any metric, grouped by tissue, region or anatomy, both preps on a shared
      scale. Each dot is one crop.</p></div>
    <div class="card"><p style="margin-top:0"><b><a href="crops.html">Crop table</a></b></p>
      <p class="muted">All {n_crops} crops with their metadata and headline numbers, linked to
      their membrane renders.</p></div>
    <div class="card"><p style="margin-top:0"><b><a href="figures.html">Figure gallery</a></b></p>
      <p class="muted">Every plot the pipeline produces.</p></div>
    <div class="card"><p style="margin-top:0"><b><a href="membranes/views.html">3D views</a>
    <a href="membranes/inspector.html">Membrane inspector</a></b></p>
      <p class="muted">Interactive 3D membrane patches; curvature, deviation and gap colormapped
      live with adjustable range.</p></div>
  </div>

  <h2>Data</h2>
  <p class="muted">Everything on this site comes from two files, both downloadable:
    <a href="data/all_metrics_long.csv">all_metrics_long.csv</a> (tidy, one row per measurement) and
    <a href="data/all_metrics_wide.csv">all_metrics_wide.csv</a> (one row per crop/run/resolution).
    Regenerate with <code>python scripts/collect_all.py</code>.</p>
</main></body></html>"""
    (DOCS / "index.html").write_text(html)
    return n_crops


def build_crops(wide_rows):
    native = [r for r in wide_rows if r["run"] == "native"]
    cols = [("volume_fraction.ecs_fraction", "ECS fraction"),
            ("ecs_width.narrow_percentiles_nm_p50", "ECS width p50 (nm)"),
            ("ecs_width.narrow_std_nm", "width SD (nm)"),
            ("sa_v.sa_v_ecs_per_nm", "SA:V (1/nm)"),
            ("sa_v.cell_density_per_um3", "cells / um3"),
            ("topology.protrusion_density_per_um2", "protrusions / um2")]

    def cell(r, k):
        v = r.get(k, "")
        if v in ("", None):
            return '<td class="num muted">—</td>'
        f = float(v)
        s = f"{f:.4g}" if abs(f) < 1000 else f"{f:,.0f}"
        return f'<td class="num">{s}</td>'

    body = ""
    for r in sorted(native, key=lambda x: x["crop"]):
        cls = "chem" if r["prep"] == "Chemical" else "hpf"
        png = f'membranes/membrane_{r["crop"]}.png'
        body += (f'<tr><td><a href="{png}">{r["crop"]}</a></td><td>{r["tissue"]}</td>'
                 f'<td>{r["region_group"] or ""}</td><td>{r["anatomy"] or ""}</td>'
                 f'<td><span class="tag {cls}">{r["prep"]}</span></td>'
                 f'<td class="num">{r["native_voxel_nm"] or ""}</td>'
                 + "".join(cell(r, k) for k, _ in cols) + "</tr>")

    head = ("<tr><th>Crop</th><th>Tissue</th><th>Region</th><th>Anatomy</th><th>Prep</th>"
            "<th class='num'>Voxel nm</th>"
            + "".join(f"<th class='num'>{lab}</th>" for _, lab in cols) + "</tr>")

    extra = """<style>#q{min-width:240px}</style>"""
    html = HEAD.format(title="Crops — ECS preservation", extra=extra)
    html += NAV.format(a_home="", a_exp="", a_crop=CUR)
    html += f"""<main>
  <h1>Crops</h1>
  <p class="lede">All {len(native)} annotated crops at native resolution, with the headline number
  from each metric family. Crop names link to the membrane render.</p>
  <div class="controls"><div class="ctl"><label for="q">Filter</label>
    <input type="search" id="q" placeholder="tissue, region, prep, crop…"></div></div>
  <div class="card scroll"><table id="t"><thead>{head}</thead><tbody>{body}</tbody></table></div>
  <p class="note">Click a column header to sort. Values are native-resolution; use the
  <a href="explore.html">explorer</a> for the resolution-matched runs.</p>
</main>
<script>
const t=document.getElementById('t'), q=document.getElementById('q');
q.addEventListener('input',()=>{{const v=q.value.toLowerCase();
  for(const tr of t.tBodies[0].rows) tr.style.display = tr.textContent.toLowerCase().includes(v)?'':'none';}});
t.tHead.addEventListener('click',e=>{{
  const th=e.target.closest('th'); if(!th)return;
  const i=[...th.parentNode.children].indexOf(th);
  const num=th.classList.contains('num');
  const dir=th.dataset.d==='1'?-1:1;
  [...t.tHead.rows[0].cells].forEach(c=>delete c.dataset.d); th.dataset.d=dir===1?'1':'0';
  const rows=[...t.tBodies[0].rows].sort((a,b)=>{{
    const x=a.cells[i].textContent.trim(), y=b.cells[i].textContent.trim();
    if(num){{const nx=parseFloat(x.replace(/,/g,'')), ny=parseFloat(y.replace(/,/g,''));
      if(isNaN(nx))return 1; if(isNaN(ny))return -1; return (nx-ny)*dir;}}
    return x.localeCompare(y)*dir;}});
  rows.forEach(r=>t.tBodies[0].appendChild(r));
}});
</script></body></html>"""
    (DOCS / "crops.html").write_text(html)


def main():
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    for f in ("all_metrics_long.csv", "all_metrics_wide.csv", "stats_native.csv",
              "summary_native_anatomy_matched.csv"):
        if (RES / f).exists():
            shutil.copy2(RES / f, DOCS / "data" / f)
    long_rows = list(csv.DictReader((DOCS / "data" / "all_metrics_long.csv").open()))
    wide_rows = list(csv.DictReader((DOCS / "data" / "all_metrics_wide.csv").open()))
    n = build_index(long_rows, wide_rows)
    build_crops(wide_rows)
    print(f"built docs/index.html and docs/crops.html ({n} crops)")


if __name__ == "__main__":
    main()
