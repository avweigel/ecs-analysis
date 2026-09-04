#!/usr/bin/env python3
"""
Cut hero artwork out of the membrane render sheets.

Those sheets are matplotlib figures: three panels, titles, colourbars, white
ground. This lifts a single panel, trims it to the mesh, and writes a
transparent PNG so the site can place it on any background.

    python scripts/make_hero_art.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "art"

# (source sheet, which of the three panels, output name)
PICKS = [
    ("docs/membranes/membrane_crop1146.png", 2, "hero-gap.png"),      # viridis, caveolae
    ("docs/membranes/membrane_crop1146.png", 0, "hero-curv.png"),     # diverging curvature
    ("docs/membranes/membrane_crop1038.png", 2, "art-disse.png"),
    ("docs/membranes/membrane_crop1126.png", 0, "art-hep.png"),
]


def panel(img: Image.Image, idx: int, n: int = 3) -> Image.Image:
    """Slice one of n horizontal panels, dropping title and colourbar rows."""
    w, h = img.size
    top, bot = int(h * 0.06), int(h * 0.88)          # strip the title and the bar
    x0, x1 = int(w * idx / n), int(w * (idx + 1) / n)
    return img.crop((x0, top, x1, bot))


def cut(im: Image.Image) -> Image.Image:
    """White ground -> transparent, then trim to the remaining content."""
    im = im.convert("RGBA")
    a = np.array(im).astype(int)
    rgb = a[..., :3]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    # the matplotlib ground is pure, unsaturated white; the mesh never is
    ground = (mn > 246) & ((mx - mn) < 6)
    a[..., 3] = np.where(ground, 0, 255)

    ys, xs = np.where(a[..., 3] > 0)
    if len(ys) == 0:
        return Image.fromarray(a.astype("uint8"))
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return Image.fromarray(a.astype("uint8"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for src, idx, name in PICKS:
        p = ROOT / src
        if not p.exists():
            print("  missing:", src)
            continue
        im = cut(panel(Image.open(p), idx))
        # cap the long edge; these are decoration, not data
        long_edge = 1600
        if max(im.size) > long_edge:
            s = long_edge / max(im.size)
            im = im.resize((int(im.size[0] * s), int(im.size[1] * s)), Image.LANCZOS)
        im.save(OUT / name, optimize=True)
        kb = (OUT / name).stat().st_size / 1024
        print(f"  {name:16s} {im.size[0]}x{im.size[1]}  {kb:.0f} KB")


if __name__ == "__main__":
    main()
