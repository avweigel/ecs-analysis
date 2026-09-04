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
    thickness  float32 [nverts]     wall-to-wall chord through the space, nm
    width      float32 [nverts]     largest ball that fits in the channel, nm
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
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates

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

    Walk the normal into the space and keep the largest distance-transform
    value met -- twice that is the channel's width, exactly for a slab or a
    tube, approximately for anything else, since the ball is constrained to be
    centred on the normal ray rather than anywhere.

    The walk STOPS at the first sample outside the ECS. Without that test the
    ray runs the full probe length, crosses the cell, and reports the width of
    whatever channel it finds on the other side: on crop1072 that was 22% of
    vertices reading a median 23 nm too wide. Both directions are walked
    because the mesh's orientation is not worth relying on; the outward one
    exits immediately and contributes nothing.
    """
    vxa, shp = np.asarray(vx), np.asarray(shape) - 1

    def probe(p):
        vi = np.clip(np.round(p / vxa).astype(int), 0, shp)
        return dt[vi[:, 0], vi[:, 1], vi[:, 2]]

    best = np.zeros(len(V))
    for sgn in (1.0, -1.0):
        inside = np.ones(len(V), bool)
        run = np.zeros(len(V))
        for t in np.arange(step_nm, max_probe_nm + 1e-9, step_nm):
            d = probe(V + (sgn * t) * normals)
            inside &= d > 0
            if not inside.any():
                break
            run = np.where(inside, np.maximum(run, d), run)
        np.maximum(best, run, out=best)
    return 2.0 * best


def diffuse_on_mesh(field, tm, V, scale_nm, lamb=0.5):
    """Average a per-vertex field over a neighbourhood of `scale_nm`.

    Umbrella (uniform 1-ring) diffusion, with the iteration count set the same
    way `smoothed_surface_deviation` sets its own: N ~ sigma^2 / (2 h^2 lamb)
    for mean edge length h.
    """
    e = np.asarray(tm.edges_unique)
    h = float(np.median(np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1))) or 1.0
    n = max(1, int(round(scale_nm ** 2 / (2 * h * h * lamb))))
    deg = np.bincount(e.ravel(), minlength=len(V)).astype(float)
    deg[deg == 0] = 1.0
    x = np.asarray(field, float).copy()
    for _ in range(n):
        acc = np.zeros_like(x)
        np.add.at(acc, e[:, 0], x[e[:, 1]])
        np.add.at(acc, e[:, 1], x[e[:, 0]])
        x = (1 - lamb) * x + lamb * (acc / deg)
    return x


def chord_thickness_nm(V, normals, field, vx, max_probe_nm, step_nm):
    """How far it is through the space, wall to wall, at each surface point.

    Start on the surface, march along the normal into the ECS, and stop where
    the space ends: the distance travelled is the thickness there. This is what
    calipers on a section would measure, and it is the number that grows when a
    channel opens up.

    It marches through the SMOOTHED occupancy field the isosurface itself came
    from, sampled trilinearly, and finds the far crossing of 0.5 by linear
    interpolation between the last two samples. Marching the binary mask
    instead quantises every chord to a whole voxel, and the moire that puts
    across a surface is not tissue.

    Differs from the inscribed-ball width on purpose: the ball is bounded by
    the nearest wall in ANY direction, so it stays small at a junction where
    sheets meet; the chord follows one line and says how far the space extends
    along it. Both are kept because they disagree informatively.

    Returns (thickness, uncertain), the second flagging rays that left the cube
    before finding the far wall -- there the answer would be the box's.
    """
    vxa = np.asarray(vx)
    shape = np.asarray(field.shape)
    hi = (shape - 1) * vxa

    def sample(p):
        return map_coordinates(field, (p / vxa).T, order=1, mode="nearest")

    def in_box(p):
        return ((p >= 0.0) & (p <= hi)).all(axis=1)

    # which way is into the space? Ask, rather than trusting the mesh's
    # orientation -- one probe half a voxel off the surface each way.
    eps = 0.5 * float(vxa[0])
    fwd = sample(V + eps * normals)
    bwd = sample(V - eps * normals)
    sgn = np.where(fwd > bwd, 1.0, -1.0)
    sgn[np.maximum(fwd, bwd) <= 0.5] = 0.0            # neither way is inside
    sgn = sgn[:, None]

    thick = np.full(len(V), np.nan)
    running = sgn[:, 0] != 0
    uncertain = ~running
    prev_v = np.where(running, np.maximum(fwd, bwd), 0.0)
    prev_t = np.full(len(V), eps)
    t = eps
    while t < max_probe_nm and running.any():
        t += step_nm
        p = V + (sgn * t) * normals
        ok = in_box(p)
        v = sample(p)
        crossed = running & ok & (v <= 0.5)
        if crossed.any():
            # linear interpolation onto the 0.5 crossing, so the chord is not
            # quantised to the marching step
            f = (prev_v[crossed] - 0.5) / np.maximum(prev_v[crossed] - v[crossed], 1e-9)
            thick[crossed] = prev_t[crossed] + f * step_nm
        gone = running & ~ok                            # left the cube first
        uncertain |= gone
        thick[gone] = t
        running &= ~(crossed | gone)
        prev_v = np.where(running, v, prev_v)
        prev_t = np.where(running, t, prev_t)
    thick[running] = max_probe_nm                       # never found a far wall
    uncertain |= running
    return thick, uncertain


def extract_patch(V, F, keep_face):
    fk = F[keep_face]
    used = np.unique(fk)
    vmap = -np.ones(len(V), dtype=int)
    vmap[used] = np.arange(len(used))
    return V[used], vmap[fk], used


def build(crop, voxel_nm, sigma_nm, cube_nm, scale_nm, margin_vox,
          max_probe_nm, probe_step_nm, curv_scale_nm, chord_probe_nm):
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

    # Curvature is stated at a scale: the raw field is averaged over a
    # `curv_scale_nm` neighbourhood on the surface before it is shown.
    #
    # At 8 nm the marching-cubes staircase off a binary mask puts a signed,
    # single-vertex wobble into H that a diverging colormap renders as a
    # herringbone over every surface. The mask cannot be smoothed harder --
    # a 30 nm sheet does not survive a 24 nm Gaussian, and thin sheets are the
    # subject -- and relaxing the mesh POSITIONS barely touches it (curvature
    # is a second derivative; nine iterations cut the vertex-to-vertex jump by
    # 15%). Averaging the field itself cuts that jump 2.6x while costing 11%
    # of |H| at p90: it removes the noise, not the structure.
    dev, _ = smoothed_surface_deviation(tm, scale_nm=scale_nm)
    H, _ = signed_mean_curvature(tm)
    H = diffuse_on_mesh(H, tm, V, curv_scale_nm)
    # negated: see the module docstring on the sign convention
    H, dev = -H, -dev

    normals = np.asarray(tm.vertex_normals)
    dt = distance_transform_edt(mask, sampling=vx)
    width = local_width_nm(V, normals, dt, vx,
                           mask.shape, max_probe_nm, probe_step_nm)
    # the same occupancy field CellMesh.from_mask isosurfaces at 0.5
    field = gaussian_filter(mask.astype(np.float32),
                            tuple(sigma_nm / v for v in vx))
    thick, thick_uncertain = chord_thickness_nm(V, normals, field, vx,
                                                chord_probe_nm, probe_step_nm / 2)
    # residual speckle comes from vertex-normal jitter, not from the tissue;
    # settle it over the same neighbourhood curvature uses
    thick = diffuse_on_mesh(thick, tm, V, curv_scale_nm)

    # The transform cannot see past the volume wall, so a channel that leaves
    # the cube reads as wider than it is. Flag anything whose half-width
    # exceeds its own distance to the wall rather than quietly clipping it.
    vol_nm = np.asarray(mask.shape) * np.asarray(vx)
    d_wall = np.minimum.reduce([V[:, 0], vol_nm[0] - V[:, 0],
                                V[:, 1], vol_nm[1] - V[:, 1],
                                V[:, 2], vol_nm[2] - V[:, 2]])
    width_uncertain = (width / 2.0) > d_wall

    # The caps STAY. Marching cubes closes the mask against the cube wall with
    # a flat face, and the first version threw those faces away -- which is
    # true to the measurement (a cut face is not tissue) and a lie about the
    # object: the ECS is a solid, and without its cut faces it renders as a
    # collection of empty shells you can see through. Keeping them, with every
    # scalar blanked so they draw in the neutral grey, shows a solid block with
    # visibly artificial faces where the crop ends. Nothing is measured on
    # them.
    m = margin_vox * vx[0]
    Vp, Fp, used = V, F, np.arange(len(V))

    # Blank each scalar over its own reach, not over the widest one. Curvature
    # only feels the wall through the 24 nm relaxation; deviation feels it over
    # its whole 60 nm kernel. Blanking both at 60 nm painted a grey band four
    # times wider than curvature needed, which is most of what looked wrong
    # about the edges.
    def near_wall(margin):
        return ((V <= margin).any(axis=1)
                | (V >= (vol_nm - margin)).any(axis=1))[used]

    cur = H[used].astype("<f4"); cur[near_wall(max(m, curv_scale_nm))] = np.nan
    dvn = dev[used].astype("<f4"); dvn[near_wall(max(m, scale_nm))] = np.nan
    wid = width[used].astype("<f4"); wid[width_uncertain[used]] = np.nan
    thk = thick[used].astype("<f4")
    thk[thick_uncertain[used] | near_wall(m)] = np.nan

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{crop.crop}.bin"
    with open(out, "wb") as f:
        for arr in (np.ascontiguousarray(Vp, "<f4"),
                    np.ascontiguousarray(Fp, "<u4"),
                    np.ascontiguousarray(cur), np.ascontiguousarray(dvn),
                    np.ascontiguousarray(thk), np.ascontiguousarray(wid)):
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
        "thickness_uncertain_frac": round(float(thick_uncertain[used].mean()), 3),
        "cap_frac": round(float(near_wall(m).mean()), 3),
        "curv_scale_nm": float(curv_scale_nm), "dev_scale_nm": float(scale_nm),
        "sigma_nm": float(sigma_nm),
        "ranges": {"curvature": rng(cur, True), "deviation": rng(dvn, True),
                   "thickness": rng(thk, False), "width": rng(wid, False)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--voxel", type=float, default=8.0)
    ap.add_argument("--sigma", type=float, default=None, help="default 1.5x voxel")
    ap.add_argument("--cube", type=float, default=800.0, help="0 for the whole crop")
    ap.add_argument("--scale", type=float, default=60.0, help="deviation scale, nm")
    ap.add_argument("--curv-scale", type=float, default=24.0,
                    help="scale the mesh is relaxed to before curvature, nm")
    ap.add_argument("--margin", type=float, default=2.0, help="wall trim, voxels")
    ap.add_argument("--probe", type=float, default=200.0, help="max half-width probed, nm")
    ap.add_argument("--probe-step", type=float, default=4.0)
    ap.add_argument("--chord-probe", type=float, default=400.0,
                    help="longest chord measured before giving up, nm")
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
                      args.margin, args.probe, args.probe_step, args.curv_scale,
                      args.chord_probe)
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
