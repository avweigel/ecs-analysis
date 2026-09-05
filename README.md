# ecs-analysis

Comparing extracellular space (ECS) geometry between two tissue-preparation
methods — Chemical fixation vs Rapid High-Pressure Freezing (HPF) — across
CellMap groundtruth crops in four mouse tissues (Kidney, Heart, Liver,
Cortex). 55 active crops, ~1,500 cells. All four tissues now have both
Chemical and HPF crops (Heart HPF added 2026-05 via `jrc_mus-heart-4`).

## Browse the data

**<https://avweigel.github.io/ecs-analysis/>**

Every measurement in this repository, browsable without cloning it: a metric
explorer over all 94 metrics, the per-crop table, the figure gallery, membrane
surfaces in 3D, and a reference page defining every metric and the caveats that
go with it. Built from `docs/` and published with GitHub Pages.

Start at the [reference page](https://avweigel.github.io/ecs-analysis/reference.html)
if you have not seen this dataset before — it explains what a crop is, what the
two preparations are, and why every metric is computed three times.

> **Quick handoff:** two zip snapshots live at the repo root, both
> self-contained (excludes `archive/` and `paper/`).
> - [`handoff.zip`](handoff.zip) — original handoff with empty
>   `results/` and `figures/` directories, intended as the canonical
>   re-run starting point.
> - [`handoff_with_results.zip`](handoff_with_results.zip) — post-run
>   snapshot that ships with the completed CSVs in `results/` and the
>   rendered PNGs in `figures/`. Use this one if you just want to see
>   the outputs without re-running anything.
> Either clone the repo or download a zip — both produce a runnable copy.

## Status (as of handoff)

All three computational phases are complete. `results/` contains the
per-crop CSVs, tissue×prep summary tables, anatomy-matched summaries,
and `stats_native.csv` (Mann-Whitney + Cliff's delta + bootstrap CIs).
`figures/` contains the rendered PNGs. The zip is fully self-contained
— you can also re-run any phase from scratch (see **Running** below).

Two follow-ups remain for the analysis (not blocking reproducibility):
1. Anatomy annotations for **2 cortex HPF crops (1116, 1141)** are still
   pending expert annotation — the expert could not confidently resolve
   the cortex HPF crops. Once added, re-run `pixi run summarize` /
   `pixi run figures` to pick them up — no per-crop recompute needed.
   (All other 53 active crops are annotated.)
2. `matched_volume_fraction.csv` is intentionally absent because the
   fast-path reads zarr metadata only valid at native resolution. If
   you want voxel-count ratios at the 8 nm matched resolution, add a
   `from_data()` call to `run_matched.METRICS`.

## Repository layout

```
ecs/
  config.py           single source of truth: crops, datasets, anatomy,
                      thresholds. Reads ECS_DATA_BASE env var for the
                      zarr root (default: /Volumes/cellmap/data).
  io.py               zarr loading, voxel-size extraction, downsampling.
                      Unions `ecs` and `bm` (basement membrane) into one
                      effective ECS mask for distance-transform analyses.
  geometry.py         distance transforms, 6-conn boundary face counting,
                      marching-cubes meshing, cotangent-Laplacian mean
                      curvature (sign-calibrated on synthetic spheres),
                      multi-scale roughness, local-extremum feature
                      detection.
  metrics/
    volume_fraction.py  ECS%, cell% (metadata fast-path, includes bm)
    ecs_width.py        distance-transform percentiles, narrow-channel
                        (<200nm) filter
    voronoi_gap.py      cell-Voronoi gap distribution + contact fractions
    sa_v.py             crop-level ECS-facing surface / cell volume
    topology.py         pooled curvature, multi-scale roughness,
                        protrusion/indentation density per um^2

docs/                   the published site (GitHub Pages serves this folder)
  index.html            overview, scope, and where the comparison is supported
  explore.html          Analysis: the live explorer plus every standing panel
  crops.html            per-crop table and the viewer, both surfaces
  reference.html        study design, how to read the charts, metric dictionary
  figures.html          a pointer into the Analysis page's sections
  membranes/            all 55 patches, paired 3D views, the methods in full
  data/                 the CSVs and metrics.json the pages read
  README.md             what is published, what is deliberately left out

scripts/
  collect_all.py        merge every per-crop metric into results/all_metrics_*
  build_metric_dictionary.py  names, units and caveats for all 94 metrics
  site_shell.py         shared header, nav and footer for every page
  build_site.py         -> docs/index.html
  build_explorer.py     -> docs/explore.html (imports the panels from below)
  build_reference.py    -> docs/reference.html
  build_crops.py        -> docs/crops.html (+ the inspector pointer)
  build_figures_page.py the panel definitions, and docs/figures.html (the pointer)
  make_ecs_surfaces.py  -> docs/membranes/ecs/*.bin, the ECS surfaces
  make_ecs_hero.py      -> docs/assets/art/hero/*.glb, the hero objects
  build_views_page.py   -> docs/membranes/views.html
  retheme_legacy.py     puts the older membrane pages on the shared shell

  run_native.py         native-resolution pass on all crops
  run_matched.py        downsample to TARGET_VOXEL_NM (8nm) then run all
  run_degradation.py    Chemical crops at multiple resolutions
                        (default 2/4/8/16 nm)
  summarize.py          aggregate CSVs into tissue x prep tables and
                        anatomy-matched comparisons
  stats.py              Mann-Whitney U + Cliff's delta + bootstrap CIs
  make_figures.py       per-metric strip plots and anatomy-matched panels
  cluster_submit.sh     LSF (Janelia) per-crop job submission

results/
  native_*.csv          one row per crop per metric (incremental writes)
  matched_*.csv         8nm-downsampled equivalents
  degradation_*.csv     one row per (crop, resolution) for Chemical crops
  summary_*.csv         aggregated tables produced by summarize.py
  stats_native.csv      Mann-Whitney + Cliff's delta + bootstrap CIs

figures/                rendered PNGs from make_figures.py
archive/                old code and CSVs from a prior pipeline (kept
                        for reference; not part of the new flow)

crop_annotations.csv    anatomy labels per crop. Covers 53 of 55 active
                        crops; only the 2 cortex HPF crops (1116, 1141)
                        remain unannotated. Once added, anatomy-matched
                        comparisons auto-update — no code change needed.
```

## Key design decisions worth knowing

1. **`bm` (basement membrane) is treated as ECS.** Per the imaging team,
   bm is structurally a sub-part of the extracellular compartment. Only
   4 Kidney-Chemical crops have any bm voxels, but for those the
   correction adds 2.7-10.4 percentage points to ECS%.

2. **Sign convention for curvature is calibrated** on synthetic spheres.
   Convex surfaces -> positive H, concave -> negative. The previous
   pipeline (in archive/) had this inverted. See
   `ecs.geometry.sphere_sign_check`.

3. **Cell inclusion uses physical volume** (`MIN_CELL_VOL_NM3`), not
   voxel count. Earlier pipelines used a fixed voxel-count threshold,
   which let many more small fragments through at finer resolutions.

4. **Per-cell metrics are pooled to the crop level** for statistics.
   Each crop contributes one number per metric. Avoids
   pseudo-replication from cells-within-crop being non-independent.

5. **All crop-level metrics are computed per-crop incrementally.**
   Mid-run failures (SMB drops, OOM, etc.) preserve completed work.

## Environment

This repo uses [pixi](https://pixi.sh) for reproducible environments. The
spec is in `pixi.toml` (Python 3.9 + numpy/scipy/zarr/scikit-image/
trimesh/matplotlib). One-time setup:

```bash
pixi install
```

That creates `.pixi/envs/default/` with everything pinned. To run a
command inside the env, prefix with `pixi run`, e.g. `pixi run python -m
scripts.run_native`. A `requirements.txt` is also kept in sync if you
prefer plain pip.

## Running

### Local (slow, single-process)

```bash
# Set the zarr root
export ECS_DATA_BASE=/Volumes/cellmap/data    # or /nrs/cellmap/data on cluster

# Native-resolution metrics on all crops (writes results/native_*.csv)
pixi run native

# Matched-resolution (downsample everything to 8nm)
pixi run matched

# Degradation: Chemical crops at 2/4/8/16 nm
pixi run degradation

# Summaries and figures from whatever CSVs exist
pixi run summarize
pixi run stats
pixi run figures
```

(Each task is just a thin wrapper around the equivalent
`python -m scripts.<name>` invocation — see `pixi.toml`.)

To resume an interrupted run, just re-run — the incremental-write
logic will skip rows that are already present (per crop). You can also
specify a subset of crops with `--only crop1026,crop1027,...` and a
subset of metrics with `--metrics ecs_width,voronoi_gap`.

### Cluster (LSF, Janelia)

```bash
# Required: where the zarr data lives
export ECS_DATA_BASE=/nrs/cellmap/data

# One-time: build the pixi env (cluster_submit.sh auto-uses it)
pixi install
# Override only if you don't want the pixi env:
# export ECS_PYTHON=/path/to/python

# Optional: where to write results. Default is `results/` in the repo,
# which means after the run you can `git add results/ && git commit && git push`
# to send everything back. If you'd rather write to shared lab space:
export ECS_RESULTS_DIR=/nrs/cellmap/ackermand/cellmap/ecs-analysis/results
export ECS_FIGURES_DIR=/nrs/cellmap/ackermand/cellmap/ecs-analysis/figures

# Optional: LSF queue + resources + billing project
export ECS_QUEUE=local
export ECS_PROJECT=cellmap   # passed as bsub -P

bash scripts/cluster_submit.sh native        # phase 2 (all metrics)
bash scripts/cluster_submit.sh matched       # phase 4 (downsampled to 8nm)
bash scripts/cluster_submit.sh degradation   # phase 5 (Chemical scan)
```

Each invocation submits one bsub job per crop. LSF logs land in
`cluster_logs/<phase>/<crop>.{out,err}` in the repo. The per-crop
incremental-write logic means each finishing job appends its row to
`<RESULTS_DIR>/<phase>_<metric>.csv` — no separate aggregation step.

Once all jobs are done, run the post-processing locally (these are fast
and don't need to go through bsub):

```bash
pixi run summarize                                          # native
pixi run python -m scripts.summarize --prefix matched
pixi run stats
pixi run figures                                            # native
pixi run python -m scripts.make_figures --prefix matched
```

To send results back: either `git add results/ && git commit && git push`
to share via the GitHub repo, or tarball the results directory and send
the file directly.

Wall-time hints (per crop):
- Topology at 2nm Cortex Chemical: 15-30 min (largest meshes)
- Topology at 4nm Chemical (Kidney/Liver): 5-10 min
- Topology at 8nm anything: 1-2 min
- Fast metrics (no topology): under 1 min

## Status of computational work

All phases below have completed successfully and `results/` /
`figures/` ship with this handoff. The commands are kept here as the
re-run recipe.

| Phase | Command | Approx cluster wall-time at 40 parallel jobs |
|---|---|---|
| 2 - Native metrics | `bash scripts/cluster_submit.sh native` | 30-60 min |
| 4 - Matched at 8nm | `bash scripts/cluster_submit.sh matched` | 15-30 min |
| 5 - Degradation (Chemical only) | `bash scripts/cluster_submit.sh degradation` | 30-90 min |

After cluster jobs finish, run locally:
- `pixi run summarize`
- `pixi run stats`
- `pixi run figures`

Phase 6 (anatomy-matched filtering) auto-activates from
`crop_annotations.csv`. Only the 2 cortex HPF crops (1116, 1141) are
still pending expert annotation. Once they land, re-run the summary and
figure scripts to pick them up — no recompute of the per-crop CSVs is
needed.

## Headline scientific finding so far

The Chem-vs-HPF ECS difference is **tissue-specific, not universal**, and
is cleanest in anatomy-matched comparisons rather than pooled tissue
medians.

**Liver and Kidney** show more ECS under Chemical fixation:
- Liver tissue (n=12 Chem, n=10 HPF): ECS volume fraction 0.184 vs 0.040
  (~4.6x; Cliff's delta = +0.47, **p = 0.070** — borderline) and SA:V
  0.0076 vs 0.0027 (~2.8x; Cliff's delta = +0.55, **p = 0.032**).
- Kidney tissue: ECS fraction 0.356 vs 0.128 (~2.8x), but the direction
  splits by anatomy (DCT/PCT brush border go Chem>HPF; glomerular and
  PCT lateral go HPF>Chem).

**Heart and Cortex do not** show the Chemical-higher pattern:
- Heart tissue (n=4 Chem, n=4 HPF, HPF arm new this round): ECS fraction
  0.158 vs 0.208, **no significant Chem-vs-HPF difference on any metric**.
- Cortex tissue: ECS fraction 0.107 (Chem) vs 0.148 (HPF), leaning
  HPF>Chem (HPF n=2).

**Resolution is not the driver for the liver SA:V difference.** Liver
Chemical crops are mostly 4nm and HPF 8nm; the matched-resolution (8nm)
SA:V is 0.0075 vs 0.0027 — essentially identical to the native-resolution
ratio. So the SA:V gap survives downsampling.

**What changed when 5 new Chemical liver hepatocyte-lateral crops
(1118-1122) and 4 Heart HPF crops (1149-1152) were added (2026-05):**
- Liver *tissue* ECS dropped from significant to borderline (p 0.003 ->
  0.070): the new Chemical lateral crops are tight, low-ECS spaces (and
  8nm vs the 4nm chemical liver crops), diluting the pooled chemical mean.
- The **hepatocyte-lateral** matched group went from 1-vs-6 to 6-vs-6 and
  is now **null** across all metrics (p>0.25) — the earlier dramatic
  lateral result rested on a single Chemical crop.
- Only two comparisons remain significant at |delta|>0.5, p<0.05: **bile
  canaliculus cell density** (Chem>HPF, delta +1.0, p=0.0497) and **liver
  tissue SA:V** (Chem>HPF, delta +0.55, p=0.032).

Takeaway: pooled tissue-level comparisons are confounded by uneven anatomy
and resolution sampling between preps; the anatomy-matched groups in
`summary_*_anatomy_matched.csv` / `stats_native.csv` are the reliable read.

## Known caveats

- **Voxel-size confound**: most Chemical crops are 2nm or 4nm and most
  HPF crops are 8nm — but this is no longer clean. The new Chemical liver
  crops (1118-1122) are 8nm-native, and Heart HPF (1149-1152) is 8nm, so
  the prep/resolution coupling now varies within a tissue. The matched
  (8nm) and degradation runs are designed to address this. See
  `ecs/config.py` constants for tunable smoothing/threshold parameters.
- **`bm` annotation is inconsistent across preps**: 4 Kidney-Chemical
  crops have bm separately labeled; HPF kidneys have bm=0 even though
  the basement membrane is physically present. We assume HPF rolled
  bm into ecs at annotation time. Worth confirming with the
  annotators.
- **Cortex Chemical is at 2nm**, finest in the dataset, but small crops
  (often <500nm cells, dominated by cell-fragment statistics).
