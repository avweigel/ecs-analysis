"""Plot cell-cell contact distance mapping by prep type."""
import matplotlib
matplotlib.use("Agg")
import csv
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os

base_dir = os.path.dirname(__file__)
csv_path = os.path.join(base_dir, "cell_contacts.csv")

tissues = ["Kidney", "Heart", "Liver", "Cortex"]
CHEM_COLOR = "#4C72B0"
HPF_COLOR = "#DD8452"
THRESHOLDS = [10, 20, 40, 80, 160, 320]
legend_handles = [Patch(facecolor=CHEM_COLOR, alpha=0.7, label="Chemical"),
                  Patch(facecolor=HPF_COLOR, alpha=0.7, label="Rapid HPF")]

# Load data
rows_by_tp = {}  # {(tissue, prep): [row_dict, ...]}
gap_median_by_tp = {}  # {(tissue, prep): [gap_median_nm, ...]}

with open(csv_path) as f:
    for row in csv.DictReader(f):
        if row["status"] != "OK" or not row["gap_median_nm"]:
            continue
        tissue = row["tissue"]
        prep = row["prep"]
        rows_by_tp.setdefault((tissue, prep), []).append(row)
        gap_median_by_tp.setdefault((tissue, prep), []).append(
            float(row["gap_median_nm"]))

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

# --- Top left: Gap median box plot by tissue ---
ax = axes[0, 0]
positions, colors, box_data = [], [], []
tick_positions, tick_labels = [], []
pos = 0
for tissue in tissues:
    chem = gap_median_by_tp.get((tissue, "Chemical"), [])
    hpf = gap_median_by_tp.get((tissue, "Rapid HPF"), [])
    has_both = bool(chem) and bool(hpf)
    if chem:
        box_data.append(chem)
        positions.append(pos)
        colors.append(CHEM_COLOR)
    if hpf:
        box_data.append(hpf)
        positions.append(pos + (1 if has_both else 0))
        colors.append(HPF_COLOR)
    mid = pos + (0.5 if has_both else 0)
    tick_positions.append(mid)
    tick_labels.append(tissue)
    pos += (2.5 if has_both else 1.5)

bp = ax.boxplot(box_data, positions=positions, widths=0.7, patch_artist=True,
                showmeans=True, meanline=True,
                meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
for patch, color in zip(bp["boxes"], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
for data, p in zip(box_data, positions):
    ax.scatter([p] * len(data), data, color="black", zorder=3, s=30, alpha=0.7)
ax.set_xticks(tick_positions)
ax.set_xticklabels(tick_labels, fontsize=11)
ax.set_ylabel("Median Cell-Cell Gap (nm)", fontsize=12)
ax.set_title("Median Inter-Cell Gap Width by Tissue and Prep", fontsize=13)
ax.legend(handles=legend_handles, loc="upper right")

# --- Top right: Overall gap comparison ---
ax = axes[0, 1]
chem_all = [v for (t, p), vals in gap_median_by_tp.items() if p == "Chemical" for v in vals]
hpf_all = [v for (t, p), vals in gap_median_by_tp.items() if p == "Rapid HPF" for v in vals]
bp2 = ax.boxplot([chem_all, hpf_all], tick_labels=["Chemical", "Rapid HPF"],
                  patch_artist=True, widths=0.5,
                  showmeans=True, meanline=True,
                  meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
bp2["boxes"][0].set_facecolor(CHEM_COLOR)
bp2["boxes"][0].set_alpha(0.7)
bp2["boxes"][1].set_facecolor(HPF_COLOR)
bp2["boxes"][1].set_alpha(0.7)
for data, x_pos in [(chem_all, 1), (hpf_all, 2)]:
    ax.scatter([x_pos] * len(data), data, color="black", zorder=3, s=30, alpha=0.7)
for i, data in enumerate([chem_all, hpf_all], 1):
    mean = sum(data) / len(data)
    ax.text(i + 0.35, mean, f"mean={mean:.1f}nm\nn={len(data)}", fontsize=9,
            color="red", va="center")
ax.set_ylabel("Median Cell-Cell Gap (nm)", fontsize=12)
ax.set_title("Overall Inter-Cell Gap by Prep", fontsize=13)

# --- Bottom left: Contact fraction curves (mean across crops by tissue+prep) ---
ax = axes[1, 0]
line_styles = {"Chemical": "-", "Rapid HPF": "--"}
markers = {"Chemical": "o", "Rapid HPF": "s"}
tissue_colors = {"Kidney": "#e41a1c", "Heart": "#377eb8",
                 "Liver": "#4daf4a", "Cortex": "#984ea3"}

for tissue in tissues:
    for prep in ["Chemical", "Rapid HPF"]:
        crop_rows = rows_by_tp.get((tissue, prep), [])
        if not crop_rows:
            continue
        mean_fracs = []
        for T in THRESHOLDS:
            fracs = [float(r[f"contact_frac_{T}nm"]) for r in crop_rows]
            mean_fracs.append(np.mean(fracs))
        label = f"{tissue} {prep}"
        ax.plot(THRESHOLDS, mean_fracs, marker=markers[prep],
                linestyle=line_styles[prep], color=tissue_colors[tissue],
                label=label, linewidth=2, markersize=6)

ax.set_xlabel("Distance Threshold (nm)", fontsize=12)
ax.set_ylabel("Fraction of Voronoi Boundary\nwith Gap < Threshold", fontsize=12)
ax.set_title("Cell-Cell Contact Fraction vs Distance Threshold", fontsize=13)
ax.set_xscale("log")
ax.set_xticks(THRESHOLDS)
ax.set_xticklabels([str(t) for t in THRESHOLDS])
ax.legend(fontsize=8, ncol=2)
ax.grid(True, alpha=0.3)

# --- Bottom right: Contact fraction at 40nm and 80nm grouped bars ---
ax = axes[1, 1]
bar_width = 0.35
x = np.arange(len(tissues))
for ref_T, offset, alpha in [(40, -bar_width/2, 0.9), (80, bar_width/2, 0.6)]:
    for i, tissue in enumerate(tissues):
        for prep, color in [("Chemical", CHEM_COLOR), ("Rapid HPF", HPF_COLOR)]:
            crop_rows = rows_by_tp.get((tissue, prep), [])
            if not crop_rows:
                continue
            fracs = [float(r[f"contact_frac_{ref_T}nm"]) for r in crop_rows]
            mean_frac = np.mean(fracs)
            hatch = "" if ref_T == 40 else "///"
            xi = i + offset + (0.08 if prep == "Rapid HPF" else -0.08)
            bar = ax.bar(xi, mean_frac, bar_width * 0.4, color=color,
                         alpha=alpha, hatch=hatch, edgecolor="white")

# Custom legend
from matplotlib.patches import Patch as P
custom = [
    P(facecolor=CHEM_COLOR, alpha=0.9, label="Chemical <40nm"),
    P(facecolor=HPF_COLOR, alpha=0.9, label="HPF <40nm"),
    P(facecolor=CHEM_COLOR, alpha=0.6, hatch="///", label="Chemical <80nm"),
    P(facecolor=HPF_COLOR, alpha=0.6, hatch="///", label="HPF <80nm"),
]
ax.legend(handles=custom, fontsize=8)
ax.set_xticks(x)
ax.set_xticklabels(tissues, fontsize=11)
ax.set_ylabel("Mean Contact Fraction", fontsize=12)
ax.set_title("Contact Fraction at 40nm and 80nm Thresholds", fontsize=13)

plt.tight_layout()
out_path = os.path.join(base_dir, "cell_contacts_by_prep.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved to {out_path}")

# Summary
print("\n=== Median Gap Width Summary ===")
for tissue in tissues:
    for prep in ["Chemical", "Rapid HPF"]:
        vals = gap_median_by_tp.get((tissue, prep), [])
        if vals:
            print(f"  {tissue:8s} {prep:12s}: n={len(vals)}, "
                  f"mean={np.mean(vals):.1f}nm, median={np.median(vals):.1f}nm")

print("\n=== Contact Fraction at Key Thresholds ===")
for T in [20, 40, 80]:
    print(f"\n  Threshold < {T}nm:")
    for tissue in tissues:
        for prep in ["Chemical", "Rapid HPF"]:
            crop_rows = rows_by_tp.get((tissue, prep), [])
            if crop_rows:
                fracs = [float(r[f"contact_frac_{T}nm"]) for r in crop_rows]
                print(f"    {tissue:8s} {prep:12s}: "
                      f"mean={np.mean(fracs)*100:.1f}%, range=[{min(fracs)*100:.1f}-{max(fracs)*100:.1f}%]")
