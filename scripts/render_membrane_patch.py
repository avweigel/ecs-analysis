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
from scipy.ndimage import distance_transform_edt

from ecs import config as cfg
from ecs import io
from ecs.geometry import (CellMesh, classify_ecs_facing_vertices,
                          count_cell_boundary_faces, signed_mean_curvature,
                          smoothed_surface_deviation)

pv.OFF_SCREEN = True
REPO_ROOT = Path(__file__).resolve().parent.parent


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
                scale: float = 60.0, contact: float = 40.0) -> dict:
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
    other = (data.cell != 0) & (data.cell != cid)
    if other.any():
        gap_field = distance_transform_edt(~other, sampling=vx)
        vi = np.clip(np.round(V / np.asarray(vx)).astype(int), 0,
                     np.asarray(data.cell.shape) - 1)
        gap = gap_field[vi[:, 0], vi[:, 1], vi[:, 2]]
    else:
        gap = np.full(len(V), np.nan)

    ecs_facing_v = classify_ecs_facing_vertices(V, vx, data.ecs)
    keep = ecs_facing_v[F].mean(axis=1) >= 0.5
    if keep.sum() < 4:
        raise ValueError("no ECS-facing membrane patch")
    Vp, Fp, used = extract_patch(V, F, keep)

    return {
        "crop": crop, "cid": cid, "Vp": Vp, "Fp": Fp,
        "curvature": H[used],
        "deviation": dev[used],
        "gap": np.nan_to_num(gap[used], nan=contact * 3),
        "Hc": float(np.percentile(np.abs(H[used]), 90)) or 1e-6,
        "Dc": float(np.percentile(np.abs(dev[used]), 90)) or 1e-6,
        "contact": contact,
        "meta": {
            "crop": crop.crop, "tissue": crop.tissue, "prep": crop.prep,
            "region_group": crop.region_group or "", "anatomy": crop.anatomy or "",
            "cell": cid, "patch_faces": int(len(Fp)), "total_faces": int(len(F)),
            "ecs_facing_frac": round(float(keep.mean()), 3),
            "ecs_frac": round(float(data.ecs.mean()), 4),
            "n_cells": len(sizes), "voxel_nm": vx[0],
        },
    }


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
    return (0.0, p["contact"] * 3)


def glb_from_patch(p: dict, out_path: Path, scalar: str = "gap") -> dict:
    """Export a vertex-colored GLB for one scalar from an already-built patch."""
    import matplotlib
    import trimesh
    field, _name, cmap, _sym = SCALARS[scalar]
    lo, hi = _clim(p, scalar)
    norm = matplotlib.colors.Normalize(vmin=lo, vmax=hi)
    colors = (matplotlib.colormaps[cmap](norm(p[field])) * 255).astype(np.uint8)
    tm = trimesh.Trimesh(p["Vp"], p["Fp"], vertex_colors=colors, process=False)
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


def render_membrane(crop, out_path: Path, cell: int | None = None,
                    voxel: float = 8.0, scale: float = 60.0,
                    contact: float = 40.0) -> dict:
    """Render one crop's ECS-facing membrane patch (3 panels) to out_path.
    Returns a metadata dict. Raises on degenerate/empty geometry."""
    p = build_patch(crop, cell=cell, voxel=voxel, scale=scale, contact=contact)
    Vp, Fp = p["Vp"], p["Fp"]
    faces_pv = np.hstack([np.full((len(Fp), 1), 3), Fp]).ravel()
    poly = pv.PolyData(Vp, faces_pv)
    poly["Signed curvature (1/nm)"] = p["curvature"]
    poly["Protrusion / indentation (nm)"] = p["deviation"]
    poly["Gap to nearest cell (nm)"] = p["gap"]
    Hc, Dc = p["Hc"], p["Dc"]

    panels = [
        ("Signed curvature (1/nm)", "RdBu_r", (-Hc, Hc)),
        ("Protrusion / indentation (nm)", "RdBu_r", (-Dc, Dc)),
        ("Gap to nearest cell (nm)", "viridis", (0, contact * 3)),
    ]
    pl = pv.Plotter(off_screen=True, shape=(1, 3), window_size=(1950, 760),
                    border=False)
    for k, (name, cmap, clim) in enumerate(panels):
        pl.subplot(0, k)
        pl.add_mesh(poly, scalars=name, cmap=cmap, clim=clim,
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
