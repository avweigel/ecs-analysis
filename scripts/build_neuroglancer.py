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
else. `s3_ready` records, per dataset, whether the EM array and the
groundtruth crops are actually there, so a link only points at the bucket when
it will load.

    python scripts/build_neuroglancer.py
"""
from __future__ import annotations

import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ecs.config import CROPS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "neuroglancer.json"

# Change this one line to move to a different bucket; nothing else depends on it.
PUBLIC_S3_BASE = "https://janelia-cosem-datasets.s3.amazonaws.com"

SOURCES = {
    "nrs": {
        "label": "Janelia (NRS)",
        "base": "https://cellmap-vm1.int.janelia.org/nrs/data",
        "note": "Works on the Janelia network or VPN only.",
    },
    # Public object store. The path layout below the bucket is identical to NRS,
    # so pointing at a different bucket is a change of this one string and
    # nothing else — which matters if the data should sit in object storage
    # without appearing in the OpenOrganelle portal, since this bucket is the
    # portal's own.
    "s3": {
        "label": "Public S3",
        "base": PUBLIC_S3_BASE,
        "note": "Public, no VPN. Only the datasets already uploaded will load.",
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
# Which datasets can actually be served from the public bucket. "Ready" means
# the EM array AND every crop this study uses are present -- not merely that the
# dataset exists there. jrc_mus-liver is the reason that distinction is spelled
# out: before this study's crops were uploaded, the bucket held 24 crops for it
# from an older series, so going by dataset presence alone would have produced
# links that 404. Refresh with:  python scripts/build_neuroglancer.py --probe
S3_READY_CACHE = ROOT / "results" / "s3_availability.json"
# Contrast for the EM layer: the `normalized` control of Neuroglancer's default
# image shader. The uint16 volumes sit in a narrow band of the 16-bit range, so
# each gets its own.
EM_SHADER = {
    "jrc_mus-kidney-4": {"normalized": {"range": [34379, 35844]}},
    "jrc_mus-heart-6":  {"normalized": {"range": [30558, 34972]}},
    "jrc_mus-heart-4":  {"normalized": {"range": [37825, 38319]}},
    "jrc_mus-liver-8":  {"normalized": {"range": [35023, 36079]}},
    "jrc_mus-cortex-2": {"normalized": {"range": [34738, 35855]}},
    "jrc_mus-cortex-3": {"normalized": {"range": [1114, 884],
                                        "window": [-281, 1395]}},
    "jrc_mus-cortex-4": {"normalized": {"range": [34502, 35462]}},
}

# The crop translations in the manifest are written in zarr axis order (z, y, x);
# Neuroglancer positions are (x, y, z). Reversing is the whole difference, and
# getting it wrong sends the viewer to a plausible-looking wrong place, so it is
# named rather than inlined.
MANIFEST_AXIS_ORDER = "zyx"


def probe_s3(ds_crops: dict) -> dict:
    """Ask the bucket what is really there: the EM array, and each study crop.

    A node is there when its zarr metadata is: `zarr.json` for zarr v3, which is
    how most of the bucket is now stored, or `.zattrs` for v2. Any key under the
    prefix is not enough -- chunks uploaded without their metadata would pass,
    and Neuroglancer cannot open those.
    """
    import urllib.error, urllib.request
    base = SOURCES["s3"]["base"]

    def zarr_format(node: str) -> int | None:
        for fmt, doc in ((3, "zarr.json"), (2, ".zattrs")):
            req = urllib.request.Request(f"{base}/{node}/{doc}", method="HEAD")
            try:
                with urllib.request.urlopen(req, timeout=25):
                    return fmt
            except urllib.error.HTTPError as e:
                # 403/404 is the bucket saying no. Anything else -- a timeout, a
                # 5xx -- says nothing about the bucket, and recording it as absent
                # would quietly send a public link back to the VPN, so stop.
                if e.code not in (403, 404):
                    raise
        return None

    out = {}
    for ds, info in sorted(ds_crops.items()):
        root = f"{ds}/{ds}.zarr/recon-1"
        em = zarr_format(f"{root}/em/{info['em']}")
        # the layer a link opens is the crop's `all` array, so that is what must exist
        crops = {c: zarr_format(f"{root}/labels/groundtruth/{c}/all")
                 for c in info["crops"]}
        missing = [c for c, f in crops.items() if f is None]
        out[ds] = {"em": em is not None, "missing_crops": missing,
                   "zarr_format": {"em": em,
                                   "crops": sorted({f for f in crops.values() if f})},
                   "ready": bool(em and not missing)}
        found = sorted({f for f in (em, *crops.values()) if f})
        state = "ready" if out[ds]["ready"] else (
            "em only" if em else "absent")
        print(f"  {ds:20s} {state}"
              + (f", {len(missing)} crop(s) missing" if em and missing else "")
              + (f"  (zarr v{'+v'.join(map(str, found))})" if found else ""))
    return out


def load_s3_cache() -> dict:
    if S3_READY_CACHE.exists():
        return json.loads(S3_READY_CACHE.read_text())
    return {}


def main():
    mani = json.loads((ROOT / "docs" / "membranes" / "manifest_inspect.json").read_text())
    if not isinstance(mani, list):
        mani = next(v for v in mani.values() if isinstance(v, list))
    geo = {e["crop"]: e for e in mani}

    # Layers are the crops this study actually analysed -- not every crop that
    # happens to exist in the volume. `active` in the config is a looser set: it
    # still contains crops excluded from the analysis.
    import csv as _csv
    study = {r["crop"] for r in _csv.DictReader(
        (ROOT / "results" / "all_metrics_wide.csv").open()) if r["run"] == "native"}

    ds = {}
    for c in CROPS:
        if c.crop not in study:
            continue
        d = ds.setdefault(c.dataset, {"crops": [], "em": EM_ARRAY.get(c.dataset),
                                      "voxel_nm": DATASET_VOXEL_NM.get(c.dataset),
                                      "shader": EM_SHADER.get(c.dataset)})
        d["crops"].append(c.crop)
    for d in ds.values():
        d["crops"].sort()

    if "--probe" in sys.argv:
        print("probing the public bucket…")
        avail = probe_s3(ds)
        S3_READY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        S3_READY_CACHE.write_text(json.dumps(avail, indent=1))
    else:
        avail = load_s3_cache()
    for name, d in ds.items():
        a = avail.get(name, {})
        d["s3_ready"] = bool(a.get("ready"))
        d["s3_note"] = ("public" if a.get("ready")
                        else "image only, crops not migrated" if a.get("em")
                        else "not on the public bucket yet")

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
    ready = sum(1 for d in ds.values() if d["s3_ready"])
    layered = sum(len(d["crops"]) for d in ds.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {len(ds)} datasets, {layered} study crops, "
          f"{len(pos)} centres, {ready}/{len(ds)} datasets servable from S3")


if __name__ == "__main__":
    main()
