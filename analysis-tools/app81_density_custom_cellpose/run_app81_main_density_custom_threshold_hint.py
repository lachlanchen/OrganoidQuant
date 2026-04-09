#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import traceback

import cv2
import numpy as np

CUSTOM_DIR = Path(__file__).resolve().parent
BASE_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_density_multiscale_cellpose')
if str(CUSTOM_DIR) not in sys.path:
    sys.path.insert(0, str(CUSTOM_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import test_app81_threshold_hint_cellpose as custom  # noqa: E402
import run_app81_main_density_large_recovery as app81_base  # noqa: E402

CONDITION_ORDER = app81_base.CONDITION_ORDER
normalize_condition = app81_base.normalize_condition
parse_date_dir = app81_base.parse_date_dir
natural_key = app81_base.natural_key
resolve_conditions = app81_base.resolve_conditions
parse_condition_from_name = app81_base.parse_condition_from_name
discover_images = app81_base.discover_images
aggregate_segmentation_metrics = app81_base.aggregate_segmentation_metrics
write_per_image_csv = app81_base.write_per_image_csv
write_daily_summary = app81_base.write_daily_summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--conditions', default=','.join(CONDITION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--diameters', default='220,320,420,520,700')
    p.add_argument('--checkpoint-every', type=int, default=10)
    p.add_argument('--max-errors', type=int, default=50)
    p.add_argument('--limit', type=int)
    return p.parse_args()


def summarize_branches(candidates: list[custom.Candidate]) -> list[dict]:
    grouped: dict[tuple[str, int], list[custom.Candidate]] = {}
    for cand in candidates:
        grouped.setdefault((cand.source_branch, int(cand.diameter)), []).append(cand)
    rows = []
    for (branch, diameter), subset in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        rows.append({
            'branch': branch,
            'diameter_px': diameter,
            'candidate_count_before_merge': len(subset),
            'mean_score': round(float(np.mean([c.score for c in subset])), 6),
            'mean_overlap_env': round(float(np.mean([c.overlap_env for c in subset])), 6),
            'mean_overlap_core': round(float(np.mean([c.overlap_core for c in subset])), 6),
        })
    return rows


def write_merge_trace(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['rank'])
        writer.writeheader()
        if rows:
            writer.writerows(rows)


def write_final_debug(
    tif: Path,
    tmp_dir: Path,
    diameters: list[int],
    signal: np.ndarray,
    hint_env: np.ndarray,
    hint_core: np.ndarray,
    label_mask: np.ndarray,
    color_mask: np.ndarray,
    overlay: np.ndarray,
    candidates: list[custom.Candidate],
    kept: list[custom.Candidate],
) -> None:
    step06 = tmp_dir / 'step06_final'
    step06.mkdir(parents=True, exist_ok=True)
    custom.save_gray(step06 / 'step60_final_mask_16bit.png', label_mask)
    custom.save_rgb(step06 / 'step61_final_instance_rgb.png', color_mask)
    custom.save_rgb(step06 / 'step62_final_overlay.png', overlay)
    custom.save_gray(step06 / 'step63_final_signal.png', signal)
    custom.save_binary(step06 / 'step64_final_hint_envelope.png', hint_env)
    custom.save_binary(step06 / 'step65_final_hint_core.png', hint_core)

    rows = []
    for idx, cand in enumerate(sorted(kept, key=lambda c: c.area, reverse=True), start=1):
        rows.append({
            'final_label': idx,
            'branch': cand.source_branch,
            'diameter_px': cand.diameter,
            'area_px': cand.area,
            'score': round(cand.score, 6),
            'circularity': round(cand.circularity, 6),
            'fill_ratio': round(cand.fill_ratio, 6),
            'overlap_env': round(cand.overlap_env, 6),
            'overlap_core': round(cand.overlap_core, 6),
            'mean_signal': round(cand.mean_signal, 6),
            'mean_sat': round(cand.mean_sat, 6),
            'border_touch': cand.border_touch,
            'bbox_cover': round(cand.bbox_cover, 6),
        })
    with (step06 / 'step66_final_object_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['final_label'])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    summary = {
        'source_tif': str(tif),
        'diameters_px': diameters,
        'candidate_count_before_merge': len(candidates),
        'final_count': int(label_mask.max()),
        'final_objects': rows,
        'notes': {
            'goal': 'Use threshold hint envelope as a soft prior while keeping Cellpose as the main segmenter.',
            'droplet_avoidance': 'Reject border-dominated large circular candidates with weak hint overlap.',
            'signal_recovery_used': False,
        },
    }
    custom.write_json(step06 / 'step67_final_summary.json', summary)
    custom.write_json(tmp_dir / 'manifest.json', {
        'source_tif': str(tif),
        'output_root': str(tmp_dir),
        'steps': ['step01_input', 'step02_threshold_hint', 'step03_cellpose_raw', 'step04_cellpose_masked', 'step05_merge', 'step06_final'],
        'summary': str((step06 / 'step67_final_summary.json').resolve()),
    })


def process_one(
    model,
    tif: Path,
    out_dir: Path,
    relative_day: int,
    condition: str,
    overwrite: bool,
    diameters: list[int],
) -> dict:
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
        existing_ok = all(path.exists() and path.stat().st_size > 0 for path in required)
        if existing_ok:
            try:
                return json.loads(metric_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass

    rgb, gray = app81_base.seg.load_rgb_gray(tif)
    signal, _, _ = app81_base.seg.compute_hybrid_signal(gray)

    tmp_dir = out_dir / f'{stem}_custom_tmp'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    step01 = tmp_dir / 'step01_input'
    custom.save_rgb(step01 / 'step01_source_rgb.png', rgb)
    custom.save_gray(step01 / 'step02_source_gray.png', gray)

    hint_env, hint_core, hint_meta = custom.build_threshold_hint(rgb, gray, signal, tmp_dir)
    candidates = custom.run_cellpose_branches(model, rgb, gray, hint_env, hint_core, diameters, tmp_dir)
    kept, merge_trace = custom.merge_candidates(candidates)
    write_merge_trace(tmp_dir / 'step05_merge' / 'merge_trace.csv', merge_trace)

    label_mask, color_mask, overlay = custom.build_final_outputs(rgb, kept)
    write_final_debug(tif, tmp_dir, diameters, signal, hint_env, hint_core, label_mask, color_mask, overlay, candidates, kept)

    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(signal_path), signal)

    shape_metrics = aggregate_segmentation_metrics(label_mask, signal)
    seg_stats = {
        'source_tif': str(tif),
        'condition': condition,
        'relative_day': relative_day,
        'stage': 'custom_threshold_hint',
        'diameters_px': diameters,
        'mask_count': int(label_mask.max()),
        'hint_env_path': str((tmp_dir / 'step02_threshold_hint/step30_hint_envelope.png').resolve()),
        'hint_core_path': str((tmp_dir / 'step02_threshold_hint/step31_hint_core.png').resolve()),
        'tmp_dir': str(tmp_dir),
        'branch_summaries': summarize_branches(candidates),
        'merged_candidates': [
            {
                'area': cand.area,
                'score': round(cand.score, 6),
                'diameter_px': cand.diameter,
                'branch': cand.source_branch,
                'overlap_env': round(cand.overlap_env, 6),
                'overlap_core': round(cand.overlap_core, 6),
                'mean_signal': round(cand.mean_signal, 6),
                'mean_sat': round(cand.mean_sat, 6),
                'circularity': round(cand.circularity, 6),
                'fill_ratio': round(cand.fill_ratio, 6),
                'border_touch': cand.border_touch,
                'bbox_cover': round(cand.bbox_cover, 6),
                'source': f'custom_{cand.source_branch}',
            }
            for cand in sorted(kept, key=lambda c: c.area, reverse=True)
        ],
        'notes': hint_meta,
    }
    stats_path.write_text(json.dumps(seg_stats, ensure_ascii=False, indent=2), encoding='utf-8')

    metric = {
        'condition': condition,
        'date_key': date_key,
        'image_name': tif.name,
        'source_tif': str(tif),
        'stage': 'custom_threshold_hint',
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


def metric_sort_key(row: dict) -> tuple[int, int, tuple[int, str]]:
    return (
        CONDITION_ORDER.index(row['condition']),
        int(row['relative_day']),
        natural_key(Path(row['image_name'])),
    )


def normalize_metrics(metrics: list[dict]) -> None:
    if not metrics:
        return
    count_norm = app81_base.base.minmax_floor([float(row['count']) for row in metrics], 0.1)
    curvature_norm = app81_base.base.minmax_floor([float(row['curvature']) for row in metrics], 0.1)
    edge_norm = app81_base.base.minmax_floor([float(row['edge_intensity']) for row in metrics], 0.1)
    for row, cn, kn, en in zip(metrics, count_norm, curvature_norm, edge_norm):
        row['count_norm'] = cn
        row['curvature_norm'] = kn
        row['edge_norm'] = en
        row['normalized_edge_over_count_curvature'] = en / (cn * kn)


def write_checkpoint(
    metrics: list[dict],
    per_image_csv: Path,
    daily_csv: Path,
    manifest_path: Path,
    manifest: dict,
    failures: list[dict],
) -> None:
    metrics.sort(key=metric_sort_key)
    normalize_metrics(metrics)
    write_per_image_csv(metrics, per_image_csv)
    write_daily_summary(metrics, daily_csv)
    manifest['n_images'] = len(metrics)
    manifest['failure_count'] = len(failures)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def append_failure_row(path: Path, row: dict) -> None:
    exists = path.exists()
    with path.open('a', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            'condition',
            'date_key',
            'date_label',
            'relative_day',
            'image_name',
            'source_tif',
            'error_type',
            'error_message',
        ])
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    args = parse_args()
    src_root = Path(args.src_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / 'runs'
    db_dir = out_dir / 'profiling' / 'quantification'
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    cv2.setNumThreads(1)
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
    os.environ.setdefault('MKL_NUM_THREADS', '1')
    os.environ.setdefault('NUMEXPR_NUM_THREADS', '1')
    os.environ.setdefault('VECLIB_MAXIMUM_THREADS', '1')
    os.environ.setdefault('TBB_NUM_THREADS', '1')
    try:
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

    conditions = resolve_conditions(args.conditions)
    images, skipped = discover_images(src_root, conditions)
    if args.limit:
        images = images[:args.limit]
    if not images:
        raise SystemExit(f'No main-phase labeled 10x TIFFs found under {src_root} for {conditions}')

    day0 = min(dt for _, _, _, dt, _ in images)
    diameters = [int(part) for part in args.diameters.split(',') if part.strip()]
    model = custom.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    failures: list[dict] = []
    total = len(images)

    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    failure_csv = db_dir / 'failed_images.csv'
    failure_log = db_dir / 'failed_images_tracebacks.log'
    manifest_path = out_dir / 'run_manifest.json'
    manifest = {
        'src_root': str(src_root),
        'out_dir': str(out_dir),
        'conditions': conditions,
        'phase': 'main_only',
        'magnification': '10x_only',
        'pipeline': 'app81_custom_threshold_hint',
        'diameters': diameters,
        'n_images': 0,
        'expected_images': total,
        'skipped': skipped,
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
        'failure_csv': str(failure_csv),
        'limit': args.limit,
    }

    for idx, (condition, date_key, date_label, dt, tif) in enumerate(images, start=1):
        per_date_out = runs_dir / condition / date_key
        per_date_out.mkdir(parents=True, exist_ok=True)
        relative_day = (dt - day0).days
        try:
            metric = process_one(
                model=model,
                tif=tif,
                out_dir=per_date_out,
                relative_day=relative_day,
                condition=condition,
                overwrite=args.overwrite,
                diameters=diameters,
            )
            metric['condition'] = condition
            metric['date_label'] = date_label
            metric['relative_day'] = relative_day
            metrics.append(metric)
            print(f'[{idx}/{total}] {condition} {date_key} {tif.name} -> count={metric["count"]}', flush=True)
            if len(metrics) % args.checkpoint_every == 0 or idx == total:
                write_checkpoint(metrics, per_image_csv, daily_csv, manifest_path, manifest, failures)
        except Exception as exc:
            failure = {
                'condition': condition,
                'date_key': date_key,
                'date_label': date_label,
                'relative_day': relative_day,
                'image_name': tif.name,
                'source_tif': str(tif),
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            }
            failures.append(failure)
            append_failure_row(failure_csv, failure)
            with failure_log.open('a', encoding='utf-8') as fh:
                fh.write(f'[{idx}/{total}] {condition} {date_key} {tif.name}\n')
                fh.write(traceback.format_exc())
                fh.write('\n')
            print(f'[{idx}/{total}] ERROR {condition} {date_key} {tif.name}: {type(exc).__name__}: {exc}', flush=True)
            if len(failures) >= args.max_errors:
                raise RuntimeError(f'Too many image failures: {len(failures)}') from exc

    write_checkpoint(metrics, per_image_csv, daily_csv, manifest_path, manifest, failures)
    print(per_image_csv)
    print(daily_csv)
    print(manifest_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
