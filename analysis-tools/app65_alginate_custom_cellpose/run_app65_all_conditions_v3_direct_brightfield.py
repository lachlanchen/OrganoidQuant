#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
import sys

import cv2
import numpy as np

CUSTOM_DIR = Path(__file__).resolve().parent
MULTISCALE_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app65_alginate_multiscale_cellpose')
if str(CUSTOM_DIR) not in sys.path:
    sys.path.insert(0, str(CUSTOM_DIR))
if str(MULTISCALE_DIR) not in sys.path:
    sys.path.insert(0, str(MULTISCALE_DIR))

import test_app65_brightfield_direct_cellpose_v3 as v3  # noqa: E402
import run_app65_all_conditions_large_recovery as app65_base  # noqa: E402

CONDITION_ORDER = app65_base.CONDITION_ORDER
normalize_condition = app65_base.normalize_condition
parse_date_dir = app65_base.parse_date_dir
natural_key = app65_base.natural_key
resolve_conditions = app65_base.resolve_conditions
parse_condition_from_name = app65_base.parse_condition_from_name
discover_images = app65_base.discover_images
aggregate_segmentation_metrics = app65_base.aggregate_segmentation_metrics
write_per_image_csv = app65_base.write_per_image_csv
write_daily_summary = app65_base.write_daily_summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--conditions', default=','.join(CONDITION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--diameters', default='220,320,420,520,700')
    return p.parse_args()


def summarize_branches(candidates: list[v3.Candidate]) -> list[dict]:
    grouped: dict[tuple[str, int], list[v3.Candidate]] = {}
    for cand in candidates:
        grouped.setdefault((cand.branch, int(cand.diameter)), []).append(cand)
    rows = []
    for (branch, diameter), subset in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        rows.append({
            'branch': branch,
            'diameter_px': diameter,
            'candidate_count_before_merge': len(subset),
            'mean_score': round(float(np.mean([c.score for c in subset])), 6),
        })
    return rows


def process_one(model, tif: Path, out_dir: Path, relative_day: int, condition: str, overwrite: bool, diameters: list[int]) -> dict:
    date_key = tif.parent.name
    stem = f'{date_key}_{tif.stem}'
    mask_path = out_dir / f'{stem}_mask_16bit.png'
    rgb_path = out_dir / f'{stem}_instance_rgb.png'
    overlay_path = out_dir / f'{stem}_overlay.png'
    signal_path = out_dir / f'{stem}_signal.png'
    stats_path = out_dir / f'{stem}_segmentation_stats.json'
    metric_path = out_dir / f'{stem}_metrics.json'

    if not overwrite:
        required = [metric_path, stats_path, mask_path, signal_path, rgb_path, overlay_path]
        existing_ok = all(p.exists() and p.stat().st_size > 0 for p in required)
        if existing_ok:
            try:
                return json.loads(metric_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass

    rgb, gray = app65_base.seg.load_rgb_gray(tif)
    signal, _, _ = app65_base.seg.compute_hybrid_signal(gray)

    tmp_dir = out_dir / f'{stem}_v3_tmp'
    if tmp_dir.exists():
        pass
    tmp_dir.mkdir(parents=True, exist_ok=True)

    clahe, wall_emphasis, grad_mag, support_mask, meta = v3.build_direct_evidence(rgb, gray, signal, tmp_dir)
    candidates = v3.run_cellpose_branches(
        model,
        rgb,
        gray,
        signal,
        clahe,
        wall_emphasis,
        grad_mag,
        support_mask,
        diameters,
        tmp_dir,
    )
    kept, _ = v3.merge_candidates(candidates)
    label_mask, color_mask, overlay = v3.build_final_outputs(rgb, kept)

    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(signal_path), signal)

    shape_metrics = aggregate_segmentation_metrics(label_mask, signal)
    obj_rows = shape_metrics['object_rows']
    seg_stats = {
        'source_tif': str(tif),
        'condition': condition,
        'relative_day': relative_day,
        'stage': 'v3_direct_brightfield',
        'diameters_px': diameters,
        'mask_count': int(label_mask.max()),
        'support_mask_path': str((tmp_dir / 'step02_brightfield_evidence/step20_support_mask.png').resolve()),
        'branch_summaries': summarize_branches(candidates),
        'merged_candidates': [
            {
                'area': cand.area,
                'score': round(cand.score, 6),
                'diameter_px': cand.diameter,
                'branch': cand.branch,
                'support_overlap': round(cand.support_overlap, 6),
                'boundary_strength': round(cand.boundary_strength, 6),
                'interior_texture': round(cand.interior_texture, 6),
                'mean_signal': round(cand.mean_signal, 6),
                'circularity': round(cand.circularity, 6),
                'fill_ratio': round(cand.fill_ratio, 6),
                'source': f'v3_{cand.branch}',
            }
            for cand in sorted(kept, key=lambda c: c.area, reverse=True)
        ],
        'notes': meta,
    }
    stats_path.write_text(json.dumps(seg_stats, ensure_ascii=False, indent=2), encoding='utf-8')

    metric = {
        'condition': condition,
        'date_key': date_key,
        'image_name': tif.name,
        'source_tif': str(tif),
        'stage': 'v3_direct_brightfield',
        'count': shape_metrics['count'],
        'curvature': shape_metrics['curvature'],
        'roundness': shape_metrics['roundness'],
        'roundness_deviation_norm': shape_metrics['roundness_deviation_norm'],
        'roundness_deviation_px_total': shape_metrics['roundness_deviation_px_total'],
        'edge_intensity': shape_metrics['edge_intensity'],
        'total_area_px': shape_metrics['total_area_px'],
        'average_perimeter_px': shape_metrics['average_perimeter_px'],
        'mask_path': str(mask_path),
        'instance_rgb_path': str(rgb_path),
        'overlay_path': str(overlay_path),
        'signal_path': str(signal_path),
        'stats_path': str(stats_path),
    }
    metric_path.write_text(json.dumps(metric, ensure_ascii=False, indent=2), encoding='utf-8')
    return metric


def main() -> int:
    args = parse_args()
    src_root = Path(args.src_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / 'runs'
    db_dir = out_dir / 'profiling' / 'quantification'
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    conditions = resolve_conditions(args.conditions)
    images = discover_images(src_root, conditions)
    if not images:
        raise SystemExit(f'No 10x TIFFs found under {src_root} for {conditions}')

    day0 = min(dt for _, _, _, dt, _ in images)
    diameters = [int(x) for x in args.diameters.split(',') if x.strip()]
    model = v3.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    total = len(images)
    for idx, (condition, date_key, date_label, dt, tif) in enumerate(images, start=1):
        per_date_out = runs_dir / condition / date_key
        per_date_out.mkdir(parents=True, exist_ok=True)
        relative_day = (dt - day0).days
        metric = process_one(model, tif, per_date_out, relative_day, condition, overwrite=args.overwrite, diameters=diameters)
        metric['condition'] = condition
        metric['date_label'] = date_label
        metric['relative_day'] = relative_day
        metrics.append(metric)
        print(f'[{idx}/{total}] {condition} {date_key} {tif.name} -> count={metric["count"]}', flush=True)

    counts_norm = app65_base.base.minmax_floor([float(r['count']) for r in metrics], 0.1)
    curvature_norm = app65_base.base.minmax_floor([float(r['curvature']) for r in metrics], 0.1)
    edge_norm = app65_base.base.minmax_floor([float(r['edge_intensity']) for r in metrics], 0.1)
    for r, cn, kn, en in zip(metrics, counts_norm, curvature_norm, edge_norm):
        r['count_norm'] = cn
        r['curvature_norm'] = kn
        r['edge_norm'] = en
        r['normalized_edge_over_count_curvature'] = en / (cn * kn)

    metrics.sort(key=lambda r: (CONDITION_ORDER.index(r['condition']), r['relative_day'], natural_key(Path(r['image_name']))))
    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    write_per_image_csv(metrics, per_image_csv)
    write_daily_summary(metrics, daily_csv)

    manifest = {
        'src_root': str(src_root),
        'out_dir': str(out_dir),
        'conditions': conditions,
        'diameters': diameters,
        'pipeline': 'app65_v3_direct_brightfield',
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
