# ECS Analysis Plan

Last updated: 2026-09-03 (rewritten after the 1 Sept call with Kayvon;
previous figure-driven version backed up in `_to_delete/`)

---

## Where this is

**Exploratory.** Not choosing figures, not choosing a framing. The job right now
is to run everything that might say something, put it all in one place, and look
at it. Naming figures comes later, and naming them early would bias what gets run.

What the 1 Sept call with Kayvon added is not a set of extra analyses bolted onto
the old figure plan — it moves the object of study. The earlier work treated the
membranes as the thing and the ECS as the gap between them. Kayvon's list treats
the ECS as the thing: a connected transport space whose shape and connectivity
fixation changes.

Worth knowing while running these: **alpha (volume fraction) and lambda
(tortuosity) are the pair the ECS transport literature is written in.** Alpha is
already measured. Lambda is not. If lambda comes out, the results become directly
comparable to decades of published diffusion measurements, and the language
changes from "the space looks different" to "a metabolite takes N times longer to
cross." That is a reason to prioritise it, not a reason to commit to it as the
story.

## Collected data — done 3 Sept

`scripts/collect_all.py` merges every per-crop metric into two tables:

- `results/all_metrics_long.csv` — tidy, 12,932 measurements
- `results/all_metrics_wide.csv` — 259 rows (crop x run x resolution), 94 metrics

Re-run it after any new analysis lands and the site picks the new metrics up
automatically. Coverage as of now: all five core families cover all 55 crops in
both the native and matched runs; degradation covers 29; bm sensitivity covers
the 13 kidney crops.

**What the coverage shows, and it matters before reading any result.** Kidney —
the tissue where the direction of the effect splits by region — is also the
tissue with the thinnest arms: PCT base is Chemical 1 / HPF 0, PCT brush border
2 / 0, PCT lateral 1 / 1, DCT base 1 / 3. Space of Disse is Chemical 3 / HPF 0.
Cortex has no region assignment at all. Five of eleven region groups cannot
support a chemical-vs-HPF comparison. The site flags these in orange rather than
letting them read as results.

## The site — done 3 Sept

Published from `docs/` (see `docs/README.md`). Overview, a metric explorer over
all 94 metrics, a crop table, the figure gallery and the membrane inspector.
Replaces the local HTML files so it can be shared by link.

The crop page's viewer takes a **view**: which surface, coloured by what. Four
membrane views work today (bare mesh, curvature, protrusion/indentation, gap to
nearest cell). Three ECS views are listed and disabled, waiting on data:

| view | needs |
| --- | --- |
| ECS mesh only | an ECS surface per crop in the `.bin` layout `docs/membranes/inspect/` uses: positions `f32[nv*3]`, indices `u32[nf*3]`, then one `f32[nv]` block per scalar |
| ECS morphology | per-vertex curvature on that surface |
| ECS thickness | per-vertex local width on that surface |

`scripts/render_ecs_3d.py` already marching-cubes the ECS mask (needs the zarr,
so VPN and a cluster job). Turning a view on is one line in `VIEWS` in
`docs/assets/viewer.js` once its `.bin` and manifest ranges exist.

## Data situation

Analyses split cleanly by whether they need the voxel data:

- **Needs the cellmap share mounted.** Source is **`smb://nrsv/cellmap/data`**,
  which mounts at `/Volumes/cellmap` on the Mac and appears at
  `$HOME/mnt/cellmap` in the analysis shell. Set
  `ECS_DATA_BASE=$HOME/mnt/cellmap/data` when running there; the config default
  (`/Volumes/cellmap/data`) is correct on the Mac itself. Items 1, 2, 5, 6
  below need it.
- **Runs from `results/*.csv` today**: items 3, 4.
- Loader is `ecs.io.CropData` — gives `ecs` (bool, ecs|bm), `cell` (int
  labels), voxel size, and downsampling state. Everything new should consume
  that, not re-read zarr directly.

**Compute note.** 55 crops at 2–8 nm. Random-walk and percolation passes are
minutes-per-crop, not seconds. The device shell here times out around 45 s, so
these run detached (`nohup … &`) with a log to poll, the same way the native /
matched / degradation passes already do.

**Resolution matching is not optional for any of this.** Connectivity,
tortuosity and pore radius are all resolution-sensitive in the same direction
(finer voxels find more narrow channels), and the crop set spans 2, 4 and 8 nm
unevenly across preps. Every new metric needs the same
native / matched-8nm treatment the existing metrics already get, or the result
is a voxel-size effect wearing a biology costume.

---

## The new programme

### 1. ECS connectivity and pore geometry  ·  needs volumes  ·  new module

New `ecs/metrics/ecs_topology.py`. One module, three outputs, all from the ECS
mask and its distance transform (`ecs.geometry.ecs_distance_nm`, already
written).

- **Betti numbers.** β0 = connected components of the ECS (`ndimage.label`).
  β2 = enclosed voids (cavity count in the complement). β1 = β0 + β2 − χ,
  with χ from `skimage.measure.euler_number`. β0 answers "is the ECS one
  connected space or does fixation break it into pockets?" — which is the
  single most consequential thing prep could do to it, and nobody has looked.
- **Critical pore radius / percolation threshold.** Threshold the distance
  transform at increasing radius and test whether the ECS still spans the crop
  face to face. The largest radius that still percolates is the biggest
  particle that can cross. Report in nm, per axis, and note anisotropy.
- **Narrowest pinch point.** Falls out of the same sweep — it is the
  bottleneck that sets the critical radius. Worth reporting separately because
  it localizes: we can render where it is.

Order of work: β0 first (cheapest, and the highest-information single number
in the whole list), then percolation, then β1/β2.

### 2. Diffusion through the ECS  ·  needs volumes  ·  new module

New `ecs/metrics/diffusion.py`. **Use random-walk Monte Carlo, not a PDE
solve.** Seed n walkers uniformly in the ECS, step with reflecting boundaries
at membranes, track mean squared displacement, and fit
λ² = D_free / D_eff from the MSD slope. Reasons to prefer it: it gives λ
directly in the form the literature reports, it is trivially parallel, it
degrades gracefully (more walkers = tighter CI, no convergence cliff), and it
needs no linear algebra on a 500³ grid.

Then the legible version for the figure: with a literature D for a small
metabolite, crossing time for a crop-width slab, chemical vs HPF.

Report **α and λ together, never λ alone.** The transport-relevant quantity is
roughly α/λ², and separating them is what distinguishes "there is less space"
from "the space is more convoluted" — which is exactly the claim the paper
wants to make.

Validation before trusting any number: run it on a synthetic geometry with a
known answer (parallel slabs, λ = 1 along the slab; a periodic sphere packing
has a published λ). This can be written and validated **now, without the
drive**, and is the best use of blocked time.

### 3. ECS width variance  ·  runs today  ·  small

`native_ecs_width.csv` already carries `narrow_std_nm` and p10–p90 per crop, so
the coefficient of variation (std/mean) is free right now, as is the IQR/median
spread. That answers "is the ECS more variable in width under one prep,
independent of being wider?"

What is **not** available: the per-voxel width distributions themselves, only
their summary. A proper scale test (Brown–Forsythe / Levene) or a shape
comparison needs `ecs_width.compute` re-run with the distribution retained.
That is a small change to the metric and a re-run — cheap, but it needs the
drive.

Do the CV analysis today; queue the distribution re-run behind item 1.

### 4. Curvature and membrane area per crop  ·  already done  ·  reporting only

This item from the call is complete and under-reported, not missing.
`native_topology.csv` has `total_ecs_surface_nm2` (membrane area per crop),
curvature median/IQR/std, signed curvature percentiles, convex/concave/flat
fractions, multi-scale roughness at 30/60/120 nm, and protrusion/indentation
density per µm². `membrane_topology_per_crop.csv` has the mesh-based version
with anatomy joined.

The open question is not how to compute it, it is whether these are wired into
the summary/stats/figure pipeline the same way the core metrics are. Check
that before writing anything new.

### 5. Kidney fiber-bundle cross sections  ·  needs volumes  ·  yours explicitly

Assigned to you by name on the call. Find the large fiber bundles in kidney,
take a cross section, count and characterize the points in it. Needs crop
selection first — start from `crop_annotations.csv` regions and the kidney
renders already in `figures/`.

### 6. Actin bundles inside cells (brush border)  ·  needs volumes  ·  exploratory

Open question from the call, no defined metric yet. Park until 1–3 land.

### 7. Pearled neurons  ·  not analysis  ·  an ask

Kayvon's suggestion to put in front of experts: can they find pearled neurons,
possibly in the first cortex volume Alyson annotated. This is an email, not a
pipeline.

---

## Carried over (still live, but not driving)

- **Kidney bm sensitivity.** `results/kidney_bm_sensitivity.csv` exists.
  Interpretation is still blocked on annotator confirmation of how the HPF
  kidneys handled basement membrane — the single biggest threat to the kidney
  numbers, and kidney is already the thinnest tissue.
- **Region assignment for cortex.** Twelve crops with no region group, which is
  why cortex can only be looked at pooled.
- **Thin arms.** Five region groups cannot support a comparison. Either more
  crops, or those regions get reported descriptively.
- The Fig 2 mockup and the A/B/C framings in
  `paper/manuscript_analysis_review.md` are on ice until there is more to look at.

## Infrastructure and deadlines

- **`figures/membranes/` — 456 MB, 165 glb, currently only on this machine and
  cellmap-vm1.** Proposal D6 is to host at UCSD next to the kidney-4 zarr.
  This has a hard deadline: cellmap-vm1 access ends. Needs Kayvon's agreement
  and a date.
- **Viewer HTMLs**: 266/267 links resolve. Finish the last one.
- **Publishing**: GitHub Pages site, assets in an **S3 bucket — not
  OpenOrganelle**. Kayvon was specific about that.
- **Remaining ~20 TB Globus batch to UCSD** (kidney-4 already done).

---

## Suggested order

1. **Now, no drive needed** — write `diffusion.py` and validate it against
   synthetic geometry with a known λ. Also compute the width CV from existing
   CSVs.
2. **Drive back** — β0 across all 55 crops. One number per crop, fast, and it
   either reveals something striking or cleanly rules it out.
3. Percolation / critical pore radius, same module.
4. Random-walk λ on the real crops; pair with existing α.
5. Everything else.

The reason for that order: steps 2–4 are one coherent result — *the ECS as a
transport space, measured* — and it is the piece that would make this paper
about the biology rather than about the method.
