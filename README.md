# ecs-analysis

Comparing extracellular space (ECS) geometry between two tissue-preparation
methods — Chemical fixation vs Rapid High-Pressure Freezing (HPF) — across
CellMap groundtruth crops in four mouse tissues (Kidney, Heart, Liver,
Cortex). 41 active crops, ~1,500 cells.

> **Quick handoff:** the file [`handoff.zip`](handoff.zip) at the repo root
> contains a self-contained snapshot of the code, current results, and
> figures (excludes `archive/` and `paper/`). Either clone the repo or
> download just that zip — both produce a runnable copy.

## Status (as of handoff)

The pipeline is built and validated. A native-resolution pass on all 41
crops is mostly complete; matched-resolution and degradation experiments
are partial. See **Status of computational work** below for what remains.

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

scripts/
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

crop_annotations.csv    anatomy labels per crop. Currently covers 31 of
                        41 crops; expert is still annotating the 10
                        cortex crops (1116, 1033-1037, 1045, 1046, 1139,
                        1141). Once added, anatomy-matched comparisons
                        auto-update — no code change needed.
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

The `results/` and `figures/` directories were cleared on handoff so the
cluster run is the canonical source. Phases to run on the cluster:

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
`crop_annotations.csv`. The 10 cortex crops are still pending expert
annotation. Once they land, re-run the summary and figure scripts to
pick them up — no recompute of the per-crop CSVs is needed.

## Headline scientific finding so far

In **Liver** (n=7 Chemical, n=10 HPF), Chemical fixation shows:
- ~5x more ECS volume fraction (Cliff's delta = +0.83, p = 0.003)
- ~3x higher SA:V ratio (Cliff's delta = +0.86, p = 0.002)
- ~2x larger ECS channel widths
- 3x higher cell density at the per-crop scale

The Liver Chemical crops are at 4nm and HPF at 8nm. The matched-
resolution (8nm) re-run shows SA:V essentially unchanged (ratio ~1.00),
ECS width changes <2nm, and Voronoi gap shifts upward by 5-19nm. So
**the Liver Chem-vs-HPF difference is not explained by the 4nm-vs-8nm
resolution gap.**

The same direction holds in 3 of 4 anatomy-matched groups (bile
canaliculus, DCT base, hepatocyte lateral). The glomerular group flips
direction (HPF > Chem) but the HPF n is 1.

## Known caveats

- **Voxel-size confound**: every Chemical crop is 2nm or 4nm; almost
  every HPF crop is 8nm. The matched and degradation runs are designed
  to address this. See `ecs/config.py` constants for tunable
  smoothing/threshold parameters.
- **`bm` annotation is inconsistent across preps**: 4 Kidney-Chemical
  crops have bm separately labeled; HPF kidneys have bm=0 even though
  the basement membrane is physically present. We assume HPF rolled
  bm into ecs at annotation time. Worth confirming with the
  annotators.
- **Cortex Chemical is at 2nm**, finest in the dataset, but small crops
  (often <500nm cells, dominated by cell-fragment statistics).
