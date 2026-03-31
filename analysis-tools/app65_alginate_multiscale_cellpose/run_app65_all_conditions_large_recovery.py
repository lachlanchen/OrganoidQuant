#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import date
from pathlib import Path
import sys

import numpy as np
import torch  # noqa: F401

SCRIPT_DIR = Path(__file__).resolve().parent
APP80_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose')
sys.path.insert(0, str(APP80_DIR))
import run_multiscale_dateaware_cellpose as seg  # noqa: E402
import run_app80_10uM_all_replicates_large_recovery as base  # noqa: E402

CONDITION_ORDER = ['No', '0.02% Alginate', '0.05% Alginate']
MONTH_MAP = {
    '十一月': 11,
    '十二月': 12,
}
DATE_RE = re.compile(r'^(\d{2})-(十一月|十二月)-(\d{4})$')
COND_RE = re.compile(r'(0\.02%\s*Alginate|0\.05%\s*Alginate|\bno\b)', re.I)
MAG_RE = re.compile(r'(10x|10X|4x|4X)(\d+)', re.I)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--conditions', default=','.join(CONDITION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    return p.parse_args()


def normalize_condition(raw: str) -> str:
    raw = re.sub(r'\s+', ' ', raw).strip()
    if raw.lower() == 'no':
        return 'No'
    if raw.lower() == '0.02% alginate':
        return '0.02% Alginate'
    if raw.lower() == '0.05% alginate':
        return '0.05% Alginate'
    raise RuntimeError(f'Unsupported condition: {raw}')


def parse_date_dir(name: str) -> tuple[str, date]:
    m = DATE_RE.match(name)
    if not m:
        raise RuntimeError(f'Cannot parse date dir: {name}')
    day = int(m.group(1))
    month = MONTH_MAP[m.group(2)]
    year = int(m.group(3))
    dt = date(year, month, day)
    date_label = f"{day:02d}-{'Nov' if month == 11 else 'Dec'}"
    return date_label, dt


def natural_key(path: Path) -> tuple[int, str]:
    m = MAG_RE.search(path.stem)
    idx = int(m.group(2)) if m else 10**9
    return (idx, path.stem.lower())


def condition_scale(condition: str, relative_day: int) -> float:
    if relative_day <= 3:
        return 1.0
    if condition == 'No':
        return 1.0
    if condition == '0.02% Alginate':
        return 0.95 if relative_day <= 10 else 0.92
    if condition == '0.05% Alginate':
        return 0.92 if relative_day <= 10 else 0.88
    return 1.0


def stage_and_diameters(condition: str, relative_day: int) -> dict:
    if relative_day <= 1:
        stage = 'early_cluster'
        base_diams = [90, 180, 320]
    elif relative_day <= 4:
        stage = 'cystic_early'
        base_diams = [180, 320, 480]
    elif relative_day <= 7:
        stage = 'cystic_mid'
        base_diams = [220, 380, 560]
    else:
        if condition == 'No':
            stage = 'fused_large' if relative_day <= 10 else 'differentiated_irregular'
        elif condition == '0.02% Alginate':
            stage = 'fused_large' if relative_day <= 11 else 'differentiated_irregular'
        else:
            stage = 'fused_large' if relative_day <= 12 else 'differentiated_irregular'
        base_diams = [380, 700, 980] if stage == 'fused_large' else [320, 600, 900]
    scale = condition_scale(condition, relative_day)
    diameters = [max(80, int(round(d * scale))) for d in base_diams]
    diameters = sorted(set(diameters))
    return {'stage': stage, 'diameters': diameters}


def resolve_conditions(raw: str) -> list[str]:
    asked = [normalize_condition(part) for part in raw.split(',') if part.strip()]
    invalid = [c for c in asked if c not in CONDITION_ORDER]
    if invalid:
        raise SystemExit(f'Unsupported conditions: {invalid}')
    return [c for c in CONDITION_ORDER if c in asked]


def parse_condition_from_name(name: str) -> str:
    m = COND_RE.search(name)
    if not m:
        raise RuntimeError(f'Cannot parse condition from {name}')
    return normalize_condition(m.group(1))


def discover_images(src_root: Path, conditions: list[str]) -> list[tuple[str, str, str, date, Path]]:
    rows: list[tuple[str, str, str, date, Path]] = []
    for date_dir in sorted([p for p in src_root.iterdir() if p.is_dir()]):
        date_key = date_dir.name
        date_label, dt = parse_date_dir(date_key)
        for tif in sorted(date_dir.iterdir(), key=natural_key):
            if not tif.is_file() or tif.suffix.lower() != '.tif':
                continue
            stem = tif.stem
            if '10x' not in stem.lower():
                continue
            condition = parse_condition_from_name(stem)
            if condition not in conditions:
                continue
            rows.append((condition, date_key, date_label, dt, tif))
    return rows


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

    import cv2
    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(signal_path), signal)

    obj_rows = base.object_metrics(label_mask)
    count = len(obj_rows)
    total_area = int(sum(r['area_px'] for r in obj_rows))
    avg_perimeter = float(np.mean([r['perimeter_px'] for r in obj_rows])) if obj_rows else 0.0
    curvature = float(sum(r['area_px'] * r['circularity'] for r in obj_rows) / total_area) if total_area > 0 else 0.0
    edge_intensity = base.boundary_edge_intensity(label_mask, signal)

    seg_stats = {
        'source_tif': str(tif),
        'condition': condition,
        'relative_day': relative_day,
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
        'image_name': tif.name,
        'source_tif': str(tif),
        'stage': cfg['stage'],
        'count': count,
        'curvature': curvature,
        'edge_intensity': edge_intensity,
        'total_area_px': total_area,
        'average_perimeter_px': avg_perimeter,
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
            'condition', 'date_key', 'date_label', 'relative_day', 'image_name', 'stage',
            'count', 'curvature', 'edge_intensity', 'total_area_px', 'average_perimeter_px',
            'count_norm', 'curvature_norm', 'edge_norm', 'normalized_edge_over_count_curvature',
            'mask_path', 'instance_rgb_path', 'overlay_path', 'signal_path', 'stats_path', 'source_tif',
        ])
        for r in rows:
            writer.writerow([
                r['condition'], r['date_key'], r['date_label'], r['relative_day'], r['image_name'], r['stage'],
                r['count'], f"{r['curvature']:.12f}", f"{r['edge_intensity']:.12f}", r['total_area_px'], f"{r['average_perimeter_px']:.12f}",
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
    metrics = ['count', 'curvature', 'edge_intensity', 'total_area_px', 'average_perimeter_px', 'normalized_edge_over_count_curvature']
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
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    conditions = resolve_conditions(args.conditions)
    images = discover_images(src_root, conditions)
    if not images:
        raise SystemExit(f'No 10x TIFFs found under {src_root} for {conditions}')

    day0 = min(dt for _, _, _, dt, _ in images)
    model = seg.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    total = len(images)
    for idx, (condition, date_key, date_label, dt, tif) in enumerate(images, start=1):
        per_date_out = runs_dir / condition / date_key
        per_date_out.mkdir(parents=True, exist_ok=True)
        relative_day = (dt - day0).days
        metric = process_one(model, tif, per_date_out, relative_day, condition, overwrite=args.overwrite)
        metric['condition'] = condition
        metric['date_label'] = date_label
        metric['relative_day'] = relative_day
        metrics.append(metric)
        print(f'[{idx}/{total}] {condition} {date_key} {tif.name} -> count={metric["count"]}', flush=True)

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
        'conditions': conditions,
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
