"""Plot cell morphology metrics (SA/V, sphericity, narrow-channel width) by prep type."""
import matplotlib
matplotlib.use("Agg")
import csv
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os

base_dir = os.path.dirname(__file__)
crop_csv = os.path.join(base_dir, "cell_morphology_crops.csv")
cell_csv = os.path.join(base_dir, "cell_morphology_per_cell.csv")

tissues = ["Kidney", "Heart", "Liver", "Cortex"]
CHEM_COLOR = "#4C72B0"
HPF_COLOR = "#DD8452"
legend_handles = [Patch(facecolor=CHEM_COLOR, alpha=0.7, label="Chemical"),
                  Patch(facecolor=HPF_COLOR, alpha=0.7, label="Rapid HPF")]

# ---- Load per-cell data ----
sav_by_tp = {}    # {(tissue, prep): [sa_v_ratio, ...]}
sph_by_tp = {}    # {(tissue, prep): [sphericity, ...]}

with open(cell_csv) as f:
    for row in csv.DictReader(f):
        tissue = row["tissue"]
        prep = row["prep"]
        sav_by_tp.setdefault((tissue, prep), []).append(float(row["sa_v_ratio"]))
        sph_by_tp.setdefault((tissue, prep), []).append(float(row["sphericity"]))

# ---- Load crop-level data ----
narrow_by_tp = {}  # {(tissue, prep): [median_narrow_width, ...]}

with open(crop_csv) as f:
    for row in csv.DictReader(f):
        if row["status"] != "OK" or not row["narrow_ecs_median_nm"]:
            continue
        tissue = row["tissue"]
        prep = row["prep"]
        narrow_by_tp.setdefault((tissue, prep), []).append(
            float(row["narrow_ecs_median_nm"]))


def tissue_boxplot(ax, data_by_tp, ylabel, title, fmt_val=".4f"):
    """Box plot by tissue, split by prep type, with individual points."""
    positions, colors, box_data = [], [], []
    tick_positions, tick_labels = [], []
    pos = 0
    for tissue in tissues:
        chem = data_by_tp.get((tissue, "Chemical"), [])
        hpf = data_by_tp.get((tissue, "Rapid HPF"), [])
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

    if not box_data:
        return

    bp = ax.boxplot(box_data, positions=positions, widths=0.7, patch_artist=True,
                    showmeans=True, meanline=True,
                    meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    for data, p in zip(box_data, positions):
        jitter = np.random.default_rng(42).uniform(-0.15, 0.15, len(data))
        ax.scatter([p + j for j in jitter], data, color="black", zorder=3,
                   s=15, alpha=0.5)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.legend(handles=legend_handles, loc="upper right")


def overall_boxplot(ax, data_by_tp, ylabel, title, fmt=".4f", unit=""):
    """Overall box plot comparing two prep types."""
    chem_all, hpf_all = [], []
    for (tissue, prep), vals in data_by_tp.items():
        if prep == "Chemical":
            chem_all.extend(vals)
        else:
            hpf_all.extend(vals)

    if not chem_all or not hpf_all:
        return

    bp = ax.boxplot([chem_all, hpf_all], tick_labels=["Chemical", "Rapid HPF"],
                    patch_artist=True, widths=0.5,
                    showmeans=True, meanline=True,
                    meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
    bp["boxes"][0].set_facecolor(CHEM_COLOR)
    bp["boxes"][0].set_alpha(0.7)
    bp["boxes"][1].set_facecolor(HPF_COLOR)
    bp["boxes"][1].set_alpha(0.7)
    for data, x_pos in [(chem_all, 1), (hpf_all, 2)]:
        jitter = np.random.default_rng(42).uniform(-0.15, 0.15, len(data))
        ax.scatter([x_pos + j for j in jitter], data, color="black", zorder=3,
                   s=10, alpha=0.4)
    for i, data in enumerate([chem_all, hpf_all], 1):
        if data:
            mean = sum(data) / len(data)
            n = len(data)
            ax.text(i + 0.35, mean, f"mean={mean:{fmt}}{unit}\nn={n}",
                    fontsize=8, color="red", va="center")
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13)


# ---- Create figure: 3 rows x 2 columns ----
fig, axes = plt.subplots(3, 2, figsize=(16, 18),
                          gridspec_kw={"width_ratios": [2, 1.2]})

# Row 1: SA/V ratio (per cell)
tissue_boxplot(axes[0, 0], sav_by_tp,
               "SA/V Ratio (1/nm)", "ECS-Facing SA/V by Tissue and Prep (per cell)")
overall_boxplot(axes[0, 1], sav_by_tp,
                "SA/V Ratio (1/nm)", "Overall SA/V by Prep", fmt=".5f", unit=" 1/nm")

# Row 2: Sphericity (per cell)
tissue_boxplot(axes[1, 0], sph_by_tp,
               "Sphericity", "Cell Sphericity by Tissue and Prep (per cell)")
overall_boxplot(axes[1, 1], sph_by_tp,
                "Sphericity", "Overall Sphericity by Prep", fmt=".3f")

# Row 3: Narrow-channel ECS width (per crop)
tissue_boxplot(axes[2, 0], narrow_by_tp,
               "Median Narrow-Channel\nHalf-Width (nm)",
               "Narrow-Channel ECS Width by Tissue and Prep (<200nm)")
overall_boxplot(axes[2, 1], narrow_by_tp,
                "Median Narrow-Channel\nHalf-Width (nm)",
                "Overall Narrow-Channel Width by Prep", fmt=".1f", unit=" nm")

plt.tight_layout()
out_path = os.path.join(base_dir, "cell_morphology_by_prep.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved to {out_path}")

# Print summary statistics
print("\n=== Summary Statistics ===")
for metric_name, data_by_tp in [("SA/V", sav_by_tp), ("Sphericity", sph_by_tp)]:
    print(f"\n{metric_name}:")
    for tissue in tissues:
        for prep in ["Chemical", "Rapid HPF"]:
            vals = data_by_tp.get((tissue, prep), [])
            if vals:
                print(f"  {tissue:8s} {prep:12s}: n={len(vals):4d}, "
                      f"mean={np.mean(vals):.5f}, median={np.median(vals):.5f}, "
                      f"std={np.std(vals):.5f}")

print("\nNarrow-channel ECS width:")
for tissue in tissues:
    for prep in ["Chemical", "Rapid HPF"]:
        vals = narrow_by_tp.get((tissue, prep), [])
        if vals:
            print(f"  {tissue:8s} {prep:12s}: n={len(vals):4d}, "
                  f"mean={np.mean(vals):.1f}nm, median={np.median(vals):.1f}nm")
