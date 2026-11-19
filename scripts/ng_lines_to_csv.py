#!/usr/bin/env python3
"""Export the annotations in a Neuroglancer link to CSV, one file per type.

Every annotation type Neuroglancer has is read: lines, points, bounding
boxes, ellipsoids and polylines. Coordinates are converted to nanometres
using the layer's coordinate space.

    lines        out.csv             start z/y/x, end z/y/x, length
    points       out_points.csv      z/y/x
    boxes        out_boxes.csv       min z/y/x, max z/y/x, size z/y/x
    ellipsoids   out_ellipsoids.csv  center z/y/x, radius z/y/x
    polylines    out_polylines.csv   one row per vertex: vertex, z/y/x,
                                     distance along the polyline

All in nm. Every file starts with layer and id, ends with segments (the
linked segment IDs), neuroglancer url, description and one column per
annotation property the layer defines. The lines file keeps the column names
annotation-processing-utils (github.com/davidackerman/annotation-processing-utils)
reads: "start z (nm)" ... "end x (nm)" and "neuroglancer url". A file is
only written for a type the link contains.

Standard library only: the link's state is decoded directly, so the
neuroglancer package is not needed. The same export runs in the browser on
the site's ng-lines.html page (built by scripts/build_ng_lines_page.py) and
writes the same files; keep the two in step.

Usage (from the repo root):
    pbpaste | python3 scripts/ng_lines_to_csv.py - out.csv      # link copied to the clipboard (macOS)
    python3 scripts/ng_lines_to_csv.py '<neuroglancer link>' out.csv
    python3 scripts/ng_lines_to_csv.py link.txt out.csv     # link saved in a file
    python3 scripts/ng_lines_to_csv.py state.json out.csv   # JSON state (Neuroglancer's {} button)

Put a pasted link in single quotes. Links contain "#!", and zsh and bash
treat "!" inside double quotes (or no quotes) as history expansion, so the
command fails with "no such event" before the script runs.

Only local annotation layers (annotations stored in the link) are read, not
annotations served from a separate annotation source.
"""
import csv
import json
import math
import sys
from pathlib import Path
from urllib.parse import unquote

AXES = ("z", "y", "x")
UNIT_TO_NM = {"m": 1e9, "mm": 1e6, "um": 1e3, "µm": 1e3, "nm": 1.0}

# Neuroglancer's type name -> (suffix of its file, singular, plural), in the
# order files are written. Lines write to the output path itself.
TYPES = {
    "line": ("", "line", "lines"),
    "point": ("points", "point", "points"),
    "axis_aligned_bounding_box": ("boxes", "box", "boxes"),
    "ellipsoid": ("ellipsoids", "ellipsoid", "ellipsoids"),
    "polyline": ("polylines", "polyline", "polylines"),
}
# the columns each type adds between "id" and "segments"
SHAPE_COLUMNS = {
    "line": [f"start {a} (nm)" for a in AXES] + [f"end {a} (nm)" for a in AXES] + ["length (nm)"],
    "point": [f"{a} (nm)" for a in AXES],
    "axis_aligned_bounding_box": ([f"min {a} (nm)" for a in AXES] + [f"max {a} (nm)" for a in AXES]
                                  + [f"size {a} (nm)" for a in AXES]),
    "ellipsoid": [f"center {a} (nm)" for a in AXES] + [f"radius {a} (nm)" for a in AXES],
    "polyline": ["vertex"] + [f"{a} (nm)" for a in AXES] + ["distance along (nm)"],
}
HEAD = ["layer", "id"]
TAIL = ["segments", "neuroglancer url", "description"]


def load_state(src: str) -> tuple[dict, str]:
    """Return (state dict, link) from a link, a file holding a link, a JSON file,
    or "-" for standard input."""
    text = src
    if src == "-":
        text = sys.stdin.read().strip()
    elif not src.startswith("http") and Path(src).exists():
        text = Path(src).read_text().strip()
    if text.startswith("{"):
        return _parse(text), ""
    if "#!" not in text:
        sys.exit("No '#!' state in that link. Copy the full address from Neuroglancer.")
    frag = unquote(text.split("#!", 1)[1])
    if frag.startswith(("http://", "https://", "gs://", "s3://")):
        sys.exit(f"This link points at a saved state ({frag[:80]}) instead of carrying it. "
                 "Open it in Neuroglancer and copy the JSON with the { } button.")
    return _parse(frag), text


def _parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        sys.exit("The link's state is not valid JSON. Was the whole address copied?")


def nm_per_unit(dims: dict) -> list[tuple[str, float]]:
    """Neuroglancer dimensions {"z": [8e-9, "m"], ...} -> [(axis, nm per unit), ...] in order."""
    out = []
    for name, (scale, unit) in dims.items():
        if unit not in UNIT_TO_NM:
            sys.exit(f"Unsupported unit {unit!r} on axis {name!r}")
        out.append((name, float(scale) * UNIT_TO_NM[unit]))
    return out


# Every value is turned into its CSV text here, so the browser page can match
# it exactly: nanometres rounded to 0.001 and written as Python writes a float.
def nm(v: float) -> str:
    return repr(round(v, 3))


def prop_text(v) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return repr(float(v))
    return "" if v is None else str(v)


def dist(a: dict, b: dict) -> float:
    # written out, not math.dist, so the page can repeat the same arithmetic
    dz, dy, dx = (b[k] - a[k] for k in AXES)
    return math.sqrt(dz * dz + dy * dy + dx * dx)


def extract(state: dict, link: str = "") -> tuple[dict, int]:
    """Return ({type: {"columns": [...], "rows": [row dict, ...]}}, skipped).
    Only types the link contains are present; `skipped` counts annotations of
    a type this script does not know."""
    tables = {t: {"columns": None, "rows": [], "props": []} for t in TYPES}
    skipped = 0
    global_dims = state.get("dimensions")
    for layer in state.get("layers", []):
        if layer.get("type") != "annotation" or "annotations" not in layer:
            continue
        name = layer.get("name", "")
        src = layer.get("source")
        dims = global_dims
        if isinstance(src, dict):
            dims = (src.get("transform") or {}).get("outputDimensions") or dims
        if not dims:
            sys.exit(f"Layer {name!r}: no coordinate space found")
        axes = nm_per_unit(dims)
        missing = set(AXES) - {a for a, _ in axes}
        if missing:
            sys.exit(f"Layer {name!r}: missing axes {sorted(missing)}")
        props = layer.get("annotationProperties") or []

        def field(ann, key):
            if key not in ann:
                sys.exit(f"Layer {name!r}: annotation {ann.get('id', '?')!r} has no {key!r}")
            return ann[key]

        def point(p):
            return {ax: float(v) * s for (ax, s), v in zip(axes, p)}

        for ann in layer["annotations"]:
            kind = ann.get("type")
            if kind not in TYPES:
                skipped += 1
                continue
            segs = []
            for group in ann.get("segments", []):
                # current Neuroglancer writes one list per linked layer; older links a flat list
                segs.extend([group] if isinstance(group, str) else group)
            tail = {"segments": ";".join(map(str, segs)), "neuroglancer url": link,
                    "description": str(ann.get("description") or "")}
            # one column per property; an id that repeats a column name gets
            # " (property)" added so it cannot overwrite that column
            base = HEAD + SHAPE_COLUMNS[kind] + TAIL
            values = ann.get("props") or []
            extra = {}
            for i, p in enumerate(props):
                pid = str(p.get("id", f"property {i + 1}"))
                extra[pid if pid not in base else f"{pid} (property)"] = prop_text(
                    values[i] if i < len(values) else p.get("default"))
            head = {"layer": name, "id": str(ann.get("id", ""))}

            shapes = []
            if kind == "line":
                a, b = point(field(ann, "pointA")), point(field(ann, "pointB"))
                s = {f"start {k} (nm)": nm(a[k]) for k in AXES}
                s.update({f"end {k} (nm)": nm(b[k]) for k in AXES})
                s["length (nm)"] = nm(dist(a, b))
                shapes.append(s)
            elif kind == "point":
                p = point(field(ann, "point"))
                shapes.append({f"{k} (nm)": nm(p[k]) for k in AXES})
            elif kind == "axis_aligned_bounding_box":
                a, b = point(field(ann, "pointA")), point(field(ann, "pointB"))
                s = {f"min {k} (nm)": nm(min(a[k], b[k])) for k in AXES}
                s.update({f"max {k} (nm)": nm(max(a[k], b[k])) for k in AXES})
                s.update({f"size {k} (nm)": nm(abs(b[k] - a[k])) for k in AXES})
                shapes.append(s)
            elif kind == "ellipsoid":
                c, r = point(field(ann, "center")), point(field(ann, "radii"))
                s = {f"center {k} (nm)": nm(c[k]) for k in AXES}
                s.update({f"radius {k} (nm)": nm(abs(r[k])) for k in AXES})
                shapes.append(s)
            elif kind == "polyline":
                along, prev = 0.0, None
                for i, raw in enumerate(field(ann, "points"), 1):
                    p = point(raw)
                    if prev is not None:
                        along += dist(prev, p)
                    prev = p
                    shapes.append({"vertex": str(i), **{f"{k} (nm)": nm(p[k]) for k in AXES},
                                   "distance along (nm)": nm(along)})

            t = tables[kind]
            t["props"] += [k for k in extra if k not in t["props"]]
            t["rows"].extend({**head, **s, **tail, **extra} for s in shapes)

    # property columns are the union over the layers that hold this type
    return ({kind: {"columns": HEAD + SHAPE_COLUMNS[kind] + TAIL + t["props"], "rows": t["rows"]}
             for kind, t in tables.items() if t["rows"]}, skipped)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, restval="")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        sys.exit(__doc__)
    state, link = load_state(argv[1])
    tables, skipped = extract(state, link)
    if not tables:
        sys.exit("No annotations found in local annotation layers.")
    out = Path(argv[2])
    for kind, (suffix, one, many) in TYPES.items():
        if kind not in tables:
            continue
        path = out if not suffix else out.with_name(f"{out.stem}_{suffix}{out.suffix or '.csv'}")
        write_csv(path, tables[kind]["columns"], tables[kind]["rows"])
        rows = tables[kind]["rows"]   # a polyline is one row per vertex
        n = len({(r["layer"], r["id"]) for r in rows}) if kind == "polyline" else len(rows)
        print(f"{n} {one if n == 1 else many} -> {path}")
    if "line" not in tables:
        print(f"(no lines, so {out} was not written)")
    if skipped:
        print(f"({skipped} annotation{'' if skipped == 1 else 's'} of an unknown type skipped)")


if __name__ == "__main__":
    main(sys.argv)
