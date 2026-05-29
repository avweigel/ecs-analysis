#!/usr/bin/env python3
"""
Regenerate the membrane PNG maps + interactive model-viewer GLBs in one pass.

Builds each crop's patch once (the expensive step), then emits the 3-panel PNG
and the three vertex-colored GLBs, and rebuilds both the static map gallery
(index.html) and the interactive 3D gallery (membranes_3d.html). Use after
changing the patch geometry (e.g. the hole-closing dilation) so PNGs and GLBs
stay consistent and hole-free.

Usage:
    python scripts/regen_galleries.py            # all active crops
    python scripts/regen_galleries.py --crops crop1039 crop1072
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecs import config as cfg
from scripts.render_membrane_patch import (SCALARS, bin_from_patch, build_patch,
                                           glb_from_patch, render_membrane)
from scripts.render_all_membranes import build_html as build_png_html
from scripts.make_membrane_glbs import build_html as build_3d_html
from scripts.make_inspector import (INSPECT_DIR, INSPECTOR_HTML, write_colormaps)

OUT_DIR = Path(__file__).resolve().parents[1] / "figures" / "membranes"
GLB_DIR = OUT_DIR / "glb"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", nargs="*", default=None)
    ap.add_argument("--voxel", type=float, default=16.0,
                    help="shared voxel for PNG + GLB (16 nm keeps GLBs light)")
    ap.add_argument("--png-only", action="store_true",
                    help="re-render PNG maps + index.html only; leave GLBs untouched")
    args = ap.parse_args()

    GLB_DIR.mkdir(parents=True, exist_ok=True)
    if not args.png_only:
        INSPECT_DIR.mkdir(parents=True, exist_ok=True)
        write_colormaps()
        (OUT_DIR / "inspector.html").write_text(INSPECTOR_HTML)
    crops = list(cfg.active_crops())
    if args.crops:
        wanted = set(args.crops)
        crops = [c for c in crops if c.crop in wanted]

    png_recs, glb_recs, ins_recs = [], [], []
    for i, crop in enumerate(crops, 1):
        try:
            p = build_patch(crop, voxel=args.voxel)            # once
            png = render_membrane(crop, OUT_DIR / f"membrane_{crop.crop}.png", patch=p)
            png_recs.append(png)
            if not args.png_only:
                glbs = {}
                for s in SCALARS:
                    m = glb_from_patch(p, GLB_DIR / f"{crop.crop}_{s}.glb", s)
                    glbs[s] = m["glb"]
                rec = dict(p["meta"]); rec["glbs"] = glbs
                glb_recs.append(rec)
                ins_recs.append(bin_from_patch(p, INSPECT_DIR / f"{crop.crop}.bin"))
            print(f"[{i}/{len(crops)}] {crop.crop} OK ({p['meta']['patch_faces']:,} faces)",
                  flush=True)
        except Exception as e:  # noqa: BLE001
            err = {"crop": crop.crop, "tissue": crop.tissue, "prep": crop.prep,
                   "region_group": crop.region_group, "error": f"{type(e).__name__}: {e}"}
            png_recs.append(err); glb_recs.append(err); ins_recs.append(err)
            print(f"[{i}/{len(crops)}] {crop.crop} FAILED: {e}", flush=True)
            traceback.print_exc()
        (OUT_DIR / "manifest.json").write_text(json.dumps(png_recs, indent=1))
        (OUT_DIR / "index.html").write_text(build_png_html(png_recs))
        if not args.png_only:
            (OUT_DIR / "manifest_3d.json").write_text(json.dumps(glb_recs, indent=1))
            (OUT_DIR / "membranes_3d.html").write_text(build_3d_html(glb_recs))
            (OUT_DIR / "manifest_inspect.json").write_text(json.dumps(ins_recs, indent=1))

    print(f"\nDone. {OUT_DIR/'membranes_3d.html'}")


if __name__ == "__main__":
    main()
