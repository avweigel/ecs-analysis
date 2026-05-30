#!/usr/bin/env python3
"""
Membrane-patch render (pyvista) of one cell's ECS-facing surface.

In these dense crops a whole cell fills the volume (box silhouette), so we
extract only the ECS-facing membrane sub-mesh — the real corrugated surface
with its microvilli — and render it three ways from the SAME geometry that
feeds the topology metrics:
  1. signed curvature      (convex / concave)
  2. protrusion/indentation (smoothed-surface deviation)
  3. gap to nearest cell    (narrow = tight apposition / contact)

Usage:
    python scripts/render_membrane_patch.py crop1039
    python scripts/render_membrane_patch.py crop1039 --cell 1 --voxel 8 --scale 60

render_membrane() is importable for batch rendering (see render_all_membranes.py).
Writes figures/membrane_<crop>_cell<ID>.png by default.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pyvista as pv
import zarr
from scipy.ndimage import distance_transform_edt

from ecs import config as cfg
from ecs import io
from ecs.geometry import (CellMesh, classify_ecs_facing_vertices,
                          count_cell_boundary_faces, signed_mean_curvature,
                          smoothed_surface_deviation)

pv.OFF_SCREEN = True
REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_crop_translation_nm(crop) -> list[float] | None:
    """Translation (offset) of the crop's groundtruth in the parent dataset's
    coordinate system, in nm. Reads OME-NGFF multiscales metadata directly so
    we can center a Neuroglancer link on the crop ROI."""
    if not crop.zarr_path.is_dir():
        return None
    z = zarr.open(str(crop.zarr_path), mode="r")
    for label in ("cell", "ecs"):
        if label not in z:
            continue
        attrs = dict(z[label].attrs)
        ms = attrs.get("cellmap", {}).get("multiscales") or attrs.get("multiscales")
        if not ms:
            continue
        datasets = ms[0].get("datasets") or []
        if not datasets:
            continue
        for t in datasets[0].get("coordinateTransformations", []):
            if t.get("type") == "translation":
                return [float(v) for v in t["translation"]]
    return None


def pick_membrane_cell(data, sizes):
    """Cell with the most ECS-facing surface (the membrane-rich one)."""
    best = None
    for cid in sizes:
        ef = count_cell_boundary_faces(data.cell, data.ecs, cid).ecs_faces
        if best is None or ef > best[0]:
            best = (ef, cid)
    return best[1]


def extract_patch(V, F, keep_face):
    """Sub-mesh of kept faces with vertices compacted."""
    fk = F[keep_face]
    used = np.unique(fk)
    vmap = -np.ones(len(V), dtype=int)
    vmap[used] = np.arange(len(used))
    return V[used], vmap[fk], used


def build_patch(crop, cell: int | None = None, voxel: float = 8.0,
                scale: float = 60.0, contact: float = 40.0,
                dilate_rings: int = 2, boundary_margin: float = 2.0) -> dict:
    """Load a crop, pick a membrane-rich cell, mesh it, and extract the
    ECS-facing membrane patch with per-vertex scalars (all aligned to the
    patch vertices). Raises on degenerate/empty geometry. Shared by the PNG
    renderer and the GLB exporter so both use identical geometry."""
    data = io.load_crop(crop)
    if data.voxel_size_nm[0] < voxel - 1e-6:
        data = io.downsample(data, voxel)
    vx = data.voxel_size_nm

    ids, counts = np.unique(data.cell, return_counts=True)
    sizes = {int(i): int(n) for i, n in zip(ids, counts) if i != 0}
    if not sizes:
        raise ValueError("no cells in crop")
    cid = cell if cell is not None else pick_membrane_cell(data, sizes)

    mesh = CellMesh.from_mask(data.cell == cid, vx, sigma_nm=voxel * 1.5)
    if mesh is None:
        raise ValueError("degenerate cell mesh")
    V, F = mesh.verts_nm, mesh.faces
    tm = mesh.trimesh

    H, _ = signed_mean_curvature(tm)
    dev, _ = smoothed_surface_deviation(tm, scale_nm=scale)
    # Distance from each cell voxel to the nearest neighbouring-cell voxel
    # WITHIN the crop. This overestimates the true gap wherever the closest
    # neighbour lies just outside the crop — the EDT can't see across the
    # volume boundary, so it returns the distance to the next-nearest
    # in-volume neighbour instead. Vertices near the crop wall therefore read
    # as "far" even when the real microenvironment is a tight apposition.
    other = (data.cell != 0) & (data.cell != cid)
    if other.any():
        gap_field = distance_transform_edt(~other, sampling=vx)
        vi = np.clip(np.round(V / np.asarray(vx)).astype(int), 0,
                     np.asarray(data.cell.shape) - 1)
        gap = gap_field[vi[:, 0], vi[:, 1], vi[:, 2]]
    else:
        gap = np.full(len(V), np.nan)
    # Per-vertex distance to the nearest of the six volume faces. The true
    # gap is bounded above by this — a neighbour cell could lie just outside
    # the crop at distance <= d_bd. We don't clip with this (that just paints
    # a low-value rim, swapping one artifact for another); instead we flag
    # any vertex where gap > d_bd as boundary-uncertain and drop those faces
    # from the gap rendering. Curvature and deviation are local and stay.
    vol_nm = np.asarray(data.cell.shape) * np.asarray(vx)
    d_bd = np.minimum.reduce([
        V[:, 0], vol_nm[0] - V[:, 0],
        V[:, 1], vol_nm[1] - V[:, 1],
        V[:, 2], vol_nm[2] - V[:, 2],
    ])
    gap_uncertain = ~np.isnan(gap) & (gap > d_bd)

    ecs_facing_v = classify_ecs_facing_vertices(V, vx, data.ecs)
    # The ECS-facing test flickers vertex-to-vertex on the smoothed surface,
    # which drops scattered interior faces (pinholes). Dilate the mask a few
    # vertex-rings along mesh edges to close those holes before extracting the
    # patch; the boundary only grows by ~dilate_rings vertices.
    if dilate_rings > 0:
        edges = np.asarray(tm.edges_unique)
        for _ in range(dilate_rings):
            grown = ecs_facing_v.copy()
            grown[edges[:, 0]] |= ecs_facing_v[edges[:, 1]]
            grown[edges[:, 1]] |= ecs_facing_v[edges[:, 0]]
            ecs_facing_v = grown
    # Where the cell touches the crop's volume boundary, marching cubes caps it
    # with a flat face; the cap's rim is an artificial 90-degree edge that reads
    # as very high curvature. Drop faces within `boundary_margin` voxels of any
    # volume face so the cut edge isn't shown / measured as real membrane.
    vol_nm = np.asarray(data.cell.shape) * np.asarray(vx)
    m = boundary_margin * vx[0]
    near_bd = (V <= m).any(axis=1) | (V >= (vol_nm - m)).any(axis=1)
    keep = (ecs_facing_v[F].mean(axis=1) >= 0.5) & ~near_bd[F].any(axis=1)
    if keep.sum() < 4:
        raise ValueError("no ECS-facing membrane patch")
    Vp, Fp, used = extract_patch(V, F, keep)

    gap_used = gap[used]
    gap_uncertain_vp = gap_uncertain[used]
    # Per-Fp face: True iff the gap reading at every vertex of this face is
    # reliable.
    gap_face_keep = ~gap_uncertain_vp[Fp].any(axis=1)
    # Visualisation-quality mask for the curvature + deviation channels.
    # The smoothed-surface-deviation kernel (`scale` nm) and the cotangent
    # Laplacian both reach beyond the mesh rim into the marching-cubes cap
    # face at the volume boundary, biasing values inward and painting a
    # dark "protrusion" stripe along the patch edge. The 2-voxel patch trim
    # kills the cap face itself but not the smoothing's reach back into it.
    # Drop faces whose vertices fall within `scale` nm of any wall from
    # the curvature/deviation render; the gap channel and the patch stats
    # are unaffected.
    vis_margin_nm = max(boundary_margin * vx[0], scale)
    near_bd_vis = ((V <= vis_margin_nm).any(axis=1)
                   | (V >= (vol_nm - vis_margin_nm)).any(axis=1))
    vis_face_keep = ~near_bd_vis[used][Fp].any(axis=1)
    # Fraction of patch vertices whose gap reading we couldn't trust.
    # (Same definition as the old bd-clip badge — just now they're dropped
    # rather than silently bounded.)
    gap_bounded_frac = float(gap_uncertain_vp.mean()) if len(Vp) else 0.0
    # Adaptive gap colormap. A fixed 0-120 nm clim is right when the patch is
    # full of close contacts, but saturates to flat yellow whenever a crop's
    # ECS-facing surface actually sits hundreds of nm away from any other
    # cell (e.g. a cell whose neighbour-facing side is the disc and whose
    # back side faces open ECS). Anchor at contact*3 so disc-style crops
    # keep the comparable scale, then expand to p95 of kept-vertex gap
    # values so wide-gap crops show gradient instead of a blob.
    used_v = np.unique(Fp[gap_face_keep]) if gap_face_keep.any() else np.array([], int)
    gap_clim_hi = float(contact * 3)
    if len(used_v) >= 20:
        p95 = float(np.percentile(gap_used[used_v], 95))
        gap_clim_hi = max(gap_clim_hi, p95)
    return {
        "crop": crop, "cid": cid, "Vp": Vp, "Fp": Fp,
        "curvature": H[used],
        "deviation": dev[used],
        "gap": np.nan_to_num(gap_used, nan=contact * 3),
        "gap_uncertain": gap_uncertain_vp,
        "gap_face_keep": gap_face_keep,
        "vis_face_keep": vis_face_keep,
        "vis_uncertain": near_bd_vis[used],
        "gap_clim_hi": gap_clim_hi,
        "Hc": float(np.percentile(np.abs(H[used]), 90)) or 1e-6,
        "Dc": float(np.percentile(np.abs(dev[used]), 90)) or 1e-6,
        "contact": contact,
        "meta": {
            "crop": crop.crop, "dataset": crop.dataset,
            "tissue": crop.tissue, "prep": crop.prep,
            "region_group": crop.region_group or "", "anatomy": crop.anatomy or "",
            "cell": cid, "patch_faces": int(len(Fp)), "total_faces": int(len(F)),
            "gap_faces": int(gap_face_keep.sum()),
            "ecs_facing_frac": round(float(keep.mean()), 3),
            "ecs_frac": round(float(data.ecs.mean()), 4),
            "gap_bounded_frac": round(gap_bounded_frac, 3),
            "gap_clim_nm": [0.0, round(gap_clim_hi, 1)],
            "n_cells": len(sizes), "voxel_nm": vx[0],
            # For the Neuroglancer link in the gallery: center the camera on
            # the crop ROI (translation + half the shape) and pre-load every
            # cell mesh that exists in this crop.
            "cell_ids": sorted(sizes.keys()),
            "crop_shape_vox": [int(s) for s in data.cell.shape],
            "translation_nm": _read_crop_translation_nm(crop) or [0.0, 0.0, 0.0],
        },
    }


def _submesh(p: dict, face_keep_key: str, scalar_key: str):
    """Compact submesh from a patch + a face-keep mask + a scalar.
    Returns (V, F, vals) — empty if every face was filtered out."""
    Vp, Fp = p["Vp"], p["Fp"]
    F = Fp[p[face_keep_key]]
    if len(F) == 0:
        return Vp[:0], F, p[scalar_key][:0]
    used = np.unique(F)
    vmap = -np.ones(len(Vp), dtype=int)
    vmap[used] = np.arange(len(used))
    return Vp[used], vmap[F], p[scalar_key][used]


def _gap_submesh(p: dict):
    """Submesh for the gap channel: drops faces whose gap reading is
    unreliable so the boundary rim disappears instead of being painted with
    a fake value."""
    return _submesh(p, "gap_face_keep", "gap")


def _vis_submesh(p: dict, scalar_key: str):
    """Submesh for curvature / deviation: drops faces near the volume
    boundary where the cotangent Laplacian (1-ring) and smoothed-deviation
    kernel reach the marching-cubes cap and bias values inward."""
    return _submesh(p, "vis_face_keep", scalar_key)


# scalar key -> (patch field, display name, cmap, symmetric?)
SCALARS = {
    "curvature": ("curvature", "Signed curvature (1/nm)", "RdBu_r", True),
    "deviation": ("deviation", "Protrusion / indentation (nm)", "RdBu_r", True),
    "gap": ("gap", "Gap to nearest cell (nm)", "viridis", False),
}


def _clim(p: dict, key: str):
    if key == "curvature":
        return (-p["Hc"], p["Hc"])
    if key == "deviation":
        return (-p["Dc"], p["Dc"])
    return (0.0, p.get("gap_clim_hi", p["contact"] * 3))


def glb_from_patch(p: dict, out_path: Path, scalar: str = "gap") -> dict:
    """Export a vertex-colored GLB for one scalar from an already-built patch.
    Each channel renders from its own boundary-reliable submesh:
      gap        → drop faces with in-volume-EDT-uncertain vertices
      curvature  → drop faces near the marching-cubes cap (1-ring bias)
      deviation  → drop faces near the cap (smoothing-kernel bias)
    """
    import matplotlib
    import trimesh
    field, _name, cmap, _sym = SCALARS[scalar]
    lo, hi = _clim(p, scalar)
    if scalar == "gap":
        V, F, vals = _gap_submesh(p)
    else:
        V, F, vals = _vis_submesh(p, field)
    norm = matplotlib.colors.Normalize(vmin=lo, vmax=hi)
    colors = (matplotlib.colormaps[cmap](norm(vals)) * 255).astype(np.uint8)
    tm = trimesh.Trimesh(V, F, vertex_colors=colors, process=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tm.export(out_path)
    meta = dict(p["meta"]); meta["glb"] = out_path.name; meta["scalar"] = scalar
    return meta


def export_patch_glb(crop, out_path: Path, scalar: str = "gap",
                     cell: int | None = None, voxel: float = 16.0,
                     scale: float = 60.0, contact: float = 40.0) -> dict:
    """Export the membrane patch as a vertex-colored GLB (for model-viewer).
    Coarser default voxel (16 nm) keeps the web mesh light. Returns metadata."""
    p = build_patch(crop, cell=cell, voxel=voxel, scale=scale, contact=contact)
    return glb_from_patch(p, out_path, scalar)


def bin_from_patch(p: dict, out_path: Path) -> dict:
    """Write raw geometry + scalar values as a flat little-endian binary for the
    three.js inspector (which colormaps client-side). Layout, in order:
        positions  float32 [nverts*3]
        indices    uint32  [nfaces*3]
        curvature  float32 [nverts]
        deviation  float32 [nverts]
        gap        float32 [nverts]
    Counts and per-scalar ranges go in the returned metadata (the inspector
    reads them from the manifest to slice the buffer)."""
    V = np.ascontiguousarray(p["Vp"], dtype="<f4")
    F = np.ascontiguousarray(p["Fp"], dtype="<u4")
    # Boundary-uncertain vertices ride into the bin as NaN so the inspector
    # renders them neutral grey. Curvature + deviation are biased by the
    # marching-cubes cap face at the volume boundary (smoothing kernel and
    # Laplacian reach back into it); gap is biased separately by the
    # in-volume EDT overestimating distance to neighbours.
    cur = p["curvature"].astype("<f4", copy=True)
    dev = p["deviation"].astype("<f4", copy=True)
    cur[p["vis_uncertain"]] = np.float32("nan")
    dev[p["vis_uncertain"]] = np.float32("nan")
    cur = np.ascontiguousarray(cur)
    dev = np.ascontiguousarray(dev)
    gap = p["gap"].astype("<f4", copy=True)
    gap[p["gap_uncertain"]] = np.float32("nan")
    gap = np.ascontiguousarray(gap)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        for arr in (V, F, cur, dev, gap):
            f.write(arr.tobytes())

    def stat(a, default_lo):
        a = np.asarray(a, float)
        return {
            "bounds": [float(a.min()), float(a.max())],
            "default": [default_lo if default_lo is not None
                        else float(np.percentile(a, 2)),
                        float(np.percentile(a, 98))],
        }
    # symmetric defaults for diverging scalars, 0-based for gap
    Hc, Dc = p["Hc"], p["Dc"]
    meta = dict(p["meta"])
    def _bounds(a):
        a = np.asarray(a, float)
        if not np.isfinite(a).any():
            return [0.0, 1.0]
        return [float(np.nanmin(a)), float(np.nanmax(a))]
    gap_max = float(np.nanmax(gap)) if np.isfinite(gap).any() else float(p["contact"] * 3)
    meta.update({
        "nverts": int(len(V)), "nfaces": int(len(F)), "bin": out_path.name,
        "ranges": {
            "curvature": {"bounds": _bounds(cur), "default": [-Hc, Hc]},
            "deviation": {"bounds": _bounds(dev), "default": [-Dc, Dc]},
            "gap": {"bounds": [0.0, gap_max],
                    "default": [0.0, float(p.get("gap_clim_hi", p["contact"] * 3))]},
        },
    })
    return meta


def render_membrane(crop, out_path: Path, cell: int | None = None,
                    voxel: float = 8.0, scale: float = 60.0,
                    contact: float = 40.0, patch: dict | None = None) -> dict:
    """Render one crop's ECS-facing membrane patch (3 panels) to out_path.
    Pass a prebuilt `patch` (from build_patch) to avoid reloading/meshing.
    Returns a metadata dict. Raises on degenerate/empty geometry."""
    p = patch if patch is not None else build_patch(
        crop, cell=cell, voxel=voxel, scale=scale, contact=contact)
    Vc, Fc, cur_vals = _vis_submesh(p, "curvature")
    Vd, Fd, dev_vals = _vis_submesh(p, "deviation")
    Vg, Fg, gap_vals = _gap_submesh(p)
    Hc, Dc = p["Hc"], p["Dc"]

    # One PolyData PER panel, each carrying only its own scalar. Sharing a
    # single multi-scalar PolyData across subplots makes pyvista map the LAST
    # active array everywhere. Each panel also uses its own boundary-cleaned
    # submesh: gap drops EDT-uncertain faces; curvature and deviation drop a
    # smoothing-scale-wide rim where the cotangent Laplacian and 60 nm
    # smoothing kernel pick up the marching-cubes cap face at the volume
    # boundary and paint an artificial protrusion stripe.
    panels = [
        ("Signed curvature (1/nm)", Vc, Fc, cur_vals, "RdBu_r", (-Hc, Hc)),
        ("Protrusion / indentation (nm)", Vd, Fd, dev_vals, "RdBu_r", (-Dc, Dc)),
        ("Gap to nearest cell (nm)", Vg, Fg, gap_vals, "viridis",
         (0, p["contact"] * 3)),
    ]
    pl = pv.Plotter(off_screen=True, shape=(1, 3), window_size=(1950, 760),
                    border=False)
    for k, (name, V, F, vals, cmap, clim) in enumerate(panels):
        pl.subplot(0, k)
        if len(F) == 0:
            pl.add_text(f"{name.split(' (')[0]}\n(no reliable faces)",
                        font_size=11, position="upper_edge")
            continue
        f_pv = np.hstack([np.full((len(F), 1), 3), F]).ravel()
        pp = pv.PolyData(V, f_pv)
        pp[name] = vals
        pp.set_active_scalars(name)
        pl.add_mesh(pp, scalars=name, cmap=cmap, clim=clim,
                    smooth_shading=True, show_scalar_bar=True,
                    scalar_bar_args=dict(title=name, n_labels=3, fmt="%.3g",
                                         title_font_size=14, label_font_size=12,
                                         position_x=0.2, position_y=0.03))
        pl.add_text(name.split(" (")[0], font_size=11, position="upper_edge")
    pl.link_views()
    pl.view_isometric()
    pl.camera.zoom(1.4)
    pl.subplot(0, 0)
    pl.add_text(f"{crop.tissue} {crop.region_group} — {crop.prep} ({crop.crop})",
                font_size=9, position="lower_left")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(out_path))
    pl.close()

    meta = dict(p["meta"])
    meta["image"] = out_path.name
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("crop")
    ap.add_argument("--cell", type=int, default=None)
    ap.add_argument("--voxel", type=float, default=8.0)
    ap.add_argument("--scale", type=float, default=60.0)
    ap.add_argument("--contact", type=float, default=40.0)
    args = ap.parse_args()

    crop = {c.crop: c for c in cfg.active_crops()}.get(args.crop)
    if crop is None:
        print(f"{args.crop}: not active"); return
    out = REPO_ROOT / "figures" / f"membrane_{crop.crop}.png"
    meta = render_membrane(crop, out, cell=args.cell, voxel=args.voxel,
                           scale=args.scale, contact=args.contact)
    print(f"{meta['crop']} cell {meta['cell']}: patch "
          f"{meta['patch_faces']:,}/{meta['total_faces']:,} faces -> {out}")


if __name__ == "__main__":
    main()
