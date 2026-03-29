#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np

DATE_RE = re.compile(r'^(\d{2})-.*-(\d{4})_')


@dataclass
class ObjectMetric:
    label: int
    area_px: int
    perimeter_px: float
    circularity: float


@dataclass
class ImageMetric:
    date_label: str
    relative_day: int
    image_name: str
    count: int
    curvature_proxy: float
    edge_intensity_second_column: float
    total_area_px: int
    average_perimeter_px: float
    inverse_fusion_proxy: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--input-dir', required=True)
    return p.parse_args()


def parse_relative_day(name: str) -> tuple[str, date]:
    m = DATE_RE.match(name)
    if not m:
        raise RuntimeError(f'Cannot parse date from {name}')
    day = int(m.group(1))
    year = int(m.group(2))
    dt = date(year, 12, day)
    return f'{day:02d}-Dec', dt


def load_mask(path: Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise RuntimeError(f'Failed to read {path}')
    if mask.ndim != 2:
        raise RuntimeError(f'Expected 2D label mask, got {mask.shape} for {path}')
    return mask


def load_gray(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f'Failed to read {path}')
    return img


def object_metrics(label_mask: np.ndarray) -> list[ObjectMetric]:
    metrics: list[ObjectMetric] = []
    labels = np.unique(label_mask)
    labels = labels[labels > 0]
    for lab in labels:
        mask = label_mask == lab
        area = int(mask.sum())
        contours, _ = cv2.findContours((mask.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        perimeter = float(sum(cv2.arcLength(c, True) for c in contours))
        circularity = 0.0
        if area > 0 and perimeter > 0:
            circularity = float((4.0 * math.pi * area) / (perimeter * perimeter))
        metrics.append(ObjectMetric(label=int(lab), area_px=area, perimeter_px=perimeter, circularity=circularity))
    return metrics


def boundary_edge_intensity(label_mask: np.ndarray, signal_gray: np.ndarray) -> float:
    signal_f = signal_gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(signal_f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(signal_f, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    boundary = np.zeros_like(label_mask, dtype=bool)
    labels = np.unique(label_mask)
    labels = labels[labels > 0]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for lab in labels:
        mask = (label_mask == lab).astype(np.uint8) * 255
        edge = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, kernel) > 0
        boundary |= edge
    if not boundary.any():
        return 0.0
    return float(grad[boundary].mean())


def compute_image_metric(mask_path: Path, signal_path: Path, relative_day0: date) -> ImageMetric:
    date_label, dt = parse_relative_day(mask_path.name)
    rel_day = (dt - relative_day0).days
    label_mask = load_mask(mask_path)
    signal_gray = load_gray(signal_path)
    objs = object_metrics(label_mask)
    count = len(objs)
    total_area = int(sum(o.area_px for o in objs))
    avg_perimeter = float(np.mean([o.perimeter_px for o in objs])) if objs else 0.0
    if total_area > 0:
        curvature_proxy = float(sum(o.area_px * o.circularity for o in objs) / total_area)
    else:
        curvature_proxy = 0.0
    edge_intensity = boundary_edge_intensity(label_mask, signal_gray)
    eps = 1e-8
    inverse_proxy = (1.0 / max(curvature_proxy, eps)) * (1.0 / max(count, 1)) * (1.0 / max(edge_intensity, eps))
    return ImageMetric(
        date_label=date_label,
        relative_day=rel_day,
        image_name=mask_path.name,
        count=count,
        curvature_proxy=curvature_proxy,
        edge_intensity_second_column=edge_intensity,
        total_area_px=total_area,
        average_perimeter_px=avg_perimeter,
        inverse_fusion_proxy=inverse_proxy,
    )


def save_csv(metrics: list[ImageMetric], out_csv: Path) -> None:
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'date_label',
            'relative_day',
            'image_name',
            'count',
            'curvature_proxy_area_weighted_circularity',
            'edge_intensity_second_column_boundary_gradient',
            'total_area_px',
            'average_perimeter_px',
            'inverse_fusion_proxy_1_over_curvature_times_1_over_count_times_1_over_edge',
        ])
        for m in metrics:
            writer.writerow([
                m.date_label,
                m.relative_day,
                m.image_name,
                m.count,
                f'{m.curvature_proxy:.8f}',
                f'{m.edge_intensity_second_column:.8f}',
                m.total_area_px,
                f'{m.average_perimeter_px:.8f}',
                f'{m.inverse_fusion_proxy:.12f}',
            ])


def plot_metrics(metrics: list[ImageMetric], out_png: Path, out_pdf: Path) -> None:
    metrics = sorted(metrics, key=lambda x: x.relative_day)
    x = [m.relative_day for m in metrics]
    labels = [m.date_label for m in metrics]

    series = [
        ('Curvature', [m.curvature_proxy for m in metrics], '#1f77b4'),
        ('Counts', [m.count for m in metrics], '#d62728'),
        ('Edge Intensity', [m.edge_intensity_second_column for m in metrics], '#2ca02c'),
        ('Area', [m.total_area_px for m in metrics], '#9467bd'),
        ('Average Perimeter', [m.average_perimeter_px for m in metrics], '#ff7f0e'),
        ('1/Curvature * 1/Counts * 1/Edge', [m.inverse_fusion_proxy for m in metrics], '#111111'),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10), constrained_layout=True)
    axes = axes.flatten()

    for ax, (title, y, color) in zip(axes, series):
        ax.plot(x, y, marker='o', linewidth=2.2, markersize=6, color=color)
        ax.set_title(title, fontsize=12, pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha='right')
        ax.grid(True, alpha=0.25)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ymin = min(y)
        ymax = max(y)
        if ymax > ymin:
            pad = 0.08 * (ymax - ymin)
            ax.set_ylim(ymin - pad, ymax + pad)

    fig.suptitle('App80 10uM First-Replicate Segmentation Metrics by Day', fontsize=15, y=1.02)
    fig.savefig(out_png, dpi=220, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    mask_paths = sorted(input_dir.glob('*_multiscale_cellpose_mask_16bit.png'))
    if not mask_paths:
        raise SystemExit(f'No masks found in {input_dir}')

    dates = [parse_relative_day(p.name)[1] for p in mask_paths]
    day0 = min(dates)

    metrics: list[ImageMetric] = []
    for mask_path in mask_paths:
        signal_path = mask_path.with_name(mask_path.name.replace('_multiscale_cellpose_mask_16bit.png', '_multiscale_signal.png'))
        metrics.append(compute_image_metric(mask_path, signal_path, day0))

    csv_path = input_dir / 'segmentation_metrics_by_day.csv'
    png_path = input_dir / 'segmentation_metrics_by_day.png'
    pdf_path = input_dir / 'segmentation_metrics_by_day.pdf'
    save_csv(metrics, csv_path)
    plot_metrics(metrics, png_path, pdf_path)
    print(csv_path)
    print(png_path)
    print(pdf_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
