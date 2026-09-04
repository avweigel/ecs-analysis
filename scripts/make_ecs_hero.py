#!/usr/bin/env python3
"""
Turn one crop's ECS surface into the front page's hero object.

The site is about the space between cells, and the hero was a membrane patch
-- the wall around the subject rather than the subject. This reads a .bin from
docs/membranes/ecs/, colours it by thickness, paints the cut faces in the same
neutral the viewer uses, and writes a vertex-coloured GLB the page can turn.

    python scripts/make_ecs_hero.py --crop crop1039
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
ECS = ROOT / "docs" / "membranes" / "ecs"
MANIFEST = ROOT / "docs" / "membranes" / "manifest_ecs.json"
OUT = ROOT / "docs" / "assets" / "art" / "hero.glb"

CUT = np.array([54, 56, 62, 255], dtype=np.uint8)      # matches CUT_GREY
NAN = np.array([78, 80, 90, 255], dtype=np.uint8)      # matches NAN_GREY


def load(entry):
    nv, nf = entry["nverts"], entry["nfaces"]
    buf = (ECS / entry["bin"]).read_bytes()
    o = 0
    V = np.frombuffer(buf, "<f4", nv * 3, o).reshape(nv, 3).astype(np.float64); o += nv * 12
    F = np.frombuffer(buf, "<u4", nf * 3, o).reshape(nf, 3).astype(np.int64);   o += nf * 12
    scal = {}
    for name in ("curvature", "deviation", "thickness", "width"):
        scal[name] = np.frombuffer(buf, "<f4", nv, o).astype(np.float64);       o += nv * 4
    return V, F, scal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crop", default=None, help="default: the crop with the most faces")
    ap.add_argument("--scalar", default="thickness")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    mani = {e["crop"]: e for e in json.loads(MANIFEST.read_text())}
    crop = args.crop or max(mani.values(), key=lambda e: e["nfaces"])["crop"]
    e = mani[crop]
    V, F, scal = load(e)
    vals = scal[args.scalar]

    lo, hi = e["ranges"][args.scalar]["default"]
    norm = matplotlib.colors.Normalize(vmin=lo, vmax=hi)
    colors = (matplotlib.colormaps["viridis"](norm(vals)) * 255).astype(np.uint8)

    # the cut faces are where the crop ended: same neutral as the viewer, so the
    # hero reads as a solid block of tissue rather than a coloured shell
    tol = float(e["voxel_nm"]) * 1.01
    lo_b, hi_b = V.min(axis=0), V.max(axis=0)
    cap = ((V - lo_b) < tol).any(axis=1) | ((hi_b - V) < tol).any(axis=1)
    colors[cap] = CUT
    colors[~cap & ~np.isfinite(vals)] = NAN

    V = V - V.mean(axis=0)                              # centre it for the viewer
    tm = trimesh.Trimesh(V, F, vertex_colors=colors, process=False)
    out = Path(args.out) if args.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    tm.export(out)
    print(f"{crop}: {len(V):,} verts, {len(F):,} faces, "
          f"{out.stat().st_size/1e6:.1f} MB -> {out}")
    return crop, e


if __name__ == "__main__":
    main()
