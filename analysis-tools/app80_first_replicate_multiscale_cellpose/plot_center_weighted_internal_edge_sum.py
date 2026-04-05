#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
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
    p.add_argument('--alpha', type=float, default=5.0)
    return p.parse_args()


def mean_std_sem(values: np.ndarray) -> tuple[float, float, float]:
    if values.size == 0:
        return 0.0, 0.0, 0.0
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if values.size > 1 else 0.0
    sem = float(std / np.sqrt(values.size)) if values.size > 1 else 0.0
    return mean, std, sem


def style_axis(ax, xticks, xticklabels, title: str) -> None:
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


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


def exponential_center_weight(centrality: np.ndarray, alpha: float) -> np.ndarray:
    denom = np.expm1(alpha)
    if not np.isfinite(denom) or denom <= 0:
        return centrality
    return np.expm1(alpha * centrality) / denom


def center_weighted_edge_sum(mask_path: Path, signal_path: Path, alpha: float) -> dict[str, float]:
    labels = load_labels(mask_path)
    signal = load_gray(signal_path)
    edge = edge_map_from_signal(signal)

    total_sum = 0.0
    total_weight = 0.0
    instance_sums: list[float] = []
    unique_labels = [int(v) for v in np.unique(labels) if int(v) > 0]

    for label_id in unique_labels:
        ys, xs = np.where(labels == label_id)
        if ys.size == 0:
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        inst = (labels[y0:y1, x0:x1] == label_id).astype(np.uint8)
        dist = cv2.distanceTransform(inst, cv2.DIST_L2, 5)
        max_dist = float(dist.max())
        if max_dist <= 0:
            continue
        centrality = dist / max_dist
        weight = exponential_center_weight(centrality, alpha)
        edge_crop = edge[y0:y1, x0:x1]
        weighted_sum = float((edge_crop * weight * inst).sum())
        total_sum += weighted_sum
        total_weight += float((weight * inst).sum())
        instance_sums.append(weighted_sum)

    return {
        'center_weighted_edge_sum': total_sum,
        'center_weighted_edge_weight_sum': total_weight,
        'center_weighted_edge_mean': (total_sum / total_weight) if total_weight > 0 else 0.0,
        'instance_center_weighted_edge_sum_mean': float(np.mean(instance_sums)) if instance_sums else 0.0,
    }


def main() -> int:
    args = parse_args()
    per_image_csv = Path(args.per_image_csv).resolve()
    quant_dir = per_image_csv.parent
    out_root = quant_dir.parent.parent
    figure_dir = out_root / 'figures' / 'fusion_internal_edge_metrics'
    figure_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(per_image_csv)

    per_rows = []
    total = len(df)
    for idx, row in df.iterrows():
        vals = center_weighted_edge_sum(Path(row['mask_path']), Path(row['signal_path']), args.alpha)
        per_rows.append({
            'concentration': row['concentration'],
            'date_key': row['date_key'],
            'date_label': row['date_label'],
            'relative_day': int(row['relative_day']),
            'image_name': row['image_name'],
            'count': int(row['count']),
            **vals,
        })
        if (idx + 1) % 50 == 0 or idx + 1 == total:
            print(f'[{idx + 1}/{total}] processed center-weighted edge sums', flush=True)

    per_df = pd.DataFrame(per_rows)
    per_out = quant_dir / 'center_weighted_internal_edge_sum_per_image.csv'
    per_df.to_csv(per_out, index=False)

    summary_rows = []
    grouped = per_df.groupby(['concentration', 'date_key', 'date_label', 'relative_day'], sort=False)
    for (concentration, date_key, date_label, relative_day), subset in grouped:
        vals = subset['center_weighted_edge_sum'].to_numpy(dtype=float)
        mean, std, sem = mean_std_sem(vals)
        summary_rows.append({
            'concentration': concentration,
            'date_key': date_key,
            'date_label': date_label,
            'relative_day': int(relative_day),
            'n_images': int(len(subset)),
            'center_weighted_edge_sum_mean': mean,
            'center_weighted_edge_sum_std': std,
            'center_weighted_edge_sum_sem': sem,
        })

    summary = pd.DataFrame(summary_rows)
    order_map = {c: i for i, c in enumerate(CONCENTRATION_ORDER)}
    summary = summary.sort_values(
        by=['concentration', 'relative_day'],
        key=lambda s: s.map(order_map) if s.name == 'concentration' else s,
    )
    summary_out = quant_dir / 'center_weighted_internal_edge_sum_daily_summary.csv'
    summary.to_csv(summary_out, index=False)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), constrained_layout=False)
    xticks = sorted(summary['relative_day'].unique().tolist())
    xticklabels = [f'D{d}' for d in xticks]
    for concentration in CONCENTRATION_ORDER:
        subset = summary[summary['concentration'] == concentration]
        if subset.empty:
            continue
        x = subset['relative_day'].to_numpy(dtype=float)
        y = subset['center_weighted_edge_sum_mean'].to_numpy(dtype=float)
        sem = subset['center_weighted_edge_sum_sem'].to_numpy(dtype=float)
        color = CONCENTRATION_COLORS[concentration]
        ax.plot(x, y, marker='o', linewidth=2.4, markersize=5.5, color=color, label=concentration)
        ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)

    style_axis(ax, xticks, xticklabels, 'Center-Weighted Internal Edge Sum')
    fig.suptitle('App80 10x Replicates: Center-Weighted Internal Edge Sum', fontsize=14, y=0.97)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=5, frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.10, right=0.985, bottom=0.13, top=0.78)

    out_png = figure_dir / 'app80_all_concentrations_center_weighted_internal_edge_sum.png'
    out_pdf = figure_dir / 'app80_all_concentrations_center_weighted_internal_edge_sum.pdf'
    fig.savefig(out_png, dpi=220, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)

    print(per_out)
    print(summary_out)
    print(out_png)
    print(out_pdf)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
