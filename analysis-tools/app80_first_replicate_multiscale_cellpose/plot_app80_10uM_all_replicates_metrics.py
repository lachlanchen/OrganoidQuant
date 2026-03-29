#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--daily-csv', required=True)
    return p.parse_args()


def read_daily(path: Path) -> list[dict]:
    rows = []
    with path.open('r', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    rows.sort(key=lambda r: int(r['relative_day']))
    return rows


def main() -> int:
    args = parse_args()
    daily_csv = Path(args.daily_csv).resolve()
    out_dir = daily_csv.parent.parent / 'figures'
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_daily(daily_csv)

    x = [int(r['relative_day']) for r in rows]
    labels = [r['date_label'] for r in rows]
    series = [
        ('Curvature', 'curvature_mean', 'curvature_sem', '#1f77b4'),
        ('Counts', 'count_mean', 'count_sem', '#d62728'),
        ('Edge Intensity', 'edge_intensity_mean', 'edge_intensity_sem', '#2ca02c'),
        ('Area', 'total_area_px_mean', 'total_area_px_sem', '#9467bd'),
        ('Average Perimeter', 'average_perimeter_px_mean', 'average_perimeter_px_sem', '#ff7f0e'),
        ('Normalized Edge / (Counts * Curvature)', 'normalized_edge_over_count_curvature_mean', 'normalized_edge_over_count_curvature_sem', '#111111'),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10), constrained_layout=True)
    axes = axes.flatten()
    for ax, (title, mean_col, sem_col, color) in zip(axes, series):
        y = np.array([float(r[mean_col]) for r in rows], dtype=float)
        sem = np.array([float(r[sem_col]) for r in rows], dtype=float)
        ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.5, color=color)
        ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.18, linewidth=0)
        ax.set_title(title, fontsize=12, pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha='right')
        ax.grid(True, alpha=0.25)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
    fig.suptitle('App80 10uM All 10x Replicates: Segmentation-Derived Metrics by Day', fontsize=15, y=1.02)
    png = out_dir / 'app80_10uM_all_replicates_segmentation_metrics.png'
    pdf = out_dir / 'app80_10uM_all_replicates_segmentation_metrics.pdf'
    fig.savefig(png, dpi=220, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(8.8, 5.4), constrained_layout=True)
    y = np.array([float(r['normalized_edge_over_count_curvature_mean']) for r in rows], dtype=float)
    sem = np.array([float(r['normalized_edge_over_count_curvature_sem']) for r in rows], dtype=float)
    ax2.plot(x, y, marker='o', linewidth=2.4, markersize=6, color='#111111')
    ax2.fill_between(x, y - sem, y + sem, color='#111111', alpha=0.18, linewidth=0)
    ax2.set_title('Normalized Edge / (Counts * Curvature)', fontsize=13, pad=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=25, ha='right')
    ax2.grid(True, alpha=0.25)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    png2 = out_dir / 'app80_10uM_all_replicates_normalized_edge_over_count_curvature.png'
    pdf2 = out_dir / 'app80_10uM_all_replicates_normalized_edge_over_count_curvature.pdf'
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
