# Methods skeletons — acquisition & processing gaps

Placeholder text for the two Methods sections we can't write ourselves:
sample preparation / FIB-SEM imaging (Chris Bleck, Wei-Ping Li, Malan Silva)
and volume reconstruction (SciComp: Eric Trautman, Michael Innerberger).
Bracketed `[...]` items are the blanks the experts need to fill or fact-check.
Paste into the manuscript Google Doc once reviewed. The analysis methods are
already written: `paper/main.tex` (metrics 1–7) and
`paper/methods_membrane_topology.tex` (mesh topology), matching
`results/stats_native.csv`.

## Datasets covered

| Dataset | Tissue | Prep | Voxel |
| :-- | :-- | :-- | :-- |
| jrc_mus-cortex-3 | Cortex | Chemical | 4 nm |
| jrc_mus-cortex-2, -4 | Cortex | Rapid HPF | 8 nm |
| jrc_mus-heart-6 | Heart | Chemical | 8 nm |
| jrc_mus-heart-4 | Heart | Rapid HPF | 8 nm |
| jrc_mus-kidney | Kidney | Chemical | 8 nm |
| jrc_mus-kidney-4 | Kidney | Rapid HPF | 8 nm |
| jrc_mus-liver | Liver | Chemical | 8 nm |
| jrc_mus-liver-8 | Liver | Rapid HPF | 8 nm |

## 1. Sample preparation (owner: Chris / Wei-Ping / Malan)

> Mouse [strain, age, sex; n animals per tissue] tissues (cortex, heart,
> kidney, liver) were harvested following [perfusion / dissection protocol;
> IACUC protocol number]. For chemically fixed samples, tissue was fixed in
> [fixative, concentration, buffer, duration, temperature], then processed
> by [rOTO protocol — exact wording from Wei-Ping], dehydrated in [series]
> and embedded in [resin]. For rapid cryo-preserved samples, tissue was
> high-pressure frozen using a [instrument, model] in [carrier / filler
> medium], freeze-substituted in [cocktail, schedule, temperatures], and
> embedded in [resin]. [Any differences between tissues — liver/kidney/
> heart/cortex handled identically or not?]

Fact-check asks:
- [ ] rOTO wording (Wei-Ping — Kayvon already pinged, confirm status)
- [ ] HPF instrument + freeze-substitution schedule per tissue
- [ ] Animal details and protocol numbers
- [ ] Whether chem and HPF samples came from the same animals

## 2. FIB-SEM imaging (owner: Chris / Wei-Ping / Malan + Hess lab?)

> Embedded blocks were mounted [stub, charge dissipation approach] and
> imaged on a [custom Zeiss FIB-SEM system, which one] at [landing energy,
> current], with [detector], milling at [nm] steps and imaging at [4 or
> 8] nm pixels, yielding isotropic voxels of 4 nm (jrc_mus-cortex-3) or
> 8 nm (all other datasets). Acquisition ran for [duration] per volume,
> covering [volume dimensions per dataset].

Fact-check asks:
- [ ] Which FIB-SEM machine(s) — and who should be in the acknowledgments
      vs. author list for acquisition
- [ ] Per-dataset volume dimensions and acquisition parameters

## 3. Volume reconstruction & processing (owner: SciComp)

Template adapted from the alignment text SciComp provided for other
CellMap manuscripts — needs per-dataset numbers:

> The raw acquired volumes ([tile / z-frame counts per dataset]) were
> aligned using Render [citation], [brief description of the alignment /
> stitching approach used for these datasets], and exported to multiscale
> OME-Zarr. [Contrast correction / destreaking / any per-dataset
> post-processing.] Aligned volumes are available through OpenOrganelle
> [citation] at [links per dataset].

Fact-check asks:
- [ ] Per-dataset alignment details and tile counts (Michael offered to
      coordinate reconstruction methods text for the stylet paper; same
      ask here)
- [ ] Correct Render + OpenOrganelle citations

## 4. Ground-truth segmentation (we can draft, annotators fact-check)

> Cubic crops ([counts: 57 analysis crops across 8 datasets; sizes]) were
> manually segmented into cell / extracellular space / [other classes] by
> expert annotators using Amira [version], following [CellMap annotation
> protocol citation]. Anatomical region assignments (e.g. bile canaliculus,
> intercalated disc, glomerular) were made by [who — expert verification
> per crop_annotations.csv].

## 5. Analysis (done)

Already written in the repo; port from `paper/main.tex` +
`paper/methods_membrane_topology.tex`. Stats: exact two-sided Mann-Whitney,
Cliff's δ, bootstrap 95% CIs (5000 resamples, seed 1234) — see
`scripts/stats.py` and `scripts/stats_add_pooled_regions.py` for the
pooled "Tubule basal" group (DCT base + PCT base).
