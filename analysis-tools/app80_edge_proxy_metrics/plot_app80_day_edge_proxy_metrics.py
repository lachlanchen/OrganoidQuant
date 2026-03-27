#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

THIS_DIR = Path(__file__).resolve().parent
FUSION_TOOL_DIR = THIS_DIR.parent / 'fusion_blind_prompt'
sys.path.insert(0, str(FUSION_TOOL_DIR))

from plot_edge_proxy_metrics import DATE_RE, compute_metrics, load_gray_u8  # noqa: E402

TIF_RE = re.compile(r'(?i)10x\d+\.tif$')


def parse_date_label(label: str) -> datetime:
    match = DATE_RE.search(label)
    if not match:
        raise ValueError(f'Could not parse date from {label}')
    return datetime.strptime(f"2025-12-{match.group('day')}", '%Y-%m-%d')


def list_10x_images(day_dir: Path) -> list[Path]:
    images = [path for path in day_dir.iterdir() if path.is_file() and TIF_RE.search(path.name)]
    images.sort(key=lambda path: path.name.lower())
    return images


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return float('nan'), float('nan')
    arr = np.array(values, dtype=np.float64)
    if arr.size == 1:
        return float(arr[0]), 0.0
    return float(arr.mean()), float(arr.std(ddof=1))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f'No rows for {path}')
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot_metric(summary_rows: list[dict], metric_key: str, title: str, ylabel: str, color: str, dest_png: Path, dest_pdf: Path) -> None:
    x = [row['relative_offset_days'] for row in summary_rows]
    y = [row[f'{metric_key}_mean'] for row in summary_rows]
    yerr = [row[f'{metric_key}_std'] for row in summary_rows]
    labels = [f"D{int(row['relative_offset_days'])}" for row in summary_rows]
    counts = [int(row['n_images']) for row in summary_rows]

    fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
    ax.plot(x, y, color=color, marker='o', linewidth=2.4, markersize=6)
    lower = np.array(y) - np.array(yerr)
    upper = np.array(y) + np.array(yerr)
    ax.fill_between(x, lower, upper, color=color, alpha=0.18)
    for xi, yi, lbl, n in zip(x, y, labels, counts):
        ax.annotate(f'{lbl}\nn={n}', (xi, yi), textcoords='offset points', xytext=(0, 9), ha='center', fontsize=9, color=color)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('Relative Day')
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.set_xticks(x, labels)
    fig.savefig(dest_png, dpi=220, bbox_inches='tight')
    fig.savefig(dest_pdf, bbox_inches='tight')
    plt.close(fig)


def plot_combined(summary_rows: list[dict], dest_png: Path, dest_pdf: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    specs = [
        ('edge_density', 'Edge Density', '#B11E35'),
        ('edge_reciprocal', 'Reciprocal Edge Density', '#1D4E89'),
        ('gradient_mean', 'Gradient Mean', '#2C6E49'),
        ('gradient_reciprocal', 'Reciprocal Gradient Mean', '#D17B0F'),
    ]
    x = [row['relative_offset_days'] for row in summary_rows]
    labels = [f"D{int(row['relative_offset_days'])}" for row in summary_rows]
    counts = [int(row['n_images']) for row in summary_rows]
    for ax, (metric_key, title, color) in zip(axes.ravel(), specs):
        y = [row[f'{metric_key}_mean'] for row in summary_rows]
        yerr = [row[f'{metric_key}_std'] for row in summary_rows]
        ax.plot(x, y, color=color, marker='o', linewidth=2.2, markersize=6)
        ax.fill_between(x, np.array(y) - np.array(yerr), np.array(y) + np.array(yerr), color=color, alpha=0.18)
        for xi, yi, lbl, n in zip(x, y, labels, counts):
            ax.annotate(f'{lbl}\nn={n}', (xi, yi), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=8, color=color)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlabel('Relative Day')
        ax.set_xticks(x, labels)
        ax.grid(True, alpha=0.25)
    fig.suptitle('App80 10uM All 10x Images: Edge/Gradient Proxy Trends', fontsize=16, fontweight='bold')
    fig.savefig(dest_png, dpi=220, bbox_inches='tight')
    fig.savefig(dest_pdf, bbox_inches='tight')
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description='Compute day-wise edge/gradient proxy metrics for all 10x images across App80 day folders')
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('day_dirs', nargs='+', type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    dated_dirs = []
    for day_dir in args.day_dirs:
        date_label = day_dir.name
        day_dt = parse_date_label(date_label)
        dated_dirs.append((day_dt, date_label, day_dir))
    dated_dirs.sort(key=lambda item: item[0])
    first_dt = dated_dirs[0][0]

    per_image_rows: list[dict] = []
    grouped: dict[str, list[dict]] = defaultdict(list)

    for day_dt, date_label, day_dir in dated_dirs:
        images = list_10x_images(day_dir)
        rel_days = (day_dt - first_dt).days
        for image_path in images:
            gray_u8 = load_gray_u8(image_path)
            metrics = compute_metrics(gray_u8)
            row = {
                'source_date': date_label,
                'relative_offset_days': rel_days,
                'image_name': image_path.name,
                'image_path': str(image_path),
                'edge_pixels': metrics['edge_pixels'],
                'masked_pixels': metrics['masked_pixels'],
                'edge_density': metrics['edge_density'],
                'edge_reciprocal': metrics['edge_reciprocal'],
                'gradient_mean': metrics['gradient_mean'],
                'gradient_reciprocal': metrics['gradient_reciprocal'],
                'canny_low': metrics['canny_low'],
                'canny_high': metrics['canny_high'],
            }
            per_image_rows.append(row)
            grouped[date_label].append(row)

    per_image_rows.sort(key=lambda row: (row['relative_offset_days'], row['image_name'].lower()))
    summary_rows: list[dict] = []
    for day_dt, date_label, _day_dir in dated_dirs:
        rows = grouped[date_label]
        rel_days = (day_dt - first_dt).days
        edge_density_values = [float(row['edge_density']) for row in rows]
        edge_recip_values = [float(row['edge_reciprocal']) for row in rows]
        gradient_mean_values = [float(row['gradient_mean']) for row in rows]
        gradient_recip_values = [float(row['gradient_reciprocal']) for row in rows]
        edge_density_mean, edge_density_std = mean_std(edge_density_values)
        edge_recip_mean, edge_recip_std = mean_std(edge_recip_values)
        gradient_mean_mean, gradient_mean_std = mean_std(gradient_mean_values)
        gradient_recip_mean, gradient_recip_std = mean_std(gradient_recip_values)
        summary_rows.append({
            'source_date': date_label,
            'relative_offset_days': rel_days,
            'n_images': len(rows),
            'edge_density_mean': edge_density_mean,
            'edge_density_std': edge_density_std,
            'edge_reciprocal_mean': edge_recip_mean,
            'edge_reciprocal_std': edge_recip_std,
            'gradient_mean_mean': gradient_mean_mean,
            'gradient_mean_std': gradient_mean_std,
            'gradient_reciprocal_mean': gradient_recip_mean,
            'gradient_reciprocal_std': gradient_recip_std,
        })

    per_image_csv = output_dir / 'app80_10uM_edge_proxy_per_image.csv'
    daily_summary_csv = output_dir / 'app80_10uM_edge_proxy_daily_summary.csv'
    write_csv(per_image_csv, per_image_rows)
    write_csv(daily_summary_csv, summary_rows)

    plot_metric(
        summary_rows,
        'edge_reciprocal',
        'App80 10uM: Mean Reciprocal Edge Density by Day',
        '1 / Edge Density',
        '#1D4E89',
        output_dir / 'app80_10uM_edge_reciprocal_by_day.png',
        output_dir / 'app80_10uM_edge_reciprocal_by_day.pdf',
    )
    plot_metric(
        summary_rows,
        'gradient_reciprocal',
        'App80 10uM: Mean Reciprocal Gradient by Day',
        '1 / Gradient Mean',
        '#D17B0F',
        output_dir / 'app80_10uM_gradient_reciprocal_by_day.png',
        output_dir / 'app80_10uM_gradient_reciprocal_by_day.pdf',
    )
    plot_combined(
        summary_rows,
        output_dir / 'app80_10uM_edge_proxy_combined_by_day.png',
        output_dir / 'app80_10uM_edge_proxy_combined_by_day.pdf',
    )

    print(json.dumps({
        'output_dir': str(output_dir),
        'n_days': len(summary_rows),
        'n_images': len(per_image_rows),
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_summary_csv),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
