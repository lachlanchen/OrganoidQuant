#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']
CONCENTRATION_COLORS = {
    'No': '#4d4d4d',
    '10uM': '#1f77b4',
    '20uM': '#2ca02c',
    '50uM': '#ff7f0e',
    '100uM': '#d62728',
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
    rows.sort(key=lambda r: (CONCENTRATION_ORDER.index(r['concentration']), r['relative_day']))
    return rows


def grouped(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c: [] for c in CONCENTRATION_ORDER}
    for row in rows:
        out.setdefault(row['concentration'], []).append(row)
    return {k: v for k, v in out.items() if v}


def style_axis(ax, xticks, xticklabels, title: str) -> None:
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=0)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def main() -> int:
    args = parse_args()
    daily_csv = Path(args.daily_csv).resolve()
    if daily_csv.parent.name == 'quantification' and daily_csv.parent.parent.name == 'profiling':
        out_dir = daily_csv.parent.parent.parent / 'figures'
    else:
        out_dir = daily_csv.parent.parent / 'figures'
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_daily(daily_csv)
    by_conc = grouped(rows)
    xticks = sorted({r['relative_day'] for r in rows})
    xticklabels = [f'D{d}' for d in xticks]

    series = [
        ('Curvature', 'curvature_mean', 'curvature_sem'),
        ('Counts', 'count_mean', 'count_sem'),
        ('Edge Intensity', 'edge_intensity_mean', 'edge_intensity_sem'),
        ('Area', 'total_area_px_mean', 'total_area_px_sem'),
        ('Average Perimeter', 'average_perimeter_px_mean', 'average_perimeter_px_sem'),
        ('Normalized Edge / (Counts * Curvature)', 'normalized_edge_over_count_curvature_mean', 'normalized_edge_over_count_curvature_sem'),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18.5, 10.5), constrained_layout=False)
    axes = axes.flatten()
    handles = [Line2D([0], [0], color=CONCENTRATION_COLORS[c], lw=2.4, marker='o', markersize=5, label=c) for c in CONCENTRATION_ORDER if c in by_conc]
    for ax, (title, mean_col, sem_col) in zip(axes, series):
        for concentration in CONCENTRATION_ORDER:
            subset = by_conc.get(concentration, [])
            if not subset:
                continue
            x = np.array([r['relative_day'] for r in subset], dtype=float)
            y = np.array([float(r[mean_col]) for r in subset], dtype=float)
            sem = np.array([float(r[sem_col]) for r in subset], dtype=float)
            color = CONCENTRATION_COLORS[concentration]
            ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.0, color=color)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, xticks, xticklabels, title)

    fig.suptitle('App80 10x Replicates: Segmentation Metrics by Day Across Concentrations', fontsize=15, y=0.975)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.93), ncol=len(handles), frameon=False, fontsize=11)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.09, top=0.82, hspace=0.34, wspace=0.24)

    png = out_dir / 'app80_all_concentrations_segmentation_metrics.png'
    pdf = out_dir / 'app80_all_concentrations_segmentation_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(10.2, 6.0), constrained_layout=False)
    for concentration in CONCENTRATION_ORDER:
        subset = by_conc.get(concentration, [])
        if not subset:
            continue
        x = np.array([r['relative_day'] for r in subset], dtype=float)
        y = np.array([float(r['normalized_edge_over_count_curvature_mean']) for r in subset], dtype=float)
        sem = np.array([float(r['normalized_edge_over_count_curvature_sem']) for r in subset], dtype=float)
        color = CONCENTRATION_COLORS[concentration]
        ax2.plot(x, y, marker='o', linewidth=2.4, markersize=5.5, color=color, label=concentration)
        ax2.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
    style_axis(ax2, xticks, xticklabels, 'Normalized Edge / (Counts * Curvature)')
    fig2.suptitle('App80 10x Replicates: Normalized Edge / (Counts * Curvature)', fontsize=14, y=0.97)
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=min(5, len(handles)), frameon=False, fontsize=10.5)
    fig2.subplots_adjust(left=0.09, right=0.985, bottom=0.13, top=0.78)

    png2 = out_dir / 'app80_all_concentrations_normalized_edge_over_count_curvature.png'
    pdf2 = out_dir / 'app80_all_concentrations_normalized_edge_over_count_curvature.pdf'
    fig2.savefig(png2, dpi=220, bbox_inches='tight')
    fig2.savefig(pdf2, bbox_inches='tight')
    plt.close(fig2)

    print(png)
    print(pdf)
    print(png2)
    print(pdf2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
