"""Plot ECS half-width (from distance transform) by prep type and tissue."""
import matplotlib
matplotlib.use("Agg")
import csv
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os

csv_path = os.path.join(os.path.dirname(__file__), "ecs_width.csv")

width_by_tp = {}  # {(tissue, prep): [median_half_width, ...]}
all_chem, all_hpf = [], []

with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["status"] != "OK" or not row["median_half_width_nm"]:
            continue
        w = float(row["median_half_width_nm"])
        tissue = row["tissue"]
        prep = row["prep"]
        width_by_tp.setdefault((tissue, prep), []).append(w)
        if prep == "Chemical":
            all_chem.append(w)
        else:
            all_hpf.append(w)

tissues = ["Kidney", "Heart", "Liver", "Cortex"]
CHEM_COLOR = "#4C72B0"
HPF_COLOR = "#DD8452"
legend_handles = [Patch(facecolor=CHEM_COLOR, alpha=0.7, label="Chemical"),
                  Patch(facecolor=HPF_COLOR, alpha=0.7, label="Rapid HPF")]

fig, axes = plt.subplots(1, 3, figsize=(18, 6),
                          gridspec_kw={"width_ratios": [2, 1.2, 1.2]})

# --- Left: Box plot by tissue ---
ax1 = axes[0]
positions, colors, box_data = [], [], []
tick_positions, tick_labels = [], []
pos = 0
for tissue in tissues:
    chem = width_by_tp.get((tissue, "Chemical"), [])
    hpf = width_by_tp.get((tissue, "Rapid HPF"), [])
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

bp = ax1.boxplot(box_data, positions=positions, widths=0.7, patch_artist=True,
                  showmeans=True, meanline=True,
                  meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
for patch, color in zip(bp["boxes"], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
for data, p in zip(box_data, positions):
    ax1.scatter([p] * len(data), data, color="black", zorder=3, s=30, alpha=0.7)
ax1.set_xticks(tick_positions)
ax1.set_xticklabels(tick_labels, fontsize=11)
ax1.set_ylabel("Median ECS Half-Width (nm)", fontsize=12)
ax1.set_title("ECS Channel Width by Tissue and Prep", fontsize=13)
ax1.legend(handles=legend_handles, loc="upper right")

# --- Middle: Overall comparison ---
ax2 = axes[1]
bp2 = ax2.boxplot([all_chem, all_hpf], tick_labels=["Chemical", "Rapid HPF"],
                    patch_artist=True, widths=0.5,
                    showmeans=True, meanline=True,
                    meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
bp2["boxes"][0].set_facecolor(CHEM_COLOR)
bp2["boxes"][0].set_alpha(0.7)
bp2["boxes"][1].set_facecolor(HPF_COLOR)
bp2["boxes"][1].set_alpha(0.7)
for data, x_pos in [(all_chem, 1), (all_hpf, 2)]:
    ax2.scatter([x_pos] * len(data), data, color="black", zorder=3, s=30, alpha=0.7)
for i, data in enumerate([all_chem, all_hpf], 1):
    if data:
        mean = sum(data) / len(data)
        ax2.text(i + 0.35, mean, f"mean={mean:.1f}nm", fontsize=9, color="red", va="center")
ax2.set_ylabel("Median ECS Half-Width (nm)", fontsize=12)
ax2.set_title("Overall ECS Width by Prep", fontsize=13)

# --- Right: Mean width by tissue, grouped bars ---
ax3 = axes[2]
x = range(len(tissues))
bar_width = 0.35
for i, tissue in enumerate(tissues):
    c = width_by_tp.get((tissue, "Chemical"), [])
    h = width_by_tp.get((tissue, "Rapid HPF"), [])
    c_mean = sum(c) / len(c) if c else 0
    h_mean = sum(h) / len(h) if h else 0
    ax3.bar(i - bar_width / 2, c_mean, bar_width, color=CHEM_COLOR, alpha=0.8,
            label="Chemical" if i == 0 else "")
    ax3.bar(i + bar_width / 2, h_mean, bar_width, color=HPF_COLOR, alpha=0.8,
            label="Rapid HPF" if i == 0 else "")
    if not c:
        ax3.text(i - bar_width / 2, 1, "N/A", ha="center", fontsize=8, color="gray")
    if not h:
        ax3.text(i + bar_width / 2, 1, "N/A", ha="center", fontsize=8, color="gray")
ax3.set_xticks(list(x))
ax3.set_xticklabels(tissues, fontsize=11)
ax3.set_ylabel("Mean of Median Half-Width (nm)", fontsize=12)
ax3.set_title("Mean ECS Width by Tissue", fontsize=13)
ax3.legend()

plt.tight_layout()
out_path = os.path.join(os.path.dirname(__file__), "ecs_width_by_prep.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved to {out_path}")
