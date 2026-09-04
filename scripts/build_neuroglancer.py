#!/usr/bin/env python3
"""
Build docs/data/neuroglancer.json — everything the site needs to construct
Neuroglancer links in the browser.

A crop's link opens the whole dataset: the EM image plus every annotated crop
in that dataset as its own segmentation layer, with the view centred on the
crop that was clicked. That way one click gives you context, not just a cube.

Two sources are emitted. NRS is the Janelia-internal host and works today, on
VPN. OpenOrganelle's S3 bucket uses an identical path layout — verified against
the live bucket, not assumed — so switching is a change of origin and nothing
else. The migration is not finished, so `s3_ready` records, per dataset,
whether the EM array and the groundtruth crops are actually there yet.

    python scripts/build_neuroglancer.py
"""
from __future__ import annotations

import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ecs.config import CROPS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "neuroglancer.json"

SOURCES = {
    "nrs": {
        "label": "Janelia (NRS)",
        "base": "https://cellmap-vm1.int.janelia.org/nrs/data",
        "note": "Works on the Janelia network or VPN only.",
    },
    "s3": {
        "label": "OpenOrganelle (S3)",
        "base": "https://janelia-cosem-datasets.s3.amazonaws.com",
        "note": "Public, no VPN. Only the datasets already migrated will load.",
    },
}

EM_ARRAY = {
    "jrc_mus-kidney": "fibsem-uint8",   "jrc_mus-kidney-4": "fibsem-uint16",
    "jrc_mus-heart-6": "fibsem-uint16", "jrc_mus-heart-4": "fibsem-uint16",
    "jrc_mus-liver": "fibsem-uint8",    "jrc_mus-liver-8": "fibsem-uint16",
    "jrc_mus-cortex-2": "fibsem-uint16","jrc_mus-cortex-3": "fibsem-int16",
    "jrc_mus-cortex-4": "fibsem-uint16",
}
DATASET_VOXEL_NM = {
    "jrc_mus-kidney": 4, "jrc_mus-kidney-4": 8, "jrc_mus-heart-6": 8,
    "jrc_mus-heart-4": 8, "jrc_mus-liver": 4, "jrc_mus-liver-8": 8,
    "jrc_mus-cortex-2": 8, "jrc_mus-cortex-3": 2, "jrc_mus-cortex-4": 8,
}
# checked against the live bucket on 2026-09-04; rerun the probe in the commit
# message to refresh
S3_READY = {
    "jrc_mus-kidney": True, "jrc_mus-liver": True,
    "jrc_mus-cortex-3": "em-only",
    "jrc_mus-cortex-2": False, "jrc_mus-cortex-4": False,
    "jrc_mus-heart-4": False, "jrc_mus-heart-6": False,
    "jrc_mus-kidney-4": False, "jrc_mus-liver-8": False,
}
EM_SHADER = {"jrc_mus-cortex-3": {"normalized": {"range": [1114, 884],
                                                 "window": [-281, 1395]}}}

# The crop translations in the manifest are written in zarr axis order (z, y, x);
# Neuroglancer positions are (x, y, z). Reversing is the whole difference, and
# getting it wrong sends the viewer to a plausible-looking wrong place, so it is
# named rather than inlined.
MANIFEST_AXIS_ORDER = "zyx"


def main():
    mani = json.loads((ROOT / "docs" / "membranes" / "manifest_inspect.json").read_text())
    if not isinstance(mani, list):
        mani = next(v for v in mani.values() if isinstance(v, list))
    geo = {e["crop"]: e for e in mani}

    ds = {}
    for c in CROPS:
        if not getattr(c, "active", True):
            continue
        d = ds.setdefault(c.dataset, {"crops": [], "em": EM_ARRAY.get(c.dataset),
                                      "voxel_nm": DATASET_VOXEL_NM.get(c.dataset),
                                      "s3_ready": S3_READY.get(c.dataset, False),
                                      "shader": EM_SHADER.get(c.dataset)})
        d["crops"].append(c.crop)
    for d in ds.values():
        d["crops"].sort()

    pos = {}
    for crop, e in geo.items():
        t, shp, pv = e.get("translation_nm"), e.get("crop_shape_vox"), e.get("voxel_nm")
        if not (t and shp and pv):
            continue
        centre_nm = [t[i] + shp[i] * pv / 2.0 for i in range(3)]
        if MANIFEST_AXIS_ORDER == "zyx":
            centre_nm = list(reversed(centre_nm))          # -> x, y, z
        pos[crop] = [round(v, 1) for v in centre_nm]

    doc = {"sources": SOURCES, "datasets": ds, "centre_nm": pos,
           "crop_dataset": {c.crop: c.dataset for c in CROPS if getattr(c, "active", True)},
           "axis_note": "centre_nm is x, y, z in nanometres"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    ready = sum(1 for v in S3_READY.values() if v is True)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(ds)} datasets, "
          f"{len(pos)} crop centres, {ready}/{len(ds)} datasets live on S3")


if __name__ == "__main__":
    main()
