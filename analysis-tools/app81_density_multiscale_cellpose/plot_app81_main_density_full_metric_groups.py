#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

CONDITION_ORDER = ['low', 'middle', 'high']
CONDITION_COLORS = {
    'low': '#1f77b4',
    'middle': '#2ca02c',
    'high': '#d62728',
}
CONDITION_LABELS = {
    'low': 'Low density',
    'middle': 'Middle density',
    'high': 'High density',
}

GROUPS = {
    'growth_full': [
        ('Counts', 'count_mean', 'count_sem'),
        ('Total Area', 'total_area_px_mean', 'total_area_px_sem'),
        ('Average Perimeter', 'average_perimeter_px_mean', 'average_perimeter_px_sem'),
        ('Signal Sum', 'sum_intensity_mean', 'sum_intensity_sem'),
        ('1 / Signal Sum', 'reciprocal_sum_intensity_mean', 'reciprocal_sum_intensity_sem'),
        ('Signal Sum Relative Change', 'sum_intensity_relative_change', None),
        ('Reciprocal Relative Change', 'reciprocal_relative_change', None),
    ],
    'fusion_core_full': [
        ('Edge Intensity', 'edge_intensity_mean', 'edge_intensity_sem'),
        ('Curvature', 'curvature_mean', 'curvature_sem'),
        ('Normalized Edge / (Counts * Curvature)', 'normalized_edge_over_count_curvature_mean', 'normalized_edge_over_count_curvature_sem'),
        ('1 / (Edge * Count * Curvature)', 'inverse_edge_count_curvature_mean', 'inverse_edge_count_curvature_sem'),
        ('Edge Density', 'edge_density_mean', 'edge_density_sem'),
        ('1 / Edge Density', 'edge_reciprocal_mean', 'edge_reciprocal_sem'),
        ('Gradient Mean', 'gradient_mean_mean', 'gradient_mean_sem'),
        ('1 / Gradient Mean', 'gradient_reciprocal_mean', 'gradient_reciprocal_sem'),
    ],
    'fusion_internal_edge_full': [
        ('Central Inside Edge', 'central_inside_edge_mean_mean', 'central_inside_edge_mean_sem'),
        ('Peripheral Inside Edge', 'peripheral_inside_edge_mean_mean', 'peripheral_inside_edge_mean_sem'),
        ('Outer Ring Edge', 'outer_ring_edge_mean_mean', 'outer_ring_edge_mean_sem'),
        ('Central Inside Fraction', 'central_inside_fraction_mean', 'central_inside_fraction_sem'),
        ('Central / Peripheral', 'central_inside_over_peripheral_mean', 'central_inside_over_peripheral_sem'),
        ('Central / Outer', 'central_inside_over_outer_mean', 'central_inside_over_outer_sem'),
        ('Peripheral / Central', 'peripheral_over_central_mean', 'peripheral_over_central_sem'),
        ('Center-Weighted Edge Sum', 'center_weighted_edge_sum_mean', 'center_weighted_edge_sum_sem'),
        ('Center-Weighted Edge Mean', 'center_weighted_edge_mean_mean', 'center_weighted_edge_mean_sem'),
        ('Area-Normalized Center-Weighted Edge', 'area_normalized_center_weighted_edge_instance_mean_mean', 'area_normalized_center_weighted_edge_instance_mean_sem'),
    ],
    'differentiation_full': [
        ('Roundness', 'roundness_mean', 'roundness_sem'),
        ('Roundness Deviation (Norm)', 'roundness_deviation_norm_mean', 'roundness_deviation_norm_sem'),
        ('Roundness Deviation (Pixels)', 'roundness_deviation_px_total_mean', 'roundness_deviation_px_total_sem'),
        ('Organoid Darkness Mean', 'organoid_darkness_mean_mean', 'organoid_darkness_mean_sem'),
        ('Organoid Darkness P90', 'organoid_darkness_p90_mean', 'organoid_darkness_p90_sem'),
        ('Organoid Darkness P95', 'organoid_darkness_p95_mean', 'organoid_darkness_p95_sem'),
        ('Very Dark Area Ratio', 'very_dark_area_ratio_gt035_mean', 'very_dark_area_ratio_gt035_sem'),
        ('Wall Darkness Mean', 'wall_darkness_mean_mean', 'wall_darkness_mean_sem'),
        ('Wall Darkness P90', 'wall_darkness_p90_mean', 'wall_darkness_p90_sem'),
        ('Core Darkness Mean', 'core_darkness_mean_mean', 'core_darkness_mean_sem'),
        ('Wall / Core Darkness Ratio', 'wall_core_darkness_ratio_mean', 'wall_core_darkness_ratio_sem'),
    ],
    'helpers_full': [
        ('Count Norm', 'count_norm_mean', 'count_norm_sem'),
        ('Curvature Norm', 'curvature_norm_mean', 'curvature_norm_sem'),
        ('Edge Norm', 'edge_norm_mean', 'edge_norm_sem'),
        ('Background Gray Median', 'background_gray_median_mean', 'background_gray_median_sem'),
        ('Organoid Pixel Count', 'organoid_pixel_count_mean', 'organoid_pixel_count_sem'),
        ('Wall Pixel Count', 'wall_pixel_count_mean', 'wall_pixel_count_sem'),
        ('Core Pixel Count', 'core_pixel_count_mean', 'core_pixel_count_sem'),
        ('Center-Weighted Edge Weight Sum', 'center_weighted_edge_weight_sum_mean', 'center_weighted_edge_weight_sum_sem'),
        ('Instance Center-Weighted Edge Sum Mean', 'instance_center_weighted_edge_sum_mean_mean', 'instance_center_weighted_edge_sum_mean_sem'),
        ('Area-Norm Edge Std', 'area_normalized_center_weighted_edge_instance_std_mean', 'area_normalized_center_weighted_edge_instance_std_sem'),
        ('Area-Norm Edge Median', 'area_normalized_center_weighted_edge_instance_median_mean', 'area_normalized_center_weighted_edge_instance_median_sem'),
    ],
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--daily-csv', required=True)
    return p.parse_args()


def read_daily(path: Path) -> list[dict]:
    rows = []
    with path.open('r', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            row['relative_day'] = int(row['relative_day'])
            rows.append(row)
    rows.sort(key=lambda r: (CONDITION_ORDER.index(r['condition']), r['relative_day']))
    return rows


def grouped(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c: [] for c in CONDITION_ORDER}
    for row in rows:
        out.setdefault(row['condition'], []).append(row)
    return {k: v for k, v in out.items() if v}


def style_axis(ax, xticks, xticklabels, title: str) -> None:
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=0)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def maybe_sci_y(ax, mean_col: str) -> None:
    sci_keys = ('area', 'perimeter', 'px_total', 'sum_intensity', 'pixel_count', 'weight_sum')
    if any(k in mean_col for k in sci_keys):
        ax.ticklabel_format(style='scientific', axis='y', scilimits=(0, 0))


def plot_group(rows: list[dict], out_dir: Path, group_name: str, specs: list[tuple[str, str, str | None]]) -> tuple[Path, Path]:
    by_cond = grouped(rows)
    xticks = sorted({r['relative_day'] for r in rows})
    xticklabels = [f'D{d}' for d in xticks]
    handles = [
        Line2D([0], [0], color=CONDITION_COLORS[c], lw=2.2, marker='o', markersize=4.8, label=CONDITION_LABELS[c])
        for c in CONDITION_ORDER if c in by_cond
    ]

    n = len(specs)
    ncols = 3
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(17.5, 4.5 * nrows), constrained_layout=False)
    axes = np.atleast_1d(axes).ravel()

    for ax, (title, mean_col, sem_col) in zip(axes, specs):
        for condition in CONDITION_ORDER:
            subset = by_cond.get(condition, [])
            if not subset:
                continue
            x = np.array([r['relative_day'] for r in subset], dtype=float)
            y = np.array([float(r[mean_col]) if r[mean_col] not in ('', 'nan', 'NaN') else np.nan for r in subset], dtype=float)
            color = CONDITION_COLORS[condition]
            ax.plot(x, y, marker='o', linewidth=2.0, markersize=4.6, color=color)
            if sem_col:
                sem = np.array([float(r[sem_col]) if r[sem_col] not in ('', 'nan', 'NaN') else np.nan for r in subset], dtype=float)
                if np.isfinite(sem).any():
                    ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, xticks, xticklabels, title)
        maybe_sci_y(ax, mean_col)

    for ax in axes[n:]:
        ax.axis('off')

    title_map = {
        'growth_full': 'App81 10x Main Phase: Growth Metrics (Full)',
        'fusion_core_full': 'App81 10x Main Phase: Fusion Metrics (Core)',
        'fusion_internal_edge_full': 'App81 10x Main Phase: Fusion Metrics (Internal Edge)',
        'differentiation_full': 'App81 10x Main Phase: Differentiation Metrics (Full)',
        'helpers_full': 'App81 10x Main Phase: Helper / Normalization Metrics',
    }
    fig.suptitle(title_map[group_name], fontsize=15, y=0.985)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.94), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.06, top=0.88, hspace=0.34, wspace=0.22)

    png = out_dir / f'app81_main_density_{group_name}.png'
    pdf = out_dir / f'app81_main_density_{group_name}.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)
    return png, pdf


def main() -> int:
    args = parse_args()
    daily_csv = Path(args.daily_csv).resolve()
    if daily_csv.parent.name == 'quantification' and daily_csv.parent.parent.name == 'profiling':
        out_dir = daily_csv.parent.parent.parent / 'figures' / 'full_metric_panels'
    else:
        out_dir = daily_csv.parent.parent / 'figures' / 'full_metric_panels'
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_daily(daily_csv)
    outputs = []
    for group_name, specs in GROUPS.items():
        outputs.extend(plot_group(rows, out_dir, group_name, specs))
    for p in outputs:
        print(p)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
