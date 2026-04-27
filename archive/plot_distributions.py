"""
Distribution plots for all kept metrics, showing per-crop distributions
across all tissues. Color-coded by prep type.
"""
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

CHEM_COLOR = '#d62728'   # red
HPF_COLOR = '#1f77b4'    # blue
TISSUES = ['Kidney', 'Heart', 'Liver', 'Cortex']

MIN_VOL_NM3 = 2560000  # Physical volume filter for SA/V


def load_ecs_volumes():
    """Load ECS volume fraction per crop."""
    rows = []
    with open('ecs_cell_volumes.csv') as f:
        for row in csv.DictReader(f):
            if row['status'] == 'OK':
                rows.append(row)
    return rows


def load_ecs_width_filtered():
    """Load filtered ECS width stats per crop."""
    rows = []
    with open('ecs_width_filtered.csv') as f:
        for row in csv.DictReader(f):
            if row['status'] == 'OK':
                rows.append(row)
    return rows


def load_sav_per_cell():
    """Load per-cell SA/V data."""
    rows = []
    with open('cell_morphology_per_cell.csv') as f:
        for row in csv.DictReader(f):
            if float(row['volume_nm3']) >= MIN_VOL_NM3:
                rows.append(row)
    return rows


def load_cell_contacts():
    """Load cell contact data per crop."""
    rows = []
    with open('cell_contacts.csv') as f:
        for row in csv.DictReader(f):
            if row['status'] == 'OK':
                rows.append(row)
    return rows


def plot_metric1(ax):
    """Metric 1: ECS Volume Fraction - strip plot per crop."""
    data = [r for r in load_ecs_volumes() if r.get('ecs_pct', '')]

    pos = 0
    tick_pos = []
    tick_labels = []
    tissue_spans = []

    for tissue in TISSUES:
        tissue_data = [r for r in data if r['tissue'] == tissue]
        if not tissue_data:
            continue
        tissue_start = pos
        for prep_label, color in [('Chemical', CHEM_COLOR), ('Rapid HPF', HPF_COLOR)]:
            crops = [r for r in tissue_data if r['prep'] == prep_label]
            if not crops:
                continue
            for crop in sorted(crops, key=lambda r: r['crop']):
                val = float(crop['ecs_pct'])
                ax.bar(pos, val, color=color, alpha=0.7, width=0.7)
                tick_pos.append(pos)
                tick_labels.append(crop['crop'].replace('crop', ''))
                pos += 1
            pos += 0.5  # gap between preps
        tissue_spans.append((tissue_start, pos - 0.5, tissue))
        pos += 1  # gap between tissues

    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, rotation=90, fontsize=6)
    ax.set_ylabel('ECS Volume Fraction (%)')
    ax.set_title('Metric 1: ECS Volume Fraction per Crop')

    # Tissue labels
    for start, end, tissue in tissue_spans:
        mid = (start + end) / 2
        ax.text(mid, ax.get_ylim()[1] * 0.95, tissue,
                ha='center', va='top', fontsize=8, fontweight='bold')


def plot_metric2(ax):
    """Metric 2: ECS Width filtered - box plots from saved percentiles."""
    data = load_ecs_width_filtered()

    pos = 0
    tick_pos = []
    tick_labels = []
    tissue_spans = []

    for tissue in TISSUES:
        tissue_data = [r for r in data if r['tissue'] == tissue]
        if not tissue_data:
            continue
        tissue_start = pos
        for prep_label, color in [('Chemical', CHEM_COLOR), ('Rapid HPF', HPF_COLOR)]:
            crops = [r for r in tissue_data if r['prep'] == prep_label]
            if not crops:
                continue
            for crop in sorted(crops, key=lambda r: r['crop']):
                p10 = float(crop['narrow_p10_nm'])
                p25 = float(crop['narrow_p25_nm'])
                med = float(crop['narrow_median_nm'])
                p75 = float(crop['narrow_p75_nm'])
                p90 = float(crop['narrow_p90_nm'])

                # Draw box (p25-p75) with whiskers (p10-p90)
                box_width = 0.6
                ax.bar(pos, p75 - p25, bottom=p25, color=color, alpha=0.4, width=box_width)
                ax.plot([pos], [med], 'k_', markersize=8, markeredgewidth=1.5)
                ax.plot([pos, pos], [p10, p25], color=color, linewidth=1)
                ax.plot([pos, pos], [p75, p90], color=color, linewidth=1)
                ax.plot([pos - box_width/4, pos + box_width/4], [p10, p10], color=color, linewidth=1)
                ax.plot([pos - box_width/4, pos + box_width/4], [p90, p90], color=color, linewidth=1)

                tick_pos.append(pos)
                tick_labels.append(crop['crop'].replace('crop', ''))
                pos += 1
            pos += 0.5
        tissue_spans.append((tissue_start, pos - 0.5, tissue))
        pos += 1

    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, rotation=90, fontsize=6)
    ax.set_ylabel('ECS Half-Width (nm)')
    ax.set_title('Metric 2: ECS Width Distribution per Crop (<200nm)')
    ax.set_ylim(0, 200)

    for start, end, tissue in tissue_spans:
        mid = (start + end) / 2
        ax.text(mid, 190, tissue, ha='center', va='top', fontsize=8, fontweight='bold')


def plot_metric3(ax):
    """Metric 3: SA/V per cell - violin-style per crop."""
    data = load_sav_per_cell()

    # Group by crop
    from collections import defaultdict
    crops_data = defaultdict(lambda: {'vals': [], 'prep': '', 'tissue': ''})
    for row in data:
        key = (row['tissue'], row['prep'], row['crop'])
        crops_data[key]['vals'].append(float(row['sa_v_ratio']))
        crops_data[key]['prep'] = row['prep']
        crops_data[key]['tissue'] = row['tissue']

    pos = 0
    tick_pos = []
    tick_labels = []
    tissue_spans = []

    for tissue in TISSUES:
        tissue_keys = [k for k in crops_data if k[0] == tissue]
        if not tissue_keys:
            continue
        tissue_start = pos
        for prep_label, color in [('Chemical', CHEM_COLOR), ('Rapid HPF', HPF_COLOR)]:
            prep_keys = sorted([k for k in tissue_keys if k[1] == prep_label], key=lambda k: k[2])
            if not prep_keys:
                continue
            for key in prep_keys:
                vals = crops_data[key]['vals']
                if len(vals) < 3:
                    # Too few cells for a meaningful distribution
                    ax.scatter([pos] * len(vals), vals, color=color, s=10, alpha=0.7)
                else:
                    parts = ax.violinplot([vals], positions=[pos], showmedians=True,
                                         showextrema=False, widths=0.7)
                    for pc in parts['bodies']:
                        pc.set_facecolor(color)
                        pc.set_alpha(0.5)
                    parts['cmedians'].set_color('black')

                tick_pos.append(pos)
                tick_labels.append(key[2].replace('crop', ''))
                pos += 1
            pos += 0.5
        tissue_spans.append((tissue_start, pos - 0.5, tissue))
        pos += 1

    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, rotation=90, fontsize=6)
    ax.set_ylabel('SA/V Ratio (1/nm)')
    ax.set_title('Metric 3: Cell SA/V Distribution per Crop (vol > 2.56M nm³)')

    for start, end, tissue in tissue_spans:
        mid = (start + end) / 2
        ax.text(mid, ax.get_ylim()[1] * 0.95, tissue,
                ha='center', va='top', fontsize=8, fontweight='bold')


def plot_metric5(ax):
    """Metric 5: Inter-cell gap width - box plots from saved percentiles."""
    data = load_cell_contacts()

    pos = 0
    tick_pos = []
    tick_labels = []
    tissue_spans = []

    for tissue in TISSUES:
        tissue_data = [r for r in data if r['tissue'] == tissue]
        if not tissue_data:
            continue
        tissue_start = pos
        for prep_label, color in [('Chemical', CHEM_COLOR), ('Rapid HPF', HPF_COLOR)]:
            crops = [r for r in tissue_data if r['prep'] == prep_label]
            if not crops:
                continue
            for crop in sorted(crops, key=lambda r: r['crop']):
                p25 = float(crop['gap_p25_nm'])
                med = float(crop['gap_median_nm'])
                p75 = float(crop['gap_p75_nm'])
                gap_min = float(crop['gap_min_nm'])

                box_width = 0.6
                ax.bar(pos, p75 - p25, bottom=p25, color=color, alpha=0.4, width=box_width)
                ax.plot([pos], [med], 'k_', markersize=8, markeredgewidth=1.5)
                ax.plot([pos, pos], [gap_min, p25], color=color, linewidth=1)
                ax.plot([pos - box_width/4, pos + box_width/4], [gap_min, gap_min],
                        color=color, linewidth=1)

                tick_pos.append(pos)
                tick_labels.append(crop['crop'].replace('crop', ''))
                pos += 1
            pos += 0.5
        tissue_spans.append((tissue_start, pos - 0.5, tissue))
        pos += 1

    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, rotation=90, fontsize=6)
    ax.set_ylabel('Inter-Cell Gap Width (nm)')
    ax.set_title('Metric 5: Voronoi Gap Width Distribution per Crop')
    ax.set_ylim(0, min(500, ax.get_ylim()[1]))

    for start, end, tissue in tissue_spans:
        mid = (start + end) / 2
        ymax = ax.get_ylim()[1]
        ax.text(mid, ymax * 0.95, tissue, ha='center', va='top', fontsize=8, fontweight='bold')


def plot_metric6(ax):
    """Metric 6: Contact fraction curves per crop."""
    data = load_cell_contacts()
    thresholds = [10, 20, 40, 80, 160, 320]

    for tissue in TISSUES:
        tissue_data = [r for r in data if r['tissue'] == tissue]
        if not tissue_data:
            continue
        for prep_label, color, ls in [('Chemical', CHEM_COLOR, '-'), ('Rapid HPF', HPF_COLOR, '--')]:
            crops = [r for r in tissue_data if r['prep'] == prep_label]
            for crop in crops:
                fracs = [float(crop[f'contact_frac_{t}nm']) for t in thresholds]
                label_str = crop['crop'].replace('crop', '')
                ax.plot(thresholds, fracs, color=color, linestyle=ls,
                        alpha=0.5, linewidth=1, marker='.', markersize=3)

    ax.set_xlabel('Distance Threshold (nm)')
    ax.set_ylabel('Contact Fraction')
    ax.set_title('Metric 6: Contact Fraction Curves per Crop')
    ax.set_xlim(0, 350)
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, color='gray', linestyle=':', linewidth=0.5)
    ax.axhline(1.0, color='gray', linestyle=':', linewidth=0.5)


def main():
    fig, axes = plt.subplots(3, 2, figsize=(20, 18))

    # Legend
    chem_patch = mpatches.Patch(color=CHEM_COLOR, alpha=0.7, label='Chemical')
    hpf_patch = mpatches.Patch(color=HPF_COLOR, alpha=0.7, label='Rapid HPF')

    plot_metric1(axes[0, 0])
    plot_metric2(axes[0, 1])
    plot_metric3(axes[1, 0])
    plot_metric5(axes[1, 1])
    plot_metric6(axes[2, 0])

    # Summary text in last panel
    ax_text = axes[2, 1]
    ax_text.axis('off')
    summary = (
        "Kept Metrics Summary\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. ECS Volume Fraction: single value/crop\n"
        "2. ECS Width (<200nm): p10-p90 distribution/crop\n"
        "3. Cell SA/V (ECS-facing): per-cell distribution/crop\n"
        "   (vol > 2.56M nm³ physical filter)\n"
        "4. Sphericity: DROPPED (redundant with SA/V)\n"
        "5. Inter-Cell Gap: p25-p75 distribution/crop\n"
        "6. Contact Fraction: cumulative curves/crop\n\n"
        "Red = Chemical fixation\n"
        "Blue = Rapid HPF\n\n"
        "Solid lines = Chemical (metric 6)\n"
        "Dashed lines = HPF (metric 6)"
    )
    ax_text.text(0.1, 0.9, summary, transform=ax_text.transAxes,
                 fontsize=11, verticalalignment='top', fontfamily='monospace')

    fig.legend(handles=[chem_patch, hpf_patch], loc='upper right', fontsize=12)
    fig.suptitle('ECS Analysis: Per-Crop Distributions Across All Tissues',
                 fontsize=14, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig('distributions_per_crop.png', dpi=150, bbox_inches='tight')
    print("Saved distributions_per_crop.png")


if __name__ == '__main__':
    main()
