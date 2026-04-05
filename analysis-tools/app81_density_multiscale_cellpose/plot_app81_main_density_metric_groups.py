#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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
    'growth': [
        ('Counts', 'count_mean', 'count_sem'),
        ('Total Area', 'total_area_px_mean', 'total_area_px_sem'),
        ('Average Perimeter', 'average_perimeter_px_mean', 'average_perimeter_px_sem'),
    ],
    'fusion': [
        ('Edge Intensity', 'edge_intensity_mean', 'edge_intensity_sem'),
        ('Curvature', 'curvature_mean', 'curvature_sem'),
        ('Normalized Edge / (Counts * Curvature)', 'normalized_edge_over_count_curvature_mean', 'normalized_edge_over_count_curvature_sem'),
    ],
    'differentiation': [
        ('Roundness', 'roundness_mean', 'roundness_sem'),
        ('Roundness Deviation (Norm)', 'roundness_deviation_norm_mean', 'roundness_deviation_norm_sem'),
        ('Roundness Deviation (Pixels)', 'roundness_deviation_px_total_mean', 'roundness_deviation_px_total_sem'),
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
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=0)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def maybe_sci_y(ax, series_key: str) -> None:
    if 'area' in series_key or 'perimeter' in series_key or 'px_total' in series_key:
        ax.ticklabel_format(style='scientific', axis='y', scilimits=(0, 0))


def plot_group(rows: list[dict], out_dir: Path, group_name: str, specs: list[tuple[str, str, str]]) -> tuple[Path, Path]:
    by_cond = grouped(rows)
    xticks = sorted({r['relative_day'] for r in rows})
    xticklabels = [f'D{d}' for d in xticks]
    handles = [
        Line2D([0], [0], color=CONDITION_COLORS[c], lw=2.4, marker='o', markersize=5, label=CONDITION_LABELS[c])
        for c in CONDITION_ORDER if c in by_cond
    ]

    fig, axes = plt.subplots(1, 3, figsize=(17.0, 5.8), constrained_layout=False)
    for ax, (title, mean_col, sem_col) in zip(axes, specs):
        for condition in CONDITION_ORDER:
            subset = by_cond.get(condition, [])
            if not subset:
                continue
            x = np.array([r['relative_day'] for r in subset], dtype=float)
            y = np.array([float(r[mean_col]) for r in subset], dtype=float)
            sem = np.array([float(r[sem_col]) for r in subset], dtype=float)
            color = CONDITION_COLORS[condition]
            ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.0, color=color)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, xticks, xticklabels, title)
        maybe_sci_y(ax, mean_col)

    suptitle = {
        'growth': 'App81 10x Main Phase: Growth Metrics',
        'fusion': 'App81 10x Main Phase: Fusion Metrics',
        'differentiation': 'App81 10x Main Phase: Differentiation Metrics',
    }[group_name]
    fig.suptitle(suptitle, fontsize=15, y=0.98)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.91), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.14, top=0.79, wspace=0.24)

    png = out_dir / f'app81_main_density_{group_name}_metrics.png'
    pdf = out_dir / f'app81_main_density_{group_name}_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)
    return png, pdf


def main() -> int:
    args = parse_args()
    daily_csv = Path(args.daily_csv).resolve()
    if daily_csv.parent.name == 'quantification' and daily_csv.parent.parent.name == 'profiling':
        out_dir = daily_csv.parent.parent.parent / 'figures' / 'metric_group_panels'
    else:
        out_dir = daily_csv.parent.parent / 'figures' / 'metric_group_panels'
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
