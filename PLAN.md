# ECS Manuscript: Analysis Plan

Working plan for the figures discussed with Kayvon (`250424 rapid HPF manuscript.ai`
mockup) mapped against what the `ecs-analysis` repo has actually produced. Scope
here is the analysis and figure-quantification work that falls on me, not the
wet-lab / sample-prep panels.

Last updated: 2026-05-28

---

## Where things stand (done)

- All three computational phases complete: native, matched-resolution (8nm),
  degradation (Chemical at 2/4/8/16nm).
- 52 active crops, ~1,500 cells. All four tissues now have both Chemical and HPF
  (Heart HPF added via `jrc_mus-heart-4`).
- 50 of 52 crops annotated. Only the 2 cortex HPF crops (1116, 1141) remain.
- Metrics implemented and run: volume fraction, ECS width, Voronoi gap, SA:V,
  topology (curvature, multi-scale roughness, protrusion/indentation density).
- Stats: Mann-Whitney U + Cliff's delta + bootstrap CIs (`stats_native.csv`).
- Anatomy-matched comparisons auto-generate from `crop_annotations.csv`.
- Headline finding stress-tested. It is tissue-specific, not universal, and
  cleanest in anatomy-matched groups. Liver SA:V survives resolution-matching;
  bile-canaliculus cell density survives. The single-crop hepatocyte-lateral
  result collapsed to null once n went to 6-vs-6 (good catch, expected).

---

## Figure targets vs repo

### Figure 1 (workflow + brain benchmarking)
Mostly wet-lab and EM material, not the analysis pipeline.
- Panel E/G cortex % ECS: **data exists** (0.107 Chem vs 0.148 HPF). Needs plotting only.
- Panels A, B, C, D, F (needle cartoon, imaging cartoon, success-rate table, TEM
  screening, FIB-SEM volume renders): **not mine.**

### Figure 2 (showcase of results, the main analysis figure)
Grid of Liver / Heart / Kidney, two anatomical areas each, with Chem example,
HPF example, and a Quantify panel, plus a "correlate of difference" row per tissue.
- Quantify panels (anatomy-matched ECS%, SA:V, etc.): **done.** Kidney bar chart
  regions (inter-duct space, finger-like projections, mesangial matrix, podocyte
  foot processes, basement membrane) map onto existing matched output.
- Example Chem/HPF image snapshots per region: **not done** (rendering work).
- "Correlate of difference" rows (contact sites / ECM / invaginations):
  **not done.** Topology module is the closest existing analysis.

### Supplemental Figure 1 ("what it took to get good samples")
Surgery/freezing cartoons, ice-damage examples, Albert's per-block quality
quantification, FigShare/open-access plan. **Almost none of this is mine.**

---

## My task list (prioritized)

### 1. Fig 2 correlate-of-difference panels  [real open analysis]
The one genuinely unfinished analysis item. Decide what "correlate of difference"
means per tissue (contact sites, ECM, invaginations) and whether the topology
module (curvature, protrusion/indentation density) can supply it.
- Check if topology metrics are wired into summaries / stats / figures the same
  way the core metrics are, or computed but under-reported.
- Confirm which Fig 2 regions the matched data actually supports for this.

### 2. Fig 2 region selection  [decision + verify]
Pick the 2 anatomical areas each for liver, heart, kidney. Confirm anatomy-matched
groups cover them with adequate n on both arms. Heart HPF is new, so heart area
panels are now possible for the first time. Flag any region where one arm is n=1.

### 3. Kidney bm sensitivity analysis  [analysis, existing data]
Kidney is the messy tissue (direction splits by region) and the bm-labeling
asymmetry sits right on it (Chemical kidneys have bm labeled, HPF kidneys have
bm=0). Recompute kidney ECS% with bm excluded on both sides to bound how much of
the kidney pattern is annotation artifact vs biology. Runnable now.

### 4. Fig 1G cortex % ECS plot  [plotting only]
Data exists. Just needs the panel rendered.

### 5. Fig 2 example image snapshots  [rendering]
Generate Chem/HPF crop snapshots for each chosen Fig 2 region. Not computation.

### 6. matched_volume_fraction.csv  [small code fix, optional]
Add a `from_data()` call to `run_matched.METRICS`. Optional, since matched SA:V
already confirms the liver resolution story.

---

## Open questions / blockers (not mine to resolve alone)

- Cortex HPF crops 1116, 1141: expert could not confidently annotate. Decide
  whether to annotate, drop, or report cortex without them.
- bm inconsistency: confirm with annotators whether HPF kidneys rolled bm into
  ecs at annotation time. Affects task 3 interpretation.
- Robustness of the two surviving liver signals (bile-canaliculus cell density
  sits at p=0.0497). Worth a sanity check before they anchor Fig 2.

---

## Notes
- Anatomy-matched groups in `summary_*_anatomy_matched.csv` / `stats_native.csv`
  are the reliable read. Pooled tissue medians are confounded by uneven anatomy
  and resolution sampling. Build Fig 2 off the matched groups.
- No paper is written yet; this plan is figure-driven, working back from the
  mockup to the analysis each panel needs.
