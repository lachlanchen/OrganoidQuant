#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
import sys

import cv2
import numpy as np
import torch  # noqa: F401

SCRIPT_DIR = Path(__file__).resolve().parent
APP80_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose')
APP81_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_density_multiscale_cellpose')
sys.path.insert(0, str(APP80_DIR))
sys.path.insert(0, str(APP81_DIR))
import run_multiscale_dateaware_cellpose as seg  # noqa: E402
import run_app80_10uM_all_replicates_large_recovery as base  # noqa: E402
import run_app81_main_density_large_recovery as app81a  # noqa: E402

CONDITION_ORDER = ['low', 'middle', 'high']
CONDITION_LABELS = {
    'low': 'Low density',
    'middle': 'Middle density',
    'high': 'High density',
}
DAY_RE = re.compile(r'(?<![A-Za-z])D(\d+)(?![A-Za-z])', re.I)
MAG_RE = re.compile(r'(?<![A-Za-z0-9])(2|4|10)[xX](?![A-Za-z0-9])')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--conditions', default=','.join(CONDITION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    return p.parse_args()


def normalize_condition(raw: str) -> str:
    raw = re.sub(r'\s+', ' ', raw).strip().lower()
    if raw in CONDITION_ORDER:
        return raw
    raise RuntimeError(f'Unsupported density condition: {raw}')


def parse_condition_from_name(name: str) -> str | None:
    low = name.lower()
    if 'high' in low:
        return 'high'
    if 'middle' in low:
        return 'middle'
    if re.search(r'\blow\b', low):
        return 'low'
    return None


def parse_day_from_name(name: str) -> int | None:
    m = DAY_RE.search(name.replace('_', ' '))
    return int(m.group(1)) if m else None


def parse_actual_magnification(name: str) -> str | None:
    mags = MAG_RE.findall(name)
    if not mags:
        return None
    return f"{mags[-1]}x"


def natural_key(path: Path) -> tuple[int, str]:
    m = re.search(r'(\d+)(?!.*\d)', path.stem)
    idx = int(m.group(1)) if m else 10**9
    return (idx, path.stem.lower())


def resolve_conditions(raw: str) -> list[str]:
    asked = [normalize_condition(part) for part in raw.split(',') if part.strip()]
    invalid = [c for c in asked if c not in CONDITION_ORDER]
    if invalid:
        raise SystemExit(f'Unsupported conditions: {invalid}')
    return [c for c in CONDITION_ORDER if c in asked]


def metadata_row(path: Path, src_root: Path) -> dict:
    rel = path.relative_to(src_root)
    low = path.name.lower()
    cond = parse_condition_from_name(path.name)
    day = parse_day_from_name(path.name)
    mag = parse_actual_magnification(path.name)
    phase = 'before_d6' if rel.parent == Path('.') else 'main'
    include = True
    skip_reason = ''
    if low.endswith('_rgb.tif'):
        include = False
        skip_reason = 'rgb_duplicate'
    elif phase != 'main':
        include = False
        skip_reason = 'before_d6_low_confidence'
    elif cond is None:
        include = False
        skip_reason = 'missing_density_label'
    elif day is None:
        include = False
        skip_reason = 'missing_day_token'
    elif mag != '10x':
        include = False
        skip_reason = 'non_10x'
    return {
        'source_tif': str(path.resolve()),
        'relative_path': rel.as_posix(),
        'phase': phase,
        'condition': cond or '',
        'day_token': day if day is not None else '',
        'date_key': f'D{day:02d}' if day is not None else '',
        'date_label': f'D{day}' if day is not None else '',
        'relative_day': day if day is not None else '',
        'magnification': mag or '',
        'rgb_flag': int(low.endswith('_rgb.tif')),
        'include_main_quant': int(include),
        'skip_reason': skip_reason,
    }


def discover_images(src_root: Path, conditions: list[str], audit_dir: Path) -> tuple[list[tuple[str, int, str, Path]], dict]:
    rows = []
    included = []
    skipped_counts: dict[str, int] = {}
    for tif in sorted(src_root.rglob('*.tif')):
        row = metadata_row(tif, src_root)
        if row['include_main_quant'] and row['condition'] not in conditions:
            row['include_main_quant'] = 0
            row['skip_reason'] = 'condition_filtered'
        rows.append(row)
        if row['include_main_quant']:
            included.append((row['condition'], int(row['relative_day']), row['date_key'], tif))
        else:
            skipped_counts[row['skip_reason']] = skipped_counts.get(row['skip_reason'], 0) + 1

    included.sort(key=lambda x: (CONDITION_ORDER.index(x[0]), x[1], natural_key(x[3])))
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_csv = audit_dir / 'metadata_audit.csv'
    with audit_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            'source_tif', 'relative_path', 'phase', 'condition', 'day_token', 'date_key', 'date_label',
            'relative_day', 'magnification', 'rgb_flag', 'include_main_quant', 'skip_reason'
        ])
        writer.writeheader()
        writer.writerows(rows)
    review_csv = audit_dir / 'review_queue.csv'
    review_rows = [r for r in rows if not r['include_main_quant']]
    with review_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(review_rows)
    skipped_counts['included_main_quant'] = len(included)
    skipped_counts['total_tif'] = len(rows)
    skipped_counts['review_csv'] = str(review_csv)
    skipped_counts['metadata_audit_csv'] = str(audit_csv)
    return included, skipped_counts


def process_one(model, tif: Path, out_dir: Path, relative_day: int, condition: str, overwrite: bool) -> dict:
    cfg = app81a.stage_and_diameters(condition, relative_day)
    date_key = f'D{relative_day:02d}'
    date_label = f'D{relative_day}'
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
    label_mask, color_mask = seg.build_outputs(rgb, kept)
    overlay = base.render_overlay(rgb, label_mask, color_mask)

    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(signal_path), signal)

    shape_metrics = app81a.aggregate_segmentation_metrics(label_mask, signal)

    seg_stats = {
        'source_tif': str(tif),
        'condition': condition,
        'relative_day': relative_day,
        'date_key': date_key,
        'date_label': date_label,
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
        'condition': condition,
        'date_key': date_key,
        'date_label': date_label,
        'relative_day': relative_day,
        'image_name': tif.name,
        'source_tif': str(tif),
        'phase': 'B_main_confirmation',
        'stage': cfg['stage'],
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


def write_per_image_csv(rows: list[dict], out_csv: Path) -> None:
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'condition', 'date_key', 'date_label', 'relative_day', 'image_name', 'phase', 'stage',
            'count', 'curvature', 'roundness', 'roundness_deviation_norm', 'roundness_deviation_px_total',
            'edge_intensity', 'total_area_px', 'average_perimeter_px',
            'count_norm', 'curvature_norm', 'edge_norm', 'normalized_edge_over_count_curvature',
            'mask_path', 'instance_rgb_path', 'overlay_path', 'signal_path', 'stats_path', 'source_tif',
        ])
        for r in rows:
            writer.writerow([
                r['condition'], r['date_key'], r['date_label'], r['relative_day'], r['image_name'], r['phase'], r['stage'],
                r['count'], f"{r['curvature']:.12f}", f"{r['roundness']:.12f}", f"{r['roundness_deviation_norm']:.12f}", r['roundness_deviation_px_total'],
                f"{r['edge_intensity']:.12f}", r['total_area_px'], f"{r['average_perimeter_px']:.12f}",
                f"{r['count_norm']:.12f}", f"{r['curvature_norm']:.12f}", f"{r['edge_norm']:.12f}",
                f"{r['normalized_edge_over_count_curvature']:.12f}",
                r.get('mask_path', ''), r.get('instance_rgb_path', ''), r.get('overlay_path', ''),
                r.get('signal_path', ''), r.get('stats_path', ''), r.get('source_tif', ''),
            ])


def write_daily_summary(rows: list[dict], out_csv: Path) -> None:
    grouped: dict[tuple[str, str, str, int], list[dict]] = {}
    for r in rows:
        key = (r['condition'], r['date_key'], r['date_label'], r['relative_day'])
        grouped.setdefault(key, []).append(r)
    metrics = [
        'count', 'curvature', 'roundness', 'roundness_deviation_norm', 'roundness_deviation_px_total',
        'edge_intensity', 'total_area_px', 'average_perimeter_px', 'normalized_edge_over_count_curvature',
    ]
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['condition', 'date_key', 'date_label', 'relative_day', 'n_images']
        for m in metrics:
            header += [f'{m}_mean', f'{m}_std', f'{m}_sem']
        writer.writerow(header)
        for key in sorted(grouped.keys(), key=lambda x: (CONDITION_ORDER.index(x[0]), x[3])):
            subset = grouped[key]
            row = [key[0], key[1], key[2], key[3], len(subset)]
            for m in metrics:
                mean, std, sem = base.mean_std_sem([float(s[m]) for s in subset])
                row += [f'{mean:.12f}', f'{std:.12f}', f'{sem:.12f}']
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    src_root = Path(args.src_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / 'runs'
    db_dir = out_dir / 'profiling' / 'quantification'
    audit_dir = out_dir / 'profiling' / 'audit'
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    conditions = resolve_conditions(args.conditions)
    images, skipped = discover_images(src_root, conditions, audit_dir)
    if not images:
        raise SystemExit(f'No usable main-phase labeled 10x TIFFs found under {src_root} for {conditions}')

    model = seg.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    total = len(images)
    for idx, (condition, relative_day, date_key, tif) in enumerate(images, start=1):
        per_day_out = runs_dir / condition / date_key
        per_day_out.mkdir(parents=True, exist_ok=True)
        metric = process_one(model, tif, per_day_out, relative_day, condition, overwrite=args.overwrite)
        metrics.append(metric)
        print(f'[{idx}/{total}] {condition} D{relative_day} {tif.name} -> count={metric["count"]}', flush=True)

    counts_norm = base.minmax_floor([float(r['count']) for r in metrics], 0.1)
    curvature_norm = base.minmax_floor([float(r['curvature']) for r in metrics], 0.1)
    edge_norm = base.minmax_floor([float(r['edge_intensity']) for r in metrics], 0.1)
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
        'experiment_id': 'test2025_density_B',
        'major_figure': 'density',
        'part': 'B',
        'conditions': conditions,
        'phase': 'independent_confirmation_main_only',
        'magnification': '10x_only',
        'n_images': len(metrics),
        'skipped': skipped,
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
