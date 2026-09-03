#!/usr/bin/env python3
"""
Build docs/data/metrics.json — the human-readable dictionary behind every
metric column the site shows.

Definitions and caveats are taken from the docstrings in ecs/metrics/*.py,
which are the authority. Where a metric is easy to misread, the caveat is
recorded here and surfaced on the site rather than left in the source.

    python scripts/build_metric_dictionary.py
"""
from __future__ import annotations

import csv, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "metrics.json"

RUNS = {
    "native": {
        "label": "Native resolution",
        "blurb": "Each crop measured at the resolution it was acquired at — 2, 4 or 8 nm.",
        "caveat": "Voxel size is not balanced across preparations, so a difference here can "
                  "be a resolution effect rather than a biological one. Check it against the "
                  "matched run before believing it.",
    },
    "matched": {
        "label": "Resolution-matched (8 nm)",
        "blurb": "Every crop downsampled to a common 8 nm voxel before measuring, so "
                 "Chemical and HPF are compared on equal footing.",
        "caveat": "The honest comparison for anything that depends on fine structure. "
                  "Downsampling loses the narrowest channels in every crop equally.",
    },
    "degradation": {
        "label": "Degradation series",
        "blurb": "One preparation measured repeatedly at 2, 4, 8 and 16 nm to show how each "
                 "metric drifts as resolution is thrown away.",
        "caveat": "This is the control that tells you how much of any difference could be "
                  "resolution alone. Read the slope, not the value.",
    },
}

FAMILIES = {
    "volume_fraction": dict(
        label="Volume fraction",
        short="How much of the crop is extracellular space",
        blurb="Voxel-count ratios: what fraction of the volume is extracellular space and "
              "what fraction is cell. The most resolution-robust family here, because it "
              "counts voxels rather than measuring distances or surfaces.",
        caveat="ECS is counted as the primary `ecs` label plus basement membrane (`bm`) "
               "where annotated, since bm is structurally part of the extracellular "
               "compartment. Four Kidney-Chemical crops under-report ECS by 2.7–10.3 "
               "percentage points without this correction — and the HPF kidneys may have "
               "handled bm differently at annotation time, which is still unconfirmed.",
    ),
    "ecs_width": dict(
        label="ECS width",
        short="How wide the extracellular gaps are",
        blurb="For every extracellular voxel, the Euclidean distance to the nearest cell "
              "voxel, summarised as percentiles across the crop.",
        caveat="This is distance to the nearest wall, not channel width. In a uniform "
               "channel of width W the values run from 0 at the walls to W/2 at the "
               "centreline, and the voxel-weighted median sits near W/4 — so multiply by "
               "roughly four to think in channel widths. The `narrow_` variants exclude "
               "anything above 200 nm, which removes vessel lumens and large pools; the "
               "`full_` variants keep them.",
    ),
    "sa_v": dict(
        label="Surface area to volume",
        short="How much ECS-facing membrane per unit of cell",
        blurb="ECS-facing membrane area divided by cell volume, pooled across every cell in "
              "the crop that passes a physical size filter.",
        caveat="Pooled at crop level, not averaged per cell — averaging per cell let "
               "truncated fragments dominate. Cells below 2.56×10⁶ nm³ are excluded so "
               "digitisation noise does not drive the ratio.",
    ),
    "voronoi_gap": dict(
        label="Cell-to-cell gap",
        short="How far apart neighbouring cells sit",
        blurb="Every extracellular voxel is assigned to its nearest cell; where two "
              "differently-assigned voxels touch, the gap between those cells is estimated "
              "from both distances plus the voxel spacing.",
        caveat="An upper bound, not the true straight-line gap — the path it measures is "
               "kinked. It also has a hard resolution floor of three voxels: at 8 nm no gap "
               "below 24 nm can be reported however narrow the real one is. Contact "
               "fractions below that floor are meaningless at 8 nm.",
    ),
    "topology": dict(
        label="Membrane shape",
        short="How folded, rough and bumpy the membrane is",
        blurb="A mesh is fitted to each cell surface, and curvature, roughness at three "
              "spatial scales, and protrusion/indentation counts are measured on the "
              "ECS-facing part of it. All vertices from all cells in a crop are pooled into "
              "one sample, weighted by surface area.",
        caveat="Convex is positive by convention, validated on synthetic spheres. Roughness "
               "is reported at 30, 60 and 120 nm, and a crop measured at 8 nm cannot "
               "resolve the 30 nm scale honestly — compare like with like.",
    ),
    "membrane_topology": dict(
        label="Membrane shape (mesh-based)",
        short="The same shape questions, measured on one representative cell",
        blurb="A second, independent implementation working from a single ECS-facing "
              "membrane patch per crop, with its own boundary handling. This is what the "
              "3D viewers show.",
        caveat="One cell per crop, not the pooled population — the newest and least "
               "stress-tested module. Vertices near the volume boundary are marked "
               "uncertain and excluded, because the smoothing kernel and the distance "
               "transform both reach into the cap face there.",
    ),
    "bm_sensitivity": dict(
        label="Basement-membrane sensitivity",
        short="How much the kidney result depends on one annotation choice",
        blurb="Kidney ECS fraction recomputed with basement membrane included and excluded, "
              "to bound how much of the kidney pattern is annotation rather than biology.",
        caveat="Kidney only. Interpretation is blocked until the annotators confirm what the "
               "HPF kidneys did with bm — this is the single biggest open threat to the "
               "kidney numbers.",
    ),
}

# exact-column overrides; everything else is derived from its name
EXACT = {
    "ecs_fraction": ("ECS fraction", "fraction of crop volume",
                     "Fraction of the crop that is extracellular space."),
    "cell_fraction": ("Cell fraction", "fraction of crop volume",
                      "Fraction of the crop that is cell."),
    "ecs_volume_um3": ("ECS volume", "µm³", "Absolute extracellular volume in the crop."),
    "cell_volume_um3": ("Cell volume", "µm³", "Absolute cell volume in the crop."),
    "total_volume_um3": ("Crop volume", "µm³", "Total volume of the crop."),
    "sa_v_ecs_per_nm": ("SA:V, ECS-facing", "nm⁻¹",
                        "ECS-facing membrane area per unit cell volume."),
    "cell_density_per_um3": ("Cell density", "cells / µm³",
                             "Cells per unit volume, after the size filter."),
    "total_ecs_facing_sa_nm2": ("ECS-facing membrane area", "nm²",
                                "Total membrane area facing extracellular space."),
    "total_cell_cell_sa_nm2": ("Cell–cell contact area", "nm²",
                               "Membrane area where two cells touch directly."),
    "total_outer_sa_nm2": ("Outer surface area", "nm²",
                           "Membrane area on the outside of the crop."),
    "total_cell_volume_nm3": ("Cell volume (filtered)", "nm³",
                              "Summed volume of cells passing the size filter."),
    "narrow_fraction": ("Narrow-channel fraction", "fraction of ECS voxels",
                        "Share of extracellular voxels sitting in channels below 200 nm."),
    "narrow_mean_nm": ("Mean distance to wall, narrow", "nm",
                       "Mean wall distance over narrow channels only."),
    "narrow_std_nm": ("Width variability, narrow", "nm",
                      "Spread of wall distances in narrow channels. Higher means the gap "
                      "width is less uniform, independent of how wide it is."),
    "gap_min_nm": ("Smallest cell–cell gap", "nm", "Narrowest gap found in the crop."),
    "gap_mean_nm": ("Mean cell–cell gap", "nm", "Average gap across Voronoi boundary faces."),
    "gap_std_nm": ("Gap variability", "nm", "Spread of cell-to-cell gaps."),
    "n_boundary_faces": ("Voronoi boundary faces", "count",
                         "How many measurements the gap distribution rests on."),
    "total_ecs_surface_nm2": ("Membrane sampled", "nm²",
                              "ECS-facing surface area entering the shape statistics."),
    "fraction_convex": ("Convex fraction", "fraction of surface",
                        "Share of ECS-facing membrane bulging outward."),
    "fraction_concave": ("Concave fraction", "fraction of surface",
                         "Share bulging inward."),
    "fraction_flat": ("Flat fraction", "fraction of surface", "Share that is neither."),
    "protrusion_density_per_um2": ("Protrusion density", "per µm²",
                                   "Outward bumps per unit membrane area."),
    "indentation_density_per_um2": ("Indentation density", "per µm²",
                                    "Inward dimples per unit membrane area."),
    "protrusion_count": ("Protrusions", "count", "Raw count of outward features."),
    "indentation_count": ("Indentations", "count", "Raw count of inward features."),
    "n_cells_considered": ("Cells considered", "count", "Cells examined in the crop."),
    "n_cells_included": ("Cells included", "count", "Cells passing the surface-area filter."),
    "n_cells_total": ("Cells in crop", "count", "All labelled cells."),
    "n_cells_passing": ("Cells passing filter", "count", "Cells above the volume floor."),
    "n_ecs_voxels": ("ECS voxels", "count", "Extracellular voxels in the crop."),
    "n_narrow_voxels": ("Narrow ECS voxels", "count", "Extracellular voxels below 200 nm."),
    "ecs_fraction_with_bm": ("ECS fraction, bm included", "fraction",
                             "Kidney ECS with basement membrane counted as extracellular."),
    "ecs_fraction_bm_excluded": ("ECS fraction, bm excluded", "fraction",
                                 "The same crop with basement membrane removed."),
    "bm_voxels": ("Basement-membrane voxels", "count", "Size of the contested annotation."),
    "frac_convex": ("Convex fraction", "fraction of patch", "Share of the patch bulging outward."),
    "frac_concave": ("Concave fraction", "fraction of patch", "Share bulging inward."),
    "frac_protrusion": ("Protrusion fraction", "fraction of patch",
                        "Share of the patch standing proud of the local plane."),
    "frac_indent": ("Indentation fraction", "fraction of patch",
                    "Share of the patch dipping below the local plane."),
    "n_curvature_kept": ("Curvature vertices used", "count",
                         "Mesh vertices contributing to curvature, after uncertain ones are dropped."),
    "n_deviation_kept": ("Deviation vertices used", "count", "Vertices contributing to deviation."),
    "n_gap_kept": ("Gap vertices used", "count", "Vertices where a facing cell was close enough to measure."),
    "total_voxels": ("Voxels in crop", "count", "Size of the crop in voxels."),
    "cell_voxels": ("Cell voxels", "count", "Voxels labelled as cell."),
    "ecs_voxels": ("ECS voxels (total)", "count", "Extracellular voxels, primary label plus basement membrane."),
    "ecs_primary_voxels": ("ECS voxels (primary label)", "count",
                           "Extracellular voxels from the `ecs` label alone."),
    "ecs_bm_voxels": ("Basement-membrane voxels", "count",
                      "Voxels annotated as basement membrane and counted into ECS."),
    "curvature_std_per_nm": ("Curvature spread (SD)", "nm⁻¹",
                             "Standard deviation of signed curvature across the membrane."),
    "curvature_iqr_per_nm": ("Curvature spread (IQR)", "nm⁻¹",
                             "Interquartile range of curvature — robust width of the distribution."),
    "patch_faces": ("Mesh faces", "count", "Triangles in the membrane patch."),
    "ecs_frac": ("ECS-facing fraction", "fraction of patch",
                 "Share of the patch that faces extracellular space."),
    "gap_bounded_frac": ("Gap-resolved fraction", "fraction of patch",
                         "Share of the patch where a facing cell was close enough to measure."),
}

PCTL = re.compile(r"^(.*?)_?p(\d{1,3})$")
ROUGH = re.compile(r"^roughness_rms_nm_p(\d+)$")


def describe(col: str, family: str):
    """Return (label, unit, blurb) for one column."""
    if col in EXACT:
        return EXACT[col]

    m = ROUGH.match(col)
    if m:
        s = m.group(1)
        return (f"Roughness at {s} nm", "nm",
                f"RMS deviation of the membrane from a local plane fitted over a {s} nm "
                f"neighbourhood — how bumpy it is at that spatial scale.")

    if col.startswith("contact_fractions_p"):
        t = col.split("_p")[-1]
        return (f"Contact fraction under {t} nm", "fraction of faces",
                f"Share of cell-to-cell boundary faces closer together than {t} nm.")


    # mesh-patch columns carry the unit as a suffix: abs_curvature_p50_nm-1
    m = re.match(r"^(abs_)?(curvature|deviation|gap)_p(\d{1,3})_(nm-1|nm)$", col)
    if m:
        absolute, what, p, unit = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        word = "median" if p == 50 else f"{p}th percentile"
        unit = "nm\u207b\u00b9" if unit == "nm-1" else "nm"
        if what == "curvature":
            name = ("Absolute curvature" if absolute else "Signed curvature")
            tail = ("how sharply the membrane bends, ignoring direction"
                    if absolute else "positive is convex, negative concave")
        elif what == "deviation":
            name = ("Absolute deviation" if absolute else "Deviation")
            tail = "departure of the membrane from a locally fitted plane"
        else:
            name = "Patch gap"
            tail = "distance from the patch to the cell facing it"
        return (f"{name}, {word}", unit, f"{word.capitalize()} {tail}.")

    # pooled topology columns put the unit last: curvature_abs_median_per_nm
    m = re.match(r"^curvature_(abs|signed)_(median|p\d{1,3})_per_nm$", col)
    if m:
        kind, stat = m.group(1), m.group(2)
        word = "median" if stat == "median" else f"{stat[1:]}th percentile"
        name = "Absolute curvature" if kind == "abs" else "Signed curvature"
        tail = ("how sharply the membrane bends, ignoring direction" if kind == "abs"
                else "positive is convex, negative concave")
        return (f"{name}, {word}", "nm\u207b\u00b9", f"{word.capitalize()} {tail}.")

    m = PCTL.match(col)
    if m:
        stem, p = m.group(1), int(m.group(2))
        ordinal = {10: "10th", 25: "25th", 50: "median", 75: "75th", 90: "90th"}.get(p, f"{p}th")
        word = "median" if p == 50 else f"{ordinal} percentile"
        if stem.startswith("narrow_percentiles_nm"):
            return (f"Wall distance, {word} (narrow)", "nm",
                    f"{word.capitalize()} distance to the nearest cell, excluding channels "
                    "wider than 200 nm.")
        if stem.startswith("full_percentiles_nm"):
            return (f"Wall distance, {word} (all)", "nm",
                    f"{word.capitalize()} distance to the nearest cell, including vessel "
                    "lumens and large pools.")
        if stem.startswith("percentiles_nm"):
            return (f"Cell–cell gap, {word}", "nm", f"{word.capitalize()} gap between neighbouring cells.")
        if "curvature_signed" in stem:
            return (f"Signed curvature, {word}", "nm⁻¹",
                    f"{word.capitalize()} signed mean curvature; positive is convex.")
        if "curvature_abs" in stem:
            return (f"Absolute curvature, {word}", "nm⁻¹",
                    f"{word.capitalize()} unsigned curvature — how sharply the membrane bends.")
        if stem.startswith("curvature"):
            return (f"Curvature, {word}", "nm⁻¹", f"{word.capitalize()} membrane curvature.")
        if stem.startswith("abs_curvature"):
            return (f"Absolute curvature, {word}", "nm⁻¹",
                    f"{word.capitalize()} unsigned curvature on the mesh patch.")
        if stem.startswith("deviation") or stem.startswith("abs_deviation"):
            a = "Absolute deviation" if stem.startswith("abs") else "Deviation"
            return (f"{a}, {word}", "nm",
                    f"{word.capitalize()} departure of the membrane from a locally fitted plane.")
        if stem.startswith("gap"):
            return (f"Patch gap, {word}", "nm",
                    f"{word.capitalize()} distance from the patch to the facing cell.")

    if col.endswith("_per_nm"):
        return (col.replace("_", " ").replace(" per nm", "").capitalize(), "nm⁻¹", "")
    if col.endswith("_nm"):
        return (col.replace("_", " ").replace(" nm", "").capitalize(), "nm", "")
    if col.startswith("frac_") or col.startswith("fraction_"):
        return (col.replace("_", " ").capitalize(), "fraction", "")
    if col.startswith("n_"):
        return (col.replace("n_", "").replace("_", " ").capitalize(), "count", "")
    return (col.replace("_", " ").capitalize(), "", "")


def main():
    rows = list(csv.DictReader((ROOT / "results" / "all_metrics_long.csv").open()))
    pairs = sorted({(r["metric_family"], r["metric"]) for r in rows})
    metrics = {}
    for fam, col in pairs:
        label, unit, blurb = describe(col, fam)
        metrics.setdefault(col, {"label": label, "unit": unit, "blurb": blurb,
                                 "families": []})
        metrics[col]["families"].append(fam)

    doc = {"runs": RUNS, "families": FAMILIES, "metrics": metrics}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    missing = [c for c, v in metrics.items() if not v["blurb"]]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(metrics)} metrics, "
          f"{len(FAMILIES)} families, {len(missing)} without a description")
    for c in missing:
        print("   no description:", c)


if __name__ == "__main__":
    main()
