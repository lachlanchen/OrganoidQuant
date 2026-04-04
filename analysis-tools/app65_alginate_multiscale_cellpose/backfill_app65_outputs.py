#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import run_app65_all_conditions_large_recovery as app65  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--out-dir', required=True)
    p.add_argument('--plot', action='store_true')
    p.add_argument('--allow-partial', action='store_true')
    return p.parse_args()


def imread_any(path: Path, flags: int) -> np.ndarray | None:
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


def refresh_metric_json(metric_path: Path) -> dict:
    data = json.loads(metric_path.read_text(encoding='utf-8'))
    mask_path = Path(data['mask_path'])
    signal_path = Path(data['signal_path'])
    label_mask = imread_any(mask_path, cv2.IMREAD_UNCHANGED)
    signal_gray = imread_any(signal_path, cv2.IMREAD_GRAYSCALE)
    if label_mask is None:
        raise RuntimeError(f'Failed to load label mask: {mask_path}')
    if signal_gray is None:
        source_tif = Path(data['source_tif'])
        _, gray = app65.seg.load_rgb_gray(source_tif)
        signal_gray, _, _ = app65.seg.compute_hybrid_signal(gray)
    shape_metrics = app65.aggregate_segmentation_metrics(label_mask, signal_gray)
    data['count'] = shape_metrics['count']
    data['curvature'] = shape_metrics['curvature']
    data['roundness'] = shape_metrics['roundness']
    data['roundness_deviation_norm'] = shape_metrics['roundness_deviation_norm']
    data['roundness_deviation_px_total'] = shape_metrics['roundness_deviation_px_total']
    data['edge_intensity'] = shape_metrics['edge_intensity']
    data['total_area_px'] = shape_metrics['total_area_px']
    data['average_perimeter_px'] = shape_metrics['average_perimeter_px']
    metric_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def load_metrics(out_dir: Path) -> list[dict]:
    runs_dir = out_dir / 'runs'
    metrics: list[dict] = []
    if not runs_dir.exists():
        return metrics
    for metric_path in sorted(runs_dir.rglob('*_metrics.json')):
        data = refresh_metric_json(metric_path)
        condition = data['condition']
        date_key = data['date_key']
        date_label, dt = app65.parse_date_dir(date_key)
        relative_day = (dt - app65.date(2025, 11, 19)).days
        row = copy.deepcopy(data)
        row['date_label'] = date_label
        row['relative_day'] = relative_day
        metrics.append(row)
    metrics.sort(key=lambda r: (app65.CONDITION_ORDER.index(r['condition']), r['relative_day'], app65.natural_key(Path(r['image_name']))))
    return metrics


def apply_norms(metrics: list[dict]) -> None:
    counts_norm = app65.base.minmax_floor([float(r['count']) for r in metrics], 0.1)
    curvature_norm = app65.base.minmax_floor([float(r['curvature']) for r in metrics], 0.1)
    edge_norm = app65.base.minmax_floor([float(r['edge_intensity']) for r in metrics], 0.1)
    for r, cn, kn, en in zip(metrics, counts_norm, curvature_norm, edge_norm):
        r['count_norm'] = cn
        r['curvature_norm'] = kn
        r['edge_norm'] = en
        r['normalized_edge_over_count_curvature'] = en / (cn * kn)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    db_dir = out_dir / 'profiling' / 'quantification'
    db_dir.mkdir(parents=True, exist_ok=True)
    metrics = load_metrics(out_dir)
    if not metrics:
        raise SystemExit(f'No metrics JSON files under {out_dir / "runs"}')
    complete_expected = 886
    if not args.allow_partial and len(metrics) < complete_expected:
        raise SystemExit(f'Only {len(metrics)} / {complete_expected} images found. Pass --allow-partial to backfill partial outputs.')
    apply_norms(metrics)
    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    app65.write_per_image_csv(metrics, per_image_csv)
    app65.write_daily_summary(metrics, daily_csv)
    manifest = {
        'out_dir': str(out_dir),
        'n_metrics_json': len(metrics),
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
        'partial': len(metrics) < complete_expected,
    }
    (out_dir / 'backfill_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.plot:
        plot_script = SCRIPT_DIR / 'plot_app65_all_conditions_metrics.py'
        import subprocess
        subprocess.run([sys.executable, str(plot_script), '--daily-csv', str(daily_csv)], check=True)
    print(per_image_csv)
    print(daily_csv)
    print(out_dir / 'backfill_manifest.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
