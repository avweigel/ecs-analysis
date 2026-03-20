# ECS Analysis: Chemical Fixation vs Rapid HPF

## Overview

Comparing extracellular space (ECS) between two tissue preparation methods
(Chemical fixation vs Rapid High Pressure Freezing) across CellMap zarr
groundtruth crops in four mouse tissues: Kidney, Heart, Liver, Cortex.

42 crops total, 1574 cells (normalized), 974 cells with curvature data.

---

## Global Confound: Voxel Size is Perfectly Confounded with Prep Type

All Chemical crops are at 2nm or 4nm voxels. All HPF crops are at 8nm voxels.
There is zero overlap in resolution between the two prep types.

| Prep | Voxel Sizes | N Crops |
|------|-------------|---------|
| Chemical | 2nm (7), 4nm (14), 8nm (3) | 24 |
| Rapid HPF | 8nm (17), unknown (1) | 18 |

Only 3 Chemical crops (Heart) share 8nm resolution with HPF. All other
Chemical crops are 2-4x higher resolution than any HPF crop.

**Metrics affected:** Every per-cell metric (SA:V, sphericity, curvature) shows
significant correlation with voxel size (Spearman p < 1e-4 for all). Crop-level
metrics (ECS volume fraction) are less affected since they are voxel-count ratios.

**Quantified correlations (all cells, native resolution):**

| Metric | Spearman r vs voxel size | p-value |
|--------|--------------------------|---------|
| SA:V ratio | -0.299 | 8.0e-26 |
| Sphericity | -0.166 | 1.1e-08 |
| Curvature median \|H\| | +0.129 | 5.4e-05 |
| Fraction convex | -0.071 | 2.8e-02 |

Any Chemical vs HPF comparison is simultaneously a high-resolution vs
low-resolution comparison. This cannot be deconfounded with the current data.

---

## Metric 1: ECS Volume Fraction

**Script:** `analyze_ecs_cell_volumes.py` -> `ecs_cell_volumes.csv`
**Plot:** `plot_ecs_by_prep.py` -> `ecs_by_prep_type.png`

### Method

Percentage of voxels in each crop labeled as ECS out of total crop volume.
Computed directly from segmentation label counts in zarr metadata.

### Pros

- Simplest metric; just counting labeled voxels
- Least sensitive to voxel size since it is a ratio of counts
- Well-established in the EM tissue preservation literature
- Computed from metadata (fast, no heavy computation)

### Cons

- One value per crop; small sample sizes (3-10 per tissue-prep group)
- No paired regions between preps
- Cannot distinguish "prep inflated ECS" from "crop landed on open space"

### Known Biases and Artifacts

- **Crop placement dominance:** Within Chemical alone, ECS ranges from 1.4% to
  74.6%. This within-group variance far exceeds any between-group signal.
- **Crop size differences:** Crops range from 9M to 250M voxels. Larger crops
  average over more tissue heterogeneity.
- **Annotation completeness:** crop1117 has no ECS/cell labels. Others may have
  incomplete annotations near crop edges.
- **Tissue type confound:** Each tissue has fundamentally different ECS
  architecture. Cross-tissue comparisons are not meaningful.

### Results

**Overall (all tissues pooled):**

| Prep | Mean ECS% | Median ECS% | IQR | N |
|------|-----------|-------------|-----|---|
| Chemical | 24.4% | 20.1% | [13.1, 31.8] | 24 |
| Rapid HPF | 16.0% | 9.6% | [3.9, 14.7] | 17 |

Mann-Whitney U=293, p=0.019.

**By tissue:**

| Tissue | Chemical | Rapid HPF |
|--------|----------|-----------|
| Kidney | 34.4 +/- 9.0% (n=7) | 24.8 +/- 11.6% (n=4) |
| Heart | 21.0 +/- 4.8% (n=3) | N/A |
| Liver | 27.1 +/- 4.5% (n=7) | 7.5 +/- 2.5% (n=10) |
| Cortex | 13.3 +/- 3.5% (n=7) | 32.9 +/- 15.0% (n=3) |

---

## Metric 2: ECS Channel Half-Width (Narrow-Filtered)

**Script:** `analyze_ecs_width_filtered.py` -> `ecs_width_filtered.csv`
(Original unfiltered: `analyze_ecs_width.py` -> `ecs_width.csv`)
**Plot:** `plot_ecs_width.py` -> `ecs_width_by_prep.png`

### Method

Distance transform on ECS mask: each ECS voxel gets its distance to the
nearest cell boundary (half-width). Filtered to <200nm half-width to exclude
vessel lumens and large open spaces. Reports distribution stats (p10-p90,
median, mean, std) plus cumulative fraction below thresholds (10-100nm).

### Pros

- Measures channel geometry, not just volume
- Physical units (nm), directly interpretable
- Filtering to <200nm removes vessel/lumen contamination
- Cumulative fraction stats give richer distributional view

### Cons

- Half-width, not full width; values must be doubled for literature comparison
- 200nm cutoff is somewhat arbitrary
- Local measure; does not capture connectivity or tortuosity

### Known Biases and Artifacts

- **Voxel quantization (MAJOR):** At 8nm voxels, minimum half-width is 4nm and
  values are quantized to ~4nm steps. At 2nm voxels, resolution is 4x better.
  This directly affects frac_below_20nm and frac_below_50nm. Demonstrated by
  comparing Chemical crops at different voxel sizes:

  | Voxel Size | N Crops | Mean Narrow Median | Mean frac<20nm |
  |------------|---------|--------------------|--------------------|
  | 2nm (Chemical) | 7 | 13.9 nm | 0.820 |
  | 4nm (Chemical) | 14 | 29.7 nm | 0.448 |
  | 8nm (Chemical) | 3 | 32.5 nm | 0.338 |
  | 8nm (HPF) | 17 | 21.6 nm | 0.621 |

  The 2nm Chemical crops report narrower ECS and more sub-20nm voxels than 4nm
  Chemical crops of the same prep type, demonstrating that resolution dominates
  the signal at fine thresholds.

- **Distance transform is not true gap width:** Reports distance to nearest
  cell surface in any direction, not specifically the gap between two opposing
  membranes. Overestimates width in complex geometries.
- **Crop boundary contamination:** ECS voxels at crop edges see artificially
  large distances (no cell beyond the edge).

### Results (filtered <200nm)

**Overall:**

| Prep | Mean Narrow Median | Mean frac<20nm | Mean frac<50nm | N |
|------|--------------------|--------------------|--------------------|----|
| Chemical | 25.4 nm | 0.543 | 0.755 | 24 |
| Rapid HPF | 21.6 nm | 0.621 | 0.848 | 17 |

**By tissue:**

| Tissue | Chemical | Rapid HPF |
|--------|----------|-----------|
| Kidney | 24.7 +/- 7.3 nm (n=7) | 32.9 +/- 9.8 nm (n=4) |
| Heart | 32.5 +/- 2.3 nm (n=3) | N/A |
| Liver | 31.9 +/- 3.0 nm (n=7) | 21.8 +/- 4.4 nm (n=10) |
| Cortex | 13.6 +/- 8.4 nm (n=7) | 30.2 +/- 16.8 nm (n=3) |

---

## Metric 3: Per-Cell SA:V Ratio

**Script:** `analyze_cell_morphology.py` -> `cell_morphology_per_cell.csv`
(Normalized: `analyze_cell_morphology_normalized.py` -> `cell_morphology_normalized.csv`)
**Plot:** `plot_cell_morphology.py` -> `cell_morphology_by_prep.png`

### Method

For each segmented cell, ratio of ECS-touching surface area to cell volume.
Surface area computed by counting exposed voxel faces (face-counting on cubic
grid). Only ECS-facing faces are counted (excluding cell-cell contacts and
crop boundary faces). Volume is total cell voxel count x voxel volume.

Two versions exist: native resolution and normalized (all resampled to 8nm
isotropic voxels). The normalized version controls for voxel-size effects on
surface area.

### Pros

- Per-cell metric; large sample sizes (n=1574 normalized cells)
- SA:V is dimensionless and scale-invariant in principle
- Only counts ECS-facing faces; excludes crop boundary artifacts
- Normalized version controls for voxel size

### Cons

- Cells truncated at crop boundaries have distorted volumes and surfaces
- High within-group variance from cell-type diversity
- Does not directly measure ECS geometry

### Known Biases and Artifacts

- **Voxel staircase effect:** Face-counting on a cubic grid systematically
  overestimates true surface area. The bias is larger at coarser voxels but
  is partially controlled by normalization to 8nm.
- **Boundary-truncated cells (MAJOR):** 601 of 1179 native-resolution cells
  are below 0.01 um3. Many are fragments, not whole cells. 158 cells have
  100% ECS-facing surface (no cell-cell contact at all), indicating isolated
  fragments entirely surrounded by ECS.
- **SA:V direction flips with size filter:** At no filter, Chemical SA:V >
  HPF. At >= 0.05 um3 filter, Chemical SA:V < HPF. The metric is unstable
  with respect to the minimum cell size threshold.
- **Normalization smoothing:** Resampling to 8nm blurs small features, which
  changes SA:V and sphericity values (sphericity increases from 0.52 to 0.65
  for Chemical after normalization).

### Results (normalized 8nm, various size filters)

| Filter | Chemical SA:V (n) | HPF SA:V (n) | p-value |
|--------|-------------------|--------------|---------|
| None | 0.050 (761) | 0.043 (813) | - |
| >= 0.005 um3 | 0.033 (341) | 0.028 (472) | 0.007 |
| >= 0.01 um3 | 0.023 (194) | 0.025 (385) | 0.033 |
| >= 0.05 um3 | 0.015 (90) | 0.019 (230) | 0.002 |

**By tissue (native resolution, physical volume filter > 2.56M nm3):**

| Tissue | Chemical | Rapid HPF |
|--------|----------|-----------|
| Kidney | 0.038 +/- 0.001 (n=230) | 0.027 +/- 0.002 (n=81) |
| Heart | 0.010 +/- 0.002 (n=11) | N/A |
| Liver | 0.039 +/- 0.002 (n=83) | 0.039 +/- 0.002 (n=142) |
| Cortex | 0.032 +/- 0.002 (n=101) | 0.033 +/- 0.001 (n=326) |

---

## Metric 4: Per-Cell Sphericity

**Script:** Same as Metric 3
**Plot:** Same as Metric 3

### Method

Sphericity = (pi^(1/3) * (6V)^(2/3)) / A, where V is cell volume and A is
total surface area. Ranges from 0 (highly non-spherical) to 1 (perfect sphere).

### Pros

- Bounded [0,1] scale; intuitive
- Per-cell metric with large sample sizes

### Cons

- Closely correlated with SA:V; partially redundant
- Voxel-based surface area systematically overestimates true area, so
  sphericity is systematically underestimated
- "Sphericity" is a poor framing for cells that are never remotely spherical

### Known Biases and Artifacts

- **Voxel staircase underestimates sphericity:** Manhattan geometry inflates
  surface area. The effect is larger at coarser voxels.
- **Normalization dramatically changes values:** Chemical sphericity jumps from
  0.518 (native) to 0.650 (normalized 8nm) purely from resampling smoothing.
- **Same boundary-truncation issues as SA:V.**

### Results (normalized 8nm, various size filters)

| Filter | Chemical Sph. (n) | HPF Sph. (n) | p-value |
|--------|-------------------|--------------|---------|
| None | 0.650 (761) | 0.601 (813) | - |
| >= 0.005 um3 | 0.570 (341) | 0.510 (472) | < 0.0001 |
| >= 0.01 um3 | 0.569 (194) | 0.482 (385) | < 0.0001 |
| >= 0.05 um3 | 0.492 (90) | 0.454 (230) | 0.046 |

Chemical cells consistently show higher sphericity than HPF across all size
filters.

---

## Metric 5: Inter-Cell Gap Width (Voronoi)

**Script:** `analyze_cell_contacts.py` -> `cell_contacts.csv`
**Plot:** `plot_cell_contacts.py` -> `cell_contacts_by_prep.png`

### Method

Voronoi tessellation of ECS: each ECS voxel assigned to nearest cell via
distance transform. At Voronoi boundaries (where two cells' territories meet),
gap width = sum of both cells' distance contributions. Reports median gap per
crop and contact fractions at various thresholds (10-320nm).

### Pros

- Directly measures cell-cell separation through ECS
- Voronoi naturally identifies cell neighbors
- Contact fraction at multiple thresholds gives cumulative distribution

### Cons

- One value per crop; small sample sizes
- High within-group variance
- No per-cell pairing information

### Known Biases and Artifacts

- **Resolution floor (CRITICAL):** At 8nm voxels, minimum measurable gap is
  approximately 2 x 1 voxel diagonal = 2 x 6.9nm ~ 13.8nm. HPF (all 8nm)
  physically cannot detect gaps below ~14nm via Voronoi. This is proven by the
  data:

  | Voxel Size | Prep | N | Mean contact_frac_20nm |
  |------------|------|---|------------------------|
  | 2nm | Chemical | 7 | 0.611 |
  | 4nm | Chemical | 14 | 0.223 |
  | 8nm | Chemical | 3 | 0.000 |
  | 8nm | HPF | 17 | 0.000 |

  Chemical 8nm crops show the exact same 0% contact at 20nm as HPF 8nm crops.
  The Chemical-vs-HPF difference at 20nm is entirely a voxel resolution
  artifact, not a biological effect.

- **Open-space contamination:** Vessel lumens and other large open spaces
  create wide Voronoi boundaries that inflate gap measurements.

### Results

**Overall:**

| Prep | Mean Gap Median | Contact frac @20nm | Contact frac @80nm | N |
|------|-----------------|--------------------|--------------------|---|
| Chemical | 48.5 nm | 0.308 | 0.720 | 24 |
| Rapid HPF | 52.5 nm | 0.000 | 0.773 | 17 |

**By tissue:**

| Tissue | Chemical | Rapid HPF |
|--------|----------|-----------|
| Kidney | 49.0 +/- 12.2 nm (n=7) | 69.2 +/- 30.2 nm (n=4) |
| Heart | 74.5 +/- 5.2 nm (n=3) | N/A |
| Liver | 65.1 +/- 10.3 nm (n=7) | 45.8 +/- 5.5 nm (n=10) |
| Cortex | 20.3 +/- 6.5 nm (n=7) | 52.6 +/- 23.6 nm (n=3) |

---

## Metric 6: Contact Fraction vs Distance Threshold

**Script:** Same as Metric 5
**Plot:** Same as Metric 5

### Method

From the Voronoi analysis: fraction of cell-cell Voronoi boundaries with gap
width below thresholds (10, 20, 40, 80, 160, 320nm).

### Pros

- Richer than single median; shows gap distribution shape
- Biologically relevant thresholds (e.g., <40nm for direct signaling)

### Cons

- Resolution floor makes thresholds below ~3x voxel size meaningless
- One curve per crop, small sample sizes
- Redundant with Metric 5 (same underlying data)

### Known Biases and Artifacts

- Same resolution floor as Metric 5. contact_frac_10nm = 0% everywhere.
  contact_frac_20nm = 0% at 8nm voxels (all HPF and 3 Chemical crops).

### Results

| Tissue | Threshold | Chemical | HPF |
|--------|-----------|----------|-----|
| Cortex | 40nm | 85.6% | 53.8% |
| Cortex | 80nm | 95.2% | 76.4% |
| Kidney | 40nm | 55.3% | 34.0% |
| Kidney | 80nm | 72.3% | 75.0% |
| Liver | 40nm | 31.0% | 53.5% |
| Liver | 80nm | 56.8% | 78.6% |

---

## Metric 7: Boundary-Based Contact Fraction (DISCARDED)

**Script:** `analyze_cell_morphology.py` -> `cell_morphology_contacts.csv`

### Method

For each crop, asks: do any boundary voxels of any two cells come within X nm
of each other? Reports fraction of crops where this is true.

### Why Discarded

Returns 1.000 (100%) for every crop at every threshold >= 20nm. Returns 0.000
for all HPF crops at 10nm and 1.000 for all Chemical crops at 10nm (pure
resolution artifact). This metric has zero discriminating power. It answers
"do any cells exist near each other in this crop?" which is trivially true.

---

## Metric 8: Surface Curvature - Voxel-Based

**Script:** `analyze_curvature.py` -> `cell_curvature.csv`

### Method

Mean curvature H at every ECS-facing surface voxel, computed via the level-set
formula on a Gaussian-smoothed (sigma=16nm physical) binary cell mask.
Positive H = convex (bulging into ECS), negative H = concave (invagination).
Reports per-cell: median |H|, mean |H|, std H, p25/p75, fraction convex,
fraction concave, median radius of curvature (1/|H|). Uses physical volume
filter (> 2.56M nm3).

### Pros

- Characterizes membrane shape at a local level
- Fixed physical smoothing scale (16nm) in principle makes curvature comparable
  across resolutions
- Per-cell metric with large sample sizes

### Cons

- Curvature from finite differences on a binary voxel grid is fundamentally
  noisy
- Smoothing scale choice directly controls results
- Mean curvature alone does not distinguish all shape types

### Known Biases and Artifacts

- **Voxel staircase noise:** Computing curvature from a cubic grid produces
  quantization artifacts. Surface normals from finite differences on binary
  masks are noisy.
- **Smoothing scale vs resolution mismatch:** 16nm = 8 voxels at 2nm but only
  2 voxels at 8nm. HPF data gets less effective smoothing.
- **Overwhelmingly concave (85-87%):** Likely reflects that voxel-based surface
  normals at concave junctions are overrepresented and flat surfaces appear
  concave due to aliasing.
- **Superseded by mesh-based curvature (Metric 9):** Mesh-based computation
  eliminates the worst voxel staircase artifacts.

### Results

**By prep (all tissues, cells > 2.56M nm3):**

| Metric | Chemical (n=425) | HPF (n=549) |
|--------|------------------|-------------|
| Median \|H\| | 0.00654 /nm | 0.00523 /nm |
| Mean \|H\| | 0.00731 /nm | 0.00638 /nm |
| Median radius | 153.0 nm | 191.2 nm |
| Fraction convex | 12.7% | 14.7% |
| Fraction concave | 87.3% | 85.3% |

**By tissue:**

| Tissue | Chemical \|H\| | HPF \|H\| | Chemical radius | HPF radius |
|--------|----------------|-----------|-----------------|------------|
| Kidney | 0.0067 (n=230) | 0.0047 (n=81) | 178 nm | 254 nm |
| Heart | 0.0030 (n=11) | N/A | 459 nm | N/A |
| Liver | 0.0077 (n=83) | 0.0075 (n=142) | 140 nm | 175 nm |
| Cortex | 0.0051 (n=101) | 0.0053 (n=326) | 221 nm | 242 nm |

---

## Metric 9: Surface Curvature - Mesh-Based

**Script:** `analyze_curvature_mesh.py` -> `cell_curvature_mesh.csv`

### Method

Marching cubes algorithm extracts a triangulated isosurface from each cell's
binary mask (with 1-voxel Gaussian smoothing). Mean curvature H computed at
each mesh vertex from the Laplace-Beltrami operator on the triangle mesh.
Only ECS-facing vertices are retained (vertices where the nearest non-self
label is ECS rather than another cell). Reports same per-cell stats as Metric 8
plus mesh quality metadata (n_mesh_verts, n_mesh_faces, n_ecs_verts).

### Pros

- Marching cubes produces a smooth triangulated surface, eliminating the worst
  voxel staircase artifacts
- Curvature from vertex normals on a proper mesh is geometrically more
  meaningful than finite differences on a binary grid
- Mesh quality metadata allows quality filtering
- Chemical vs HPF curvature is nearly identical without size filtering,
  suggesting this method is more stable than voxel-based

### Cons

- Marching cubes + any smoothing acts as a low-pass filter; amount of smoothing
  determines which features survive
- Higher curvature magnitude than voxel method (~2x); unclear whether this
  reflects real features or mesh artifacts
- Computationally expensive (mesh extraction + curvature per cell)

### Known Biases and Artifacts

- **Implicit smoothing:** Marching cubes inherently smooths the voxel surface.
  Additional Gaussian smoothing (sigma=1 voxel) further regularizes. The net
  effect is resolution-dependent.
- **Still concave-biased (82%):** Less extreme than voxel-based (87%) but still
  dominated by concavity. Some concavity is real (cells wrap around each other)
  but the magnitude may be inflated by ECS-vertex selection bias.
- **ECS-vertex selection bias:** Curvature computed only at ECS-facing vertices.
  This preferentially samples membrane at invaginations and concavities where
  cells separate from neighbors, rather than flat contact surfaces.
- **Mesh resolution varies with cell size:** Median 26k vertices for Chemical
  cells vs 14k for HPF cells. HPF cells tend to be larger (higher volume in
  crop) but have fewer vertices due to coarser voxels. Unknown whether this
  affects curvature convergence.
- **Method disagreement with voxel-based:** Mesh median |H| is ~2x voxel-based
  (0.0107 vs 0.0065 for Chemical). Mesh radius of curvature is ~60% smaller
  (94nm vs 153nm). This could mean mesh resolves real high-curvature features
  or that mesh triangulation introduces noise.

### Results (various size filters)

**No filter:**

| Metric | Chemical (n=425) | HPF (n=549) |
|--------|------------------|-------------|
| Median \|H\| | 0.01066 /nm | 0.01046 /nm |
| Mean \|H\| | 0.02003 /nm | 0.02003 /nm |
| Median radius | 93.8 nm | 95.6 nm |
| Fraction convex | 18.1% | 17.1% |
| Fraction concave | 81.9% | 82.9% |
| Median mesh verts | 26,198 | 14,009 |
| Median ECS verts | 20,190 | 13,481 |

**Size-filtered (Mann-Whitney on median |H|):**

| Filter | Chemical \|H\| (n) | HPF \|H\| (n) | Chemical radius | HPF radius | p-value |
|--------|---------------------|---------------|-----------------|------------|---------|
| None | 0.01066 (425) | 0.01046 (549) | 93.8 nm | 95.6 nm | - |
| >= 0.005 um3 | 0.00891 (340) | 0.00961 (471) | 112.3 nm | 104.0 nm | 0.086 |
| >= 0.01 um3 | 0.00659 (193) | 0.00862 (383) | 151.7 nm | 116.0 nm | < 0.0001 |
| >= 0.05 um3 | 0.00608 (92) | 0.00752 (230) | 164.3 nm | 132.9 nm | 0.002 |

**Size-filtered fraction convex:**

| Filter | Chemical frac_convex (n) | HPF frac_convex (n) |
|--------|--------------------------|---------------------|
| None | 0.181 (425) | 0.171 (549) |
| >= 0.005 um3 | 0.244 (340) | 0.206 (471) |
| >= 0.01 um3 | 0.349 (193) | 0.237 (383) |
| >= 0.05 um3 | 0.418 (92) | 0.319 (230) |

**By tissue (no size filter, values are medians across cells):**

| Tissue | Chemical \|H\| | HPF \|H\| | Chemical radius | HPF radius |
|--------|----------------|-----------|-----------------|------------|
| Kidney | 0.0129 (n=230) | 0.0093 (n=81) | 77.6 nm | 107.7 nm |
| Heart | 0.0042 (n=11) | N/A | 238.8 nm | N/A |
| Liver | 0.0130 (n=83) | 0.0153 (n=142) | 77.1 nm | 65.5 nm |
| Cortex | 0.0062 (n=101) | 0.0096 (n=326) | 161.8 nm | 104.3 nm |

---

## Metrics Summary Table

| # | Metric | Level | N (Chem/HPF) | Voxel-size confounded? | Status |
|---|--------|-------|--------------|------------------------|--------|
| 1 | ECS Volume Fraction | Crop | 24 / 17 | Low | Keep |
| 2 | ECS Half-Width (filtered) | Crop | 24 / 17 | High at fine thresholds | Keep with caveats |
| 3 | SA:V Ratio | Cell | 761 / 813 (norm) | High (r=-0.30) | Keep with caveats |
| 4 | Sphericity | Cell | 761 / 813 (norm) | High (r=-0.17) | Keep with caveats |
| 5 | Voronoi Gap Width | Crop | 24 / 17 | High at <40nm | Keep with caveats |
| 6 | Contact Fraction | Crop | 24 / 17 | Critical at <20nm | Keep at >=40nm only |
| 7 | Boundary Contact Frac. | Crop | 24 / 17 | - | **Discarded** |
| 8 | Curvature (voxel) | Cell | 425 / 549 | Moderate (r=+0.13) | Superseded by #9 |
| 9 | Curvature (mesh) | Cell | 425 / 549 | Moderate | Keep |

---

## Data Sources

- Zarr crops from CellMap, accessed via SMB mount at `/Volumes/cellmap/data`
- Path pattern: `{NRS_BASE}/{dataset}/{dataset}.zarr/recon-1/labels/groundtruth/{crop}`
- Voxel sizes from zarr metadata
- ECS = semantic segmentation (0/1), Cell = instance segmentation (0=absent, nonzero=cell IDs)

## Datasets

| Dataset | Tissue | Prep | Voxel Size | Crops |
|---------|--------|------|------------|-------|
| jrc_mus-kidney | Kidney | Chemical | 4nm | crop1026-1032 (7) |
| jrc_mus-kidney-4 | Kidney | Rapid HPF | 8nm | crop1134,1136,1137,1144 (4) |
| jrc_mus-heart-6 | Heart | Chemical | 8nm | crop1145-1147 (3) |
| jrc_mus-liver | Liver | Chemical | 4nm | crop1038-1044 (7) |
| jrc_mus-liver-8 | Liver | Rapid HPF | 8nm | crop1071-1075,1123-1127 (10) |
| jrc_mus-cortex-2 | Cortex | Rapid HPF | 8nm | crop1116,1117 (2) |
| jrc_mus-cortex-3 | Cortex | Chemical | 2nm | crop1033-1037,1045,1046 (7) |
| jrc_mus-cortex-4 | Cortex | Rapid HPF | 8nm | crop1139,1141 (2) |

## Scripts

| Script | Output | Description |
|--------|--------|-------------|
| `analyze_ecs_cell_volumes.py` | `ecs_cell_volumes.csv` | ECS and cell volume fractions per crop |
| `analyze_ecs_width.py` | `ecs_width.csv` | ECS half-width distribution (unfiltered) |
| `analyze_ecs_width_filtered.py` | `ecs_width_filtered.csv` | ECS half-width filtered to <200nm |
| `analyze_cell_morphology.py` | `cell_morphology_per_cell.csv`, `cell_morphology_crops.csv`, `cell_morphology_contacts.csv` | Per-cell SA:V, sphericity, ECS-facing SA; per-crop summaries; boundary contacts |
| `analyze_cell_morphology_normalized.py` | `cell_morphology_normalized.csv` | Per-cell morphology normalized to 8nm isotropic |
| `analyze_cell_contacts.py` | `cell_contacts.csv` | Voronoi-based inter-cell gap widths and contact fractions |
| `analyze_curvature.py` | `cell_curvature.csv` | Voxel-based mean curvature per cell |
| `analyze_curvature_mesh.py` | `cell_curvature_mesh.csv` | Mesh-based mean curvature per cell |
| `plot_ecs_by_prep.py` | `ecs_by_prep_type.png` | ECS volume fraction plots |
| `plot_ecs_width.py` | `ecs_width_by_prep.png` | ECS width distribution plots |
| `plot_cell_morphology.py` | `cell_morphology_by_prep.png` | Cell morphology comparison plots |
| `plot_cell_contacts.py` | `cell_contacts_by_prep.png` | Cell contact distribution plots |
| `plot_distributions.py` | `distributions_per_crop.png` | Per-crop distribution plots |
| `plot_summary.py` | `ecs_analysis_summary.png` | Summary figure |
