#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
import sys

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import run_multiscale_dateaware_cellpose as seg  # noqa: E402

DATE_RE = re.compile(r'^(\d{2})-.*-(\d{4})$')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--overwrite', action='store_true')
    return p.parse_args()


def parse_date_dir(name: str) -> tuple[str, date]:
    m = DATE_RE.match(name)
    if not m:
        raise RuntimeError(f'Cannot parse date dir: {name}')
    day = int(m.group(1))
    year = int(m.group(2))
    dt = date(year, 12, day)
    return f'{day:02d}-Dec', dt


def natural_key(path: Path) -> tuple[int, str]:
    m = re.search(r'(\d+)$', path.stem)
    return (int(m.group(1)) if m else 10**9, path.stem.lower())


def object_metrics(label_mask: np.ndarray) -> list[dict]:
    rows: list[dict] = []
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
        rows.append({'label': int(lab), 'area_px': area, 'perimeter_px': perimeter, 'circularity': circularity})
    return rows


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


def minmax_floor(values: list[float], floor: float) -> list[float]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    if vmax <= vmin:
        return [1.0 for _ in values]
    span = vmax - vmin
    return [floor + (1.0 - floor) * ((v - vmin) / span) for v in values]


def discover_images(src_root: Path) -> list[tuple[str, str, date, Path]]:
    rows: list[tuple[str, str, date, Path]] = []
    for date_key in seg.DATE_CONFIG:
        d = src_root / date_key
        if not d.is_dir():
            continue
        date_label, dt = parse_date_dir(date_key)
        for tif in sorted(d.iterdir(), key=natural_key):
            if not tif.is_file() or tif.suffix.lower() != '.tif':
                continue
            if '10x' not in tif.stem.lower():
                continue
            rows.append((date_key, date_label, dt, tif))
    return rows


def process_one(model, tif: Path, out_dir: Path, overwrite: bool) -> dict:
    date_key = tif.parent.name
    cfg = seg.DATE_CONFIG[date_key]
    stem = f'{date_key}_{tif.stem}'
    mask_path = out_dir / f'{stem}_mask_16bit.png'
    signal_path = out_dir / f'{stem}_signal.png'
    stats_path = out_dir / f'{stem}_segmentation_stats.json'
    metric_path = out_dir / f'{stem}_metrics.json'

    if not overwrite and metric_path.exists() and stats_path.exists() and mask_path.exists() and signal_path.exists():
        return json.loads(metric_path.read_text(encoding='utf-8'))

    rgb, gray = seg.load_rgb_gray(tif)
    signal, support, grad_norm = seg.compute_hybrid_signal(gray)

    candidates: list[seg.Candidate] = []
    branch_summaries = []
    for branch_rank, diameter in enumerate(cfg['diameters']):
        try:
            masks, *_ = model.eval(gray, diameter=float(diameter), channels=[0, 0], normalize=True, do_3D=False)
            masks = masks.astype(np.uint16)
            branch_count = 0
            for label in range(1, int(masks.max()) + 1):
                cand = seg.build_candidate(masks, label, diameter, branch_rank, signal, support, grad_norm, cfg['stage'])
                if cand is not None:
                    candidates.append(cand)
                    branch_count += 1
            branch_summaries.append({'diameter_px': diameter, 'kept_candidates_before_merge': branch_count, 'status': 'ok'})
        except Exception as exc:
            branch_summaries.append({'diameter_px': diameter, 'kept_candidates_before_merge': 0, 'status': f'failed: {type(exc).__name__}'})

    signal_candidates = seg.recover_signal_candidates(signal, support, grad_norm, cfg['stage'])
    candidates.extend(signal_candidates)
    branch_summaries.append({'diameter_px': None, 'kept_candidates_before_merge': len(signal_candidates), 'status': 'ok', 'source': 'signal_recovery'})

    kept = seg.merge_candidates(candidates)
    label_mask, _ = seg.build_outputs(rgb, kept)

    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(signal_path), signal)

    obj_rows = object_metrics(label_mask)
    count = len(obj_rows)
    total_area = int(sum(r['area_px'] for r in obj_rows))
    avg_perimeter = float(np.mean([r['perimeter_px'] for r in obj_rows])) if obj_rows else 0.0
    curvature = float(sum(r['area_px'] * r['circularity'] for r in obj_rows) / total_area) if total_area > 0 else 0.0
    edge_intensity = boundary_edge_intensity(label_mask, signal)

    seg_stats = {
        'source_tif': str(tif),
        'stage': cfg['stage'],
        'diameters_px': cfg['diameters'],
        'mask_count': int(label_mask.max()),
        'branch_summaries': branch_summaries,
        'merged_candidates': [
            {
                'area': cand.area,
                'score': round(cand.score, 4),
                'diameter_px': cand.diameter,
                'support_ratio': round(cand.support_ratio, 4),
                'mean_signal': round(cand.mean_signal, 4),
                'edge_strength': round(cand.edge_strength, 4),
                'circularity': round(cand.circularity, 4),
                'source': cand.source,
            }
            for cand in sorted(kept, key=lambda c: c.area, reverse=True)
        ],
    }
    stats_path.write_text(json.dumps(seg_stats, ensure_ascii=False, indent=2), encoding='utf-8')

    metric = {
        'date_key': date_key,
        'image_name': tif.name,
        'source_tif': str(tif),
        'stage': cfg['stage'],
        'count': count,
        'curvature': curvature,
        'edge_intensity': edge_intensity,
        'total_area_px': total_area,
        'average_perimeter_px': avg_perimeter,
        'mask_path': str(mask_path),
        'signal_path': str(signal_path),
        'stats_path': str(stats_path),
    }
    metric_path.write_text(json.dumps(metric, ensure_ascii=False, indent=2), encoding='utf-8')
    return metric


def write_per_image_csv(rows: list[dict], out_csv: Path) -> None:
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'date_key', 'date_label', 'relative_day', 'image_name', 'stage',
            'count', 'curvature', 'edge_intensity', 'total_area_px', 'average_perimeter_px',
            'count_norm', 'curvature_norm', 'edge_norm', 'normalized_edge_over_count_curvature'
        ])
        for r in rows:
            writer.writerow([
                r['date_key'], r['date_label'], r['relative_day'], r['image_name'], r['stage'],
                r['count'], f"{r['curvature']:.12f}", f"{r['edge_intensity']:.12f}", r['total_area_px'], f"{r['average_perimeter_px']:.12f}",
                f"{r['count_norm']:.12f}", f"{r['curvature_norm']:.12f}", f"{r['edge_norm']:.12f}", f"{r['normalized_edge_over_count_curvature']:.12f}",
            ])


def mean_std_sem(values: list[float]) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(arr.mean()) if arr.size else 0.0
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    sem = float(std / math.sqrt(arr.size)) if arr.size > 1 else 0.0
    return mean, std, sem


def write_daily_summary(rows: list[dict], out_csv: Path) -> None:
    grouped: dict[tuple[str, str, int], list[dict]] = {}
    for r in rows:
        key = (r['date_key'], r['date_label'], r['relative_day'])
        grouped.setdefault(key, []).append(r)
    metrics = ['count', 'curvature', 'edge_intensity', 'total_area_px', 'average_perimeter_px', 'normalized_edge_over_count_curvature']
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['date_key', 'date_label', 'relative_day', 'n_images']
        for m in metrics:
            header += [f'{m}_mean', f'{m}_std', f'{m}_sem']
        writer.writerow(header)
        for key in sorted(grouped.keys(), key=lambda x: x[2]):
            subset = grouped[key]
            row = [key[0], key[1], key[2], len(subset)]
            for m in metrics:
                mean, std, sem = mean_std_sem([float(s[m]) for s in subset])
                row += [f'{mean:.12f}', f'{std:.12f}', f'{sem:.12f}']
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    src_root = Path(args.src_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / 'runs'
    db_dir = out_dir / 'databases'
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    images = discover_images(src_root)
    if not images:
        raise SystemExit(f'No 10x TIFFs found under {src_root}')

    day0 = min(dt for _, _, dt, _ in images)

    model = seg.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    total = len(images)
    for idx, (date_key, date_label, dt, tif) in enumerate(images, start=1):
        per_date_out = runs_dir / date_key
        per_date_out.mkdir(parents=True, exist_ok=True)
        metric = process_one(model, tif, per_date_out, overwrite=args.overwrite)
        metric['date_label'] = date_label
        metric['relative_day'] = (dt - day0).days
        metrics.append(metric)
        print(f'[{idx}/{total}] {date_key} {tif.name} -> count={metric["count"]}')

    counts_norm = minmax_floor([float(r['count']) for r in metrics], 0.1)
    curvature_norm = minmax_floor([float(r['curvature']) for r in metrics], 0.1)
    edge_norm = minmax_floor([float(r['edge_intensity']) for r in metrics], 0.1)
    for r, cn, kn, en in zip(metrics, counts_norm, curvature_norm, edge_norm):
        r['count_norm'] = cn
        r['curvature_norm'] = kn
        r['edge_norm'] = en
        r['normalized_edge_over_count_curvature'] = en / (cn * kn)

    metrics.sort(key=lambda r: (r['relative_day'], natural_key(Path(r['image_name']))))
    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    write_per_image_csv(metrics, per_image_csv)
    write_daily_summary(metrics, daily_csv)

    manifest = {
        'src_root': str(src_root),
        'out_dir': str(out_dir),
        'n_images': len(metrics),
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
    }
    (out_dir / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(per_image_csv)
    print(daily_csv)
    print(out_dir / 'run_manifest.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
