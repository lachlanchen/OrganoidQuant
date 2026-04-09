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

BASE_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_density_multiscale_cellpose')
APP80_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose')
for path in (BASE_DIR, APP80_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_app81_main_density_large_recovery as app81_base  # noqa: E402
import run_multiscale_dateaware_cellpose as seg  # noqa: E402

CONDITION_ORDER = app81_base.CONDITION_ORDER
resolve_conditions = app81_base.resolve_conditions
parse_date_dir = app81_base.parse_date_dir
natural_key = app81_base.natural_key
parse_condition_from_name = app81_base.parse_condition_from_name
discover_images = app81_base.discover_images
aggregate_segmentation_metrics = app81_base.aggregate_segmentation_metrics
write_per_image_csv = app81_base.write_per_image_csv
write_daily_summary = app81_base.write_daily_summary
stage_and_diameters = app81_base.stage_and_diameters

SCALES = [0.5, 0.25, 0.125]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--conditions', default=','.join(CONDITION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--checkpoint-every', type=int, default=10)
    p.add_argument('--max-errors', type=int, default=50)
    p.add_argument('--limit', type=int)
    return p.parse_args()


def resize_gray(gray: np.ndarray, scale: float) -> np.ndarray:
    h, w = gray.shape
    return cv2.resize(gray, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)


def upscale_mask(mask_small: np.ndarray, out_shape: tuple[int, int]) -> np.ndarray:
    return cv2.resize(mask_small.astype(np.uint8), (out_shape[1], out_shape[0]), interpolation=cv2.INTER_NEAREST) > 0


def save_gray(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def save_binary(path: Path, mask: np.ndarray) -> None:
    save_gray(path, (mask.astype(np.uint8) * 255))


def scaled_diameters(base_diams: list[int], scale: float) -> list[int]:
    vals = sorted({max(16, int(round(d * scale))) for d in base_diams})
    return vals


def coarse_area_ok(scale: float, area: int) -> bool:
    if scale == 0.5:
        return area >= 1200
    if scale == 0.25:
        return area >= 5000
    return area >= 15000


def extra_app81_filter(cand: seg.Candidate, image_shape: tuple[int, int]) -> bool:
    h, w = image_shape
    img_area = float(h * w)
    frac = cand.area / img_area if img_area else 0.0
    ys, xs = np.where(cand.mask)
    if cand.area <= 0 or ys.size == 0:
        return False
    bbox_w = int(xs.max() - xs.min() + 1)
    bbox_h = int(ys.max() - ys.min() + 1)
    bbox_cover = max(bbox_w / w if w else 0.0, bbox_h / h if h else 0.0)
    border_touch = bool(cand.mask[0, :].any() or cand.mask[-1, :].any() or cand.mask[:, 0].any() or cand.mask[:, -1].any())

    # Stronger droplet/container rejection than the old App81 production path.
    if border_touch and frac > 0.18 and bbox_cover > 0.55 and cand.circularity > 0.80 and cand.support_ratio < 0.38:
        return False
    if border_touch and frac > 0.30 and cand.circularity > 0.74 and cand.mean_signal < 0.52:
        return False
    if frac > 0.55 and cand.circularity > 0.82 and cand.support_ratio < 0.50:
        return False
    return True


def scale_bonus(scale: float, stage: str) -> float:
    if scale == 0.5:
        return 0.06 if stage in {'early_cluster', 'cystic_early', 'cystic_mid'} else 0.02
    if scale == 0.25:
        return 0.08 if stage in {'cystic_mid', 'fused_large', 'differentiated_irregular'} else 0.03
    return 0.10 if stage in {'fused_large', 'differentiated_irregular'} else 0.01


def summarize_branches(candidates: list[seg.Candidate]) -> list[dict]:
    grouped: dict[tuple[str, int], list[seg.Candidate]] = {}
    for cand in candidates:
        grouped.setdefault((str(cand.source), int(cand.diameter)), []).append(cand)
    rows = []
    for (branch, diameter), subset in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        rows.append({
            'branch': branch,
            'diameter_px': diameter,
            'candidate_count_before_merge': len(subset),
            'mean_score': round(float(np.mean([c.score for c in subset])), 6),
            'mean_area': round(float(np.mean([c.area for c in subset])), 2),
            'mean_support_ratio': round(float(np.mean([c.support_ratio for c in subset])), 6),
        })
    return rows


def build_outputs(rgb: np.ndarray, kept: list[seg.Candidate]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    label_mask, color_mask = seg.build_outputs(rgb, kept)
    overlay = cv2.addWeighted(rgb, 0.72, color_mask, 0.55, 0)
    edges = cv2.Canny((label_mask > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (255, 0, 0)
    return label_mask, color_mask, overlay


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


def write_checkpoint(metrics: list[dict], per_image_csv: Path, daily_csv: Path, manifest_path: Path, manifest: dict, failures: list[dict]) -> None:
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
        writer = csv.DictWriter(fh, fieldnames=['condition', 'date_key', 'date_label', 'relative_day', 'image_name', 'source_tif', 'error_type', 'error_message'])
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def process_one(model, tif: Path, out_dir: Path, relative_day: int, condition: str, overwrite: bool) -> dict:
    date_key = tif.parent.name
    cfg = stage_and_diameters(condition, relative_day)
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

    rgb, gray = seg.load_rgb_gray(tif)
    signal, support, grad_norm = seg.compute_hybrid_signal(gray)
    h, w = gray.shape

    tmp_dir = out_dir / f'{stem}_resized_multiscale_tmp'
    step01 = tmp_dir / 'step01_input'
    step02 = tmp_dir / 'step02_multiscale'
    step03 = tmp_dir / 'step03_final'
    step01.mkdir(parents=True, exist_ok=True)
    step02.mkdir(parents=True, exist_ok=True)
    step03.mkdir(parents=True, exist_ok=True)
    save_rgb(step01 / 'step01_source_rgb.png', rgb)
    save_gray(step01 / 'step02_source_gray.png', gray)
    save_gray(step01 / 'step03_signal.png', signal)
    save_gray(step01 / 'step04_support.png', support)

    candidates: list[seg.Candidate] = []
    branch_summaries: list[dict] = []
    for scale_idx, scale in enumerate(SCALES):
        small = resize_gray(gray, scale)
        save_gray(step02 / f'scale_{scale:.3f}_gray.png', small)
        branch_count_scale = 0
        for diameter in scaled_diameters(cfg['diameters'], scale):
            masks, *_ = model.eval(small, diameter=float(diameter), channels=[0, 0], normalize=True, do_3D=False)
            masks = masks.astype(np.uint16)
            label_preview = np.zeros((h, w), dtype=np.uint16)
            kept_count = 0
            original_diameter = max(16, int(round(diameter / scale)))
            for label in range(1, int(masks.max()) + 1):
                mask_small = masks == label
                if not coarse_area_ok(scale, int(mask_small.sum())):
                    continue
                full_mask = upscale_mask(mask_small, (h, w))
                cand = seg.build_candidate_from_mask(full_mask, original_diameter, scale_idx, signal, support, grad_norm, cfg['stage'], source=f'rescale_{scale:.3f}')
                if cand is None:
                    continue
                if not extra_app81_filter(cand, (h, w)):
                    continue
                cand.score += scale_bonus(scale, cfg['stage'])
                candidates.append(cand)
                kept_count += 1
                branch_count_scale += 1
                label_preview[full_mask] = kept_count
            save_gray(step02 / f'scale_{scale:.3f}_diameter_{diameter:04d}_labels_16bit.png', label_preview)
            branch_summaries.append({
                'scale': scale,
                'diameter_px_scaled': diameter,
                'diameter_px_original_equiv': original_diameter,
                'kept_candidates_before_merge': kept_count,
                'status': 'ok',
            })

    kept = seg.merge_candidates(candidates)
    label_mask, color_mask, overlay = build_outputs(rgb, kept)

    save_gray(step03 / 'step30_final_mask_16bit.png', label_mask)
    save_rgb(step03 / 'step31_final_instance_rgb.png', color_mask)
    save_rgb(step03 / 'step32_final_overlay.png', overlay)

    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(signal_path), signal)

    shape_metrics = aggregate_segmentation_metrics(label_mask, signal)
    seg_stats = {
        'source_tif': str(tif),
        'condition': condition,
        'relative_day': relative_day,
        'stage': cfg['stage'],
        'pipeline': 'app81_resized_multiscale_v1',
        'scales': SCALES,
        'base_diameters_px': cfg['diameters'],
        'mask_count': int(label_mask.max()),
        'tmp_dir': str(tmp_dir),
        'branch_summaries': branch_summaries,
        'merged_candidates': [
            {
                'area': cand.area,
                'score': round(cand.score, 6),
                'diameter_px': cand.diameter,
                'support_ratio': round(cand.support_ratio, 6),
                'mean_signal': round(cand.mean_signal, 6),
                'edge_strength': round(cand.edge_strength, 6),
                'circularity': round(cand.circularity, 6),
                'source': cand.source,
            }
            for cand in sorted(kept, key=lambda c: c.area, reverse=True)
        ],
        'notes': {
            'goal': 'Simpler App81 multiscale segmentation using resized grayscale passes at 1/2, 1/4, and 1/8 resolution.',
            'no_crop_rescue': True,
            'no_threshold_hint_gate': True,
        },
    }
    stats_path.write_text(json.dumps(seg_stats, ensure_ascii=False, indent=2), encoding='utf-8')

    metric = {
        'condition': condition,
        'date_key': date_key,
        'image_name': tif.name,
        'source_tif': str(tif),
        'stage': 'resized_multiscale_v1',
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
    model = seg.models.CellposeModel(gpu=True)
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
        'pipeline': 'app81_resized_multiscale_v1',
        'scales': SCALES,
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
            metric = process_one(model, tif, per_date_out, relative_day, condition, args.overwrite)
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
