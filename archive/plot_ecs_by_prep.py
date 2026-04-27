"""Plot ECS percentage and physical volume by prep type, grouped by tissue."""
import matplotlib
matplotlib.use("Agg")
import csv
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os

csv_path = os.path.join(os.path.dirname(__file__), "ecs_cell_volumes.csv")

# Collect data grouped by tissue and prep
pct_by_tp = {}   # {(tissue, prep): [ecs_pct, ...]}
vol_by_tp = {}   # {(tissue, prep): [ecs_volume_um3, ...]}
all_chem_pct, all_hpf_pct = [], []
all_chem_vol, all_hpf_vol = [], []

with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["status"] != "OK" or not row["ecs_pct"] or not row["ecs_volume_um3"]:
            continue
        pct = float(row["ecs_pct"])
        vol = float(row["ecs_volume_um3"])
        tissue = row["tissue"]
        prep = row["prep"]
        pct_by_tp.setdefault((tissue, prep), []).append(pct)
        vol_by_tp.setdefault((tissue, prep), []).append(vol)
        if prep == "Chemical":
            all_chem_pct.append(pct)
            all_chem_vol.append(vol)
        else:
            all_hpf_pct.append(pct)
            all_hpf_vol.append(vol)

tissues = ["Kidney", "Heart", "Liver", "Cortex"]
CHEM_COLOR = "#4C72B0"
HPF_COLOR = "#DD8452"
legend_handles = [Patch(facecolor=CHEM_COLOR, alpha=0.7, label="Chemical"),
                  Patch(facecolor=HPF_COLOR, alpha=0.7, label="Rapid HPF")]


def make_tissue_boxplot(ax, data_by_tp, ylabel, title):
    """Box plot by tissue, split by prep type."""
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

    bp = ax.boxplot(box_data, positions=positions, widths=0.7, patch_artist=True,
                    showmeans=True, meanline=True,
                    meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    for data, p in zip(box_data, positions):
        ax.scatter([p] * len(data), data, color="black", zorder=3, s=25, alpha=0.7)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.legend(handles=legend_handles, loc="upper right")


def make_overall_boxplot(ax, chem_data, hpf_data, ylabel, title, fmt=".1f", unit="%"):
    """Overall box plot comparing two prep types."""
    bp = ax.boxplot([chem_data, hpf_data], tick_labels=["Chemical", "Rapid HPF"],
                    patch_artist=True, widths=0.5,
                    showmeans=True, meanline=True,
                    meanprops=dict(color="red", linewidth=1.5, linestyle="--"))
    bp["boxes"][0].set_facecolor(CHEM_COLOR)
    bp["boxes"][0].set_alpha(0.7)
    bp["boxes"][1].set_facecolor(HPF_COLOR)
    bp["boxes"][1].set_alpha(0.7)
    for data, x_pos in [(chem_data, 1), (hpf_data, 2)]:
        ax.scatter([x_pos] * len(data), data, color="black", zorder=3, s=25, alpha=0.7)
    for i, data in enumerate([chem_data, hpf_data], 1):
        if data:
            mean = sum(data) / len(data)
            ax.text(i + 0.35, mean, f"mean={mean:{fmt}}{unit}", fontsize=9,
                    color="red", va="center")
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=13)


# --- Create figure: 2 rows x 3 columns ---
fig, axes = plt.subplots(2, 3, figsize=(18, 11),
                          gridspec_kw={"width_ratios": [2, 1.2, 1.2]})

# Row 1: ECS percentage
make_tissue_boxplot(axes[0, 0], pct_by_tp, "ECS (%)", "ECS % by Tissue and Prep Type")
make_overall_boxplot(axes[0, 1], all_chem_pct, all_hpf_pct,
                     "ECS (%)", "Overall ECS % by Prep")

# Mean ECS % grouped bars
ax_pct = axes[0, 2]
x = range(len(tissues))
bar_width = 0.35
for i, tissue in enumerate(tissues):
    c = pct_by_tp.get((tissue, "Chemical"), [])
    h = pct_by_tp.get((tissue, "Rapid HPF"), [])
    c_mean = sum(c) / len(c) if c else 0
    h_mean = sum(h) / len(h) if h else 0
    ax_pct.bar(i - bar_width / 2, c_mean, bar_width, color=CHEM_COLOR, alpha=0.8,
               label="Chemical" if i == 0 else "")
    ax_pct.bar(i + bar_width / 2, h_mean, bar_width, color=HPF_COLOR, alpha=0.8,
               label="Rapid HPF" if i == 0 else "")
    if not c:
        ax_pct.text(i - bar_width / 2, 1, "N/A", ha="center", fontsize=8, color="gray")
    if not h:
        ax_pct.text(i + bar_width / 2, 1, "N/A", ha="center", fontsize=8, color="gray")
ax_pct.set_xticks(list(x))
ax_pct.set_xticklabels(tissues, fontsize=11)
ax_pct.set_ylabel("Mean ECS (%)", fontsize=12)
ax_pct.set_title("Mean ECS % by Tissue", fontsize=13)
ax_pct.legend()

# Row 2: ECS physical volume (µm³)
make_tissue_boxplot(axes[1, 0], vol_by_tp,
                    "ECS Volume (µm³)", "ECS Volume by Tissue and Prep Type")
make_overall_boxplot(axes[1, 1], all_chem_vol, all_hpf_vol,
                     "ECS Volume (µm³)", "Overall ECS Volume by Prep",
                     fmt=".2f", unit=" µm³")

# Mean ECS volume grouped bars
ax_vol = axes[1, 2]
for i, tissue in enumerate(tissues):
    c = vol_by_tp.get((tissue, "Chemical"), [])
    h = vol_by_tp.get((tissue, "Rapid HPF"), [])
    c_mean = sum(c) / len(c) if c else 0
    h_mean = sum(h) / len(h) if h else 0
    ax_vol.bar(i - bar_width / 2, c_mean, bar_width, color=CHEM_COLOR, alpha=0.8,
               label="Chemical" if i == 0 else "")
    ax_vol.bar(i + bar_width / 2, h_mean, bar_width, color=HPF_COLOR, alpha=0.8,
               label="Rapid HPF" if i == 0 else "")
    if not c:
        ax_vol.text(i - bar_width / 2, 0.05, "N/A", ha="center", fontsize=8, color="gray")
    if not h:
        ax_vol.text(i + bar_width / 2, 0.05, "N/A", ha="center", fontsize=8, color="gray")
ax_vol.set_xticks(list(x))
ax_vol.set_xticklabels(tissues, fontsize=11)
ax_vol.set_ylabel("Mean ECS Volume (µm³)", fontsize=12)
ax_vol.set_title("Mean ECS Volume by Tissue", fontsize=13)
ax_vol.legend()

plt.tight_layout()
out_path = os.path.join(os.path.dirname(__file__), "ecs_by_prep_type.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved to {out_path}")
