#!/usr/bin/env python3
"""
3D render of the extracellular space (ECS) for one or more crops.

Loads a crop's labels from the mounted cellmap zarr, downsamples to a common
voxel size for comparability, marching-cubes the ECS mask into a mesh (reusing
ecs.geometry.CellMesh so the geometry matches the quantification pipeline),
saves the mesh as PLY, and renders a shaded preview. Multiple crops render
side by side so Chemical vs Rapid HPF can be compared directly.

Usage:
    python scripts/render_ecs_3d.py crop1039 crop1072
    python scripts/render_ecs_3d.py crop1039 crop1072 --voxel 16 --out figures/ecs3d_bile.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ecs import config as cfg
from ecs.geometry import pca_view_init
from ecs import io
from ecs.geometry import CellMesh

REPO_ROOT = Path(__file__).resolve().parent.parent
MESH_DIR = REPO_ROOT / "meshes"


def _center_cube(mask: np.ndarray, voxel_nm: float, cube_nm: float) -> np.ndarray:
    """Centered cube of cube_nm physical size, for equal-tissue-volume views."""
    n = int(round(cube_nm / voxel_nm))
    out = mask
    for ax in range(3):
        size = out.shape[ax]
        if size <= n:
            continue
        start = (size - n) // 2
        out = np.take(out, range(start, start + n), axis=ax)
    return out


def build_ecs_mesh(crop, voxel_nm: float, sigma_nm: float, cube_nm: float | None):
    data = io.load_crop(crop)
    if voxel_nm and data.voxel_size_nm[0] < voxel_nm - 1e-6:
        data = io.downsample(data, voxel_nm)
    ecs = data.ecs
    frac = float(ecs.mean())
    if cube_nm:
        ecs = _center_cube(ecs, data.voxel_size_nm[0], cube_nm)
        frac = float(ecs.mean())
    mesh = CellMesh.from_mask(ecs, data.voxel_size_nm, sigma_nm=sigma_nm)
    return data, mesh, frac


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("crops", nargs="+")
    ap.add_argument("--voxel", type=float, default=16.0,
                    help="common voxel size (nm) to downsample to")
    ap.add_argument("--sigma", type=float, default=None,
                    help="smoothing sigma (nm); default = 1.5x voxel")
    ap.add_argument("--cube", type=float, default=1500.0,
                    help="centered cube (nm) carved from each crop for equal-"
                         "volume comparison; 0 to disable")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    sigma = args.sigma if args.sigma is not None else args.voxel * 1.5
    by_id = {c.crop: c for c in cfg.active_crops()}
    MESH_DIR.mkdir(exist_ok=True)

    items = []
    for cid in args.crops:
        crop = by_id.get(cid)
        if crop is None:
            print(f"  {cid}: not an active crop, skipping")
            continue
        cube = args.cube if args.cube else None
        data, mesh, frac = build_ecs_mesh(crop, args.voxel, sigma, cube)
        if mesh is None:
            print(f"  {cid}: degenerate ECS mesh, skipping")
            continue
        ply = MESH_DIR / f"{cid}_ecs_{int(args.voxel)}nm.ply"
        mesh.trimesh.export(ply)
        print(f"  {cid}: {len(mesh.faces):,} faces, ECS frac {frac:.3f} -> {ply.name}")
        items.append((crop, data, mesh, frac))

    if not items:
        print("nothing rendered")
        return

    # Volume-match: same physical box (the largest extent) for every panel,
    # so ECS amount is comparable by eye and a single scale bar applies.
    global_ext = max((m.verts_nm.max(0) - m.verts_nm.min(0)).max()
                     for _, _, m, _ in items)

    fig = plt.figure(figsize=(6.2 * len(items), 6.6))
    for k, (crop, data, mesh, frac) in enumerate(items):
        ax = fig.add_subplot(1, len(items), k + 1, projection="3d")
        v = mesh.verts_nm
        tri = ax.plot_trisurf(v[:, 0], v[:, 1], v[:, 2], triangles=mesh.faces,
                              linewidth=0, antialiased=False)
        tri.set_facecolors(_shade(v, mesh.faces, "#2563eb"))

        mid = (v.max(0) + v.min(0)) / 2
        lo = mid - global_ext / 2
        for setlim, m in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), mid):
            setlim(m - global_ext / 2, m + global_ext / 2)
        # 500 nm scale bar along x at a back-bottom corner
        bar = 500.0
        bx, by, bz = lo[0] + 0.08 * global_ext, lo[1] + 0.05 * global_ext, lo[2] + 0.05 * global_ext
        ax.plot([bx, bx + bar], [by, by], [bz, bz], color="black", lw=3)
        ax.text(bx + bar / 2, by, bz - 0.04 * global_ext, "500 nm",
                fontsize=8, ha="center")

        ax.set_title(f"{crop.tissue} {crop.region_group}\n{crop.prep} ({crop.crop})\n"
                     f"ECS frac {frac:.3f}", fontsize=10)
        ax.set_axis_off()
        elev, azim = pca_view_init(v)
        ax.view_init(elev=elev, azim=azim)

    fig.suptitle("Extracellular space — 3D (volume-matched)", fontsize=13, y=0.99)
    fig.tight_layout()
    out = Path(args.out) if args.out else REPO_ROOT / "figures" / "ecs3d.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Wrote {out}")


def _shade(verts: np.ndarray, faces: np.ndarray, base_hex: str,
           light=(0.35, 0.25, 1.0)) -> np.ndarray:
    """Per-face lambertian shading -> RGBA array for set_facecolors."""
    from matplotlib.colors import to_rgb
    fv = verts[faces]
    n = np.cross(fv[:, 1] - fv[:, 0], fv[:, 2] - fv[:, 0])
    n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)
    L = np.asarray(light, float)
    L /= np.linalg.norm(L)
    inten = 0.35 + 0.65 * np.clip(np.abs(n @ L), 0, 1)
    base = np.asarray(to_rgb(base_hex))
    rgb = np.clip(inten[:, None] * base[None, :], 0, 1)
    return np.concatenate([rgb, np.ones((len(rgb), 1))], axis=1)


if __name__ == "__main__":
    main()
