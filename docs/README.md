# ECS preservation — data site

Static site published from this folder at
<https://avweigel.github.io/ecs-analysis/>.

## What is here

| Page | Source | Notes |
| :-- | :-- | :-- |
| `index.html` | generated | overview, coverage table |
| `explore.html` | hand-written | metric explorer; reads `data/all_metrics_long.csv` at runtime |
| `crops.html` | generated | per-crop table |
| `figures.html` | copied from `out/ecs-handoff/` | plot gallery |
| `membranes/views.html` | `scripts/build_views_page.py` | curated 3D gallery, 19 crops |
| `membranes/` | copied from `figures/membranes/` | inspector + `.bin` + PNG stills |
| `data/` | copied from `results/` | the CSVs the site reads |

## Rebuilding

```
python scripts/collect_all.py     # results/*.csv  -> all_metrics_{long,wide}.csv
python scripts/build_site.py      # -> docs/index.html, docs/crops.html, docs/data/
```

`explore.html` needs no rebuild — it reads the CSVs directly.

## Deliberate omissions

- **Most of `figures/membranes/glb/`.** 19 of the 165 files are published
  (curvature only, 36.5 MB) as the quick-look gallery at `membranes/views.html`:
  one representative per tissue x region x preparation, chosen as the
  median-sized patch in each group so it is typical rather than largest. The
  other 146 are redundant — `inspect/*.bin` carries the same geometry plus all
  three scalars for all 55 crops, and the inspector colormaps them live.
  Regenerate the selection and page with `python scripts/build_views_page.py`.
- **The Neuroglancer pages** (`out/ecs-handoff/index.html`, `sanity-check.html`,
  `contacts.html`) are not published: they carry 90 links to
  `cellmap-vm1.int.janelia.org`, which is reachable only from inside Janelia.
  They can be added once the crop zarrs have a public home.
