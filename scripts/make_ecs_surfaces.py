#!/usr/bin/env python3
"""
Build the ECS surfaces the crop viewer loads: the extracellular space itself
as a mesh, with per-vertex scalars, in the same flat binary the membrane
patches use.

Where the membrane view shows one cell's ECS-facing skin, this shows the
space between the cells -- the network the membranes bound. Per crop it
writes docs/membranes/ecs/<crop>.bin and an entry in manifest_ecs.json.

Binary layout, little-endian, in this order:
    positions  float32 [nverts*3]   nm, in the carved sub-volume's frame
    indices    uint32  [nfaces*3]
    curvature  float32 [nverts]     signed mean curvature, 1/nm
    deviation  float32 [nverts]     protrusion / indentation, nm
    width      float32 [nverts]     local channel width, nm
NaN marks a value we do not trust; the viewer paints those vertices grey.

Sign convention: both curvature and deviation are negated relative to what
the shared geometry code returns, because that code is calibrated on a CELL
mask -- positive means the surface bulges away from the mask's interior.
Feeding it the ECS mask flips the meaning of "away". Negating puts both
views on one scale: positive still means the membrane bulges into the ECS.

Width is the local channel width, not the wall distance: at a point ON the
ECS surface the distance to the nearest cell is zero by construction. So we
walk the surface normal into the space, take the largest distance-transform
value we meet, and double it -- the diameter of the largest ball that fits in
the channel at that point. It is an estimate, and it reads as one: it
saturates in open pools, which is what the `ecs_width` metric's cutoff exists
to handle too.

Usage:
    python scripts/make_ecs_surfaces.py --crops crop1026 crop1072
    python scripts/make_ecs_surfaces.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import zarr
from scipy.ndimage import distance_transform_edt

from ecs import config as cfg
from ecs.geometry import (CellMesh, signed_mean_curvature,
                          smoothed_surface_deviation)
from ecs.io import _read_voxel_size, _ECS_SUBPART_LABELS

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "membranes" / "ecs"
MANIFEST = ROOT / "docs" / "membranes" / "manifest_ecs.json"


def load_ecs_mask(crop, target_voxel_nm: float):
    """ECS (pooled with its sub-parts, as every other metric does) at the
    target voxel size.

    Reads only the ECS labels, never the cell instances: this machine has
    4 GB and the largest crop is 250 Mvox, so pulling the instance array we
    would not use is the difference between running and being killed. The
    downsample is the same nearest-neighbour striding `ecs.io.downsample`
    applies, so the mask matches the one the metrics saw.
    """
    z = zarr.open(str(crop.zarr_path), mode="r")
    if "ecs" not in z or "s0" not in z["ecs"]:
        raise ValueError(f"{crop.crop}: missing ecs/s0")
    vx = _read_voxel_size(z["ecs"])
    if vx is None:
        raise ValueError(f"{crop.crop}: missing voxel-size metadata")
    step = max(1, int(round(target_voxel_nm / vx[0])))
    sl = (slice(None, None, step),) * 3
    mask = (np.asarray(z["ecs"]["s0"][sl]) == 1)
    for lbl in _ECS_SUBPART_LABELS:
        if lbl not in z or "s0" not in z[lbl]:
            continue
        cc = (dict(z[lbl]["s0"].attrs).get("cellmap", {})
              .get("annotation", {}).get("complement_counts", {}))
        if cc.get("present", 0) == 0:
            continue
        sub = (np.asarray(z[lbl]["s0"][sl]) == 1)
        if sub.shape == mask.shape:
            mask |= sub
    return mask, tuple(v * step for v in vx)


def pick_window(mask, voxel_nm, cube_nm, stride_frac=0.25):
    """A fixed-size cube carved from the crop, chosen to be representative.

    Crops run from 0.8 to 4.4 um on a side, so meshing all of each one gives
    surfaces that differ 50-fold in size -- useless to compare side by side
    with a shared camera, and unshippable for the big ones. A fixed cube
    fixes that, but the OBVIOUS choice, the middle of the crop, is wrong: a
    1 um cube at the centre of a liver crop can sit entirely inside one
    hepatocyte and contain no extracellular space at all (crop1072 does).

    So slide the cube over a coarse grid and keep the position whose ECS
    fraction is closest to the whole crop's. Not the emptiest window, and
    deliberately not the fullest either -- picking the widest patch of ECS in
    every crop would flatter exactly the thing the study measures.

    Returns (sub_mask, origin_voxels).
    """
    n = int(round(cube_nm / voxel_nm))
    n = [min(n, s) for s in mask.shape]
    if all(n[a] == mask.shape[a] for a in range(3)):
        return mask, (0, 0, 0)
    target = float(mask.mean())
    # summed-area table, so each candidate window is 8 lookups
    c = np.cumsum(np.cumsum(np.cumsum(
        mask.astype(np.int64), axis=0), axis=1), axis=2)
    c = np.pad(c, ((1, 0), (1, 0), (1, 0)))

    def count(o):
        z, y, x = o; dz, dy, dx = n
        return int(c[z+dz, y+dy, x+dx] - c[z, y+dy, x+dx] - c[z+dz, y, x+dx]
                   - c[z+dz, y+dy, x] + c[z, y, x+dx] + c[z, y+dy, x]
                   + c[z+dz, y, x] - c[z, y, x])

    steps = [max(1, int(n[a] * stride_frac)) for a in range(3)]
    axes = [list(range(0, mask.shape[a] - n[a] + 1, steps[a])) or [0]
            for a in range(3)]
    for a in range(3):                       # always consider the far edge
        last = mask.shape[a] - n[a]
        if axes[a][-1] != last:
            axes[a].append(last)
    vol = n[0] * n[1] * n[2]
    best, best_o = None, (0, 0, 0)
    for z in axes[0]:
        for y in axes[1]:
            for x in axes[2]:
                score = abs(count((z, y, x)) / vol - target)
                if best is None or score < best:
                    best, best_o = score, (z, y, x)
    z, y, x = best_o
    return mask[z:z+n[0], y:y+n[1], x:x+n[2]], best_o


def local_width_nm(V, normals, dt, vx, shape, max_probe_nm, step_nm):
    """Diameter of the largest ball that fits in the channel at each vertex.

    Walks both ways along the normal (the mesh's orientation is not something
    to rely on) and keeps the largest distance-transform value found; outside
    the ECS the transform is 0, so the wrong direction contributes nothing.
    """
    vxa, shp = np.asarray(vx), np.asarray(shape) - 1
    best = np.zeros(len(V))
    for sgn in (1.0, -1.0):
        for t in np.arange(0.0, max_probe_nm + 1e-9, step_nm):
            p = V + (sgn * t) * normals
            vi = np.clip(np.round(p / vxa).astype(int), 0, shp)
            np.maximum(best, dt[vi[:, 0], vi[:, 1], vi[:, 2]], out=best)
    return 2.0 * best


def extract_patch(V, F, keep_face):
    fk = F[keep_face]
    used = np.unique(fk)
    vmap = -np.ones(len(V), dtype=int)
    vmap[used] = np.arange(len(used))
    return V[used], vmap[fk], used


def build(crop, voxel_nm, sigma_nm, cube_nm, scale_nm, margin_vox,
          max_probe_nm, probe_step_nm):
    mask, vx = load_ecs_mask(crop, voxel_nm)
    full_frac = float(mask.mean())
    origin = (0, 0, 0)
    if cube_nm:
        mask, origin = pick_window(mask, vx[0], cube_nm)
    if not mask.any():
        raise ValueError("no ECS voxels in the carved volume")
    frac = float(mask.mean())

    mesh = CellMesh.from_mask(mask, vx, sigma_nm=sigma_nm)
    if mesh is None:
        raise ValueError("degenerate ECS mesh")
    V, F, tm = mesh.verts_nm, mesh.faces, mesh.trimesh

    # negated: see the module docstring on the sign convention
    H, _ = signed_mean_curvature(tm)
    dev, _ = smoothed_surface_deviation(tm, scale_nm=scale_nm)
    H, dev = -H, -dev

    dt = distance_transform_edt(mask, sampling=vx)
    width = local_width_nm(V, np.asarray(tm.vertex_normals), dt, vx,
                           mask.shape, max_probe_nm, probe_step_nm)

    # The transform cannot see past the volume wall, so a channel that leaves
    # the cube reads as wider than it is. Flag anything whose half-width
    # exceeds its own distance to the wall rather than quietly clipping it.
    vol_nm = np.asarray(mask.shape) * np.asarray(vx)
    d_wall = np.minimum.reduce([V[:, 0], vol_nm[0] - V[:, 0],
                                V[:, 1], vol_nm[1] - V[:, 1],
                                V[:, 2], vol_nm[2] - V[:, 2]])
    width_uncertain = (width / 2.0) > d_wall

    # Marching cubes caps the mask at the wall with a flat face; that cap is
    # not membrane, and its rim reads as extreme curvature. Drop it, and drop
    # the curvature/deviation values whose kernels reached into it.
    m = margin_vox * vx[0]
    near = (V <= m).any(axis=1) | (V >= (vol_nm - m)).any(axis=1)
    keep = ~near[F].any(axis=1)
    if keep.sum() < 4:
        raise ValueError("nothing left after trimming the wall")
    Vp, Fp, used = extract_patch(V, F, keep)

    vis_m = max(m, scale_nm)
    vis_bad = ((V <= vis_m).any(axis=1) | (V >= (vol_nm - vis_m)).any(axis=1))[used]
    cur = H[used].astype("<f4"); cur[vis_bad] = np.nan
    dvn = dev[used].astype("<f4"); dvn[vis_bad] = np.nan
    wid = width[used].astype("<f4"); wid[width_uncertain[used]] = np.nan

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{crop.crop}.bin"
    with open(out, "wb") as f:
        for arr in (np.ascontiguousarray(Vp, "<f4"),
                    np.ascontiguousarray(Fp, "<u4"),
                    np.ascontiguousarray(cur), np.ascontiguousarray(dvn),
                    np.ascontiguousarray(wid)):
            f.write(arr.tobytes())

    def rng(a, symmetric):
        a = np.asarray(a, float); a = a[np.isfinite(a)]
        if not a.size:
            return {"bounds": [0.0, 1.0], "default": [0.0, 1.0]}
        if symmetric:
            c = float(np.percentile(np.abs(a), 90)) or 1e-6
            return {"bounds": [float(a.min()), float(a.max())], "default": [-c, c]}
        return {"bounds": [float(a.min()), float(a.max())],
                "default": [0.0, float(np.percentile(a, 98))]}

    return {
        "crop": crop.crop, "dataset": crop.dataset, "tissue": crop.tissue,
        "prep": crop.prep, "region_group": crop.region_group or "",
        "anatomy": crop.anatomy or "",
        "nverts": int(len(Vp)), "nfaces": int(len(Fp)),
        "bin": f"{crop.crop}.bin", "bytes": int(out.stat().st_size),
        "voxel_nm": float(vx[0]), "cube_nm": (float(cube_nm) if cube_nm else None),
        "box_nm": [round(float(x), 1) for x in vol_nm],
        "window_origin_vox": [int(v) for v in origin],
        "window_origin_nm": [round(float(o * vx[i]), 1) for i, o in enumerate(origin)],
        "ecs_frac": round(frac, 4), "ecs_frac_full_crop": round(full_frac, 4),
        "width_uncertain_frac": round(float(width_uncertain[used].mean()), 3),
        "ranges": {"curvature": rng(cur, True), "deviation": rng(dvn, True),
                   "width": rng(wid, False)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--voxel", type=float, default=8.0)
    ap.add_argument("--sigma", type=float, default=None, help="default 1.5x voxel")
    ap.add_argument("--cube", type=float, default=800.0, help="0 for the whole crop")
    ap.add_argument("--scale", type=float, default=60.0, help="deviation scale, nm")
    ap.add_argument("--margin", type=float, default=2.0, help="wall trim, voxels")
    ap.add_argument("--probe", type=float, default=200.0, help="max half-width probed, nm")
    ap.add_argument("--probe-step", type=float, default=8.0)
    args = ap.parse_args()

    sigma = args.sigma if args.sigma is not None else args.voxel * 1.5
    by_id = {c.crop: c for c in cfg.active_crops()}
    want = list(by_id) if (args.all or not args.crops) else args.crops

    entries = {}
    if MANIFEST.exists():                      # keep crops we are not rebuilding
        try:
            entries = {e["crop"]: e for e in json.loads(MANIFEST.read_text())}
        except Exception:
            entries = {}

    for cid in want:
        crop = by_id.get(cid)
        if crop is None:
            print(f"  {cid}: not an active crop", flush=True); continue
        t = time.time()
        try:
            e = build(crop, args.voxel, sigma, args.cube or None, args.scale,
                      args.margin, args.probe, args.probe_step)
            e["built_s"] = round(time.time() - t, 1)
            entries[cid] = e
            print(f"  {cid}: {e['nverts']:>7,} verts  {e['nfaces']:>7,} faces  "
                  f"{e['bytes']/1e6:5.1f} MB  {e['built_s']:5.1f}s", flush=True)
        except Exception as exc:
            print(f"  {cid}: FAILED {exc}", flush=True)
            traceback.print_exc()
        MANIFEST.write_text(json.dumps([entries[k] for k in sorted(entries)],
                                       indent=1))
    print(f"{len(entries)} crops in {MANIFEST.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
