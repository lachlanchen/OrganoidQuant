#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch  # noqa: F401

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import run_multiscale_dateaware_cellpose as seg  # noqa: E402
import run_app80_10uM_all_replicates_large_recovery as base  # noqa: E402

CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--concentrations', default=','.join(CONCENTRATION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    return p.parse_args()


def resolve_concentrations(raw: str) -> list[str]:
    asked = [part.strip() for part in raw.split(',') if part.strip()]
    invalid = [c for c in asked if c not in CONCENTRATION_ORDER]
    if invalid:
        raise SystemExit(f'Unsupported concentrations: {invalid}')
    return [c for c in CONCENTRATION_ORDER if c in asked]


def discover_images(src_root: Path, concentrations: list[str]) -> list[tuple[str, str, str, object, Path]]:
    rows: list[tuple[str, str, str, object, Path]] = []
    for concentration in concentrations:
        conc_dir = src_root / concentration
        if not conc_dir.is_dir():
            continue
        for date_key in seg.DATE_CONFIG:
            date_dir = conc_dir / date_key
            if not date_dir.is_dir():
                continue
            date_label, dt = base.parse_date_dir(date_key)
            for tif in sorted(date_dir.iterdir(), key=base.natural_key):
                if not tif.is_file() or tif.suffix.lower() != '.tif':
                    continue
                if '10x' not in tif.stem.lower():
                    continue
                rows.append((concentration, date_key, date_label, dt, tif))
    return rows


def mean_std_sem(values: list[float]) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(arr.mean()) if arr.size else 0.0
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    sem = float(std / math.sqrt(arr.size)) if arr.size > 1 else 0.0
    return mean, std, sem


def write_per_image_csv(rows: list[dict], out_csv: Path) -> None:
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'concentration', 'date_key', 'date_label', 'relative_day', 'image_name', 'stage',
            'count', 'curvature', 'roundness', 'roundness_deviation_norm', 'roundness_deviation_px_total',
            'edge_intensity', 'total_area_px', 'average_perimeter_px',
            'count_norm', 'curvature_norm', 'edge_norm', 'normalized_edge_over_count_curvature',
            'mask_path', 'instance_rgb_path', 'overlay_path', 'signal_path', 'stats_path', 'source_tif',
        ])
        for r in rows:
            writer.writerow([
                r['concentration'], r['date_key'], r['date_label'], r['relative_day'], r['image_name'], r['stage'],
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
        key = (r['concentration'], r['date_key'], r['date_label'], r['relative_day'])
        grouped.setdefault(key, []).append(r)
    metrics = [
        'count',
        'curvature',
        'roundness',
        'roundness_deviation_norm',
        'roundness_deviation_px_total',
        'edge_intensity',
        'total_area_px',
        'average_perimeter_px',
        'normalized_edge_over_count_curvature',
    ]
    with out_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['concentration', 'date_key', 'date_label', 'relative_day', 'n_images']
        for m in metrics:
            header += [f'{m}_mean', f'{m}_std', f'{m}_sem']
        writer.writerow(header)
        for key in sorted(grouped.keys(), key=lambda x: (CONCENTRATION_ORDER.index(x[0]), x[3])):
            subset = grouped[key]
            row = [key[0], key[1], key[2], key[3], len(subset)]
            for m in metrics:
                mean, std, sem = mean_std_sem([float(s[m]) for s in subset])
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

    concentrations = resolve_concentrations(args.concentrations)
    images = discover_images(src_root, concentrations)
    if not images:
        raise SystemExit(f'No 10x TIFFs found under {src_root} for {concentrations}')

    day0 = min(dt for _, _, _, dt, _ in images)
    model = seg.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    total = len(images)
    for idx, (concentration, date_key, date_label, dt, tif) in enumerate(images, start=1):
        per_date_out = runs_dir / concentration / date_key
        per_date_out.mkdir(parents=True, exist_ok=True)
        metric = base.process_one(model, tif, per_date_out, overwrite=args.overwrite)
        metric['concentration'] = concentration
        metric['date_label'] = date_label
        metric['relative_day'] = (dt - day0).days
        metrics.append(metric)
        print(f'[{idx}/{total}] {concentration} {date_key} {tif.name} -> count={metric["count"]}')

    counts_norm = base.minmax_floor([float(r['count']) for r in metrics], 0.1)
    curvature_norm = base.minmax_floor([float(r['curvature']) for r in metrics], 0.1)
    edge_norm = base.minmax_floor([float(r['edge_intensity']) for r in metrics], 0.1)
    for r, cn, kn, en in zip(metrics, counts_norm, curvature_norm, edge_norm):
        r['count_norm'] = cn
        r['curvature_norm'] = kn
        r['edge_norm'] = en
        r['normalized_edge_over_count_curvature'] = en / (cn * kn)

    metrics.sort(key=lambda r: (CONCENTRATION_ORDER.index(r['concentration']), r['relative_day'], base.natural_key(Path(r['image_name']))))
    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    write_per_image_csv(metrics, per_image_csv)
    write_daily_summary(metrics, daily_csv)

    manifest = {
        'src_root': str(src_root),
        'out_dir': str(out_dir),
        'concentrations': concentrations,
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
