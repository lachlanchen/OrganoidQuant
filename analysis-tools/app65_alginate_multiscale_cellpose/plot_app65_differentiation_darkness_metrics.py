#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import run_app65_all_conditions_large_recovery as app65  # noqa: E402

VERY_DARK_THRESHOLD = 0.35
CONDITION_ORDER = app65.CONDITION_ORDER
CONDITION_COLORS = {
    'No': '#4d4d4d',
    '0.02% Alginate': '#1f77b4',
    '0.05% Alginate': '#d62728',
}
CONDITION_LABELS = {
    'No': 'Control',
    '0.02% Alginate': '0.02% Alginate',
    '0.05% Alginate': '0.05% Alginate',
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--out-dir', required=True)
    return p.parse_args()


def imread_any(path: Path, flags: int) -> np.ndarray | None:
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


def mean_std_sem(values: list[float]) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(arr.mean()) if arr.size else 0.0
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    sem = float(std / math.sqrt(arr.size)) if arr.size > 1 else 0.0
    return mean, std, sem


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


def compute_image_metrics(metric_json: Path) -> dict:
    record = json.loads(metric_json.read_text(encoding='utf-8'))
    source_tif = Path(record['source_tif'])
    source_bgr = imread_any(source_tif, cv2.IMREAD_COLOR)
    if source_bgr is None:
        raise RuntimeError(f'Failed to load source image: {source_tif}')
    gray = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2GRAY)
    label_mask = imread_any(Path(record['mask_path']), cv2.IMREAD_UNCHANGED)
    if label_mask is None:
        raise RuntimeError(f'Failed to load label mask: {record["mask_path"]}')

    inside = label_mask > 0
    dil_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
    bg_exclude = cv2.dilate((inside.astype(np.uint8) * 255), dil_kernel) > 0
    bg_region = ~bg_exclude
    if bg_region.sum() < 1000:
        bg_region = ~inside
    bg_median = float(np.median(gray[bg_region])) if bg_region.any() else float(np.median(gray))

    if not inside.any():
        return {
            'condition': record['condition'],
            'date_key': record['date_key'],
            'image_name': record['image_name'],
            'source_tif': record['source_tif'],
            'mask_path': record['mask_path'],
            'relative_day': (app65.parse_date_dir(record['date_key'])[1] - app65.date(2025, 11, 19)).days,
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

    gray_f = gray.astype(np.float32)
    darkness = np.clip((bg_median - gray_f) / max(bg_median, 1.0), 0.0, 1.0)
    organoid_vals = darkness[inside]

    wall_mask, core_mask = compute_wall_core_masks(label_mask)
    wall_vals = darkness[wall_mask]
    core_vals = darkness[core_mask]

    metrics = {
        'condition': record['condition'],
        'date_key': record['date_key'],
        'image_name': record['image_name'],
        'source_tif': record['source_tif'],
        'mask_path': record['mask_path'],
        'relative_day': (app65.parse_date_dir(record['date_key'])[1] - app65.date(2025, 11, 19)).days,
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
    return metrics


def write_per_image(rows: list[dict], out_csv: Path) -> None:
    fields = [
        'condition', 'date_key', 'relative_day', 'image_name', 'source_tif', 'mask_path',
        'background_gray_median',
        'organoid_darkness_mean', 'organoid_darkness_p90', 'organoid_darkness_p95',
        'very_dark_area_ratio_gt035',
        'wall_darkness_mean', 'wall_darkness_p90', 'core_darkness_mean', 'wall_core_darkness_ratio',
        'organoid_pixel_count', 'wall_pixel_count', 'core_pixel_count',
    ]
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_daily(rows: list[dict], out_csv: Path) -> None:
    metrics = [
        'organoid_darkness_mean', 'organoid_darkness_p90', 'organoid_darkness_p95',
        'very_dark_area_ratio_gt035', 'wall_darkness_mean', 'wall_darkness_p90',
        'core_darkness_mean', 'wall_core_darkness_ratio',
    ]
    grouped: dict[tuple[str, str, int], list[dict]] = {}
    for row in rows:
        key = (row['condition'], row['date_key'], row['relative_day'])
        grouped.setdefault(key, []).append(row)
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['condition', 'date_key', 'date_label', 'relative_day', 'n_images']
        for m in metrics:
            header += [f'{m}_mean', f'{m}_std', f'{m}_sem']
        writer.writerow(header)
        for key in sorted(grouped, key=lambda x: (CONDITION_ORDER.index(x[0]), x[2])):
            subset = grouped[key]
            date_label, _ = app65.parse_date_dir(key[1])
            row = [key[0], key[1], date_label, key[2], len(subset)]
            for metric in metrics:
                vals = [float(s[metric]) for s in subset if not math.isnan(float(s[metric]))]
                mean, std, sem = mean_std_sem(vals)
                row += [f'{mean:.12f}', f'{std:.12f}', f'{sem:.12f}']
            writer.writerow(row)


def merge_into_main_per_image(main_csv: Path, dark_csv: Path) -> None:
    with dark_csv.open('r', encoding='utf-8', newline='') as f:
        dark_rows = list(csv.DictReader(f))
    dark_index = {
        (r['condition'], r['date_key'], r['image_name']): r
        for r in dark_rows
    }
    with main_csv.open('r', encoding='utf-8', newline='') as f:
        main_rows = list(csv.DictReader(f))
        main_fields = list(main_rows[0].keys())

    new_fields = [
        'background_gray_median',
        'organoid_darkness_mean',
        'organoid_darkness_p90',
        'organoid_darkness_p95',
        'very_dark_area_ratio_gt035',
        'wall_darkness_mean',
        'wall_darkness_p90',
        'core_darkness_mean',
        'wall_core_darkness_ratio',
        'organoid_pixel_count',
        'wall_pixel_count',
        'core_pixel_count',
    ]
    fieldnames = main_fields + [f for f in new_fields if f not in main_fields]

    for row in main_rows:
        key = (row['condition'], row['date_key'], row['image_name'])
        dark = dark_index.get(key)
        for field in new_fields:
            row[field] = dark[field] if dark else ''

    with main_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(main_rows)


def merge_into_main_daily(main_csv: Path, dark_csv: Path) -> None:
    with dark_csv.open('r', encoding='utf-8', newline='') as f:
        dark_rows = list(csv.DictReader(f))
    dark_index = {
        (r['condition'], r['date_key'], r['relative_day']): r
        for r in dark_rows
    }
    with main_csv.open('r', encoding='utf-8', newline='') as f:
        main_rows = list(csv.DictReader(f))
        main_fields = list(main_rows[0].keys())

    metrics = [
        'organoid_darkness_mean',
        'organoid_darkness_p90',
        'organoid_darkness_p95',
        'very_dark_area_ratio_gt035',
        'wall_darkness_mean',
        'wall_darkness_p90',
        'core_darkness_mean',
        'wall_core_darkness_ratio',
    ]
    new_fields = []
    for metric in metrics:
        new_fields.extend([f'{metric}_mean', f'{metric}_std', f'{metric}_sem'])
    fieldnames = main_fields + [f for f in new_fields if f not in main_fields]

    for row in main_rows:
        key = (row['condition'], row['date_key'], row['relative_day'])
        dark = dark_index.get(key)
        for field in new_fields:
            row[field] = dark[field] if dark else ''

    with main_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(main_rows)


def read_daily(path: Path) -> list[dict]:
    rows = []
    with path.open('r', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            row['relative_day'] = int(row['relative_day'])
            rows.append(row)
    rows.sort(key=lambda r: (CONDITION_ORDER.index(r['condition']), r['relative_day']))
    return rows


def grouped_daily(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c: [] for c in CONDITION_ORDER}
    for row in rows:
        out.setdefault(row['condition'], []).append(row)
    return {k: v for k, v in out.items() if v}


def style_axis(ax, xticks, xticklabels, title: str) -> None:
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=0)
    ax.grid(True, alpha=0.22)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def plot_all(daily_csv: Path, fig_dir: Path) -> list[Path]:
    rows = read_daily(daily_csv)
    by_cond = grouped_daily(rows)
    xticks = sorted({r['relative_day'] for r in rows})
    xticklabels = [f'D{d}' for d in xticks]
    handles = [Line2D([0], [0], color=CONDITION_COLORS[c], lw=2.4, marker='o', markersize=5, label=CONDITION_LABELS[c]) for c in CONDITION_ORDER if c in by_cond]

    series = [
        ('Organoid Darkness Mean', 'organoid_darkness_mean_mean', 'organoid_darkness_mean_sem'),
        ('Organoid Darkness P90', 'organoid_darkness_p90_mean', 'organoid_darkness_p90_sem'),
        ('Very Dark Area Ratio', 'very_dark_area_ratio_gt035_mean', 'very_dark_area_ratio_gt035_sem'),
        ('Wall Darkness Mean', 'wall_darkness_mean_mean', 'wall_darkness_mean_sem'),
        ('Wall Darkness P90', 'wall_darkness_p90_mean', 'wall_darkness_p90_sem'),
        ('Wall / Core Darkness Ratio', 'wall_core_darkness_ratio_mean', 'wall_core_darkness_ratio_sem'),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18.8, 10.8), constrained_layout=False)
    axes = axes.flatten()
    for ax, (title, mean_col, sem_col) in zip(axes, series):
        for condition in CONDITION_ORDER:
            subset = by_cond.get(condition, [])
            if not subset:
                continue
            x = np.array([r['relative_day'] for r in subset], dtype=float)
            y = np.array([float(r[mean_col]) for r in subset], dtype=float)
            sem = np.array([float(r[sem_col]) for r in subset], dtype=float)
            color = CONDITION_COLORS[condition]
            ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.0, color=color)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, xticks, xticklabels, title)
    fig.suptitle('App65 10x Replicates: Differentiation Darkness Metrics by Day', fontsize=15, y=0.975)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.93), ncol=len(handles), frameon=False, fontsize=11)
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.09, top=0.83, hspace=0.34, wspace=0.24)
    out_png = fig_dir / 'app65_all_conditions_differentiation_darkness_metrics.png'
    out_pdf = fig_dir / 'app65_all_conditions_differentiation_darkness_metrics.pdf'
    fig.savefig(out_png, dpi=220, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)

    focus = [
        ('Organoid Darkness P90', 'organoid_darkness_p90_mean', 'organoid_darkness_p90_sem'),
        ('Very Dark Area Ratio', 'very_dark_area_ratio_gt035_mean', 'very_dark_area_ratio_gt035_sem'),
        ('Wall / Core Darkness Ratio', 'wall_core_darkness_ratio_mean', 'wall_core_darkness_ratio_sem'),
    ]
    fig2, axes2 = plt.subplots(1, 3, figsize=(16.5, 5.6), constrained_layout=False)
    for ax, (title, mean_col, sem_col) in zip(axes2, focus):
        for condition in CONDITION_ORDER:
            subset = by_cond.get(condition, [])
            if not subset:
                continue
            x = np.array([r['relative_day'] for r in subset], dtype=float)
            y = np.array([float(r[mean_col]) for r in subset], dtype=float)
            sem = np.array([float(r[sem_col]) for r in subset], dtype=float)
            color = CONDITION_COLORS[condition]
            ax.plot(x, y, marker='o', linewidth=2.2, markersize=5.0, color=color)
            ax.fill_between(x, y - sem, y + sem, color=color, alpha=0.14, linewidth=0)
        style_axis(ax, xticks, xticklabels, title)
    fig2.suptitle('App65 10x Replicates: Differentiation Darkness Focus', fontsize=15, y=0.98)
    fig2.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.94), ncol=len(handles), frameon=False, fontsize=11)
    fig2.subplots_adjust(left=0.06, right=0.985, bottom=0.15, top=0.80, wspace=0.24)
    out_png2 = fig_dir / 'app65_all_conditions_differentiation_darkness_focus.png'
    out_pdf2 = fig_dir / 'app65_all_conditions_differentiation_darkness_focus.pdf'
    fig2.savefig(out_png2, dpi=220, bbox_inches='tight')
    fig2.savefig(out_pdf2, bbox_inches='tight')
    plt.close(fig2)
    return [out_png, out_pdf, out_png2, out_pdf2]


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / 'runs'
    quant_dir = out_dir / 'profiling' / 'quantification'
    fig_dir = out_dir / 'figures' / 'differentiation_darkness'
    quant_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    metric_paths = sorted(runs_dir.rglob('*_metrics.json'))
    for idx, metric_json in enumerate(metric_paths, start=1):
        rows.append(compute_image_metrics(metric_json))
        if idx % 50 == 0 or idx == len(metric_paths):
            print(f'[{idx}/{len(metric_paths)}] processed {metric_json.name}', flush=True)
    rows.sort(key=lambda r: (CONDITION_ORDER.index(r['condition']), r['relative_day'], Path(r['image_name']).name.lower()))

    per_image_csv = quant_dir / 'differentiation_darkness_per_image.csv'
    daily_csv = quant_dir / 'differentiation_darkness_daily_summary.csv'
    write_per_image(rows, per_image_csv)
    write_daily(rows, daily_csv)
    merge_into_main_per_image(quant_dir / 'per_image_metrics.csv', per_image_csv)
    merge_into_main_daily(quant_dir / 'daily_summary.csv', daily_csv)
    plot_paths = plot_all(daily_csv, fig_dir)

    manifest = {
        'out_dir': str(out_dir),
        'n_images': len(rows),
        'thresholds': {
            'very_dark_threshold_normalized': VERY_DARK_THRESHOLD,
        },
        'metric_notes': {
            'normalized_darkness': 'max(0, background_median - gray) / background_median inside segmented organoids',
            'wall_band': 'inner boundary band from adaptive erosion based on equivalent radius',
            'wall_core_ratio': 'wall_darkness_mean / core_darkness_mean',
        },
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
        'plots': [str(p) for p in plot_paths],
    }
    manifest_path = quant_dir / 'differentiation_darkness_manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    print(per_image_csv)
    print(daily_csv)
    for p in plot_paths:
        print(p)
    print(manifest_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
