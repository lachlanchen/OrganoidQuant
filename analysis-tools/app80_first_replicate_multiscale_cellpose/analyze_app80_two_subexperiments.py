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

CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']
CONCENTRATION_LABELS = {
    'No': 'Control',
    '10uM': '10 uM',
    '20uM': '20 uM',
    '50uM': '50 uM',
    '100uM': '100 uM',
}
CONCENTRATION_DOSE = {
    'No': 0,
    '10uM': 10,
    '20uM': 20,
    '50uM': 50,
    '100uM': 100,
}
CONCENTRATION_COLORS = {
    'No': '#4d4d4d',
    '10uM': '#1f77b4',
    '20uM': '#2ca02c',
    '50uM': '#ff7f0e',
    '100uM': '#d62728',
}

PANEL_A_METRICS = [
    ('Total Area', 'total_area_px_mean', 'total_area_px_sem'),
    ('Count', 'count_mean', 'count_sem'),
    ('Center-Weighted Edge Sum', 'center_weighted_edge_sum_mean', 'center_weighted_edge_sum_sem'),
    ('Normalized Edge / (Count * Curvature)', 'normalized_edge_over_count_curvature_mean', 'normalized_edge_over_count_curvature_sem'),
    ('Roundness', 'roundness_mean', 'roundness_sem'),
    ('Wall Darkness Mean', 'wall_darkness_mean_mean', 'wall_darkness_mean_sem'),
]

PANEL_B_METRICS = [
    ('Total Area Context', 'total_area_px'),
    ('Count Context', 'count'),
    ('Center-Weighted Edge Sum', 'center_weighted_edge_sum'),
    ('Central / Peripheral Edge', 'central_inside_over_peripheral'),
    ('Area-Normalized Center-Weighted Edge', 'area_normalized_center_weighted_edge_instance_mean'),
    ('Normalized Edge / (Count * Curvature)', 'normalized_edge_over_count_curvature'),
]

PANEL_B_TREND_NOTES = {
    'total_area_px': 'higher can support larger fused masses but remains a context metric',
    'count': 'lower can reflect fusion, but count is ambiguous because growth and splitting also affect it',
    'center_weighted_edge_sum': 'higher suggests stronger internalized edge structure in connected masses',
    'central_inside_over_peripheral': 'higher suggests edge structure lies deeper inside segmented objects',
    'area_normalized_center_weighted_edge_instance_mean': 'higher suggests stronger internal edge signal after size normalization',
    'normalized_edge_over_count_curvature': 'higher is intended as a fusion proxy but can inflate when count becomes small',
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--per-image-csv', required=True)
    p.add_argument('--daily-csv', required=True)
    return p.parse_args()


def derive_output_root(daily_csv: Path) -> Path:
    if daily_csv.parent.name == 'quantification' and daily_csv.parent.parent.name == 'profiling':
        return daily_csv.parent.parent.parent / 'subexperiment_analysis'
    return daily_csv.parent.parent / 'subexperiment_analysis'


def style_axis(ax, title: str, xticks: list[float] | None = None, xticklabels: list[str] | None = None) -> None:
    ax.set_title(title, fontsize=11, pad=8)
    if xticks is not None:
        ax.set_xticks(xticks)
    if xticklabels is not None:
        ax.set_xticklabels(xticklabels, rotation=0)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def maybe_scientific(ax, column_name: str) -> None:
    sci_keys = ('area', 'sum', 'pixel', 'perimeter')
    if any(key in column_name.lower() for key in sci_keys):
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
        Line2D([0], [0], color=CONCENTRATION_COLORS[c], lw=2.2, marker='o', markersize=5, label=CONCENTRATION_LABELS[c])
        for c in CONCENTRATION_ORDER
    ]

    for ax, (title, mean_col, sem_col) in zip(axes, PANEL_A_METRICS):
        for concentration in CONCENTRATION_ORDER:
            subset = daily[daily['concentration'] == concentration].sort_values('relative_day')
            x = subset['relative_day'].to_numpy(dtype=float)
            y = subset[mean_col].to_numpy(dtype=float)
            sem = subset[sem_col].to_numpy(dtype=float)
            color = CONCENTRATION_COLORS[concentration]
            ax.plot(x, y, color=color, lw=2.2, marker='o', markersize=4.8)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, title, xticks, xticklabels)
        maybe_scientific(ax, mean_col)

    fig.suptitle('App80 Panel A: Longitudinal Time-Course Using Saved Segmentation Metrics', fontsize=15, y=0.985)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.945), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.88, hspace=0.34, wspace=0.24)

    png = out_dir / 'app80_panel_a_longitudinal_primary_metrics.png'
    pdf = out_dir / 'app80_panel_a_longitudinal_primary_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)

    selected_cols = ['concentration', 'date_key', 'date_label', 'relative_day', 'n_images']
    for _, mean_col, sem_col in PANEL_A_METRICS:
        selected_cols.extend([mean_col, sem_col])
    table = daily[selected_cols].copy()
    csv_path = out_dir / 'panel_a_selected_daily_summary.csv'
    table.to_csv(csv_path, index=False)
    return png, pdf, csv_path


def boxplot_with_points(ax, data_by_condition: list[np.ndarray], metric_name: str, y_col: str) -> None:
    positions = np.arange(1, len(CONCENTRATION_ORDER) + 1)
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
    for patch, concentration in zip(bp['boxes'], CONCENTRATION_ORDER):
        patch.set_facecolor(CONCENTRATION_COLORS[concentration])
        patch.set_alpha(0.28)
        patch.set_edgecolor(CONCENTRATION_COLORS[concentration])

    rng = np.random.default_rng(0)
    for pos, values, concentration in zip(positions, data_by_condition, CONCENTRATION_ORDER):
        if values.size == 0:
            continue
        jitter = rng.normal(0, 0.055, size=values.size)
        ax.scatter(
            np.full(values.size, pos, dtype=float) + jitter,
            values,
            s=18,
            alpha=0.65,
            color=CONCENTRATION_COLORS[concentration],
            edgecolors='none',
        )

    style_axis(ax, metric_name)
    ax.set_xticks(positions)
    ax.set_xticklabels([CONCENTRATION_LABELS[c] for c in CONCENTRATION_ORDER], rotation=0)
    maybe_scientific(ax, y_col)


def plot_panel_b(day6: pd.DataFrame, out_dir: Path, date_label: str) -> tuple[Path, Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(17.5, 10.0), constrained_layout=False)
    axes = axes.ravel()
    for ax, (title, column) in zip(axes, PANEL_B_METRICS):
        data_by_condition = []
        for concentration in CONCENTRATION_ORDER:
            subset = day6[day6['concentration'] == concentration][column].dropna().to_numpy(dtype=float)
            data_by_condition.append(subset)
        boxplot_with_points(ax, data_by_condition, title, column)

    handles = [
        Line2D([0], [0], color=CONCENTRATION_COLORS[c], lw=0, marker='s', markersize=10,
               markerfacecolor=CONCENTRATION_COLORS[c], alpha=0.28, label=CONCENTRATION_LABELS[c])
        for c in CONCENTRATION_ORDER
    ]
    fig.suptitle(f'App80 Panel B: Dedicated Day 6 Fusion Comparison ({date_label})', fontsize=15, y=0.985)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.945), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.88, hspace=0.34, wspace=0.24)

    png = out_dir / 'app80_panel_b_day6_fusion_metrics.png'
    pdf = out_dir / 'app80_panel_b_day6_fusion_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)

    per_image_csv = out_dir / 'panel_b_day6_per_image.csv'
    cols = ['concentration', 'date_key', 'date_label', 'relative_day', 'image_name'] + [c for _, c in PANEL_B_METRICS]
    day6[cols].to_csv(per_image_csv, index=False)

    summary_rows = []
    for concentration in CONCENTRATION_ORDER:
        subset = day6[day6['concentration'] == concentration]
        row = {
            'concentration': concentration,
            'condition_label': CONCENTRATION_LABELS[concentration],
            'date_label': date_label,
            'n_images': int(len(subset)),
        }
        for _, column in PANEL_B_METRICS:
            s = subset[column].dropna()
            row[f'{column}_mean'] = float(s.mean()) if len(s) else np.nan
            row[f'{column}_median'] = float(s.median()) if len(s) else np.nan
            row[f'{column}_std'] = float(s.std(ddof=1)) if len(s) > 1 else np.nan
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)
    summary_csv = out_dir / 'panel_b_day6_summary.csv'
    summary_df.to_csv(summary_csv, index=False)

    trend_rows = []
    day6 = day6.copy()
    day6['dose_uM'] = day6['concentration'].map(CONCENTRATION_DOSE)
    for _, column in PANEL_B_METRICS:
        s = day6[['dose_uM', column]].dropna()
        rho = s['dose_uM'].rank().corr(s[column].rank()) if len(s) > 1 else np.nan
        trend_rows.append({
            'metric': column,
            'spearman_rank_rho_vs_dose': float(rho) if pd.notna(rho) else np.nan,
            'n_images': int(len(s)),
            'interpretation_note': PANEL_B_TREND_NOTES[column],
        })
    trend_df = pd.DataFrame(trend_rows)
    trend_csv = out_dir / 'panel_b_day6_trend_stats.csv'
    trend_df.to_csv(trend_csv, index=False)

    return png, pdf, per_image_csv, summary_csv, trend_csv


def write_manifest(out_root: Path, panel_a_outputs: tuple[Path, ...], panel_b_outputs: tuple[Path, ...], day6_relative_day: int, day6_label: str) -> Path:
    manifest = {
        'analysis_name': 'app80_two_subexperiments',
        'panel_a': {
            'description': 'Longitudinal time-course panel using daily summary metrics from the saved App80 segmentation database',
            'outputs': [str(p) for p in panel_a_outputs],
        },
        'panel_b': {
            'description': 'Dedicated day 6 fusion comparison using per-image measurements from the saved App80 segmentation database',
            'relative_day': day6_relative_day,
            'date_label': day6_label,
            'outputs': [str(p) for p in panel_b_outputs],
        },
    }
    manifest_path = out_root / 'app80_two_subexperiments_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest_path


def main() -> int:
    args = parse_args()
    per_image_csv = Path(args.per_image_csv).resolve()
    daily_csv = Path(args.daily_csv).resolve()
    per_image = pd.read_csv(per_image_csv)
    daily = pd.read_csv(daily_csv)

    daily['relative_day'] = daily['relative_day'].astype(int)
    per_image['relative_day'] = per_image['relative_day'].astype(int)

    out_root = derive_output_root(daily_csv)
    panel_a_dir = out_root / 'panel_a_longitudinal'
    panel_b_dir = out_root / 'panel_b_day6_fusion'
    out_root.mkdir(parents=True, exist_ok=True)

    panel_a_outputs = plot_panel_a(daily, panel_a_dir)

    day6 = per_image[per_image['relative_day'] == 6].copy()
    if day6.empty:
        raise SystemExit('No relative_day == 6 rows found in per-image metrics.')
    day6_label_values = sorted(day6['date_label'].dropna().unique().tolist())
    day6_label = day6_label_values[0] if day6_label_values else 'Day 6'
    panel_b_outputs = plot_panel_b(day6, panel_b_dir, day6_label)

    manifest_path = write_manifest(out_root, panel_a_outputs, panel_b_outputs, 6, day6_label)
    print(manifest_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
