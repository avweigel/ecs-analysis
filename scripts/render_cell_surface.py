#!/usr/bin/env python3
"""
Cell surface topology + contact-site render for a single cell.

Picks one cell from a crop, meshes it (reusing ecs.geometry so the surface
matches the topology metrics), and renders three views of the SAME mesh:
  1. signed mean curvature   (convex red / concave blue)
  2. protrusion/indentation  (smoothed-surface deviation at a chosen scale)
  3. contact map             (gap to the nearest neighbouring cell; close = contact)

Usage:
    python scripts/render_cell_surface.py crop1039
    python scripts/render_cell_surface.py crop1039 --cell 5 --voxel 8 --scale 60
Writes figures/cellsurf_<crop>_cell<ID>.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import distance_transform_edt

from scipy.ndimage import find_objects

from ecs import config as cfg
from ecs import io
from ecs.geometry import (CellMesh, classify_ecs_facing_vertices,
                          count_cell_boundary_faces, signed_mean_curvature,
                          smoothed_surface_deviation)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pick_interior_cell(data, sizes: dict[int, int]) -> int:
    """Pick a membrane-rich, mostly-interior cell: among cells touching <=2 of
    the 6 volume faces and not space-filling, the one with the most ECS-facing
    surface. Falls back to the largest if no clean interior cell exists."""
    shape = np.asarray(data.cell.shape)
    total = int(np.prod(shape))
    slices = find_objects(data.cell)
    scored = []
    for cid, n in sizes.items():
        sl = slices[cid - 1] if cid - 1 < len(slices) else None
        if sl is None:
            continue
        touches = sum((sl[a].start == 0) + (sl[a].stop == shape[a]) for a in range(3))
        if touches > 2 or n > 0.6 * total or n < 0.005 * total:
            continue
        ecs_faces = count_cell_boundary_faces(data.cell, data.ecs, cid).ecs_faces
        scored.append((ecs_faces, cid))
    if scored:
        return max(scored)[1]
    return max(sizes, key=sizes.get)


def shade_by_scalar(verts, faces, vvals, cmap, vlim, color_mask=None,
                    light=(0.35, 0.25, 1.0)):
    """Per-face color = cmap(scalar) modulated by lambertian shading. Faces
    where color_mask is False are drawn neutral gray (e.g. crop-boundary cut
    faces that are not real membrane)."""
    fvals = vvals[faces].mean(axis=1)
    norm = mcolors.Normalize(vmin=-vlim, vmax=vlim) if vlim is not None \
        else mcolors.Normalize(vmin=fvals.min(), vmax=fvals.max())
    rgb = matplotlib.colormaps[cmap](norm(fvals))[:, :3]
    if color_mask is not None:
        rgb[~color_mask] = (0.82, 0.82, 0.82)
    fv = verts[faces]
    n = np.cross(fv[:, 1] - fv[:, 0], fv[:, 2] - fv[:, 0])
    n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
    L = np.asarray(light, float); L /= np.linalg.norm(L)
    inten = 0.45 + 0.55 * np.clip(np.abs(n @ L), 0, 1)
    rgb = np.clip(rgb * inten[:, None], 0, 1)
    return np.concatenate([rgb, np.ones((len(rgb), 1))], axis=1), norm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("crop")
    ap.add_argument("--cell", type=int, default=None, help="cell id (default: largest)")
    ap.add_argument("--voxel", type=float, default=8.0)
    ap.add_argument("--scale", type=float, default=60.0,
                    help="deviation smoothing scale (nm) for protrusion/indentation")
    ap.add_argument("--contact", type=float, default=40.0, help="contact gap threshold (nm)")
    args = ap.parse_args()

    crop = {c.crop: c for c in cfg.active_crops()}.get(args.crop)
    if crop is None:
        print(f"{args.crop}: not an active crop"); return
    data = io.load_crop(crop)
    if data.voxel_size_nm[0] < args.voxel - 1e-6:
        data = io.downsample(data, args.voxel)
    vx = data.voxel_size_nm

    ids, counts = np.unique(data.cell, return_counts=True)
    sizes = {int(i): int(n) for i, n in zip(ids, counts) if i != 0}
    cid = args.cell if args.cell is not None else _pick_interior_cell(data, sizes)
    print(f"{crop.crop} {crop.tissue}/{crop.prep} {crop.region_group}: "
          f"cell {cid} ({sizes.get(cid,0):,} vox), {len(sizes)} cells total")

    mesh = CellMesh.from_mask(data.cell == cid, vx, sigma_nm=args.voxel * 1.5)
    if mesh is None:
        print("degenerate cell mesh"); return
    V, F = mesh.verts_nm, mesh.faces
    tm = mesh.trimesh

    # Real membrane = ECS-facing vertices; the rest are crop-boundary cut faces
    # or cell-cell contacts. Topology coloring is only meaningful on membrane.
    ecs_facing_v = classify_ecs_facing_vertices(V, vx, data.ecs)
    face_ecs = ecs_facing_v[F].mean(axis=1) >= 0.5
    print(f"  {face_ecs.mean()*100:.0f}% of faces are ECS-facing membrane")

    # 1. signed curvature
    H, _ = signed_mean_curvature(tm)
    # 2. protrusion/indentation
    dev, _ = smoothed_surface_deviation(tm, scale_nm=args.scale)
    # 3. contact: gap from each vertex to nearest OTHER cell
    other = (data.cell != 0) & (data.cell != cid)
    if other.any():
        gap_field = distance_transform_edt(~other, sampling=vx)
        vi = np.clip(np.round(V / np.asarray(vx)).astype(int), 0,
                     np.asarray(data.cell.shape) - 1)
        gap = gap_field[vi[:, 0], vi[:, 1], vi[:, 2]]
    else:
        gap = np.full(len(V), np.nan)

    panels = [
        ("Signed curvature\n(convex red / concave blue)", H, "RdBu_r",
         float(np.percentile(np.abs(H), 90)), "|H| 1/nm"),
        (f"Protrusion / indentation\n(scale {args.scale:.0f} nm)", dev, "RdBu_r",
         float(np.percentile(np.abs(dev), 90)), "nm (+out/-in)"),
        (f"Contact map\ngap to nearest cell", gap, "viridis",
         None, "gap (nm)"),
    ]

    fig = plt.figure(figsize=(6.0 * len(panels), 6.4))
    ext = (V.max(0) - V.min(0)).max(); mid = (V.max(0) + V.min(0)) / 2
    for k, (title, vals, cmap, vlim, clabel) in enumerate(panels):
        ax = fig.add_subplot(1, len(panels), k + 1, projection="3d")
        if title.startswith("Contact"):
            # clip gap to [0, 3*threshold] so contact patches pop
            cap = args.contact * 3
            cvals = np.clip(np.nan_to_num(vals, nan=cap), 0, cap)
            fc, norm = shade_by_scalar(V, F, cvals, "viridis", None)
            # recolor with fixed 0..cap range for a stable legend
            fvals = cvals[F].mean(axis=1)
            norm = mcolors.Normalize(0, cap)
            rgb = matplotlib.colormaps["viridis"](norm(fvals))[:, :3]
            fvn = V[F]; n = np.cross(fvn[:, 1] - fvn[:, 0], fvn[:, 2] - fvn[:, 0])
            n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
            L = np.array([0.35, 0.25, 1.0]); L /= np.linalg.norm(L)
            inten = 0.45 + 0.55 * np.clip(np.abs(n @ L), 0, 1)
            fc = np.concatenate([np.clip(rgb * inten[:, None], 0, 1),
                                 np.ones((len(rgb), 1))], axis=1)
        else:
            fc, norm = shade_by_scalar(V, F, vals, cmap, vlim, color_mask=face_ecs)
        tri = ax.plot_trisurf(V[:, 0], V[:, 1], V[:, 2], triangles=F,
                              linewidth=0, antialiased=False)
        tri.set_facecolors(fc)
        for sl, m in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), mid):
            sl(m - ext / 2, m + ext / 2)
        ax.set_axis_off(); ax.view_init(elev=18, azim=-60)
        ax.set_title(title, fontsize=10)
        m = cm.ScalarMappable(norm=norm, cmap=cmap); m.set_array([])
        cb = fig.colorbar(m, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label(clabel, fontsize=8); cb.ax.tick_params(labelsize=7)

    fig.suptitle(f"{crop.tissue} {crop.region_group} — {crop.prep} "
                 f"({crop.crop}, cell {cid})", fontsize=12, y=1.0)
    fig.tight_layout()
    out = REPO_ROOT / "figures" / f"cellsurf_{crop.crop}_cell{cid}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
