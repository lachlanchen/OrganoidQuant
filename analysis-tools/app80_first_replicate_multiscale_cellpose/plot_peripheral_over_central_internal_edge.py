#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
    p.add_argument('--per-image-csv', required=True)
    return p.parse_args()


def mean_std_sem(values: np.ndarray) -> tuple[float, float, float]:
    if values.size == 0:
        return float('nan'), float('nan'), float('nan')
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if values.size > 1 else 0.0
    sem = float(std / np.sqrt(values.size)) if values.size > 1 else 0.0
    return mean, std, sem


def main() -> int:
    args = parse_args()
    per_image_csv = Path(args.per_image_csv).resolve()
    quant_dir = per_image_csv.parent
    out_root = quant_dir.parent.parent
    figure_dir = out_root / 'figures' / 'fusion_internal_edge_metrics'
    figure_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(per_image_csv)
    for col in ['central_inside_edge_mean', 'peripheral_inside_edge_mean', 'relative_day']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    valid = (df['central_inside_edge_mean'] > 0) & (df['peripheral_inside_edge_mean'] >= 0)
    df['peripheral_over_central'] = np.where(
        valid,
        df['peripheral_inside_edge_mean'] / df['central_inside_edge_mean'],
        np.nan,
    )

    summary_rows = []
    grouped = df.groupby(['concentration', 'date_key', 'date_label', 'relative_day'], sort=False)
    for (concentration, date_key, date_label, relative_day), subset in grouped:
        vals = subset['peripheral_over_central'].dropna().to_numpy(dtype=float)
        mean, std, sem = mean_std_sem(vals)
        summary_rows.append({
            'concentration': concentration,
            'date_key': date_key,
            'date_label': date_label,
            'relative_day': int(relative_day),
            'n_images': int(len(subset)),
            'n_valid': int(vals.size),
            'peripheral_over_central_mean': mean,
            'peripheral_over_central_std': std,
            'peripheral_over_central_sem': sem,
        })

    summary = pd.DataFrame(summary_rows)
    order_map = {c: i for i, c in enumerate(CONCENTRATION_ORDER)}
    summary = summary.sort_values(by=['concentration', 'relative_day'], key=lambda s: s.map(order_map) if s.name == 'concentration' else s)

    out_csv = quant_dir / 'peripheral_over_central_daily_summary.csv'
    summary.to_csv(out_csv, index=False)

    fig, ax = plt.subplots(figsize=(10.6, 6.3), constrained_layout=False)
    xticks = sorted(summary['relative_day'].unique().tolist())
    xticklabels = [f'D{d}' for d in xticks]
    for concentration in CONCENTRATION_ORDER:
        subset = summary[summary['concentration'] == concentration]
        if subset.empty:
            continue
        x = subset['relative_day'].to_numpy(dtype=float)
        y = subset['peripheral_over_central_mean'].to_numpy(dtype=float)
        sem = subset['peripheral_over_central_sem'].to_numpy(dtype=float)
        color = CONCENTRATION_COLORS[concentration]
        ax.plot(x, y, marker='o', linewidth=2.4, markersize=5.5, color=color, label=concentration)
        ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)

    ax.set_title('Peripheral Inside Edge / Central Inside Edge', fontsize=13, pad=10)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.suptitle('App80 10x Replicates: Peripheral / Central Internal Edge Ratio', fontsize=14, y=0.97)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=5, frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.10, right=0.985, bottom=0.13, top=0.78)

    out_png = figure_dir / 'app80_all_concentrations_peripheral_over_central_internal_edge.png'
    out_pdf = figure_dir / 'app80_all_concentrations_peripheral_over_central_internal_edge.pdf'
    fig.savefig(out_png, dpi=220, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)

    print(out_csv)
    print(out_png)
    print(out_pdf)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
