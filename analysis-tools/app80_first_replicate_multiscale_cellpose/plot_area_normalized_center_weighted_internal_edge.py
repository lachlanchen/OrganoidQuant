#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import plot_center_weighted_internal_edge_sum as base


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--per-image-csv', required=True)
    p.add_argument('--alpha', type=float, default=5.0)
    return p.parse_args()


def per_instance_area_normalized_values(mask_path: Path, signal_path: Path, alpha: float) -> dict[str, float]:
    labels = base.load_labels(mask_path)
    signal = base.load_gray(signal_path)
    edge = base.edge_map_from_signal(signal)

    values: list[float] = []
    unique_labels = [int(v) for v in np.unique(labels) if int(v) > 0]
    for label_id in unique_labels:
        ys, xs = np.where(labels == label_id)
        if ys.size == 0:
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        inst = (labels[y0:y1, x0:x1] == label_id).astype(np.uint8)
        area = int(inst.sum())
        if area <= 0:
            continue
        dist = cv2.distanceTransform(inst, cv2.DIST_L2, 5)
        max_dist = float(dist.max())
        if max_dist <= 0:
            continue
        centrality = dist / max_dist
        weight = base.exponential_center_weight(centrality, alpha)
        edge_crop = edge[y0:y1, x0:x1]
        weighted_sum = float((edge_crop * weight * inst).sum())
        values.append(weighted_sum / float(area))

    arr = np.asarray(values, dtype=np.float64)
    return {
        'instance_count_valid': int(arr.size),
        'area_normalized_center_weighted_edge_instance_mean': float(arr.mean()) if arr.size else 0.0,
        'area_normalized_center_weighted_edge_instance_std': float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
        'area_normalized_center_weighted_edge_instance_median': float(np.median(arr)) if arr.size else 0.0,
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
        vals = per_instance_area_normalized_values(Path(row['mask_path']), Path(row['signal_path']), args.alpha)
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
            print(f'[{idx + 1}/{total}] processed area-normalized center-weighted edge metric', flush=True)

    per_df = pd.DataFrame(per_rows)
    per_out = quant_dir / 'area_normalized_center_weighted_internal_edge_per_image.csv'
    per_df.to_csv(per_out, index=False)

    summary_rows = []
    grouped = per_df.groupby(['concentration', 'date_key', 'date_label', 'relative_day'], sort=False)
    for (concentration, date_key, date_label, relative_day), subset in grouped:
        vals = subset['area_normalized_center_weighted_edge_instance_mean'].to_numpy(dtype=float)
        mean, std, sem = base.mean_std_sem(vals)
        summary_rows.append({
            'concentration': concentration,
            'date_key': date_key,
            'date_label': date_label,
            'relative_day': int(relative_day),
            'n_images': int(len(subset)),
            'area_normalized_center_weighted_edge_instance_mean_mean': mean,
            'area_normalized_center_weighted_edge_instance_mean_std': std,
            'area_normalized_center_weighted_edge_instance_mean_sem': sem,
        })

    summary = pd.DataFrame(summary_rows)
    order_map = {c: i for i, c in enumerate(base.CONCENTRATION_ORDER)}
    summary = summary.sort_values(
        by=['concentration', 'relative_day'],
        key=lambda s: s.map(order_map) if s.name == 'concentration' else s,
    )
    summary_out = quant_dir / 'area_normalized_center_weighted_internal_edge_daily_summary.csv'
    summary.to_csv(summary_out, index=False)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), constrained_layout=False)
    xticks = sorted(summary['relative_day'].unique().tolist())
    xticklabels = [f'D{d}' for d in xticks]
    for concentration in base.CONCENTRATION_ORDER:
        subset = summary[summary['concentration'] == concentration]
        if subset.empty:
            continue
        x = subset['relative_day'].to_numpy(dtype=float)
        y = subset['area_normalized_center_weighted_edge_instance_mean_mean'].to_numpy(dtype=float)
        sem = subset['area_normalized_center_weighted_edge_instance_mean_sem'].to_numpy(dtype=float)
        color = base.CONCENTRATION_COLORS[concentration]
        ax.plot(x, y, marker='o', linewidth=2.4, markersize=5.5, color=color, label=concentration)
        ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)

    base.style_axis(ax, xticks, xticklabels, 'Area-Normalized Center-Weighted Internal Edge')
    fig.suptitle('App80 10x Replicates: Area-Normalized Center-Weighted Internal Edge', fontsize=14, y=0.97)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=5, frameon=False, fontsize=10.5)
    fig.subplots_adjust(left=0.10, right=0.985, bottom=0.13, top=0.78)

    out_png = figure_dir / 'app80_all_concentrations_area_normalized_center_weighted_internal_edge.png'
    out_pdf = figure_dir / 'app80_all_concentrations_area_normalized_center_weighted_internal_edge.pdf'
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
