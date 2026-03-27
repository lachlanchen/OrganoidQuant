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
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str((THIS_DIR.parent / 'fusion_blind_prompt').resolve()))

from plot_app80_day_edge_proxy_metrics import list_10x_images, mean_std, parse_date_label, write_csv  # noqa: E402
from plot_edge_proxy_metrics import compute_metrics, load_gray_u8  # noqa: E402

CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']
COLORS = {
    'No': '#4C4C4C',
    '10uM': '#1D4E89',
    '20uM': '#2C6E49',
    '50uM': '#D17B0F',
    '100uM': '#B11E35',
}
DATE_RE = re.compile(r'(?P<day>\d{2})-十二月-2025')


def relative_day(date_label: str, first_dt: datetime) -> int:
    match = DATE_RE.search(date_label)
    if not match:
        raise ValueError(f'Could not parse date from {date_label}')
    dt = datetime.strptime(f"2025-12-{match.group('day')}", '%Y-%m-%d')
    return (dt - first_dt).days


def collect_concentration_dirs(root: Path) -> list[tuple[str, Path]]:
    found = []
    for name in CONCENTRATION_ORDER:
        path = root / name
        if path.is_dir():
            found.append((name, path))
    return found


def plot_multi(summary_rows: list[dict], metric_key: str, title: str, ylabel: str, dest_png: Path, dest_pdf: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 6), constrained_layout=True)
    for concentration in CONCENTRATION_ORDER:
        rows = [row for row in summary_rows if row['concentration'] == concentration]
        if not rows:
            continue
        rows.sort(key=lambda row: row['relative_offset_days'])
        x = [row['relative_offset_days'] for row in rows]
        y = [row[f'{metric_key}_mean'] for row in rows]
        yerr = [row[f'{metric_key}_std'] for row in rows]
        color = COLORS[concentration]
        ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.5, color=color, label=concentration)
        ax.fill_between(x, np.array(y) - np.array(yerr), np.array(y) + np.array(yerr), color=color, alpha=0.12)
    all_days = sorted({int(row['relative_offset_days']) for row in summary_rows})
    ax.set_xticks(all_days, [f'D{d}' for d in all_days])
    ax.set_xlabel('Relative Day')
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False, ncol=3)
    fig.savefig(dest_png, dpi=220, bbox_inches='tight')
    fig.savefig(dest_pdf, bbox_inches='tight')
    plt.close(fig)


def plot_combined(summary_rows: list[dict], dest_png: Path, dest_pdf: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    specs = [
        ('edge_density', 'Edge Density', 'Edge Density'),
        ('edge_reciprocal', 'Reciprocal Edge Density', '1 / Edge Density'),
        ('gradient_mean', 'Gradient Mean', 'Gradient Mean'),
        ('gradient_reciprocal', 'Reciprocal Gradient Mean', '1 / Gradient Mean'),
    ]
    all_days = sorted({int(row['relative_offset_days']) for row in summary_rows})

    for ax, (metric_key, title, ylabel) in zip(axes.ravel(), specs):
        for concentration in CONCENTRATION_ORDER:
            rows = [row for row in summary_rows if row['concentration'] == concentration]
            if not rows:
                continue
            rows.sort(key=lambda row: row['relative_offset_days'])
            x = [row['relative_offset_days'] for row in rows]
            y = [row[f'{metric_key}_mean'] for row in rows]
            yerr = [row[f'{metric_key}_std'] for row in rows]
            color = COLORS[concentration]
            ax.plot(x, y, marker='o', linewidth=2.0, markersize=5, color=color, label=concentration)
            ax.fill_between(x, np.array(y) - np.array(yerr), np.array(y) + np.array(yerr), color=color, alpha=0.10)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlabel('Relative Day')
        ax.set_ylabel(ylabel)
        ax.set_xticks(all_days, [f'D{d}' for d in all_days])
        ax.grid(True, alpha=0.25)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=5, frameon=False)
    fig.suptitle('App80 All Concentrations: Edge/Gradient Proxy Trends', fontsize=16, fontweight='bold')
    fig.savefig(dest_png, dpi=220, bbox_inches='tight')
    fig.savefig(dest_pdf, bbox_inches='tight')
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description='Compute and compare App80 edge proxy metrics across concentrations')
    parser.add_argument('app80_root', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()

    root = args.app80_root
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    concentration_dirs = collect_concentration_dirs(root)
    if not concentration_dirs:
        raise RuntimeError(f'No concentration directories found under {root}')

    all_dates = []
    per_image_rows: list[dict] = []
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for concentration, conc_dir in concentration_dirs:
        day_dirs = [path for path in conc_dir.iterdir() if path.is_dir()]
        day_dirs.sort(key=lambda path: path.name)
        for day_dir in day_dirs:
            all_dates.append(day_dir.name)

    first_dt = min(parse_date_label(label) for label in all_dates)

    for concentration, conc_dir in concentration_dirs:
        day_dirs = [path for path in conc_dir.iterdir() if path.is_dir()]
        day_dirs.sort(key=lambda path: path.name)
        for day_dir in day_dirs:
            date_label = day_dir.name
            rel_days = relative_day(date_label, first_dt)
            images = list_10x_images(day_dir)
            for image_path in images:
                gray_u8 = load_gray_u8(image_path)
                metrics = compute_metrics(gray_u8)
                row = {
                    'concentration': concentration,
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
                grouped[(concentration, date_label)].append(row)

    per_image_rows.sort(key=lambda row: (CONCENTRATION_ORDER.index(row['concentration']), row['relative_offset_days'], row['image_name'].lower()))
    summary_rows: list[dict] = []
    for concentration, conc_dir in concentration_dirs:
        day_dirs = [path for path in conc_dir.iterdir() if path.is_dir()]
        day_dirs.sort(key=lambda path: path.name)
        for day_dir in day_dirs:
            date_label = day_dir.name
            rows = grouped[(concentration, date_label)]
            rel_days = relative_day(date_label, first_dt)
            edge_density_values = [float(row['edge_density']) for row in rows]
            edge_recip_values = [float(row['edge_reciprocal']) for row in rows]
            gradient_mean_values = [float(row['gradient_mean']) for row in rows]
            gradient_recip_values = [float(row['gradient_reciprocal']) for row in rows]
            edge_density_mean, edge_density_std = mean_std(edge_density_values)
            edge_recip_mean, edge_recip_std = mean_std(edge_recip_values)
            gradient_mean_mean, gradient_mean_std = mean_std(gradient_mean_values)
            gradient_recip_mean, gradient_recip_std = mean_std(gradient_recip_values)
            summary_rows.append({
                'concentration': concentration,
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

    write_csv(output_dir / 'app80_all_concentration_edge_proxy_per_image.csv', per_image_rows)
    write_csv(output_dir / 'app80_all_concentration_edge_proxy_daily_summary.csv', summary_rows)

    plot_multi(
        summary_rows,
        'edge_reciprocal',
        'App80: Reciprocal Edge Density by Day and Concentration',
        '1 / Edge Density',
        output_dir / 'app80_all_concentration_edge_reciprocal_by_day.png',
        output_dir / 'app80_all_concentration_edge_reciprocal_by_day.pdf',
    )
    plot_multi(
        summary_rows,
        'gradient_reciprocal',
        'App80: Reciprocal Gradient by Day and Concentration',
        '1 / Gradient Mean',
        output_dir / 'app80_all_concentration_gradient_reciprocal_by_day.png',
        output_dir / 'app80_all_concentration_gradient_reciprocal_by_day.pdf',
    )
    plot_combined(
        summary_rows,
        output_dir / 'app80_all_concentration_edge_proxy_combined_by_day.png',
        output_dir / 'app80_all_concentration_edge_proxy_combined_by_day.pdf',
    )

    print(json.dumps({
        'output_dir': str(output_dir),
        'n_concentrations': len(concentration_dirs),
        'n_days': len({(row['concentration'], row['source_date']) for row in summary_rows}),
        'n_images': len(per_image_rows),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
