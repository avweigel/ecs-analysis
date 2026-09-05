#!/usr/bin/env python3
"""
Turn crops' ECS surfaces into the site's hero objects.

The site is about the space between cells, and the hero was a membrane patch
-- the wall around the subject rather than the subject. This reads a .bin from
docs/membranes/ecs/, colours it by thickness, paints the cut faces in the same
neutral the viewer uses, and writes a vertex-coloured GLB the page can turn.

    python scripts/make_ecs_hero.py --set        # the eight the pages deal from
    python scripts/make_ecs_hero.py --crop crop1039 --out docs/assets/art/hero.glb
"""
from __future__ import annotations

import argparse
import json
import pathlib
from pathlib import Path

import matplotlib
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
ECS = ROOT / "docs" / "membranes" / "ecs"
MANIFEST = ROOT / "docs" / "membranes" / "manifest_ecs.json"
HERO_DIR = ROOT / "docs" / "assets" / "art" / "hero"
OUT = HERO_DIR / "index.json"

# Two crops from each tissue, one of each preparation, small enough to ship:
# a refresh shows a different tissue and quietly shows the comparison too.
SET = ["crop1035", "crop1142",      # cortex: chemical, HPF
       "crop1147", "crop1151",      # heart
       "crop1031", "crop1136",      # kidney
       "crop1121", "crop1072"]      # liver

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


def build_one(crop, mani, scalar, out_path):
    e = mani[crop]
    V, F, scal = load(e)
    vals = scal[scalar]
    lo, hi = e["ranges"][scalar]["default"]
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tm.export(out_path)
    return {"crop": crop, "file": out_path.name, "tissue": e["tissue"],
            "prep": e["prep"], "region": e.get("region_group") or e.get("anatomy") or "",
            "scalar": scalar, "faces": e["nfaces"],
            "bytes": out_path.stat().st_size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crop", default=None)
    ap.add_argument("--set", action="store_true",
                    help="build the whole set the pages deal from")
    ap.add_argument("--scalar", default="thickness")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    mani = {e["crop"]: e for e in json.loads(MANIFEST.read_text())}

    if args.set or not args.crop:
        entries = []
        for crop in SET:
            if crop not in mani:
                print(f"  {crop}: no ECS surface, skipping")
                continue
            entries.append(build_one(crop, mani, args.scalar,
                                     HERO_DIR / f"{crop}.glb"))
            e = entries[-1]
            print(f"  {e['crop']:10s} {e['tissue']:7s} {e['prep']:10s} "
                  f"{e['faces']:7,} faces  {e['bytes']/1e6:4.1f} MB")
        OUT.write_text(json.dumps(entries, indent=1))
        print(f"{len(entries)} hero objects, "
              f"{sum(e['bytes'] for e in entries)/1e6:.1f} MB, listed in {OUT.name}")
        return

    out = pathlib.Path(args.out) if args.out else HERO_DIR / f"{args.crop}.glb"
    e = build_one(args.crop, mani, args.scalar, out)
    print(f"{e['crop']}: {e['faces']:,} faces, {e['bytes']/1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
