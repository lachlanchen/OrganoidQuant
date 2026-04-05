#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import ScalarFormatter
import numpy as np
import pandas as pd

CONDITION_ORDER = ['No', '0.02% Alginate', '0.05% Alginate']
CONDITION_LABELS = {
    'No': 'Control',
    '0.02% Alginate': '0.02% Alginate',
    '0.05% Alginate': '0.05% Alginate',
}
CONDITION_COLORS = {
    'No': '#4d4d4d',
    '0.02% Alginate': '#1f77b4',
    '0.05% Alginate': '#d62728',
}

PANEL_A_METRICS = [
    ('Total Area', 'total_area_px_mean', 'total_area_px_sem'),
    ('Count', 'count_mean', 'count_sem'),
    ('Center-Weighted Edge Sum', 'center_weighted_edge_sum_mean', 'center_weighted_edge_sum_sem'),
    ('Roundness', 'roundness_mean', 'roundness_sem'),
    ('Wall Darkness Mean', 'wall_darkness_mean_mean', 'wall_darkness_mean_sem'),
    ('Very Dark Area Ratio', 'very_dark_area_ratio_gt035_mean', 'very_dark_area_ratio_gt035_sem'),
]

PANEL_B_DAYS = [7, 13]
PANEL_B_METRICS = [
    ('Total Area', 'total_area_px'),
    ('Center-Weighted Edge Sum', 'center_weighted_edge_sum'),
    ('Area-Normalized Center-Weighted Edge', 'area_normalized_center_weighted_edge_instance_mean'),
    ('Roundness', 'roundness'),
    ('Wall Darkness Mean', 'wall_darkness_mean'),
    ('Very Dark Area Ratio', 'very_dark_area_ratio_gt035'),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--per-image-csv', required=True)
    p.add_argument('--daily-csv', required=True)
    return p.parse_args()


def derive_output_root(daily_csv: Path) -> Path:
    if daily_csv.parent.name == 'quantification' and daily_csv.parent.parent.name == 'profiling':
        return daily_csv.parent.parent.parent / 'subexperiment_analysis'
    return daily_csv.parent.parent / 'subexperiment_analysis'


def style_axis(ax, title: str, xticks=None, xticklabels=None) -> None:
    ax.set_title(title, fontsize=11, pad=8)
    if xticks is not None:
        ax.set_xticks(xticks)
    if xticklabels is not None:
        ax.set_xticklabels(xticklabels, rotation=0)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def maybe_scientific(ax, column_name: str) -> None:
    if any(key in column_name.lower() for key in ('area', 'sum', 'pixel', 'perimeter')):
        formatter = ScalarFormatter(useMathText=True)
        formatter.set_powerlimits((0, 0))
        ax.yaxis.set_major_formatter(formatter)


def plot_panel_a(daily: pd.DataFrame, out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    xticks = sorted(daily['relative_day'].unique().tolist())
    xticklabels = [f'D{int(d)}' for d in xticks]
    fig, axes = plt.subplots(2, 3, figsize=(17.5, 10.0), constrained_layout=False)
    axes = axes.ravel()
    handles = [
        Line2D([0], [0], color=CONDITION_COLORS[c], lw=2.2, marker='o', markersize=5, label=CONDITION_LABELS[c])
        for c in CONDITION_ORDER
    ]

    for ax, (title, mean_col, sem_col) in zip(axes, PANEL_A_METRICS):
        for condition in CONDITION_ORDER:
            subset = daily[daily['condition'] == condition].sort_values('relative_day')
            x = subset['relative_day'].to_numpy(dtype=float)
            y = subset[mean_col].to_numpy(dtype=float)
            sem = subset[sem_col].to_numpy(dtype=float)
            color = CONDITION_COLORS[condition]
            ax.plot(x, y, color=color, lw=2.2, marker='o', markersize=4.8)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, title, xticks, xticklabels)
        maybe_scientific(ax, mean_col)

    fig.suptitle('App65 Panel A: Longitudinal Alginate Time-Course Using Saved Segmentation Metrics', fontsize=15, y=0.985)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.945), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.88, hspace=0.34, wspace=0.24)

    png = out_dir / 'app65_panel_a_longitudinal_primary_metrics.png'
    pdf = out_dir / 'app65_panel_a_longitudinal_primary_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)

    selected_cols = ['condition', 'date_key', 'date_label', 'relative_day', 'n_images']
    for _, mean_col, sem_col in PANEL_A_METRICS:
        selected_cols.extend([mean_col, sem_col])
    csv_path = out_dir / 'panel_a_selected_daily_summary.csv'
    daily[selected_cols].to_csv(csv_path, index=False)
    return png, pdf, csv_path


def boxplot_with_points(ax, data_by_condition: list[np.ndarray], metric_name: str, y_col: str) -> None:
    positions = np.arange(1, len(CONDITION_ORDER) + 1)
    bp = ax.boxplot(
        data_by_condition,
        positions=positions,
        widths=0.65,
        patch_artist=True,
        showfliers=False,
        medianprops={'color': '#111111', 'linewidth': 1.4},
        whiskerprops={'color': '#666666', 'linewidth': 1.0},
        capprops={'color': '#666666', 'linewidth': 1.0},
        boxprops={'linewidth': 1.0},
    )
    for patch, condition in zip(bp['boxes'], CONDITION_ORDER):
        patch.set_facecolor(CONDITION_COLORS[condition])
        patch.set_alpha(0.28)
        patch.set_edgecolor(CONDITION_COLORS[condition])

    rng = np.random.default_rng(0)
    for pos, values, condition in zip(positions, data_by_condition, CONDITION_ORDER):
        if values.size == 0:
            continue
        jitter = rng.normal(0, 0.055, size=values.size)
        ax.scatter(np.full(values.size, pos) + jitter, values, s=18, alpha=0.65, color=CONDITION_COLORS[condition], edgecolors='none')

    style_axis(ax, metric_name)
    ax.set_xticks(positions)
    ax.set_xticklabels([CONDITION_LABELS[c] for c in CONDITION_ORDER], rotation=0)
    maybe_scientific(ax, y_col)


def plot_panel_b(per_image: pd.DataFrame, out_dir: Path) -> tuple[Path, Path, list[Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    day_subsets = {day: per_image[per_image['relative_day'] == day].copy() for day in PANEL_B_DAYS}
    fig, axes = plt.subplots(len(PANEL_B_DAYS), len(PANEL_B_METRICS), figsize=(22.0, 7.2 * len(PANEL_B_DAYS)), constrained_layout=False)
    axes = np.atleast_2d(axes)

    for row_idx, day in enumerate(PANEL_B_DAYS):
        subset_day = day_subsets[day]
        date_label_values = sorted(subset_day['date_label'].dropna().unique().tolist())
        row_date_label = date_label_values[0] if date_label_values else f'D{day}'
        for col_idx, (title, column) in enumerate(PANEL_B_METRICS):
            ax = axes[row_idx, col_idx]
            data_by_condition = []
            for condition in CONDITION_ORDER:
                vals = subset_day[subset_day['condition'] == condition][column].dropna().to_numpy(dtype=float)
                data_by_condition.append(vals)
            boxplot_with_points(ax, data_by_condition, title, column)
            if col_idx == 0:
                ax.set_ylabel(f'{row_date_label}\nvalue', fontsize=11)

    handles = [
        Line2D([0], [0], color=CONDITION_COLORS[c], lw=0, marker='s', markersize=10,
               markerfacecolor=CONDITION_COLORS[c], alpha=0.28, label=CONDITION_LABELS[c])
        for c in CONDITION_ORDER
    ]
    fig.suptitle('App65 Panel B: Dedicated Day 7 and Day 13 Condition Comparison', fontsize=15, y=0.985)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.952), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.05, right=0.992, bottom=0.06, top=0.90, hspace=0.30, wspace=0.24)

    png = out_dir / 'app65_panel_b_day7_day13_detailed_metrics.png'
    pdf = out_dir / 'app65_panel_b_day7_day13_detailed_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)

    csv_paths: list[Path] = []
    for day in PANEL_B_DAYS:
        subset_day = day_subsets[day]
        per_image_csv = out_dir / f'panel_b_day{day}_per_image.csv'
        keep_cols = ['condition', 'date_key', 'date_label', 'relative_day', 'image_name'] + [c for _, c in PANEL_B_METRICS]
        subset_day[keep_cols].to_csv(per_image_csv, index=False)
        csv_paths.append(per_image_csv)

        rows = []
        for condition in CONDITION_ORDER:
            sub = subset_day[subset_day['condition'] == condition]
            row = {
                'condition': condition,
                'condition_label': CONDITION_LABELS[condition],
                'relative_day': day,
                'date_label': sorted(sub['date_label'].dropna().unique().tolist())[0] if not sub.empty else f'D{day}',
                'n_images': int(len(sub)),
            }
            for _, column in PANEL_B_METRICS:
                s = sub[column].dropna()
                row[f'{column}_mean'] = float(s.mean()) if len(s) else np.nan
                row[f'{column}_median'] = float(s.median()) if len(s) else np.nan
                row[f'{column}_std'] = float(s.std(ddof=1)) if len(s) > 1 else np.nan
            rows.append(row)
        summary_csv = out_dir / f'panel_b_day{day}_summary.csv'
        pd.DataFrame(rows).to_csv(summary_csv, index=False)
        csv_paths.append(summary_csv)

    return png, pdf, csv_paths


def write_manifest(out_root: Path, panel_a_outputs: tuple[Path, ...], panel_b_png: Path, panel_b_pdf: Path, panel_b_csvs: list[Path]) -> Path:
    manifest = {
        'analysis_name': 'app65_two_subexperiments',
        'panel_a': {
            'description': 'Longitudinal alginate time-course from the saved App65 segmentation database',
            'outputs': [str(p) for p in panel_a_outputs],
        },
        'panel_b': {
            'description': 'Dedicated Day 7 and Day 13 detailed comparison from the saved App65 per-image database',
            'days': PANEL_B_DAYS,
            'outputs': [str(panel_b_png), str(panel_b_pdf)] + [str(p) for p in panel_b_csvs],
        },
    }
    path = out_root / 'app65_two_subexperiments_manifest.json'
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def main() -> int:
    args = parse_args()
    per_image_csv = Path(args.per_image_csv).resolve()
    daily_csv = Path(args.daily_csv).resolve()
    per_image = pd.read_csv(per_image_csv)
    daily = pd.read_csv(daily_csv)
    per_image['relative_day'] = per_image['relative_day'].astype(int)
    daily['relative_day'] = daily['relative_day'].astype(int)

    out_root = derive_output_root(daily_csv)
    panel_a_dir = out_root / 'panel_a_longitudinal'
    panel_b_dir = out_root / 'panel_b_day7_day13'
    out_root.mkdir(parents=True, exist_ok=True)

    panel_a_outputs = plot_panel_a(daily, panel_a_dir)
    panel_b_png, panel_b_pdf, panel_b_csvs = plot_panel_b(per_image, panel_b_dir)
    manifest = write_manifest(out_root, panel_a_outputs, panel_b_png, panel_b_pdf, panel_b_csvs)
    print(manifest)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
