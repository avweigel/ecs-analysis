#!/usr/bin/env python3
"""Load spreadsheets of annotations back into a Neuroglancer link.

The reverse of ng_lines_to_csv.py: give it the CSV files that script (or the
site's Annotations page) wrote -- edited or not -- and it prints a Neuroglancer
link that opens with those annotations. Each file's type is read from its
column names, so lines, points, boxes, ellipsoids and polylines can be
loaded together. Coordinates are in nanometres, as exported.

What the annotations are shown on:
    default      the view saved in the spreadsheet's "neuroglancer url" column
    --base LINK  another Neuroglancer link (or a file holding one, or JSON state)
    --dataset X  one of this study's datasets, e.g. jrc_mus-kidney-4
    --bare       nothing else: the annotations on their own

If that view already has an annotation layer with the same name as the
spreadsheet's "layer" column, the loaded types replace that layer's
annotations of the same type, and everything else about the layer stays: its
other annotation types, linked segmentation layer, properties and colours.
Otherwise a new annotation layer is added.

Usage (from the repo root):
    python3 scripts/ng_csv_to_link.py out.csv out_points.csv
    python3 scripts/ng_csv_to_link.py out.csv --dataset jrc_mus-kidney-4
    python3 scripts/ng_csv_to_link.py out.csv | pbcopy        # link onto the clipboard (macOS)

The link is printed on its own; what was loaded is reported on stderr. The
same thing runs in the browser on the site's ng-lines.html page and builds
the same view; keep the two in step.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ng_lines_to_csv import AXES, HEAD, SHAPE_COLUMNS, TAIL, TYPES, load_state, nm_per_unit

ROOT = Path(__file__).resolve().parent.parent
NG_HOST = "https://neuroglancer-demo.appspot.com/"
NM_SPACE = {a: [1e-9, "m"] for a in AXES}

# The columns a file must have to be read as each type, checked in this order
# (a polyline file also has the point columns, so it is tried first).
REQUIRED = {
    "line": [f"start {a} (nm)" for a in AXES] + [f"end {a} (nm)" for a in AXES],
    "axis_aligned_bounding_box": [f"min {a} (nm)" for a in AXES] + [f"max {a} (nm)" for a in AXES],
    "ellipsoid": [f"center {a} (nm)" for a in AXES] + [f"radius {a} (nm)" for a in AXES],
    "polyline": ["vertex"] + [f"{a} (nm)" for a in AXES],
    "point": [f"{a} (nm)" for a in AXES],
}
# Neuroglancer's field for each coordinate group, per type
FIELDS = {
    "line": (("pointA", "start "), ("pointB", "end ")),
    "point": (("point", ""),),
    "axis_aligned_bounding_box": (("pointA", "min "), ("pointB", "max ")),
    "ellipsoid": (("center", "center "), ("radii", "radius ")),
}
NUMERIC_PROPS = {"uint8", "int8", "uint16", "int16", "uint32", "int32", "float32"}


def fail(msg: str):
    sys.exit(msg)


def kind_of(columns: list[str]) -> str | None:
    cols = set(columns)
    return next((k for k, req in REQUIRED.items() if set(req) <= cols), None)


def number(row: dict, col: str, where: str) -> float:
    v = (row.get(col) or "").strip()
    try:
        return float(v)
    except ValueError:
        fail(f"{where}: {col!r} is {v!r}, which is not a number")


def read_files(paths: list[str]) -> tuple[list[dict], list[str], list[str]]:
    """Return (records, links, unread columns). A record is one annotation:
    kind, layer, id, coords {field: [z, y, x] nm}, description, segments, extra."""
    records, links, unread = [], [], []
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:   # -sig: Excel's byte-order mark
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            kind = kind_of(cols)
            if not kind:
                fail(f"{path}: these columns are not an exported annotation file: {cols}")
            known = set(HEAD + SHAPE_COLUMNS[kind] + TAIL)
            extra_cols = [c for c in cols if c not in known]
            polylines: dict = {}
            open_key, unnamed = None, 0
            for n, row in enumerate(reader, 2):        # line 1 is the header
                row.pop(None, None)                    # fields beyond the header, e.g. trailing commas
                if not any((v or "").strip() for v in row.values()):
                    continue                           # a blank row left by a spreadsheet
                where = f"{path}, row {n}"
                if (row.get("neuroglancer url") or "").strip():
                    links.append(row["neuroglancer url"].strip())
                segs = [s.strip() for s in (row.get("segments") or "").split(";") if s.strip()]
                rec = {"kind": kind, "layer": (row.get("layer") or "").strip() or "annotations",
                       "id": (row.get("id") or "").strip(),
                       "description": row.get("description") or "", "segments": segs,
                       "extra": {c: row.get(c) or "" for c in extra_cols}}
                if kind == "polyline":
                    p = [number(row, f"{a} (nm)", where) for a in AXES]
                    v = number(row, "vertex", where)
                    # rows of one polyline share an id; without ids, vertex 1 starts a new one
                    if rec["id"]:
                        key = (rec["layer"], rec["id"])
                    else:
                        if v == 1 or open_key is None:
                            unnamed += 1
                            open_key = (rec["layer"], None, unnamed)
                        key = open_key
                    if key not in polylines:
                        rec["coords"] = {"points": []}
                        polylines[key] = rec
                        records.append(rec)
                    polylines[key]["coords"]["points"].append((v, p))
                else:
                    rec["coords"] = {fld: [number(row, f"{pre}{a} (nm)", where) for a in AXES]
                                     for fld, pre in FIELDS[kind]}
                    records.append(rec)
            unread += [c for c in extra_cols if c not in unread]
    for rec in records:      # vertices in order of their number, then drop the number
        if rec["kind"] == "polyline":
            rec["coords"]["points"] = [p for _, p in sorted(rec["coords"]["points"], key=lambda t: t[0])]
    return records, links, unread


def dataset_state(name: str) -> dict:
    """A view of one of this study's datasets: the EM and every crop's labels."""
    ng = json.loads((ROOT / "docs" / "data" / "neuroglancer.json").read_text())
    d = ng["datasets"].get(name)
    if not d:
        fail(f"No dataset {name!r}. Choose one of: {', '.join(sorted(ng['datasets']))}")
    base = ng["sources"]["s3" if d.get("s3_ready") else "nrs"]["base"]
    root = f"zarr://{base}/{name}/{name}.zarr/recon-1"
    em = {"type": "image", "source": f"{root}/em/{d['em']}", "name": "em"}
    if d.get("shader"):
        em["shaderControls"] = d["shader"]
    layers = [em] + [{"type": "segmentation", "source": f"{root}/labels/groundtruth/{c}/all",
                      "name": c, "visible": True} for c in d["crops"]]
    v = d.get("voxel_nm") or 8
    return {"dimensions": {a: [v * 1e-9, "m"] for a in "xyz"}, "layers": layers, "layout": "4panel"}


def prop_value(text: str, prop: dict):
    if not text.strip():
        return prop.get("default", 0 if prop.get("type") in NUMERIC_PROPS else "")
    if prop.get("type") in NUMERIC_PROPS:
        x = float(text)
        return x if prop["type"] == "float32" else int(math.floor(x + 0.5))
    return text


def to_layer_units(p: list[float], axes: list[tuple[str, float]], radius: bool = False) -> list[float]:
    """[z, y, x] in nm -> the layer's own axes and units. An axis other than
    z, y, x (time, channel) gets 0; radii are kept positive."""
    nm = dict(zip(AXES, p))
    out = []
    for a, s in axes:
        v = nm[a] / s if a in nm else 0.0
        out.append(abs(v) if radius else v)
    return out


def build(records: list[dict], state: dict) -> tuple[dict, list[str], set]:
    """Put the records into `state` (changed in place).
    Returns (state, notes, the extra columns that were restored as properties)."""
    notes, used_cols = [], set()
    layers = state.setdefault("layers", [])
    order = list(dict.fromkeys(r["layer"] for r in records))
    for name in order:
        recs = [r for r in records if r["layer"] == name]
        kinds = {r["kind"] for r in recs}
        layer = next((l for l in layers if l.get("type") == "annotation" and l.get("name") == name
                      and isinstance(l.get("annotations"), list)), None)
        if layer is not None:
            src = layer.get("source")
            dims = (src.get("transform") or {}).get("outputDimensions") if isinstance(src, dict) else None
            dims = dims or state.get("dimensions") or NM_SPACE
            kept = [a for a in layer["annotations"] if a.get("type") not in kinds]
            words = ", ".join(TYPES[k][2] for k in TYPES if k in kinds)
            notes.append(f"layer {name!r}: replaced its {words}"
                         + (f", kept {len(kept)} other annotation{'' if len(kept) == 1 else 's'}"
                            if kept else ""))
        else:
            layer = {"type": "annotation", "name": name,
                     "source": {"url": "local://annotations", "transform": {"outputDimensions": NM_SPACE}},
                     "tab": "annotations", "annotations": []}
            layers.append(layer)
            dims, kept = NM_SPACE, []
            notes.append(f"layer {name!r}: new")
        axes = nm_per_unit(dims)
        props = layer.get("annotationProperties") or []
        used = {str(a.get("id")) for a in kept}
        anns = []
        for i, r in enumerate(recs, 1):
            ann = {"type": r["kind"]}
            if r["kind"] == "polyline":
                ann["points"] = [to_layer_units(p, axes) for p in r["coords"]["points"]]
            else:
                for fld, val in r["coords"].items():
                    ann[fld] = to_layer_units(val, axes, radius=(fld == "radii"))
                if r["kind"] == "axis_aligned_bounding_box":   # min and max, in layer order
                    a, b = ann["pointA"], ann["pointB"]
                    ann["pointA"], ann["pointB"] = [min(x, y) for x, y in zip(a, b)], [max(x, y) for x, y in zip(a, b)]
            # ids must be unique in a layer; a missing or repeated one gets a numbered id
            aid = r["id"] or f"{r['kind']}-{i}"
            while aid in used:
                aid += "+"
            used.add(aid)
            ann["id"] = aid
            if r["description"]:
                ann["description"] = r["description"]
            if r["segments"]:
                ann["segments"] = [r["segments"]]
            if props:
                base = HEAD + SHAPE_COLUMNS[r["kind"]] + TAIL
                ann["props"] = []
                for j, p in enumerate(props):
                    pid = str(p.get("id", f"property {j + 1}"))
                    col = pid if pid not in base else f"{pid} (property)"
                    if col in r["extra"]:
                        used_cols.add(col)
                    ann["props"].append(prop_value(r["extra"].get(col, ""), p))
            anns.append(ann)
        layer["annotations"] = kept + anns
    return state, notes, used_cols


def centre(records: list[dict]) -> dict:
    """The middle of everything loaded, in nm per axis."""
    pts = []
    for r in records:
        for fld, val in r["coords"].items():
            if fld == "points":
                pts += val
            elif fld != "radii":
                pts.append(val)
    return {a: (min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i, a in enumerate(AXES)}


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n\n".join(__doc__.split("\n\n")[1:]))
    ap.add_argument("files", nargs="+", help="CSV files written by ng_lines_to_csv.py or the site")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--base", help="show the annotations on this Neuroglancer link (or file, or JSON)")
    g.add_argument("--dataset", help="show them on one of this study's datasets")
    g.add_argument("--bare", action="store_true", help="show the annotations on their own")
    args = ap.parse_args(argv[1:])

    records, links, unread = read_files(args.files)
    if not records:
        fail("Those files have no annotations in them.")
    host, keep_view = NG_HOST, True
    if args.base:
        state, link = load_state(args.base)
        on = "the link given"
    elif args.dataset:
        state, link, keep_view = dataset_state(args.dataset), "", False
        on = f"dataset {args.dataset}"
    elif links and not args.bare:
        state, link = load_state(links[0])
        on = "the view saved in the spreadsheet"
        if len(set(links)) > 1:
            on += " (the first of several links in the files)"
    else:
        state, link, keep_view = {"dimensions": dict(NM_SPACE), "layers": [], "layout": "4panel"}, "", False
        on = "nothing else (no link in the spreadsheet)" if not args.bare else "nothing else"
    if link and "#!" in link:
        host = link.split("#!", 1)[0]

    state, notes, used_cols = build(records, state)
    unread = [c for c in unread if c not in used_cols]
    if not keep_view:   # a fresh view: centre it on the annotations
        c = centre(records)
        state["position"] = [c[a] / s if a in c else 0.0 for a, s in nm_per_unit(state["dimensions"])]
        state["selectedLayer"] = {"layer": records[0]["layer"], "visible": True}

    counts = {k: sum(r["kind"] == k for r in records) for k in TYPES}
    loaded = ", ".join(f"{n} {TYPES[k][1] if n == 1 else TYPES[k][2]}" for k, n in counts.items() if n)
    print(f"{loaded}, shown on {on}", file=sys.stderr)
    for note in notes:
        print(f"  {note}", file=sys.stderr)
    if unread:
        print(f"  not loaded (no matching property in the layer): {', '.join(unread)}", file=sys.stderr)
    print(host + "#!" + quote(json.dumps(state, separators=(",", ":")), safe=""))


if __name__ == "__main__":
    main(sys.argv)
