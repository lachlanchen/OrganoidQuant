#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import date
from pathlib import Path

import cv2
import numpy as np
import tifffile

CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']
MONTH_MAP = {
    '十二月': 12,
}
DATE_RE = re.compile(r'^(\d{2})-(十二月)-(\d{4})$')
MAG_RE = re.compile(r'(10x|10X|4x|4X)(\d+)?', re.I)
VERY_DARK_THRESHOLD = 0.35
EPS = 1e-9


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--out-dir', required=True)
    p.add_argument('--skip-refresh', action='store_true')
    return p.parse_args()


def parse_date_dir(name: str) -> tuple[str, date]:
    m = DATE_RE.match(name)
    if not m:
        raise RuntimeError(f'Cannot parse date dir: {name}')
    day = int(m.group(1))
    month = MONTH_MAP[m.group(2)]
    year = int(m.group(3))
    dt = date(year, month, day)
    return f'{day:02d}-Dec', dt


def natural_key(name: str) -> tuple[int, str]:
    stem = Path(name).stem
    m = MAG_RE.search(stem)
    idx = int(m.group(2)) if m and m.group(2) else 10**9
    return (idx, stem.lower())


def mean_std_sem(values: list[float]) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return float('nan'), float('nan'), float('nan')
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    sem = float(std / math.sqrt(arr.size)) if arr.size > 1 else 0.0
    return mean, std, sem


def minmax_floor(values: list[float], floor: float) -> list[float]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return []
    lo = float(arr.min())
    hi = float(arr.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return [max(floor, 1.0) for _ in arr]
    out = (arr - lo) / (hi - lo)
    out = np.clip(out, floor, 1.0)
    return [float(v) for v in out]


def imread_any(path: Path, flags: int) -> np.ndarray | None:
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


def load_labels(path: Path) -> np.ndarray:
    arr = imread_any(path, cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise FileNotFoundError(path)
    if arr.ndim != 2:
        raise ValueError(f'Expected 2D label image: {path}')
    return arr


def load_gray_png(path: Path) -> np.ndarray:
    arr = imread_any(path, cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise FileNotFoundError(path)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr.astype(np.uint8)


def load_source_gray(path: Path) -> np.ndarray:
    arr = tifffile.imread(str(path))
    if arr.ndim == 2:
        gray = arr
    elif arr.ndim == 3 and arr.shape[-1] in (3, 4):
        rgb = arr[..., :3].astype(np.uint8)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    elif arr.ndim == 3:
        gray = arr[0]
    else:
        raise RuntimeError(f'Unsupported shape {arr.shape} for {path}')
    return gray.astype(np.uint8)


def normalize_u8(gray: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(gray, [1, 99])
    if hi <= lo:
        return np.clip(gray, 0, 255).astype(np.uint8)
    scaled = (gray.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(scaled, 0, 255).astype(np.uint8)


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
            centroid = np.array([float(xs.sum()) / float(xs.size), float(ys.sum()) / float(ys.size)])
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


def compute_edge_proxy_metrics(gray_u8: np.ndarray) -> dict[str, float]:
    norm = normalize_u8(gray_u8)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(norm)
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
    gradient_mean = float(grad_values.mean()) if grad_values.size else 0.0
    gradient_reciprocal = 1.0 / max(gradient_mean, EPS)
    return {
        'edge_density': float(edge_density),
        'edge_reciprocal': float(edge_reciprocal),
        'gradient_mean': float(gradient_mean),
        'gradient_reciprocal': float(gradient_reciprocal),
    }


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


def compute_internal_edge_metrics(labels: np.ndarray, signal_u8: np.ndarray) -> dict[str, float]:
    edge = edge_map_from_signal(signal_u8)
    unique_labels = [int(v) for v in np.unique(labels) if int(v) > 0]
    if not unique_labels:
        return {
            'central_inside_edge_mean': float('nan'),
            'peripheral_inside_edge_mean': float('nan'),
            'outer_ring_edge_mean': float('nan'),
            'central_inside_fraction': float('nan'),
            'central_inside_over_peripheral': float('nan'),
            'central_inside_over_outer': float('nan'),
            'peripheral_over_central': float('nan'),
        }

    central_num = 0.0
    central_den = 0.0
    periph_num = 0.0
    periph_den = 0.0

    union = labels > 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    outer_ring = cv2.dilate(union.astype(np.uint8), kernel, iterations=1).astype(bool) & (~union)
    outer_ring_edge_mean = float(edge[outer_ring].mean()) if np.any(outer_ring) else float('nan')

    for label_id in unique_labels:
        inst = labels == label_id
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

    central_mean = central_num / central_den if central_den > 0 else float('nan')
    periph_mean = periph_num / periph_den if periph_den > 0 else float('nan')
    central_fraction = central_mean / (central_mean + periph_mean) if np.isfinite(central_mean) and np.isfinite(periph_mean) and (central_mean + periph_mean) > 0 else float('nan')
    central_over_periph = central_mean / periph_mean if np.isfinite(central_mean) and np.isfinite(periph_mean) and periph_mean > 0 else float('nan')
    central_over_outer = central_mean / outer_ring_edge_mean if np.isfinite(central_mean) and np.isfinite(outer_ring_edge_mean) and outer_ring_edge_mean > 0 else float('nan')
    peripheral_over_central = periph_mean / central_mean if np.isfinite(central_mean) and central_mean > 0 and np.isfinite(periph_mean) else float('nan')
    return {
        'central_inside_edge_mean': float(central_mean),
        'peripheral_inside_edge_mean': float(periph_mean),
        'outer_ring_edge_mean': float(outer_ring_edge_mean),
        'central_inside_fraction': float(central_fraction),
        'central_inside_over_peripheral': float(central_over_periph),
        'central_inside_over_outer': float(central_over_outer),
        'peripheral_over_central': float(peripheral_over_central),
    }


def exponential_center_weight(centrality: np.ndarray, alpha: float) -> np.ndarray:
    denom = np.expm1(alpha)
    if not np.isfinite(denom) or denom <= 0:
        return centrality
    return np.expm1(alpha * centrality) / denom


def compute_center_weighted_metrics(labels: np.ndarray, signal_u8: np.ndarray, alpha: float = 5.0) -> dict[str, float]:
    edge = edge_map_from_signal(signal_u8)
    total_sum = 0.0
    total_weight = 0.0
    instance_sums: list[float] = []
    area_normalized_values: list[float] = []
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
        weight = exponential_center_weight(centrality, alpha)
        edge_crop = edge[y0:y1, x0:x1]
        weighted_sum = float((edge_crop * weight * inst).sum())
        total_sum += weighted_sum
        total_weight += float((weight * inst).sum())
        instance_sums.append(weighted_sum)
        area_normalized_values.append(weighted_sum / float(area))

    arr = np.asarray(area_normalized_values, dtype=np.float64)
    return {
        'center_weighted_edge_sum': float(total_sum),
        'center_weighted_edge_weight_sum': float(total_weight),
        'center_weighted_edge_mean': float(total_sum / total_weight) if total_weight > 0 else 0.0,
        'instance_center_weighted_edge_sum_mean': float(np.mean(instance_sums)) if instance_sums else 0.0,
        'area_normalized_center_weighted_edge_instance_mean': float(arr.mean()) if arr.size else 0.0,
        'area_normalized_center_weighted_edge_instance_std': float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
        'area_normalized_center_weighted_edge_instance_median': float(np.median(arr)) if arr.size else 0.0,
    }


def safe_mean(arr: np.ndarray) -> float:
    return float(arr.mean()) if arr.size else float('nan')


def quantile(arr: np.ndarray, q: float) -> float:
    return float(np.quantile(arr, q)) if arr.size else float('nan')


def compute_wall_core_masks(label_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    wall = np.zeros(label_mask.shape, dtype=bool)
    core = np.zeros(label_mask.shape, dtype=bool)
    labels = np.unique(label_mask)
    labels = labels[labels > 0]
    for lab in labels:
        mask = label_mask == lab
        area = int(mask.sum())
        if area <= 0:
            continue
        eq_radius = math.sqrt(area / math.pi)
        band_px = int(np.clip(round(eq_radius * 0.12), 5, 30))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band_px + 1, 2 * band_px + 1))
        mask_u8 = (mask.astype(np.uint8) * 255)
        eroded = cv2.erode(mask_u8, kernel) > 0
        wall |= mask & ~eroded
        core |= eroded
    return wall, core


def compute_darkness_metrics(label_mask: np.ndarray, source_gray: np.ndarray) -> dict[str, float]:
    inside = label_mask > 0
    dil_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
    bg_exclude = cv2.dilate((inside.astype(np.uint8) * 255), dil_kernel) > 0
    bg_region = ~bg_exclude
    if bg_region.sum() < 1000:
        bg_region = ~inside
    bg_median = float(np.median(source_gray[bg_region])) if bg_region.any() else float(np.median(source_gray))

    if not inside.any():
        return {
            'background_gray_median': bg_median,
            'organoid_darkness_mean': float('nan'),
            'organoid_darkness_p90': float('nan'),
            'organoid_darkness_p95': float('nan'),
            'very_dark_area_ratio_gt035': float('nan'),
            'wall_darkness_mean': float('nan'),
            'wall_darkness_p90': float('nan'),
            'core_darkness_mean': float('nan'),
            'wall_core_darkness_ratio': float('nan'),
            'organoid_pixel_count': 0,
            'wall_pixel_count': 0,
            'core_pixel_count': 0,
        }

    gray_f = source_gray.astype(np.float32)
    darkness = np.clip((bg_median - gray_f) / max(bg_median, 1.0), 0.0, 1.0)
    organoid_vals = darkness[inside]
    wall_mask, core_mask = compute_wall_core_masks(label_mask)
    wall_vals = darkness[wall_mask]
    core_vals = darkness[core_mask]

    return {
        'background_gray_median': bg_median,
        'organoid_darkness_mean': safe_mean(organoid_vals),
        'organoid_darkness_p90': quantile(organoid_vals, 0.90),
        'organoid_darkness_p95': quantile(organoid_vals, 0.95),
        'very_dark_area_ratio_gt035': float((organoid_vals > VERY_DARK_THRESHOLD).mean()),
        'wall_darkness_mean': safe_mean(wall_vals),
        'wall_darkness_p90': quantile(wall_vals, 0.90),
        'core_darkness_mean': safe_mean(core_vals),
        'wall_core_darkness_ratio': float(safe_mean(wall_vals) / max(safe_mean(core_vals), 1e-6)) if core_vals.size else float('nan'),
        'organoid_pixel_count': int(organoid_vals.size),
        'wall_pixel_count': int(wall_vals.size),
        'core_pixel_count': int(core_vals.size),
    }


def compute_signal_metrics(signal_u8: np.ndarray) -> dict[str, float]:
    sum_intensity = int(np.asarray(signal_u8, dtype=np.uint64).sum())
    reciprocal = 1.0 / float(sum_intensity) if sum_intensity > 0 else float('nan')
    return {
        'sum_intensity': float(sum_intensity),
        'reciprocal_sum_intensity': float(reciprocal),
    }


def refresh_metric_json(metric_path: Path) -> dict:
    data = json.loads(metric_path.read_text(encoding='utf-8'))
    mask_path = Path(data['mask_path'])
    signal_path = Path(data['signal_path'])
    source_tif = Path(data['source_tif'])
    labels = load_labels(mask_path)
    signal = load_gray_png(signal_path)
    source_gray = load_source_gray(source_tif)

    inv = np.nan
    if float(data.get('count', 0)) > 0 and float(data.get('curvature', 0)) > 0 and float(data.get('edge_intensity', 0)) > 0:
        inv = 1.0 / (float(data['edge_intensity']) * float(data['count']) * float(data['curvature']))

    data.update(compute_signal_metrics(signal))
    data.update(compute_edge_proxy_metrics(source_gray))
    data.update(compute_internal_edge_metrics(labels, signal))
    data.update(compute_center_weighted_metrics(labels, signal))
    data.update(compute_darkness_metrics(labels, source_gray))
    data['inverse_edge_count_curvature'] = inv
    metric_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def load_metrics(out_dir: Path, *, skip_refresh: bool = False) -> list[dict]:
    runs_dir = out_dir / 'runs'
    metrics: list[dict] = []
    metric_paths = sorted(runs_dir.rglob('*_metrics.json'))
    if not metric_paths:
        return metrics
    dates = []
    for metric_path in metric_paths:
        data0 = json.loads(metric_path.read_text(encoding='utf-8'))
        _, dt = parse_date_dir(data0['date_key'])
        dates.append(dt)
    day0 = min(dates)
    for metric_path in metric_paths:
        if skip_refresh:
            data = json.loads(metric_path.read_text(encoding='utf-8'))
        else:
            data = refresh_metric_json(metric_path)
        concentration = metric_path.parent.parent.name
        date_label, dt = parse_date_dir(data['date_key'])
        relative_day = (dt - day0).days
        row = dict(data)
        row['concentration'] = concentration
        row['date_label'] = date_label
        row['relative_day'] = relative_day
        metrics.append(row)
    metrics.sort(key=lambda r: (CONCENTRATION_ORDER.index(r['concentration']), r['relative_day'], natural_key(r['image_name'])))
    return metrics


def apply_norms(metrics: list[dict]) -> None:
    counts_norm = minmax_floor([float(r['count']) for r in metrics], 0.1)
    curvature_norm = minmax_floor([float(r['curvature']) for r in metrics], 0.1)
    edge_norm = minmax_floor([float(r['edge_intensity']) for r in metrics], 0.1)
    for r, cn, kn, en in zip(metrics, counts_norm, curvature_norm, edge_norm):
        r['count_norm'] = cn
        r['curvature_norm'] = kn
        r['edge_norm'] = en
        r['normalized_edge_over_count_curvature'] = en / (cn * kn)
        if not np.isfinite(r.get('inverse_edge_count_curvature', float('nan'))):
            if float(r['count']) > 0 and float(r['curvature']) > 0 and float(r['edge_intensity']) > 0:
                r['inverse_edge_count_curvature'] = 1.0 / (float(r['edge_intensity']) * float(r['count']) * float(r['curvature']))


def write_per_image_csv(rows: list[dict], out_csv: Path) -> list[str]:
    fields = [
        'concentration', 'date_key', 'date_label', 'relative_day', 'image_name', 'stage',
        'count', 'curvature', 'roundness', 'roundness_deviation_norm', 'roundness_deviation_px_total',
        'edge_intensity', 'total_area_px', 'average_perimeter_px',
        'count_norm', 'curvature_norm', 'edge_norm', 'normalized_edge_over_count_curvature',
        'inverse_edge_count_curvature',
        'sum_intensity', 'reciprocal_sum_intensity',
        'edge_density', 'edge_reciprocal', 'gradient_mean', 'gradient_reciprocal',
        'central_inside_edge_mean', 'peripheral_inside_edge_mean', 'outer_ring_edge_mean',
        'central_inside_fraction', 'central_inside_over_peripheral', 'central_inside_over_outer', 'peripheral_over_central',
        'center_weighted_edge_sum', 'center_weighted_edge_weight_sum', 'center_weighted_edge_mean', 'instance_center_weighted_edge_sum_mean',
        'area_normalized_center_weighted_edge_instance_mean', 'area_normalized_center_weighted_edge_instance_std', 'area_normalized_center_weighted_edge_instance_median',
        'background_gray_median', 'organoid_darkness_mean', 'organoid_darkness_p90', 'organoid_darkness_p95',
        'very_dark_area_ratio_gt035', 'wall_darkness_mean', 'wall_darkness_p90', 'core_darkness_mean', 'wall_core_darkness_ratio',
        'organoid_pixel_count', 'wall_pixel_count', 'core_pixel_count',
        'mask_path', 'instance_rgb_path', 'overlay_path', 'signal_path', 'stats_path', 'source_tif',
    ]
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return fields


def write_daily_summary(rows: list[dict], out_csv: Path) -> tuple[list[str], list[dict]]:
    metric_fields = [
        'count', 'curvature', 'roundness', 'roundness_deviation_norm', 'roundness_deviation_px_total',
        'edge_intensity', 'total_area_px', 'average_perimeter_px',
        'count_norm', 'curvature_norm', 'edge_norm', 'normalized_edge_over_count_curvature', 'inverse_edge_count_curvature',
        'sum_intensity', 'reciprocal_sum_intensity',
        'edge_density', 'edge_reciprocal', 'gradient_mean', 'gradient_reciprocal',
        'central_inside_edge_mean', 'peripheral_inside_edge_mean', 'outer_ring_edge_mean',
        'central_inside_fraction', 'central_inside_over_peripheral', 'central_inside_over_outer', 'peripheral_over_central',
        'center_weighted_edge_sum', 'center_weighted_edge_weight_sum', 'center_weighted_edge_mean', 'instance_center_weighted_edge_sum_mean',
        'area_normalized_center_weighted_edge_instance_mean', 'area_normalized_center_weighted_edge_instance_std', 'area_normalized_center_weighted_edge_instance_median',
        'background_gray_median', 'organoid_darkness_mean', 'organoid_darkness_p90', 'organoid_darkness_p95',
        'very_dark_area_ratio_gt035', 'wall_darkness_mean', 'wall_darkness_p90', 'core_darkness_mean', 'wall_core_darkness_ratio',
        'organoid_pixel_count', 'wall_pixel_count', 'core_pixel_count',
    ]
    grouped: dict[tuple[str, str, str, int], list[dict]] = {}
    for row in rows:
        key = (row['concentration'], row['date_key'], row['date_label'], int(row['relative_day']))
        grouped.setdefault(key, []).append(row)

    summary_rows: list[dict] = []
    for key in sorted(grouped.keys(), key=lambda x: (CONCENTRATION_ORDER.index(x[0]), x[3])):
        subset = grouped[key]
        out = {
            'concentration': key[0],
            'date_key': key[1],
            'date_label': key[2],
            'relative_day': key[3],
            'n_images': len(subset),
        }
        for metric in metric_fields:
            vals = []
            for row in subset:
                raw = row.get(metric, '')
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(val):
                    vals.append(val)
            mean, std, sem = mean_std_sem(vals)
            out[f'{metric}_mean'] = mean
            out[f'{metric}_std'] = std
            out[f'{metric}_sem'] = sem
        summary_rows.append(out)

    by_conc: dict[str, list[dict]] = {c: [] for c in CONCENTRATION_ORDER}
    for row in summary_rows:
        by_conc[row['concentration']].append(row)
    for concentration, subset in by_conc.items():
        subset.sort(key=lambda r: int(r['relative_day']))
        prev_sum = None
        prev_recip = None
        for row in subset:
            sum_mean = row['sum_intensity_mean']
            recip_mean = row['reciprocal_sum_intensity_mean']
            if prev_sum is None or not np.isfinite(prev_sum) or prev_sum == 0 or not np.isfinite(sum_mean):
                row['sum_intensity_relative_change'] = float('nan')
            else:
                row['sum_intensity_relative_change'] = float((sum_mean - prev_sum) / prev_sum)
            if prev_recip is None or not np.isfinite(prev_recip) or prev_recip == 0 or not np.isfinite(recip_mean):
                row['reciprocal_relative_change'] = float('nan')
            else:
                row['reciprocal_relative_change'] = float((recip_mean - prev_recip) / prev_recip)
            prev_sum = sum_mean
            prev_recip = recip_mean

    header = ['concentration', 'date_key', 'date_label', 'relative_day', 'n_images']
    for metric in metric_fields:
        header += [f'{metric}_mean', f'{metric}_std', f'{metric}_sem']
    header += ['sum_intensity_relative_change', 'reciprocal_relative_change']
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(summary_rows)
    return metric_fields, summary_rows


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    db_dir = out_dir / 'profiling' / 'quantification'
    db_dir.mkdir(parents=True, exist_ok=True)
    metrics = load_metrics(out_dir, skip_refresh=args.skip_refresh)
    if not metrics:
        raise SystemExit(f'No metrics JSON files under {out_dir / "runs"}')
    apply_norms(metrics)
    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    fields = write_per_image_csv(metrics, per_image_csv)
    metric_fields, summary_rows = write_daily_summary(metrics, daily_csv)
    manifest = {
        'out_dir': str(out_dir),
        'n_metrics_json': len(metrics),
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
        'all_metric_fields': metric_fields,
        'per_image_fields': fields,
        'n_daily_rows': len(summary_rows),
    }
    (out_dir / 'backfill_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(per_image_csv)
    print(daily_csv)
    print(out_dir / 'backfill_manifest.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
