#!/usr/bin/env python3
"""
Build figures/membranes/methods.html — a long-form methods page for the
mesh-based membrane topology analysis, mirroring the LaTeX in
paper/methods_membrane_topology.tex. Reads the aggregate JSON written by
aggregate_topology_stats.py so the per-tissue and region-matched tables
stay in sync with the data.

Usage:
    python scripts/build_methods_page.py
"""
from __future__ import annotations

import json
import math
import shutil
from html import escape
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "figures" / "membranes" / "methods.html"
AGG = REPO_ROOT / "results" / "membrane_topology_aggregates.json"
OUTLIERS_JSON = REPO_ROOT / "results" / "topology_outliers.json"


# References for the methods text. Keys mirror paper/references.bib so the
# HTML page and the LaTeX manuscript stay in lockstep. When citing from the
# BODY template, use [{key}] (e.g. [Lorensen1987]); _resolve_cites() replaces
# them with anchored superscripts and the trailing References section is
# rendered from the entries actually cited (in citation order).
REFS = {
    "Lorensen1987": (
        "Lorensen WE, Cline HE. Marching cubes: A high resolution 3D surface "
        "construction algorithm. Proc. SIGGRAPH '87, 163–169 (1987). "
        "doi:10.1145/37401.37422"
    ),
    "Pinkall1993": (
        "Pinkall U, Polthier K. Computing discrete minimal surfaces and "
        "their conjugates. Experimental Mathematics 2(1): 15–36 (1993). "
        "doi:10.1080/10586458.1993.10504266"
    ),
    "Meyer2003": (
        "Meyer M, Desbrun M, Schröder P, Barr AH. Discrete differential-"
        "geometry operators for triangulated 2-manifolds. Visualization and "
        "Mathematics III, 35–57 (Springer, 2003). "
        "doi:10.1007/978-3-662-05105-4_2"
    ),
    "Desbrun1999": (
        "Desbrun M, Meyer M, Schröder P, Barr AH. Implicit fairing of "
        "irregular meshes using diffusion and curvature flow. Proc. "
        "SIGGRAPH '99, 317–324 (1999). doi:10.1145/311535.311576"
    ),
    "Maurer2003": (
        "Maurer CR, Qi R, Raghavan V. A linear time algorithm for computing "
        "exact Euclidean distance transforms of binary images in arbitrary "
        "dimensions. IEEE TPAMI 25(2): 265–270 (2003). "
        "doi:10.1109/TPAMI.2003.1177156"
    ),
    "vanderWalt2014": (
        "van der Walt S, Schönberger JL, Nunez-Iglesias J, et al. "
        "scikit-image: image processing in Python. PeerJ 2: e453 (2014). "
        "doi:10.7717/peerj.453"
    ),
    "Virtanen2020": (
        "Virtanen P, Gommers R, Oliphant TE, et al. SciPy 1.0: fundamental "
        "algorithms for scientific computing in Python. Nature Methods 17: "
        "261–272 (2020). doi:10.1038/s41592-019-0686-2"
    ),
    "Harris2020": (
        "Harris CR, Millman KJ, van der Walt SJ, et al. Array programming "
        "with NumPy. Nature 585: 357–362 (2020). "
        "doi:10.1038/s41586-020-2649-2"
    ),
    "DawsonHaggerty2019": (
        "Dawson-Haggerty M et al. trimesh: Python library for triangular "
        "mesh processing. <a href='https://github.com/mikedh/trimesh'>"
        "github.com/mikedh/trimesh</a>"
    ),
    "Neuroglancer": (
        "Maitin-Shepard J et al. Neuroglancer: web-based volumetric data "
        "viewer. <a href='https://github.com/google/neuroglancer'>"
        "github.com/google/neuroglancer</a>"
    ),
    "ModelViewer": (
        "Google. &lt;model-viewer&gt;: easily display interactive 3D models "
        "on the web and in augmented reality. "
        "<a href='https://github.com/google/model-viewer'>"
        "github.com/google/model-viewer</a>"
    ),
    "Heinrich2021": (
        "Heinrich L, Bennett D, Ackerman D, et al. Whole-cell organelle "
        "segmentation in volume electron microscopy. Nature 599: 141–146 "
        "(2021). doi:10.1038/s41586-021-03977-3"
    ),
    "Xu2021": (
        "Xu CS, et al. An open-access volume electron microscopy atlas of "
        "whole cells and tissues. Nature 599: 147–151 (2021). "
        "doi:10.1038/s41586-021-03992-4"
    ),
}


def sensitivity_table(cmp_combined: list[dict], outliers: dict) -> str:
    """Side-by-side Chem-vs-HPF ratio table, all-crops vs outliers-excluded.
    Rows where outlier exclusion shrinks n are highlighted; unchanged rows
    appear in muted styling so the contrast is obvious."""
    affected = {(o["tissue"], o["region_group"]) for o in outliers.values()}
    rows = []

    def _r(v, hi=False, lo=False, dim=False):
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return "<td>—</td>"
        cls = "ratio"
        if hi: cls += " hi"
        if lo: cls += " lo"
        if dim: cls += " dim"
        return f"<td class='{cls}'>{v:.2f}</td>"
    for r in cmp_combined:
        key = (r["tissue"], r["region_group"])
        is_affected = key in affected
        tr_cls = "affected" if is_affected else "muted"
        n_all_c, n_all_h = r["n_chem"], r["n_hpf"]
        n_cln_c = r.get("n_chem_no_outliers", n_all_c)
        n_cln_h = r.get("n_hpf_no_outliers", n_all_h)
        rows.append(
            f"<tr class='{tr_cls}'>"
            f"<td>{escape(r['tissue'])}</td>"
            f"<td>{escape(r['region_group'])}</td>"
            f"<td class=n>{n_all_c}/{n_all_h}</td>"
            f"{_r(r.get('H_ratio_chem_over_hpf'), dim=not is_affected)}"
            f"{_r(r.get('d_ratio_chem_over_hpf'), dim=not is_affected)}"
            f"{_r(r.get('g_ratio_chem_over_hpf'), dim=not is_affected)}"
            f"<td class=n>{n_cln_c}/{n_cln_h}</td>"
            f"{_r(r.get('H_ratio_chem_over_hpf_no_outliers'), dim=not is_affected)}"
            f"{_r(r.get('d_ratio_chem_over_hpf_no_outliers'), dim=not is_affected)}"
            f"{_r(r.get('g_ratio_chem_over_hpf_no_outliers'), dim=not is_affected)}"
            f"</tr>")
    return ("<table class=sensitivity><thead>"
            "<tr><th rowspan=2>Tissue</th><th rowspan=2>Region group</th>"
            "<th colspan=4>All crops</th>"
            "<th colspan=4>Outliers excluded</th></tr>"
            "<tr><th>n (C/H)</th><th>H</th><th>d</th><th>g</th>"
            "<th>n (C/H)</th><th>H</th><th>d</th><th>g</th></tr>"
            "</thead><tbody>" + "".join(rows) + "</tbody></table>")


def outliers_table(outliers: dict) -> str:
    """Render the per-crop outlier candidates as a table. Outliers are sorted
    by (tissue, region, prep, crop) for a stable display order; empty input
    renders a friendly 'no candidates' note instead of an empty table."""
    if not outliers:
        return ("<p style='color:#445;font-size:14px'><em>No outlier "
                "candidates with the current thresholds.</em></p>")
    rows = []
    for crop, info in sorted(outliers.items(),
                             key=lambda kv: (kv[1]["tissue"],
                                             kv[1]["region_group"],
                                             kv[1]["prep"], kv[0])):
        prep_cls = "chem" if info["prep"] == "Chemical" else "hpf"

        def cell_ratio(r):
            if r is None or not math.isfinite(r):
                return "—"
            cls = "hi" if r > 1.7 else ("lo" if r < 0.6 else "")
            return f"<span class='ratio {cls}'>{r:.2f}×</span>"
        rows.append(
            f"<tr>"
            f"<td><code>{escape(crop)}</code></td>"
            f"<td>{escape(info['tissue'])}</td>"
            f"<td>{escape(info['region_group'])}</td>"
            f"<td><span class='prep {prep_cls}'>{escape(info['prep'])}</span></td>"
            f"<td class=n>{info['group_n']}</td>"
            f"<td>{cell_ratio(info.get('H_ratio'))}</td>"
            f"<td>{cell_ratio(info.get('d_ratio'))}</td>"
            f"<td class=reason>{escape(info['reason'])}</td>"
            f"</tr>")
    return ("<table class=outliers><thead><tr>"
            "<th>Crop</th><th>Tissue</th><th>Region group</th>"
            "<th>Prep</th><th>n</th>"
            "<th>|H| vs group</th><th>|d| vs group</th>"
            "<th>Reason</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def _resolve_cites(text: str) -> tuple[str, list[str]]:
    """Replace [Key] / [Key1,Key2] markers in `text` with numbered superscript
    HTML anchors, returning (rendered text, ordered list of cited keys). Each
    key is numbered in first-citation order. Unknown keys raise LookupError so
    typos in the template surface immediately rather than silently."""
    import re
    order: list[str] = []
    nums: dict[str, int] = {}

    def repl(m: re.Match) -> str:
        keys = [k.strip() for k in m.group(1).split(",")]
        # Only treat as a citation when every key is a known ref. Other
        # bracketed content (e.g. table captions like [Q1, Q3]) passes
        # through unchanged.
        if not all(k in REFS for k in keys):
            return m.group(0)
        parts = []
        for k in keys:
            if k not in nums:
                order.append(k)
                nums[k] = len(order)
            n = nums[k]
            parts.append(f"<a class=cite href='#ref-{k}'>{n}</a>")
        return f"<sup class=cite>[{','.join(parts)}]</sup>"

    rendered = re.sub(r"\[([A-Za-z][A-Za-z0-9]*(?:\s*,\s*[A-Za-z][A-Za-z0-9]*)*)\]",
                      repl, text)
    return rendered, order


def _references_html(order: list[str]) -> str:
    items = []
    for i, k in enumerate(order, 1):
        items.append(f"<li id='ref-{k}'><span class=refn>{i}.</span> {REFS[k]}</li>")
    return ("<h2 id=refs>References</h2>"
            "<ol class=refs>" + "".join(items) + "</ol>")


def _fmt(v, fmt=".3g"):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return format(v, fmt)


def _cell(r, col, fmt=".3g"):
    if r is None:
        return "—"
    return (f"{_fmt(r[col + '_median'], fmt)} "
            f"<span class=iqr>[{_fmt(r[col + '_iqr_lo'], fmt)}, "
            f"{_fmt(r[col + '_iqr_hi'], fmt)}]</span>")


def tissue_table(by_tissue: list[dict]) -> str:
    rows = []
    for r in sorted(by_tissue, key=lambda r: (r["tissue"], r["prep"])):
        prep_cls = "chem" if r["prep"] == "Chemical" else "hpf"
        rows.append(
            f"<tr>"
            f"<td>{escape(r['tissue'])}</td>"
            f"<td><span class='prep {prep_cls}'>{escape(r['prep'])}</span></td>"
            f"<td class=n>{r['n_crops']}</td>"
            f"<td>{_cell(r, 'abs_curvature_p50_nm-1', '.4f')}</td>"
            f"<td>{_cell(r, 'abs_deviation_p50_nm', '.2f')}</td>"
            f"<td>{_cell(r, 'gap_p50_nm', '.1f')}</td>"
            f"<td>{_fmt(r['gap_bounded_frac_median'], '.2f')}</td>"
            f"</tr>")
    return ("<table class=stats><thead><tr>"
            "<th>Tissue</th><th>Fixation</th><th>n</th>"
            "<th>|H| (1/nm)</th><th>|d| (nm)</th><th>g (nm)</th>"
            "<th>bd-clip</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def region_table(by_region: list[dict]) -> str:
    by_key: dict[tuple[str, str], dict[str, dict]] = {}
    for r in by_region:
        if not r["region_group"]:
            continue
        by_key.setdefault((r["tissue"], r["region_group"]), {})[r["prep"]] = r
    rows = []
    for (tissue, region), preps in sorted(by_key.items()):
        chem, hpf = preps.get("Chemical"), preps.get("Rapid HPF")
        if not (chem and hpf):
            continue
        rows.append(
            f"<tr>"
            f"<td>{escape(tissue)}</td>"
            f"<td>{escape(region)}</td>"
            f"<td class=n>{chem['n_crops']}/{hpf['n_crops']}</td>"
            f"<td>{_cell(chem, 'abs_curvature_p50_nm-1', '.4f')}</td>"
            f"<td>{_cell(hpf,  'abs_curvature_p50_nm-1', '.4f')}</td>"
            f"<td>{_cell(chem, 'abs_deviation_p50_nm', '.2f')}</td>"
            f"<td>{_cell(hpf,  'abs_deviation_p50_nm', '.2f')}</td>"
            f"<td>{_cell(chem, 'gap_p50_nm', '.1f')}</td>"
            f"<td>{_cell(hpf,  'gap_p50_nm', '.1f')}</td>"
            f"</tr>")
    return ("<table class=stats><thead><tr>"
            "<th rowspan=2>Tissue</th><th rowspan=2>Region group</th>"
            "<th rowspan=2>n (Chem/HPF)</th>"
            "<th colspan=2>|H| (1/nm)</th>"
            "<th colspan=2>|d| (nm)</th>"
            "<th colspan=2>g (nm)</th></tr>"
            "<tr><th class=chem>Chem</th><th class=hpf>HPF</th>"
            "<th class=chem>Chem</th><th class=hpf>HPF</th>"
            "<th class=chem>Chem</th><th class=hpf>HPF</th></tr></thead>"
            "<tbody>" + "".join(rows) + "</tbody></table>")


BODY = """
<h1>Methods — mesh-based membrane topology</h1>
<p class=lead>
This page documents the per-crop pipeline that produces the curvature,
protrusion/indentation, and contact-gap channels rendered in the
<a href="membranes_3d.html">interactive 3D gallery</a> and the
<a href="index.html">static maps</a>. It is the web companion to the
manuscript draft at <code>paper/methods_membrane_topology.tex</code>
and stays in sync with the results CSVs at <code>results/</code>.
</p>

<nav class=toc>
  <a href="#wha">What was done</a> ·
  <a href="#curv">Curvature</a> ·
  <a href="#prot">Protrusion</a> ·
  <a href="#gap">Contact gap</a> ·
  <a href="#bd">Boundary handling</a> ·
  <a href="#stats">Per-crop stats</a> ·
  <a href="#viz">Visualisation</a> ·
  <a href="#res">Results — overall</a> ·
  <a href="#reg">Results — region-matched</a> ·
  <a href="#figs">Figures</a> ·
  <a href="#headline">Headline observations</a> ·
  <a href="#outliers">Outlier candidates</a> ·
  <a href="#sens">Sensitivity</a> ·
  <a href="#voronoi">vs Metric 5 (Voronoi)</a> ·
  <a href="#refs">references</a>
</nav>

<h2 id=wha>What was done</h2>
<p>
For each crop a single membrane-rich cell was selected as the cell with
the greatest area of cell–ECS interface (counted as the number of cell
faces sharing a boundary with an ECS voxel; ties broken by cell index).
Crops with finer-than-16&nbsp;nm native voxel size were box-downsampled
to 16&nbsp;nm isotropic prior to meshing, so all crops feed an identical
analysis grid regardless of acquisition resolution.
</p>
<p>
The cell's binary mask was smoothed with a 3D Gaussian of physical width
<code>σ = 1.5·v<sub>x</sub></code> nm (= 24&nbsp;nm at the 16&nbsp;nm
working voxel), then surfaced by marching cubes [Lorensen1987] at
iso-level 0.5 (<code>scikit-image</code> implementation
[vanderWalt2014]). Surface vertices are placed in nm coordinates
accounting for both the cropping bounding-box offset and the smoothing
pad. The sign convention is calibrated against a synthetic convex
sphere of radius 400&nbsp;nm through the same pipeline; convex membranes
return positive curvature.
</p>

<h2 id=curv>Signed mean curvature <code>H</code> (1/nm)</h2>
<p>
Computed from the <b>cotangent Laplacian</b>
[Pinkall1993,Meyer2003], a strictly <i>local</i> 1-ring quantity. For
each interior edge of the mesh, cotangent weights
of the two opposite angles enter a sparse Laplacian operator
<code>L</code>; the mean-curvature normal vector at vertex <i>i</i> is
<code>H<sub>i</sub>·n<sub>i</sub> = (LV)<sub>i</sub> / (2A<sub>i</sub>)</code>,
where <code>A<sub>i</sub></code> is the barycentric vertex area. The
magnitude is the unsigned curvature; the sign is taken from
<code>sgn(H<sub>i</sub> · n<sub>i</sub><sup>trimesh</sup>)</code>,
calibrated so convex (membrane-into-ECS) surfaces are positive.
</p>
<p>
The radius of curvature is <code>R = 1/|H|</code>. Representative
values:
</p>
<table class=small>
<thead><tr><th>H (1/nm)</th><th>R</th><th>Feature</th></tr></thead>
<tbody>
<tr><td>0.001</td><td>1000 nm</td><td>essentially flat</td></tr>
<tr><td>0.005</td><td>200 nm</td><td>gentle membrane bend</td></tr>
<tr><td>0.010</td><td>100 nm</td><td>cell-body curvature</td></tr>
<tr><td>0.020</td><td>50 nm</td><td>microvillus shaft</td></tr>
<tr><td>0.050</td><td>20 nm</td><td>sharp microvillus tip</td></tr>
<tr><td>0.100</td><td>10 nm</td><td>very sharp spike</td></tr>
</tbody></table>

<h2 id=prot>Protrusion / indentation <code>d</code> (nm)</h2>
<p>
Per-vertex signed normal-projected displacement of each vertex from a
smoothed reference surface generated from the same mesh. The reference
is produced by random-walk Laplacian iteration on vertex coordinates
(<code>v<sub>new</sub> = v − λ&nbsp;D<sup>−1</sup>&nbsp;L&nbsp;v</code>,
<code>λ&nbsp;=&nbsp;0.5</code>) [Desbrun1999] with the iteration count
chosen so the
effective smoothing scale is <code>σ&nbsp;=&nbsp;60&nbsp;nm</code> given
the mesh's mean edge length:
<code>N&nbsp;≈&nbsp;σ²/(2h²λ)</code>. The signed deviation is the
inward-normal projection of the original-minus-smoothed displacement,
so <code>d&nbsp;&gt;&nbsp;0</code> = vertex protrudes outward into ECS,
<code>d&nbsp;&lt;&nbsp;0</code> = indentation.
</p>
<p>
<b>Scale-aware where curvature isn't.</b> Curvature answers
<i>"is the surface bent here, and which way?"</i>; protrusion
answers <i>"does this point stick out (or in) compared to its
~60&nbsp;nm neighbourhood?"</i>. A gentle 100&nbsp;nm-tall ridge gives
large positive <code>d</code> but small <code>|H|</code>; a 5&nbsp;nm
bump on flat membrane gives small <code>d</code> but large
<code>|H|</code>. The two channels agree at microvillar features
(sharp tip + reaching shaft) and diverge over gently undulating
surfaces.
</p>

<h2 id=gap>Local contact gap <code>g</code> (nm)</h2>
<p>
3D Euclidean distance transform (EDT) [Maurer2003,Virtanen2020] of the
"not-other-cell" indicator field, sampled at the rounded voxel
coordinate of each mesh vertex.
<code>g<sub>i</sub></code> is therefore the distance from vertex
<code>i</code> to the nearest voxel belonging to any cell other than
the one being analysed. A membrane patch was isolated by retaining
only vertices within one voxel (max-norm) of an ECS-labelled voxel;
the per-vertex test was dilated by two ring-neighbour iterations on
the mesh edge graph to close scattered single-vertex dropouts.
Faces with ≥&nbsp;50% ECS-facing vertices were included in the patch.
Faces within two voxels of any volume face were dropped from the
patch to avoid marching-cubes cap-face artifacts.
</p>

<h2 id=bd>Volume-boundary handling</h2>
<p>
Two boundary effects are corrected in the per-channel rendering and
summary statistics.
</p>
<p>
<b>(i) Gap channel.</b> The in-volume EDT overestimates the gap
whenever the nearest neighbouring cell lies <i>outside</i> the crop.
Formally, for every vertex
<code>g<sub>i</sub><sup>true</sup>&nbsp;≤&nbsp;min(g<sub>i</sub><sup>EDT</sup>,&nbsp;d<sub>i</sub><sup>wall</sup>)</code>
where <code>d<sub>i</sub><sup>wall</sup></code> is the L∞ distance from
vertex <code>i</code> to the nearest of the six volume faces.
Vertices satisfying
<code>g<sub>i</sub><sup>EDT</sup>&nbsp;&gt;&nbsp;d<sub>i</sub><sup>wall</sup></code>
are flagged as <b>boundary-uncertain</b> and dropped from the gap
channel (rather than silently clipped — clipping just paints a
low-value rim, swapping one artifact for another). The per-patch
boundary-uncertain fraction (<code>bd-clip</code>, shown on each
gallery card) is the quality indicator.
</p>
<p>
<b>(ii) Curvature + protrusion channels.</b> The cotangent Laplacian
and the 60&nbsp;nm smoothing kernel both <i>reach beyond</i> the patch
rim into the marching-cubes cap face at the volume boundary, biasing
values inward and painting an artificial protrusion stripe along the
edge of every patch. Faces whose vertices lie within
<code>σ&nbsp;=&nbsp;60&nbsp;nm</code> of any volume face are therefore
dropped from the curvature + protrusion render. Patch geometry and
per-cell statistics (face counts, ECS-facing area fraction) are
reported on the unfiltered patch, so the boundary trims affect
rendering and per-channel summaries but not the geometric denominator.
</p>

<h2 id=stats>Per-crop statistics emitted</h2>
<p>
For each crop's patch the manifest records: patch face count, full-cell
mesh face count, ECS-facing fraction, gap-channel face count,
boundary-uncertain fraction, dataset and cell id, adaptive gap
colormap range, and per-channel signed/unsigned percentile statistics
(<code>p10/p50/p90</code> of <code>H</code>, <code>d</code>,
<code>g</code>; <code>|H|</code> and <code>|d|</code> at the same
percentiles; convex/concave and protrusion/indent fractions). See
<code>results/membrane_topology_per_crop.csv</code> for the full
per-crop table.
</p>

<h2 id=viz>Visualisation</h2>
<p>
The interactive 3D gallery exports each per-vertex scalar as a
vertex-coloured glTF&nbsp;2.0 (<code>.glb</code>) mesh via
<code>trimesh</code> [DawsonHaggerty2019] coloured with the
<code>matplotlib</code> <code>RdBu_r</code> (curvature, protrusion) and
<code>viridis</code> (gap) colormaps; meshes are rendered in the
browser by the <code>&lt;model-viewer&gt;</code> web component
[ModelViewer]. Each gallery card also exposes a Neuroglancer
[Neuroglancer] link wired to the underlying crop with the EM, ECS
silhouette mesh, and all cell meshes pre-loaded for visual
verification against the raw FIB-SEM EM. The volumes themselves are
hosted by the CellMap project [Heinrich2021, Xu2021]. The numerical
pipeline runs on top of NumPy [Harris2020] and SciPy [Virtanen2020].
</p>

<h2 id=res>Results — overall</h2>
<p>
The Liver Chemical pool shows the largest membrane topology magnitudes
(median <code>|H|&nbsp;=&nbsp;0.0048&nbsp;1/nm</code>,
<code>R&nbsp;≈&nbsp;208&nbsp;nm</code>; median
<code>|d|&nbsp;=&nbsp;3.2&nbsp;nm</code>) and the largest Chem–HPF gap
(Liver HPF: <code>|H|&nbsp;=&nbsp;0.0024&nbsp;1/nm</code>,
<code>|d|&nbsp;=&nbsp;1.4&nbsp;nm</code>). Heart and Kidney show
smaller fixation differences. The contact-gap median on the
ECS-facing patch is 25–90&nbsp;nm across tissues; Cortex Chemical is
the tightest (<code>g&nbsp;=&nbsp;16&nbsp;nm</code>) and Heart HPF the
widest (<code>g&nbsp;=&nbsp;88&nbsp;nm</code>).
<code>bd-clip</code> is below 0.21 in every (tissue, prep) cell,
indicating the gap channel is data-driven for almost all crops.
</p>
__TISSUE_TABLE__
<p class=note>
Each cell reports the <b>median across crops</b> of the per-crop median
of the absolute scalar value, with [Q1, Q3] across crops. <code>n</code>
is the number of crops in that (tissue, prep) cell.
</p>

<h2 id=reg>Results — region-matched</h2>
<p>
Eight region groups have both Chemical and HPF representation in the
crop set. Within these matched pools:
</p>
<ul>
<li><b>Liver Hepatocyte lateral</b> — Chemical ≈ HPF. Both report a
tight, smooth interface (Chem <code>|H|&nbsp;=&nbsp;0.0023</code> vs
HPF <code>0.0016</code>; <code>|d|&nbsp;=&nbsp;1.3</code> vs
<code>0.8&nbsp;nm</code>; <code>g&nbsp;=&nbsp;25</code> vs
<code>30&nbsp;nm</code>).</li>
<li><b>Liver Bile canaliculus</b> — Chemical shows substantially
sharper, more protrusive membranes than HPF
(Chem <code>|H|&nbsp;=&nbsp;0.0075</code>, <code>|d|&nbsp;=&nbsp;4.4&nbsp;nm</code>
vs HPF <code>0.0035</code>, <code>2.0&nbsp;nm</code>). Chemical fixation
appears to over-resolve / sharpen the microvillar brush border.</li>
<li><b>Heart Intercalated disc</b> — <i>HPF</i> higher than Chemical
(HPF <code>|H|&nbsp;=&nbsp;0.0034</code>, <code>|d|&nbsp;=&nbsp;2.2</code>
vs Chem <code>0.0026</code>, <code>1.7</code>) — opposite of the Bile
canaliculus trend. Consistent with HPF preserving the interdigitating
microvilli that Chemical collapses.</li>
<li><b>Kidney Glomerular</b> — HPF higher than Chemical
(<code>|H|&nbsp;=&nbsp;0.0047</code> vs <code>0.0037</code>;
<code>g&nbsp;=&nbsp;144</code> vs <code>87&nbsp;nm</code>).</li>
<li>Other region groups have small <code>n</code> per prep — read trends
off the per-crop CSV rather than the aggregate.</li>
</ul>
__REGION_TABLE__

<h2 id=figs>Figures</h2>
<p>
The membrane-topology and effect-size graphs are shown below. The full set of
per-metric Chemical-vs-HPF plots (volume fraction, ECS width, Voronoi gap, SA:V,
both native and resolution-matched) plus region vignettes and 3D renders is in
the <a href="../figures.html">figures gallery</a>.
</p>
<figure class=fig><a href="fig2_effect_matrix.png" target=_blank>
<img src="fig2_effect_matrix.png" alt="Cliff's delta effect-size matrix"></a>
<figcaption>Cliff's δ effect-size matrix across the region-matched comparisons
(warm = Chemical&nbsp;&gt;&nbsp;HPF, cool = HPF&nbsp;&gt;&nbsp;Chemical).</figcaption></figure>
<figure class=fig><a href="native_topology.png" target=_blank>
<img src="native_topology.png" alt="membrane topology strip plots"></a>
<figcaption>Membrane topology per tissue at native resolution — signed curvature,
roughness, and protrusion/indentation density (Chemical vs Rapid HPF, one dot per crop).</figcaption></figure>
<figure class=fig><a href="native_anatomy_matched.png" target=_blank>
<img src="native_anatomy_matched.png" alt="region-matched metric panel"></a>
<figcaption>Region-matched Chemical-vs-HPF comparison across the full metric suite.</figcaption></figure>

<h2 id=headline>Headline observations</h2>
<p>
Reading these as observations from the 55-crop set, not yet biological
conclusions:
</p>
<ol class=findings>
<li>
<b>Chemical fixation has opposite effects on two microvillar
interfaces.</b> Liver Bile canaliculus is sharper and more
protrusive under Chemical than under HPF (|H| ratio 2.11×, |d| ratio
2.24×) — consistent with chemical fixation rigidifying or
over-resolving the canalicular brush border. Heart Intercalated disc
runs the other way: HPF is sharper than Chemical (|H| ratio 0.74,
|d| ratio 0.75) — consistent with chemical fixation collapsing the
interdigitating microvilli at the disc. <i>The same fixation
condition produces opposite topology changes at two microvillar
interfaces.</i> A single &ldquo;Chemical smooths&rdquo; / &ldquo;Chemical sharpens&rdquo;
narrative doesn't fit the data.
</li>
<li>
<b>Kidney Glomerular: HPF preserves a substantially larger
interstitial gap.</b> Median <code>g</code> = 144&nbsp;nm under HPF
vs 87&nbsp;nm under Chemical — a 1.66× preservation. HPF also shows
higher curvature and protrusion (1.27× each), tracking the genuine
podocyte / endothelium / basal-membrane morphology that chemical
fixation collapses into a flatter, narrower interface.
</li>
<li>
<b>Liver Hepatocyte lateral is the calmest baseline, but also the
noisiest peer group.</b> Median values (|H| 0.0023 vs 0.0016,
<code>g</code> 25 vs 30&nbsp;nm) suggest a real tight apposition
with weak fixation effect. <i>But all four outlier candidates land
in this group</i>: crop1044 (Chemical) and crop1071 (HPF) both at
&gt;2× the group median on |H| and |d|. The peer-group label may
be too coarse (Kupffer / sinusoidal interfaces likely confounded
with hepatocyte–hepatocyte appositions), or the cell-selection
heuristic may have picked a non-representative cell. The flagged
crops are linked on the gallery for review.
</li>
<li>
<b>Cortex Chemical patches are tightly packed.</b> Median
<code>g</code> = 16&nbsp;nm — the smallest in the dataset —
with median <code>bd-clip</code> = 0.00 across the 7-crop pool,
indicating the reading is data-driven, not boundary-affected.
Consistent with the historically reported severe ECS reduction in
chemically-fixed cortex (Korogod et&nbsp;al.&nbsp;2015 territory).
</li>
<li>
<b>Outlier exclusion does not flip any Chem-vs-HPF conclusion.</b>
Excluding the 4 candidate outliers from Hepatocyte lateral leaves
every direction unchanged; the Chemical/HPF |H| and |d| ratios
actually shift slightly more extreme (1.44 → 1.56 on H, 1.58 → 1.87
on d). The matched-region story does not depend on the suspicious
crops.
</li>
<li>
<b>The Bile-canaliculus vs Intercalated-disc divergence is a finding
the Voronoi-only gap metric (Metric&nbsp;5) cannot see.</b> Metric 5
reports gap and only gap; it cannot distinguish &ldquo;sharpened brush
border&rdquo; from &ldquo;collapsed brush border&rdquo; if their gap distributions
happen to look similar. The shape channels in Metric&nbsp;8 are what
make observation&nbsp;1 visible.
</li>
</ol>

<h2 id=outliers>Outlier candidates within annotated peer groups</h2>
<p>
For each annotation group ((tissue, region group, fixation) with n&nbsp;≥&nbsp;3
crops), the per-crop median curvature |H| and median protrusion |d| are
compared against the within-group median. Any crop whose ratio to the
group median exceeds <code>1.7×</code> or falls below <code>0.6×</code>
on either metric is flagged. Singleton and n=2 groups are skipped (the
median is ill-defined for a peer of one or two). These are <i>candidates
for re-annotation or sub-grouping</i>, not automatic rejections — the
gallery cards surface a <span class=outlier-inline>⚠ outlier</span>
badge so the candidates aren't forgotten. Re-annotation decisions
belong to the annotator (Kayvon, Wei-Ping). The flagged list:
</p>
__OUTLIER_LIST__
<p class=note>
Heuristic rationale: within a correctly-annotated region group the
per-crop topology should cluster (the membrane biology should be the
same modulo crop-level variation). A &gt;1.7× or &lt;0.6× spread on
either |H| or |d| is well outside the typical within-group MAD
observed across the other 6 groups, so an outlier here usually
indicates either (a) the cell selected by the most-ECS-facing-surface
heuristic happens to capture a non-representative part of the tissue
(e.g.~a Kupffer cell rather than a hepatocyte in the
<i>Hepatocyte lateral</i> pool), (b) the underlying anatomical
substructure is heterogeneous and the region group label is too
coarse, or (c) the crop genuinely sits at the tail of the biological
distribution.
</p>

<h2 id=sens>Sensitivity of Chem-vs-HPF to outlier exclusion</h2>
<p>
To check whether the candidate outliers drive the Chem-vs-HPF
comparison in their region groups, every aggregate was recomputed with
the flagged crops removed. The table below shows the per-region
Chemical-to-HPF ratio of the per-crop median values (so values
&gt; 1 mean Chemical is higher than HPF on that channel) for every
region with both prep arms, computed twice: with all crops and with
the candidate outliers excluded. Only region groups whose <code>n</code>
changed under exclusion are highlighted; the others reproduce
verbatim (the outliers all sit in one region group in the current
data).
</p>
__SENSITIVITY_TABLE__
<p class=note>
Reading the table: a "<code>1.50</code>" in the <code>H</code> column
means the per-region median |H| of the Chemical crops is 1.5× that
of the HPF crops; a value &lt; 1 means HPF higher. In the current
data the only region group whose ratio changes is Liver Hepatocyte
lateral, and the direction of the Chem-vs-HPF effect is preserved
when the outliers are excluded — H and d ratios drift slightly higher
(Chem ≫ HPF becomes a touch more pronounced), and the gap ratio
shifts from 0.84 (HPF wider) to 1.00 (parity). No flagged outlier
flips the sign of any Chem-vs-HPF comparison.
</p>

<h2 id=voronoi>Methods comparison vs Metric 5 (Voronoi gap)</h2>
<p>
The mesh-based contact gap channel measures the same physical quantity
as the manuscript's Voronoi-tessellation Metric&nbsp;5, but the two
operate on different supports and disagree in instructive ways.
</p>
<table class=cmp>
<thead><tr><th></th>
<th>Metric 5 — Voronoi gap</th>
<th>Metric 8 — Mesh gap (this analysis)</th></tr></thead>
<tbody>
<tr><th>Support</th>
<td>every ECS Voronoi-boundary voxel (population of all cell–cell appositions in the crop)</td>
<td>vertices of one ECS-facing membrane patch (the most ECS-rich cell, per-vertex distribution)</td></tr>
<tr><th>Voxel floor</th>
<td>~14&nbsp;nm at 8&nbsp;nm voxels — drives a documented Chem-vs-HPF artifact at thresholds &lt; 20&nbsp;nm</td>
<td>same EDT floor, but every crop downsamples to a uniform 16&nbsp;nm working voxel — floor is shared between Chem and HPF, eliminating the prep×voxel confound</td></tr>
<tr><th>Open-space inflation</th>
<td>large ECS pools (vessel lumen, bile canaliculus) widen the Voronoi boundary and inflate the population median</td>
<td>EDT sampled at the membrane surface, so the reading is "distance from this membrane point to the nearest other cell" — open pools register as correctly high gap on the relevant patch vertices</td></tr>
<tr><th>Boundary handling</th>
<td>boundary overestimates absorbed into the crop-level median</td>
<td>per-vertex boundary uncertainty made explicit and dropped from the gap channel; per-crop <code>bd-clip</code> quantifies the loss</td></tr>
<tr><th>Co-located channels</th>
<td>gap only</td>
<td>gap colocated with curvature and protrusion on the same support — supports per-vertex queries like "what is the gap at the microvillus tip vs base"</td></tr>
</tbody></table>
<p>
The two metrics answer complementary questions: Metric&nbsp;5
characterises the population of cell–cell appositions per crop;
Metric&nbsp;8 characterises the shape and contact landscape of one
representative cell's ECS-facing surface. Consilience across both
metrics (e.g. Liver Hepatocyte lateral Chem ≈ HPF, Heart Intercalated
disc HPF-preserved, Liver Bile canaliculus Chem-sharpens) is taken
as confirmation; disagreements are usually traceable to support /
scale.
</p>
"""


def main() -> None:
    if not AGG.exists():
        raise SystemExit(
            f"missing {AGG}; run scripts/aggregate_topology_stats.py first")
    data = json.loads(AGG.read_text())
    try:
        outliers = json.loads(OUTLIERS_JSON.read_text())
    except FileNotFoundError:
        outliers = {}
    body, cited_order = _resolve_cites(BODY)
    body = (body
            .replace("__TISSUE_TABLE__", tissue_table(data["by_tissue"]))
            .replace("__REGION_TABLE__", region_table(data["by_region"]))
            .replace("__OUTLIER_LIST__", outliers_table(outliers))
            .replace("__SENSITIVITY_TABLE__",
                     sensitivity_table(data.get("chem_vs_hpf", []), outliers))
            + _references_html(cited_order))

    html = ("<!doctype html><meta charset=utf-8>\n"
            "<title>Methods — mesh-based membrane topology</title>\n"
            "<style>\n"
            " :root{--bg:#0f1420;--card:#1a2030;--card2:#222b3e;--ink:#e8ecf3;"
            "--muted:#8a93a6;--line:#2a3346;--accent:#5b9cff;--head:#cfe0ff}\n"
            " *{box-sizing:border-box}\n"
            " body{font-family:'Segoe UI',Tahoma,sans-serif;"
            "margin:0;background:var(--bg);color:var(--ink);line-height:1.6}\n"
            " .container{max-width:920px;margin:0 auto;padding:24px 32px 64px}\n"
            " nav.bar{background:linear-gradient(135deg,#16243f,#1d3a33);"
            "border-bottom:1px solid var(--line);"
            "padding:12px 32px;font-size:13px;display:flex;gap:14px;color:var(--ink)}\n"
            " nav.bar a{color:var(--accent);text-decoration:none;font-weight:600}\n"
            " nav.bar a:hover{text-decoration:underline}\n"
            " h1{font-size:26px;margin:14px 0 4px;color:var(--ink)}\n"
            " h2{font-size:19px;color:var(--head);border-bottom:1px solid var(--line);"
            "padding-bottom:6px;margin-top:36px}\n"
            " p.lead{color:#c4ccda;font-size:15px;max-width:760px}\n"
            " p,li{font-size:14px;color:#c0c8d6}\n"
            " p strong,li strong,p b,li b{color:var(--ink)}\n"
            " code{background:var(--card2);color:#d6deea;border-radius:3px;padding:1px 5px;"
            "font-family:ui-monospace,Menlo,monospace;font-size:12.5px}\n"
            " a{color:var(--accent)}\n"
            " nav.toc{background:var(--card);border:1px solid var(--line);border-radius:10px;"
            "padding:10px 14px;margin:12px 0 22px;font-size:12.5px;line-height:1.9;color:var(--muted)}\n"
            " nav.toc a{color:var(--accent);text-decoration:none}\n"
            " nav.toc a:hover{text-decoration:underline}\n"
            " table.small{border-collapse:collapse;margin:8px 0 18px;"
            "background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}\n"
            " table.small th,table.small td{padding:6px 10px;font-size:13px;text-align:left;"
            "border-bottom:1px solid var(--line)}\n"
            " table.small tr:last-child td{border-bottom:none}\n"
            " table.small th{background:var(--card2);color:var(--head);font-weight:600}\n"
            " table.small td{color:#c0c8d6}\n"
            " table.stats{width:100%;border-collapse:collapse;margin:8px 0 6px;"
            "background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}\n"
            " table.stats th,table.stats td{padding:7px 10px;font-size:13px;"
            "text-align:left;border-bottom:1px solid var(--line)}\n"
            " table.stats tbody tr:last-child td{border-bottom:none}\n"
            " table.stats thead{background:var(--card2)}\n"
            " table.stats th{font-weight:600;color:var(--head)}\n"
            " table.stats td{color:#c0c8d6}\n"
            " table.stats td.n{font-variant-numeric:tabular-nums;color:var(--muted)}\n"
            " table.stats .iqr{color:var(--muted);font-size:11.5px}\n"
            " table.stats th.chem{color:#ff8b4a}\n"
            " table.stats th.hpf{color:#7ec0ff}\n"
            " span.prep{font-size:10.5px;font-weight:600;padding:1px 7px;"
            "border-radius:4px;text-transform:uppercase;letter-spacing:.04em;color:#fff}\n"
            " span.prep.chem{background:#d9480f}\n"
            " span.prep.hpf{background:#1971c2}\n"
            " p.note{color:var(--muted);font-size:12.5px;margin-top:4px}\n"
            " table.cmp{width:100%;border-collapse:collapse;margin:10px 0 14px;"
            "background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}\n"
            " table.cmp th,table.cmp td{padding:8px 12px;font-size:13px;"
            "vertical-align:top;border-bottom:1px solid var(--line);color:#c0c8d6}\n"
            " table.cmp tbody tr:last-child td{border-bottom:none}\n"
            " table.cmp thead th{background:var(--card2);color:var(--head)}\n"
            " table.cmp tbody th{background:#13182a;text-align:left;width:120px;"
            "color:var(--head);font-weight:600}\n"
            " sup.cite{font-size:10.5px;color:var(--accent);font-weight:600;vertical-align:super;"
            "line-height:0}\n"
            " sup.cite a{color:inherit;text-decoration:none}\n"
            " sup.cite a:hover{text-decoration:underline}\n"
            " ol.refs{list-style:none;padding:0;margin:8px 0 0;counter-reset:r}\n"
            " ol.refs li{font-size:13px;color:#c0c8d6;margin:6px 0;padding:6px 10px 6px 38px;"
            "position:relative;border-bottom:1px solid var(--line)}\n"
            " ol.refs li:target{background:#3a2e1c;border-radius:4px}\n"
            " ol.refs .refn{position:absolute;left:8px;color:var(--accent);font-weight:600;"
            "font-variant-numeric:tabular-nums}\n"
            " table.outliers{width:100%;border-collapse:collapse;margin:6px 0 12px;"
            "background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}\n"
            " table.outliers th,table.outliers td{padding:7px 10px;font-size:13px;"
            "text-align:left;border-bottom:1px solid var(--line);vertical-align:top;color:#c0c8d6}\n"
            " table.outliers tbody tr:last-child td{border-bottom:none}\n"
            " table.outliers thead{background:#3a1e1e}\n"
            " table.outliers th{font-weight:600;color:#ff8585}\n"
            " table.outliers td.n{font-variant-numeric:tabular-nums;color:var(--muted)}\n"
            " table.outliers td.reason{color:#aeb6c4;font-size:12.5px;max-width:340px}\n"
            " table.outliers .ratio{font-variant-numeric:tabular-nums;font-weight:600;"
            "color:#c0c8d6}\n"
            " table.outliers .ratio.hi{color:#ff8585}\n"
            " table.outliers .ratio.lo{color:#7adcaa}\n"
            " span.outlier-inline{background:#3a1e1e;color:#ff8585;"
            "border:1px solid #6b3030;border-radius:4px;padding:0 6px;"
            "font-size:11.5px;font-weight:700}\n"
            " table.sensitivity{width:100%;border-collapse:collapse;margin:6px 0 6px;"
            "background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}\n"
            " table.sensitivity th,table.sensitivity td{padding:7px 10px;font-size:13px;"
            "text-align:center;border-bottom:1px solid var(--line);color:#c0c8d6}\n"
            " table.sensitivity tbody tr:last-child td{border-bottom:none}\n"
            " table.sensitivity th{font-weight:600;color:var(--head);background:var(--card2)}\n"
            " table.sensitivity td:first-child,table.sensitivity td:nth-child(2)"
            "{text-align:left;color:#c0c8d6}\n"
            " table.sensitivity td.n{font-variant-numeric:tabular-nums;color:var(--muted)}\n"
            " table.sensitivity td.ratio{font-variant-numeric:tabular-nums;font-weight:600;color:var(--ink)}\n"
            " table.sensitivity td.ratio.dim{color:var(--muted);font-weight:500}\n"
            " table.sensitivity tr.affected{background:#2b2412}\n"
            " table.sensitivity tr.affected td{color:var(--ink)}\n"
            " ol.findings{counter-reset:f;list-style:none;padding:0;margin:8px 0 14px}\n"
            " ol.findings>li{counter-increment:f;background:var(--card);border:1px solid var(--line);"
            "border-left:4px solid var(--accent);border-radius:8px;padding:12px 16px 12px 56px;"
            "margin:10px 0;position:relative;font-size:14px;color:#c0c8d6;line-height:1.6}\n"
            " ol.findings>li::before{content:counter(f);position:absolute;left:16px;top:13px;"
            "width:28px;height:28px;line-height:28px;text-align:center;background:var(--accent);"
            "color:#0a0f1c;border-radius:999px;font-weight:700;font-size:13px;"
            "font-variant-numeric:tabular-nums}\n"
            " ol.findings>li b{color:var(--head)}\n"
            " ol.findings>li i{color:#aeb6c4}\n"
            " figure.fig{margin:14px 0;background:var(--card);border:1px solid var(--line);"
            "border-radius:10px;padding:12px;max-width:760px}\n"
            " figure.fig img{width:100%;height:auto;border-radius:8px;background:#fff;display:block}\n"
            " figure.fig figcaption{font-size:12.5px;color:#aeb6c4;margin-top:9px;line-height:1.5}\n"
            "</style>\n"
            "<nav class=bar>"
            "<a href='../home.html'>⌂ project home</a>"
            "<a href='membranes_3d.html'>interactive 3D gallery</a>"
            "<a href='index.html'>static map gallery</a>"
            "<a href='inspector.html'>adjustable-scale inspector</a>"
            "</nav>\n"
            "<div class=container>" + body + "</div>\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Copy the embedded figures next to methods.html so the relative <img>
    # paths resolve both locally and on the deployed site (membranes/).
    for fname in ("fig2_effect_matrix.png", "native_topology.png",
                  "native_anatomy_matched.png"):
        src = REPO_ROOT / "figures" / fname
        if src.exists():
            shutil.copy2(src, OUT.parent / fname)
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
