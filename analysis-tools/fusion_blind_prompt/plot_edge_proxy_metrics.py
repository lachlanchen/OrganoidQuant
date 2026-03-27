#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from PIL import Image

DATE_RE = re.compile(r"(?P<day>\d{2})-十二月-2025")
EPS = 1e-9


def parse_rows(mapping_csv: Path):
    with mapping_csv.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError('empty mapping csv')
    return rows


def normalize_u8(gray: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(gray, [1, 99])
    if hi <= lo:
        return np.clip(gray, 0, 255).astype(np.uint8)
    scaled = (gray.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def load_gray_u8(path: Path) -> np.ndarray:
    try:
        with Image.open(path) as image:
            gray = np.array(image.convert('L'))
    except Exception:
        try:
            image = tifffile.imread(str(path))
            if image.ndim >= 3:
                image = np.squeeze(image)
            if image.ndim == 3:
                gray = image[..., :3].mean(axis=2)
            else:
                gray = image
        except Exception:
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise
            if image.ndim == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
    return normalize_u8(gray)


def compute_tissue_mask(gray_u8: np.ndarray) -> np.ndarray:
    blur_large = cv2.GaussianBlur(gray_u8, (0, 0), 18)
    residual = cv2.subtract(blur_large, gray_u8)
    thresh = max(10, int(np.percentile(residual, 82)))
    mask = (residual >= thresh).astype(np.uint8) * 255
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if num_labels > 1:
        keep = np.zeros_like(mask)
        h, w = mask.shape
        center = np.array([w / 2.0, h / 2.0])
        best_idx = None
        best_score = None
        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            if area < 2000:
                continue
            ys, xs = np.where(labels == idx)
            if xs.size == 0 or ys.size == 0:
                continue
            centroid = np.array([
                float(xs.sum()) / float(xs.size),
                float(ys.sum()) / float(ys.size),
            ])
            dist = float(np.linalg.norm(centroid - center))
            score = area - 12.0 * dist
            if best_score is None or score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None:
            keep[labels == best_idx] = 255
            mask = keep

    if np.count_nonzero(mask) < gray_u8.size * 0.03:
        h, w = gray_u8.shape
        yy, xx = np.ogrid[:h, :w]
        cx, cy = w / 2.0, h / 2.0
        rx, ry = w * 0.42, h * 0.42
        ellipse = (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) <= 1.0
        mask = (ellipse.astype(np.uint8) * 255)
    return mask


def compute_metrics(gray_u8: np.ndarray):
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray_u8)
    blur = cv2.GaussianBlur(clahe, (5, 5), 0)
    mask = compute_tissue_mask(blur)

    median = float(np.median(blur[mask > 0])) if np.count_nonzero(mask) else float(np.median(blur))
    low = int(max(0, 0.66 * median))
    high = int(min(255, 1.33 * median))
    if high <= low:
        low, high = 40, 120

    edges = cv2.Canny(blur, low, high)
    masked_pixels = max(int(np.count_nonzero(mask)), 1)
    edge_pixels = int(np.count_nonzero((edges > 0) & (mask > 0)))
    edge_density = edge_pixels / masked_pixels
    edge_reciprocal = 1.0 / max(edge_density, EPS)

    sobel_x = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(sobel_x, sobel_y)
    grad_values = grad_mag[mask > 0] if np.count_nonzero(mask) else grad_mag.ravel()
    gradient_mean = float(grad_values.mean())
    gradient_reciprocal = 1.0 / max(gradient_mean, EPS)

    return {
        'clahe': clahe,
        'blur': blur,
        'mask': mask,
        'edges': edges,
        'edge_pixels': edge_pixels,
        'masked_pixels': masked_pixels,
        'edge_density': edge_density,
        'edge_reciprocal': edge_reciprocal,
        'gradient_mean': gradient_mean,
        'gradient_reciprocal': gradient_reciprocal,
        'canny_low': low,
        'canny_high': high,
    }


def save_overlay(gray_u8: np.ndarray, mask: np.ndarray, edges: np.ndarray, dest: Path) -> None:
    rgb = cv2.cvtColor(gray_u8, cv2.COLOR_GRAY2RGB)
    rgb[mask > 0] = (0.65 * rgb[mask > 0] + 0.35 * np.array([0, 255, 0])).astype(np.uint8)
    rgb[edges > 0] = np.array([255, 0, 0], dtype=np.uint8)
    Image.fromarray(rgb).save(dest)


def main() -> int:
    parser = argparse.ArgumentParser(description='Plot exploratory edge/gradient proxy metrics for a blinded fusion cohort')
    parser.add_argument('mapping_csv', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir
    overlay_dir = output_dir / 'edge_proxy_overlays'
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    rows = parse_rows(args.mapping_csv)
    dated = []
    for row in rows:
        date_label = Path(row['source_folder']).name
        dated.append((date_label, row))
    dated.sort(key=lambda item: item[0])

    first_match = DATE_RE.search(dated[0][0])
    if not first_match:
        raise ValueError('Could not parse first date label')
    first_dt = datetime.strptime(f"2025-12-{first_match.group('day')}", '%Y-%m-%d')

    table_rows = []
    for seq_idx, (date_label, row) in enumerate(dated, start=1):
        source_path = Path(row['source_path'])
        gray_u8 = load_gray_u8(source_path)
        metrics = compute_metrics(gray_u8)
        rel_days = (datetime.strptime(f"2025-12-{DATE_RE.search(date_label).group('day')}", '%Y-%m-%d') - first_dt).days
        overlay_path = overlay_dir / f"{row['uid']}_edge_overlay.png"
        save_overlay(gray_u8, metrics['mask'], metrics['edges'], overlay_path)
        table_rows.append({
            'sequence_day': seq_idx,
            'source_date': date_label,
            'relative_offset_days': rel_days,
            'uid': row['uid'],
            'source_basename': row['source_basename'],
            'edge_pixels': metrics['edge_pixels'],
            'masked_pixels': metrics['masked_pixels'],
            'edge_density': metrics['edge_density'],
            'edge_reciprocal': metrics['edge_reciprocal'],
            'gradient_mean': metrics['gradient_mean'],
            'gradient_reciprocal': metrics['gradient_reciprocal'],
            'canny_low': metrics['canny_low'],
            'canny_high': metrics['canny_high'],
            'overlay_path': str(overlay_path),
        })

    csv_path = output_dir / 'set_001_edge_proxy_table.csv'
    with csv_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table_rows[0].keys()))
        writer.writeheader()
        writer.writerows(table_rows)

    x = [row['sequence_day'] for row in table_rows]
    xticks = [f"D{row['sequence_day']}\n{row['source_date'][:2]}" for row in table_rows]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    metrics_to_plot = [
        ('edge_density', 'Canny Edge Density', '#B11E35'),
        ('edge_reciprocal', 'Reciprocal Edge Density', '#1D4E89'),
        ('gradient_mean', 'Gradient Mean', '#2C6E49'),
        ('gradient_reciprocal', 'Reciprocal Gradient Mean', '#D17B0F'),
    ]

    for ax, (key, title, color) in zip(axes.ravel(), metrics_to_plot):
        y = [row[key] for row in table_rows]
        ax.plot(x, y, marker='o', linewidth=2.2, markersize=6, color=color)
        for xi, yi, row in zip(x, y, table_rows):
            ax.annotate(row['uid'].replace('uid_', '')[:6], (xi, yi), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=8, color=color)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xticks(x, xticks)
        ax.grid(True, alpha=0.25)
        ax.set_xlabel('Blind Sequence Day')

    fig.suptitle('Set 001 Exploratory Edge/Gradient Fusion Proxies', fontsize=16, fontweight='bold')
    png_path = output_dir / 'set_001_edge_proxy_trends.png'
    pdf_path = output_dir / 'set_001_edge_proxy_trends.pdf'
    fig.savefig(png_path, dpi=220, bbox_inches='tight')
    fig.savefig(pdf_path, bbox_inches='tight')
    plt.close(fig)

    print(json.dumps({
        'csv': str(csv_path),
        'png': str(png_path),
        'pdf': str(pdf_path),
        'overlays': str(overlay_dir),
        'rows': len(table_rows),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
