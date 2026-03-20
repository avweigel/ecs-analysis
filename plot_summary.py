"""Comprehensive visual summary of all ECS analyses."""
import matplotlib
matplotlib.use("Agg")
import csv
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os

base_dir = os.path.dirname(__file__)

tissues = ["Kidney", "Heart", "Liver", "Cortex"]
CHEM_COLOR = "#4C72B0"
HPF_COLOR = "#DD8452"
CHEM_LABEL = "Chemical"
HPF_LABEL = "Rapid HPF"

# ---- Load all data ----

# 1. ECS percentage (from ecs_cell_volumes.csv)
pct_by_tp = {}
with open(os.path.join(base_dir, "ecs_cell_volumes.csv")) as f:
    for row in csv.DictReader(f):
        if row["status"] != "OK" or not row["ecs_pct"]:
            continue
        pct_by_tp.setdefault((row["tissue"], row["prep"]), []).append(float(row["ecs_pct"]))

# 2. ECS half-width (from ecs_width.csv)
width_by_tp = {}
with open(os.path.join(base_dir, "ecs_width.csv")) as f:
    for row in csv.DictReader(f):
        if row["status"] != "OK" or not row["median_half_width_nm"]:
            continue
        width_by_tp.setdefault((row["tissue"], row["prep"]), []).append(
            float(row["median_half_width_nm"]))

# 3. Per-cell SA/V and sphericity (from cell_morphology_per_cell.csv)
sav_by_tp = {}
sph_by_tp = {}
with open(os.path.join(base_dir, "cell_morphology_per_cell.csv")) as f:
    for row in csv.DictReader(f):
        t, p = row["tissue"], row["prep"]
        sav_by_tp.setdefault((t, p), []).append(float(row["sa_v_ratio"]))
        sph_by_tp.setdefault((t, p), []).append(float(row["sphericity"]))

# 4. Narrow-channel ECS width (from cell_morphology_crops.csv)
narrow_by_tp = {}
with open(os.path.join(base_dir, "cell_morphology_crops.csv")) as f:
    for row in csv.DictReader(f):
        if row["status"] != "OK" or not row["narrow_ecs_median_nm"]:
            continue
        narrow_by_tp.setdefault((row["tissue"], row["prep"]), []).append(
            float(row["narrow_ecs_median_nm"]))

# 5. Cell-cell gap width and contact fractions (from cell_contacts.csv)
gap_by_tp = {}
contact_rows_by_tp = {}
with open(os.path.join(base_dir, "cell_contacts.csv")) as f:
    for row in csv.DictReader(f):
        if row["status"] != "OK" or not row["gap_median_nm"]:
            continue
        t, p = row["tissue"], row["prep"]
        gap_by_tp.setdefault((t, p), []).append(float(row["gap_median_nm"]))
        contact_rows_by_tp.setdefault((t, p), []).append(row)


# ---- Plotting helpers ----

def grouped_bar(ax, data_by_tp, ylabel, title, fmt=".1f", unit=""):
    """Grouped bar chart: mean per tissue, Chemical vs HPF side by side."""
    x = np.arange(len(tissues))
    bar_w = 0.35
    chem_means, hpf_means = [], []
    chem_sems, hpf_sems = [], []
    for tissue in tissues:
        c = data_by_tp.get((tissue, "Chemical"), [])
        h = data_by_tp.get((tissue, "Rapid HPF"), [])
        chem_means.append(np.mean(c) if c else 0)
        hpf_means.append(np.mean(h) if h else 0)
        chem_sems.append(np.std(c)/np.sqrt(len(c)) if len(c) > 1 else 0)
        hpf_sems.append(np.std(h)/np.sqrt(len(h)) if len(h) > 1 else 0)

    bars1 = ax.bar(x - bar_w/2, chem_means, bar_w, yerr=chem_sems,
                   color=CHEM_COLOR, alpha=0.8, capsize=3, label=CHEM_LABEL)
    bars2 = ax.bar(x + bar_w/2, hpf_means, bar_w, yerr=hpf_sems,
                   color=HPF_COLOR, alpha=0.8, capsize=3, label=HPF_LABEL)

    # Scatter individual points
    for i, tissue in enumerate(tissues):
        c = data_by_tp.get((tissue, "Chemical"), [])
        h = data_by_tp.get((tissue, "Rapid HPF"), [])
        if c:
            jitter = np.random.default_rng(42).uniform(-0.08, 0.08, len(c))
            ax.scatter(i - bar_w/2 + jitter, c, color="black", s=12, alpha=0.5, zorder=3)
        if h:
            jitter = np.random.default_rng(43).uniform(-0.08, 0.08, len(h))
            ax.scatter(i + bar_w/2 + jitter, h, color="black", s=12, alpha=0.5, zorder=3)

    for i, tissue in enumerate(tissues):
        c = data_by_tp.get((tissue, "Chemical"), [])
        h = data_by_tp.get((tissue, "Rapid HPF"), [])
        if not c:
            ax.text(i - bar_w/2, 0, "N/A", ha="center", va="bottom", fontsize=7, color="gray")
        if not h:
            ax.text(i + bar_w/2, 0, "N/A", ha="center", va="bottom", fontsize=7, color="gray")

    ax.set_xticks(x)
    ax.set_xticklabels(tissues, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)


# ---- Create figure: 3 rows x 2 columns ----
fig, axes = plt.subplots(3, 2, figsize=(14, 16))
fig.suptitle("ECS Analysis Summary: Chemical Fixation vs Rapid HPF",
             fontsize=14, fontweight="bold", y=0.98)

# (0,0) ECS Volume Fraction
grouped_bar(axes[0, 0], pct_by_tp, "ECS (%)", "A. ECS Volume Fraction")

# (0,1) ECS Half-Width (distance transform)
grouped_bar(axes[0, 1], width_by_tp, "Median Half-Width (nm)",
            "B. ECS Channel Half-Width")

# (1,0) Per-cell SA/V ratio
# Aggregate per-cell to per-crop means first for bar chart
sav_crop_by_tp = {}
for (t, p), vals in sav_by_tp.items():
    sav_crop_by_tp[(t, p)] = vals  # keep per-cell for scatter
grouped_bar(axes[1, 0], sav_by_tp, "SA/V Ratio (1/nm)",
            "C. Cell ECS-Facing SA/V Ratio (per cell)")

# (1,1) Per-cell Sphericity
grouped_bar(axes[1, 1], sph_by_tp, "Sphericity",
            "D. Cell Sphericity (per cell)")

# (2,0) Cell-cell gap width
grouped_bar(axes[2, 0], gap_by_tp, "Median Gap (nm)",
            "E. Inter-Cell Gap Width (Voronoi)")

# (2,1) Contact fraction curves
ax = axes[2, 1]
THRESHOLDS = [10, 20, 40, 80, 160, 320]
# Aggregate across all tissues for Chemical vs HPF
for prep, color, ls in [(CHEM_LABEL, CHEM_COLOR, "-"), (HPF_LABEL, HPF_COLOR, "--")]:
    all_rows = []
    for (t, p), rows in contact_rows_by_tp.items():
        if p == prep:
            all_rows.extend(rows)
    if not all_rows:
        continue
    mean_fracs = []
    sem_fracs = []
    for T in THRESHOLDS:
        fracs = [float(r[f"contact_frac_{T}nm"]) for r in all_rows]
        mean_fracs.append(np.mean(fracs))
        sem_fracs.append(np.std(fracs) / np.sqrt(len(fracs)) if len(fracs) > 1 else 0)
    ax.errorbar(THRESHOLDS, mean_fracs, yerr=sem_fracs, marker="o",
                linestyle=ls, color=color, linewidth=2.5, markersize=7,
                label=f"{prep} (n={len(all_rows)})", capsize=3)

ax.set_xlabel("Distance Threshold (nm)", fontsize=10)
ax.set_ylabel("Fraction in Contact", fontsize=10)
ax.set_title("F. Cell-Cell Contact vs Distance Threshold", fontsize=11, fontweight="bold")
ax.set_xscale("log")
ax.set_xticks(THRESHOLDS)
ax.set_xticklabels([str(t) for t in THRESHOLDS])
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
ax.set_ylim(-0.05, 1.05)

# Add annotation about resolution caveat
ax.annotate("Note: 8nm-voxel HPF crops\ncannot resolve gaps <24nm",
            xy=(20, 0.0), fontsize=7, color="gray", style="italic",
            ha="center", va="bottom")

plt.tight_layout(rect=[0, 0, 1, 0.96])
out_path = os.path.join(base_dir, "ecs_analysis_summary.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved to {out_path}")

# ---- Print table summary ----
print("\n" + "="*80)
print("SUMMARY TABLE: Chemical vs Rapid HPF (mean ± SEM)")
print("="*80)

metrics = [
    ("ECS %", pct_by_tp, ".1f", "%"),
    ("ECS Half-Width", width_by_tp, ".1f", " nm"),
    ("SA/V Ratio", sav_by_tp, ".4f", " 1/nm"),
    ("Sphericity", sph_by_tp, ".3f", ""),
    ("Inter-Cell Gap", gap_by_tp, ".1f", " nm"),
]

for name, data, fmt, unit in metrics:
    print(f"\n{name}:")
    print(f"  {'Tissue':10s} {'Chemical':>25s}   {'Rapid HPF':>25s}   {'Direction':>12s}")
    for tissue in tissues:
        c = data.get((tissue, "Chemical"), [])
        h = data.get((tissue, "Rapid HPF"), [])
        c_str = f"{np.mean(c):{fmt}}±{np.std(c)/np.sqrt(len(c)):{fmt}} (n={len(c)})" if c else "N/A"
        h_str = f"{np.mean(h):{fmt}}±{np.std(h)/np.sqrt(len(h)):{fmt}} (n={len(h)})" if h else "N/A"
        if c and h:
            diff = "Chem > HPF" if np.mean(c) > np.mean(h) else "HPF > Chem"
        else:
            diff = "-"
        print(f"  {tissue:10s} {c_str:>25s}   {h_str:>25s}   {diff:>12s}")
