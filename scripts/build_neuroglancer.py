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
# Which datasets can actually be served from the public bucket. "Ready" means
# the EM array AND every crop this study uses are present -- not merely that the
# dataset exists there. jrc_mus-liver is the reason that distinction is spelled
# out: the bucket holds 24 crops for it, none of which are ours (they are an
# older crop series), so going by dataset presence alone would have produced
# links that 404. Refresh with:  python scripts/build_neuroglancer.py --probe
S3_READY_CACHE = ROOT / "results" / "s3_availability.json"
EM_SHADER = {"jrc_mus-cortex-3": {"normalized": {"range": [1114, 884],
                                                 "window": [-281, 1395]}}}

# The crop translations in the manifest are written in zarr axis order (z, y, x);
# Neuroglancer positions are (x, y, z). Reversing is the whole difference, and
# getting it wrong sends the viewer to a plausible-looking wrong place, so it is
# named rather than inlined.
MANIFEST_AXIS_ORDER = "zyx"


def probe_s3(ds_crops: dict) -> dict:
    """Ask the bucket what is really there: the EM array, and each study crop."""
    import urllib.request, urllib.parse
    base = SOURCES["s3"]["base"]

    def exists(key: str) -> bool:
        url = f"{base}/?list-type=2&prefix={urllib.parse.quote(key)}&max-keys=1"
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return b"<Contents>" in r.read()
        except Exception:
            return False

    out = {}
    for ds, info in sorted(ds_crops.items()):
        em = exists(f"{ds}/{ds}.zarr/recon-1/em/{info['em']}/")
        missing = [c for c in info["crops"]
                   if not exists(f"{ds}/{ds}.zarr/recon-1/labels/groundtruth/{c}/")]
        out[ds] = {"em": em, "missing_crops": missing,
                   "ready": bool(em and not missing)}
        state = "ready" if out[ds]["ready"] else (
            "em only" if em else "absent")
        print(f"  {ds:20s} {state}"
              + (f", {len(missing)} crop(s) missing" if em and missing else ""))
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
