# Analysis review for the manuscript — what we have, what it shows, what to include

Working memo for Aubrey, 2026-08-24. Options laid out, not verdicts — mark up
freely, then we distill for Kayvon. Every number here is from
`results/stats_native.csv` and the results CSVs as of commit `e9d0df4`.

Reading guide: δ is Cliff's delta (+1 = every Chem crop above every HPF crop),
p is the exact Mann-Whitney. At our n (2–6 per arm) p has a hard floor
(0.057 at 3v4, 0.20 at 2v3, 0.333 at 2v2), so δ + bootstrap CI is the honest
readout for region-level claims; p only has room to work at tissue level.

---

## 0. The dataset, honestly stated

57 active crops across 8 datasets, 4 tissues × 2 preps, ~1,500 cells.
All crops annotated. Known asymmetries that constrain claims:

| Issue | Facts | Consequence |
| :-- | :-- | :-- |
| Voxel-size confound | All HPF at 8 nm; Chemical mixes 2, 4, 8 nm | Any fine-scale metric favors Chem artifactually. Addressed by the matched-resolution (8 nm) phase and the degradation series — every headline claim should cite the matched number. |
| Kidney bm labeling | Chemical kidneys have basement membrane labeled; HPF kidneys have bm = 0 voxels | Part of kidney Chem>HPF ECS is annotation, not biology. bm-sensitivity run bounds it (see §7). Still needs annotator confirmation of what HPF did with bm. |
| Chem-only regions | Space of Disse (n=3), PCT brush border (n=2) have no HPF arm | Descriptive only; can't support comparisons. |
| Exclusions | crop1117 (no labels), crop1139 (vessel lumen); cortex-2 crops 1113–1115 not in active set | State in methods; manifest column `in_analysis` tracks it. |
| Boundary truncation | 51% of cells sit below 0.01 µm³ (crop-edge fragments) | Filtered for per-cell metrics; must be stated. |

---

## 1. ECS volume fraction (metric 1)

**What it is.** Fraction of crop volume labeled ECS. The headline metric,
and the one with the literature conversation (brain cryo vs aldehyde).

**What it shows.**

| Group | Chem | HPF | δ | p | n |
| :-- | --: | --: | --: | --: | :-- |
| Liver (tissue) | 18.4% | 4.0% | +0.47 | 0.069 | 12v10 |
| Kidney (tissue) | 35.6% | 12.8% | +0.38 | 0.30 | 7v6 |
| Cortex (tissue) | 10.7% | 14.7% | −0.37 | 0.34 | 7v5 |
| Heart (tissue) | 15.8% | 20.8% | −0.12 | 0.89 | 4v4 |
| Bile canaliculus | 19.2% | 7.3% | +1.00 | 0.057* | 3v4 |
| Tubule basal (pooled) | 24.9% | 10.9% | +1.00 | 0.20* | 2v3 |
| Hepatocyte lateral | 4.5% | 2.8% | +0.33 | 0.39 | 6v6 |
| Glomerular | 40% | 50% | 0.00 | 1.0 | 2v2 |
| Cardiac interstitial | 25.8% | 29.9% | −0.50 | 0.67 | 2v2 |
| Intercalated disc | 10.2% | 12.4% | 0.00 | 1.0 | 2v2 |

*p at its floor — δ is maxed, the test literally cannot go lower at this n.

**For inclusion.** It's the field's reference quantity; the region-matched
liver and tubule numbers are large, consistent, and survive every control we
ran. The cortex direction (Chem < HPF) flips against liver/kidney — that
inversion is arguably the single most interesting fact in the study.

**Against / caveats.** Tissue-level pooled numbers are confounded by crop
placement (within Chem alone, ECS ranges 1.4%–74.6% across crops) and uneven
anatomy sampling — main.tex documents this bluntly. Only the anatomy-matched
rows are defensible. Kidney needs the bm caveat attached every time.

**Options.** (a) Main figure as region-matched panels only, tissue pooled
numbers nowhere; (b) main figure with tissue-level shown as context but
greyed/annotated; (c) ECS% as supplement, lead with SA:V instead.

---

## 2. ECS channel half-width (metric 2)

**What it shows.** Cortex width p50: Chem 6 nm vs HPF 11.3 nm (δ=−0.71,
p=0.048) — narrower channels in chem cortex, consistent with the classic
brain-shrinkage literature. Tubule basal δ=+1.00 (33 vs 11 nm). Liver regions
mixed and mostly null after matching.

**For.** Direct, intuitive, literature-comparable ("ECS width" is what
physiologists quote). The cortex result is one of the few p<0.05 non-topology
signals.

**Against.** Voxel quantization is severe: at 8 nm voxels the minimum
half-width is ~4 nm and values step in ~4 nm increments; Chem's 2–4 nm crops
measure finer for free. The matched run shrinks several gaps (hepatocyte
lateral p50: 16 vs 11.3 nm at matched 8 nm — modest). Must report half-width
vs full-width carefully.

**Options.** (a) Supplement in full with the matched numbers primary;
(b) one width panel in the main cortex/liver figure, matched-resolution only;
(c) fold into the ECS% panel as a secondary axis and keep prose minimal.

---

## 3. Voronoi gap / cell-contact fractions (metric 5)

**What it shows.** Cortex: contact<40nm 96% (Chem) vs 67% (HPF), p=0.048;
gap p25/p50/p75 all Chem<HPF. Elsewhere mostly floor-p or null.

**For.** "How much of the membrane is within X of a neighbor" is the most
functionally interpretable framing for synaptic/diffusion audiences, and the
cortex contact story complements the width story.

**Against (critical).** Resolution floor: at 8 nm voxels the minimum
measurable gap is ~13.8 nm, so HPF physically cannot register the tightest
contacts that Chem's 2 nm crops can. main.tex flags this as proven-by-data.
Only matched-resolution comparisons are honest, and after matching the
effect weakens.

**Options.** (a) Report only matched-resolution contact fractions, main text
for cortex, supplement elsewhere; (b) drop the Voronoi machinery from the
main story and keep ECS width as the sole gap metric; (c) supplement-only
with the resolution-floor demonstration as its own methods panel (it's a
nice cautionary result in itself — reviewers will like the honesty).

---

## 4. SA:V and cell density (metric 3)

**What it shows.** The robustness champion. Bile canaliculus SA:V:
Chem 0.0100 vs HPF 0.0029 /nm at matched 8 nm (3.4×), δ=+1.00; cell density
3.42 vs 0.87 /µm³ matched. Liver tissue-level SA:V p=0.030, δ=+0.55.
Tubule basal SA:V δ=+1.00. Degradation series: liver SA:V is 0.01006 at 4 nm,
0.00997 at 8 nm, 0.00749 at 16 nm — flat through the working range, so
resolution does not manufacture the effect. Hepatocyte lateral collapsed to
~null at 6v6 after an early single-crop artifact — a good stress-test story.

**For.** Survived resolution matching, degradation, and the n-expansion that
killed the weaker liver signal. If one quantity anchors Fig 2, the case for
SA:V is the strongest in the repo.

**Against.** One step removed from "ECS" per se (it measures cell surface
geometry); staircase bias inflates absolute values (fine for Chem-vs-HPF at
matched voxels, awkward for literature comparison); 51% boundary-cell
filtering must be prominent.

**Options.** (a) Co-headline with ECS% in Fig 2 (fraction says "how much
space", SA:V says "what the membranes are doing about it"); (b) headline
metric with ECS% as context; (c) per-region supplement table only.

---

## 5. Sphericity (metric 4)

**What it shows.** Chem cells "rounder" — but normalization alone moves
Chem sphericity from 0.518 to 0.650 (pure resampling smoothing, zero
biology), and it's largely redundant with SA:V.

**For.** Familiar shape descriptor.

**Against.** The normalization artifact is disqualifying for a headline;
redundancy adds nothing SA:V doesn't already say.

**Options.** (a) Drop entirely; (b) supplement table row with the artifact
documented. Hard to see a main-text case.

---

## 6. Membrane topology (metric 8, mesh-based) — the correlate-of-difference module

**What it shows.** The strongest p-values in the entire study, all in cortex:
roughness at every scale (60 nm: 2.8 vs 4.7, p=0.0025, δ=−1.00 — HPF rougher),
curvature std p=0.0025, fraction convex 0.37 vs 0.60 p=0.0025, protrusion
density 34.5 vs 16.1 /µm² p=0.0025 δ=+1.00 (Chem more protrusions).
Liver: protrusion density 13.9 vs 10.6 p=0.009 δ=+0.65, indentation p=0.025.
Kidney: curvature std p=0.022 δ=−0.76. Heart: null (Albert's caveolae are the
heart membrane story). Outlier handling exists and is principled
(topology_outliers.json; hepatocyte-lateral survives with and without).

**For.** This is the module that answers "what does fixation actually do to
membranes" — the mechanistic correlate the April plan said was missing. The
per-tissue signatures differ (cortex: HPF-rough/Chem-protrusive; liver:
Chem-protrusive both ways), which is either the paper's most novel content
or its hardest-to-explain content, depending on framing.

**Against.** One cell per crop (the most membrane-rich one) — a deliberate,
defensible, but attackable sampling choice. Mesh smoothing choices control
absolute magnitudes (2× above voxel method); only relative Chem-vs-HPF claims
at matched working resolution (16 nm grid) are safe. Newest module = least
battle-tested.

**Options.** (a) Full correlate-of-difference row in Fig 2 per tissue, as the
mockup wanted; (b) cortex-only topology figure (where p is unambiguous) with
liver protrusions in supplement; (c) all topology to supplement pending a
multi-cell-per-crop robustness check (the one analysis addition that would
bulletproof it).

---

## 7. The control analyses (these are content, not just hygiene)

**Matched-resolution phase (8 nm).** The reason any fine-scale claim
survives review. Liver SA:V and bile-canaliculus cell density survive;
several width/contact effects shrink. Option: a dedicated "resolution
controls" supplement figure; every main-text number gets its matched twin.

**Degradation series (Chem at 2/4/8/16 nm).** Shows metric-by-metric drift
with voxel size; liver SA:V flat 4→8 nm. Option: supplement figure +
one-line methods claim "effects are stable across the acquisition range."

**Kidney bm sensitivity.** Excluding bm: Chem glomerular 44.4→38.5% and
35.6→32.9%, PCT base 30.3→19.9%, DCT base 19.5→13.7%; HPF unchanged (bm=0).
Direction of kidney/tubule effects survives, magnitude shrinks. Options:
(a) report bm-excluded as the primary kidney numbers; (b) both, with bm
asymmetry as explicit caveat; (c) hold kidney out of quantitative claims
until annotators confirm how HPF handled bm.

**Voxel-vs-mesh curvature comparison (metric 7 vs 8).** Methods-validation
content. Option: supplement only, as justification for the mesh choice.

**Stats machinery.** Exact MW + δ + bootstrap CI, seed-pinned; pooled
Tubule basal now scripted (`stats_add_pooled_regions.py`, n=2v3 — Kayvon
should bless the pooling). The p-floor argument needs to be in methods
regardless of framing, or reviewers will read every 0.057 as "trend."

---

## 8. Candidate story framings

**Framing A — "The fixation artifact atlas": prep effects are tissue- and
structure-specific.** Lead with the inversion: chemical fixation *shrinks*
ECS in cortex (classic literature direction) but *inflates* apparent ECS in
liver and kidney tubules, and does ~nothing to heart. Fig 2 = the six-region
grid (matrix + vignettes already built). Topology rows explain the mechanism
per tissue. Pros: uses everything we built, matches the existing mockup,
the inversion is memorable, honest about heterogeneity. Cons: "it depends"
stories are harder to title and abstract; needs the kidney bm caveat managed
carefully; cortex ECS% itself is not significant (δ=−0.37, p=0.34) so the
inversion leans on width/contact/topology for cortex.

**Framing B — "Membranes remember fixation": topology as the headline.**
Lead with the strongest statistics in the study (cortex roughness/protrusion
p=0.0025 across the board), present ECS volume changes as the downstream
consequence of membrane deformation. Pros: cleanest p-values, most novel
measurement, differentiates from prior ECS-shrinkage papers. Cons: hangs the
paper on the newest, least-stress-tested module and a one-cell-per-crop
sampling choice; liver ECS story (our most robust effect-size result) gets
demoted; Fig 1 cortex benchmarking (Kayvon/Albert's) would need to align.

**Framing C — "How much can you trust chemical fixation? A quantitative
correction guide."** Practical framing: per-tissue, per-structure effect
sizes with CIs, presented as correction factors / trust levels, with the
resolution-floor and bm analyses elevated to first-class results (the paper
doubles as a methods-caveats guide for the field). Pros: maximally honest,
every control becomes content, very reviewer-proof, service value to the
volume-EM community. Cons: less of a discovery narrative; risks reading as
a technical report; effect-size-without-p framing needs confident writing.

These aren't exclusive — A with B's cortex topology panel as the mechanism
inset is the closest fit to the existing Fig 2 mockup.

---

## 9. Decision grid (mark up: M = main, S = supplement, D = drop, ? = discuss)

| Analysis | A fit | B fit | C fit | Your call |
| :-- | :-- | :-- | :-- | :-- |
| ECS% region-matched | M | S | M | |
| ECS% tissue pooled | S/D | D | S | |
| ECS width (matched) | M(cortex) | S | M | |
| Voronoi contact (matched) | S | S | M(as caveat demo) | |
| SA:V + cell density | M | S | M | |
| Sphericity | D | D | S/D | |
| Topology cortex | M(inset) | M | M | |
| Topology liver/kidney | M(row) | M | S | |
| Voxel-vs-mesh comparison | S | S | S | |
| Degradation series | S | S | M | |
| Kidney bm sensitivity | S | S | M | |
| Chem-only regions (Disse, brush border) | S(descriptive) | D | S | |

## 10. Things that would change the answers (open items)

Annotator confirmation on HPF kidney bm handling. Multi-cell-per-crop
topology robustness check (only if B). Whether Fig 1 (Kayvon/Albert, cortex
benchmark) claims the cortex story — if yes, A's inversion lead needs
coordinating so Fig 2 doesn't repeat Fig 1. Heart caveolae (Albert) — the
heart "null" in our metrics is only half the heart story. Bile-canaliculus
p-floor framing (D4, agreed: δ + CI, not p).
