#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
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


def style_axis(ax, xticks, xticklabels, title: str) -> None:
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def mean_std_sem(values: np.ndarray) -> tuple[float, float, float]:
    if values.size == 0:
        return float('nan'), float('nan'), float('nan')
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if values.size > 1 else 0.0
    sem = float(std / np.sqrt(values.size)) if values.size > 1 else 0.0
    return mean, std, sem


def load_gray(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise FileNotFoundError(path)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr


def load_labels(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise FileNotFoundError(path)
    if arr.ndim != 2:
        raise ValueError(f'Expected 2D label image: {path}')
    return arr


def edge_map_from_signal(signal_u8: np.ndarray) -> np.ndarray:
    signal_f = signal_u8.astype(np.float32) / 255.0
    gx = cv2.Sobel(signal_f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(signal_f, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    scale = float(np.percentile(mag, 99.5))
    if not np.isfinite(scale) or scale <= 0:
        scale = float(mag.max()) if mag.size else 0.0
    if not np.isfinite(scale) or scale <= 0:
        return np.zeros_like(mag, dtype=np.float32)
    return np.clip(mag / scale, 0.0, 1.0)


def compute_internal_edge_metrics(mask_path: Path, signal_path: Path) -> dict[str, float]:
    labels = load_labels(mask_path)
    signal = load_gray(signal_path)
    edge = edge_map_from_signal(signal)

    unique_labels = [int(v) for v in np.unique(labels) if int(v) > 0]
    if not unique_labels:
        return {
            'central_inside_edge_mean': np.nan,
            'peripheral_inside_edge_mean': np.nan,
            'outer_ring_edge_mean': np.nan,
            'central_inside_fraction': np.nan,
            'central_inside_over_peripheral': np.nan,
            'central_inside_over_outer': np.nan,
        }

    central_num = 0.0
    central_den = 0.0
    periph_num = 0.0
    periph_den = 0.0

    union = labels > 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    outer_ring = cv2.dilate(union.astype(np.uint8), kernel, iterations=1).astype(bool) & (~union)
    outer_ring_edge_mean = float(edge[outer_ring].mean()) if np.any(outer_ring) else np.nan

    for label_id in unique_labels:
        inst = labels == label_id
        if not np.any(inst):
            continue
        dist = cv2.distanceTransform(inst.astype(np.uint8), cv2.DIST_L2, 5)
        max_dist = float(dist.max())
        if max_dist <= 0:
            continue
        centrality = dist / max_dist
        periph_weight = 1.0 - centrality

        central_num += float((edge * centrality)[inst].sum())
        central_den += float(centrality[inst].sum())
        periph_num += float((edge * periph_weight)[inst].sum())
        periph_den += float(periph_weight[inst].sum())

    central_mean = central_num / central_den if central_den > 0 else np.nan
    periph_mean = periph_num / periph_den if periph_den > 0 else np.nan
    central_fraction = central_mean / (central_mean + periph_mean) if np.isfinite(central_mean) and np.isfinite(periph_mean) and (central_mean + periph_mean) > 0 else np.nan
    central_over_periph = central_mean / periph_mean if np.isfinite(central_mean) and np.isfinite(periph_mean) and periph_mean > 0 else np.nan
    central_over_outer = central_mean / outer_ring_edge_mean if np.isfinite(central_mean) and np.isfinite(outer_ring_edge_mean) and outer_ring_edge_mean > 0 else np.nan

    return {
        'central_inside_edge_mean': central_mean,
        'peripheral_inside_edge_mean': periph_mean,
        'outer_ring_edge_mean': outer_ring_edge_mean,
        'central_inside_fraction': central_fraction,
        'central_inside_over_peripheral': central_over_periph,
        'central_inside_over_outer': central_over_outer,
    }


def main() -> int:
    args = parse_args()
    per_image_csv = Path(args.per_image_csv).resolve()
    quant_dir = per_image_csv.parent
    out_root = quant_dir.parent.parent
    figure_dir = out_root / 'figures' / 'fusion_internal_edge_metrics'
    figure_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(per_image_csv)

    metric_rows = []
    total = len(df)
    for idx, row in df.iterrows():
        vals = compute_internal_edge_metrics(Path(row['mask_path']), Path(row['signal_path']))
        metric_rows.append({
            'concentration': row['concentration'],
            'date_key': row['date_key'],
            'date_label': row['date_label'],
            'relative_day': int(row['relative_day']),
            'image_name': row['image_name'],
            **vals,
        })
        if (idx + 1) % 50 == 0 or idx + 1 == total:
            print(f'[{idx + 1}/{total}] processed internal-edge centrality metrics')

    per_metric_df = pd.DataFrame(metric_rows)
    per_metric_csv = quant_dir / 'internal_edge_centrality_per_image.csv'
    per_metric_df.to_csv(per_metric_csv, index=False)

    summary_rows = []
    metric_cols = [
        'central_inside_edge_mean',
        'peripheral_inside_edge_mean',
        'outer_ring_edge_mean',
        'central_inside_fraction',
        'central_inside_over_peripheral',
        'central_inside_over_outer',
    ]
    grouped = per_metric_df.groupby(['concentration', 'date_key', 'date_label', 'relative_day'], sort=False)
    for (concentration, date_key, date_label, relative_day), subset in grouped:
        row = {
            'concentration': concentration,
            'date_key': date_key,
            'date_label': date_label,
            'relative_day': int(relative_day),
            'n_images': int(len(subset)),
        }
        for metric in metric_cols:
            vals = subset[metric].dropna().to_numpy(dtype=float)
            mean, std, sem = mean_std_sem(vals)
            row[f'{metric}_mean'] = mean
            row[f'{metric}_std'] = std
            row[f'{metric}_sem'] = sem
            row[f'{metric}_n_valid'] = int(vals.size)
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    order_map = {c: i for i, c in enumerate(CONCENTRATION_ORDER)}
    summary = summary.sort_values(by=['concentration', 'relative_day'], key=lambda s: s.map(order_map) if s.name == 'concentration' else s)
    summary_csv = quant_dir / 'internal_edge_centrality_daily_summary.csv'
    summary.to_csv(summary_csv, index=False)

    xticks = sorted(summary['relative_day'].unique().tolist())
    xticklabels = [f'D{d}' for d in xticks]
    handles = [Line2D([0], [0], color=CONCENTRATION_COLORS[c], lw=2.4, marker='o', markersize=5, label=c) for c in CONCENTRATION_ORDER if c in summary['concentration'].unique()]

    plot_specs = [
        ('Central Inside Edge', 'central_inside_edge_mean'),
        ('Peripheral Inside Edge', 'peripheral_inside_edge_mean'),
        ('Central Inside Fraction', 'central_inside_fraction'),
        ('Central / Peripheral Edge', 'central_inside_over_peripheral'),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14.8, 9.6), constrained_layout=False)
    axes = axes.flatten()
    for ax, (title, metric) in zip(axes, plot_specs):
        sem_col = f'{metric}_sem'
        mean_col = f'{metric}_mean'
        for concentration in CONCENTRATION_ORDER:
            subset = summary[summary['concentration'] == concentration]
            if subset.empty:
                continue
            x = subset['relative_day'].to_numpy(dtype=float)
            y = subset[mean_col].to_numpy(dtype=float)
            sem = subset[sem_col].to_numpy(dtype=float)
            color = CONCENTRATION_COLORS[concentration]
            ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.0, color=color)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, xticks, xticklabels, title)

    fig.suptitle('App80 10x Replicates: Internal Edge Centrality Metrics', fontsize=15, y=0.975)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.92), ncol=len(handles), frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.07, right=0.985, bottom=0.09, top=0.82, hspace=0.34, wspace=0.24)

    out_png = figure_dir / 'app80_all_concentrations_internal_edge_centrality_metrics.png'
    out_pdf = figure_dir / 'app80_all_concentrations_internal_edge_centrality_metrics.pdf'
    fig.savefig(out_png, dpi=220, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(10.6, 6.3), constrained_layout=False)
    for concentration in CONCENTRATION_ORDER:
        subset = summary[summary['concentration'] == concentration]
        if subset.empty:
            continue
        x = subset['relative_day'].to_numpy(dtype=float)
        y = subset['central_inside_over_peripheral_mean'].to_numpy(dtype=float)
        sem = subset['central_inside_over_peripheral_sem'].to_numpy(dtype=float)
        color = CONCENTRATION_COLORS[concentration]
        ax2.plot(x, y, marker='o', linewidth=2.4, markersize=5.5, color=color, label=concentration)
        ax2.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
    style_axis(ax2, xticks, xticklabels, 'Central Inside Edge / Peripheral Inside Edge')
    fig2.suptitle('App80 10x Replicates: Fusion Proxy from Internal Edge Centrality', fontsize=14, y=0.97)
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=min(5, len(handles)), frameon=False, fontsize=10.5)
    fig2.subplots_adjust(left=0.10, right=0.985, bottom=0.13, top=0.78)

    out_png2 = figure_dir / 'app80_all_concentrations_internal_edge_centrality_fusion_proxy.png'
    out_pdf2 = figure_dir / 'app80_all_concentrations_internal_edge_centrality_fusion_proxy.pdf'
    fig2.savefig(out_png2, dpi=220, bbox_inches='tight')
    fig2.savefig(out_pdf2, bbox_inches='tight')
    plt.close(fig2)

    print(per_metric_csv)
    print(summary_csv)
    print(out_png)
    print(out_pdf)
    print(out_png2)
    print(out_pdf2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
