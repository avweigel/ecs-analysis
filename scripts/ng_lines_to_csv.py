#!/usr/bin/env python3
"""Export line annotations from a Neuroglancer link to CSV.

The CSV uses the column names that annotation-processing-utils
(github.com/davidackerman/annotation-processing-utils) reads:
"start z (nm)", "start y (nm)", "start x (nm)", "end z (nm)", "end y (nm)",
"end x (nm)", plus "neuroglancer url". Extra columns: layer, id,
"length (nm)" and the linked segment IDs.

Standard library only: the link's state is decoded directly, so the
neuroglancer package is not needed.

Usage:
    python scripts/ng_lines_to_csv.py "<neuroglancer link>" out.csv
    python scripts/ng_lines_to_csv.py link.txt out.csv     # link saved in a file
    python scripts/ng_lines_to_csv.py state.json out.csv   # JSON state (Neuroglancer's {} button)

Only local annotation layers (annotations stored in the link) are read.
Points and other annotation types are skipped and counted.
"""
import csv
import json
import math
import sys
from pathlib import Path
from urllib.parse import unquote

AXES = ("z", "y", "x")
UNIT_TO_NM = {"m": 1e9, "mm": 1e6, "um": 1e3, "µm": 1e3, "nm": 1.0}


def load_state(src: str) -> tuple[dict, str]:
    """Return (state dict, link) from a link, a file holding a link, or a JSON file."""
    text = src
    if not src.startswith("http") and Path(src).exists():
        text = Path(src).read_text().strip()
    if text.startswith("{"):
        return json.loads(text), ""
    if "#!" not in text:
        sys.exit("No '#!' state in that link. Copy the full address from Neuroglancer.")
    frag = text.split("#!", 1)[1]
    return json.loads(unquote(frag)), text


def nm_per_unit(dims: dict) -> list[tuple[str, float]]:
    """Neuroglancer dimensions {"z": [8e-9, "m"], ...} -> [(axis, nm per unit), ...] in order."""
    out = []
    for name, (scale, unit) in dims.items():
        if unit not in UNIT_TO_NM:
            sys.exit(f"Unsupported unit {unit!r} on axis {name!r}")
        out.append((name, float(scale) * UNIT_TO_NM[unit]))
    return out


def extract(state: dict, link: str = "") -> tuple[list[dict], int]:
    rows, skipped = [], 0
    global_dims = state.get("dimensions")
    for layer in state.get("layers", []):
        if layer.get("type") != "annotation" or "annotations" not in layer:
            continue
        src = layer.get("source")
        dims = global_dims
        if isinstance(src, dict):
            dims = (src.get("transform") or {}).get("outputDimensions") or dims
        if not dims:
            sys.exit(f"Layer {layer.get('name')!r}: no coordinate space found")
        axes = nm_per_unit(dims)
        missing = set(AXES) - {a for a, _ in axes}
        if missing:
            sys.exit(f"Layer {layer.get('name')!r}: missing axes {sorted(missing)}")
        for ann in layer["annotations"]:
            if ann.get("type") != "line":
                skipped += 1
                continue
            a = {ax: float(v) * s for (ax, s), v in zip(axes, ann["pointA"])}
            b = {ax: float(v) * s for (ax, s), v in zip(axes, ann["pointB"])}
            row = {"layer": layer.get("name", ""), "id": ann.get("id", "")}
            row.update({f"start {ax} (nm)": round(a[ax], 3) for ax in AXES})
            row.update({f"end {ax} (nm)": round(b[ax], 3) for ax in AXES})
            row["length (nm)"] = round(math.dist([a[k] for k in AXES], [b[k] for k in AXES]), 3)
            segs = [s for group in ann.get("segments", []) for s in group]
            row["segments"] = ";".join(map(str, segs))
            row["neuroglancer url"] = link
            rows.append(row)
    return rows, skipped


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        sys.exit(__doc__)
    state, link = load_state(argv[1])
    rows, skipped = extract(state, link)
    if not rows:
        sys.exit("No line annotations found in local annotation layers.")
    with open(argv[2], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    msg = f"{len(rows)} lines -> {argv[2]}"
    if skipped:
        msg += f" ({skipped} non-line annotations skipped)"
    print(msg)


if __name__ == "__main__":
    main(sys.argv)
