#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2


REPO_ROOT = Path(__file__).resolve().parents[2]
APP80_DIR = REPO_ROOT / 'analysis-tools' / 'app80_first_replicate_multiscale_cellpose'
APP81_DIR = REPO_ROOT / 'analysis-tools' / 'app81_density_multiscale_cellpose'
sys.path.insert(0, str(APP80_DIR))
sys.path.insert(0, str(APP81_DIR))

import run_app80_10uM_all_replicates_large_recovery as base  # noqa: E402
import run_app81_main_density_large_recovery as app81  # noqa: E402
import backfill_app81_full_metrics as backfill  # noqa: E402


DEFAULT_EXPORT_ROOT = REPO_ROOT / 'analysis-output' / 'app81_density_stitched_cellpose_v5_final_single_exports_v2'
DEFAULT_OUT_DIR = REPO_ROOT / 'analysis-output' / 'app81_density_stitched_cellpose_v5_final_metrics_v1'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--export-root', default=str(DEFAULT_EXPORT_ROOT))
    p.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR))
    p.add_argument('--overwrite', action='store_true')
    return p.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def ensure_symlink(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    try:
        dest.symlink_to(src)
    except OSError:
        dest.write_text(str(src) + '\n', encoding='utf-8')


def selection_rank(selection_mode: str) -> tuple[int, str]:
    mode = (selection_mode or '').strip()
    if mode == 'replicate_match':
        return (0, mode)
    if mode == 'backfill_from_replicate_01':
        return (1, mode)
    return (2, mode)


def load_canonical_records(export_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = read_json(export_root / 'export_records.json')
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        export_dir = Path(record['exports']['instance_mask_rgb_png']).resolve().parent
        meta = read_json(export_dir / 'panel_export_metadata.json')
        entry = {
            'record': record,
            'meta': meta,
            'export_dir': export_dir,
            'selected_source': str(Path(meta['selected_source']).resolve()),
        }
        grouped.setdefault(entry['selected_source'], []).append(entry)

    canonical: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for source_tif, entries in grouped.items():
        entries.sort(
            key=lambda e: (
                selection_rank(e['meta'].get('selection_mode', '')),
                int(e['meta'].get('replicate_index', 10**9)),
                str(e['meta'].get('collage_name', '')),
            )
        )
        chosen = entries[0]
        chosen['duplicate_count'] = len(entries) - 1
        chosen['duplicate_exports'] = [str(e['export_dir']) for e in entries[1:]]
        canonical.append(chosen)
        for dup in entries[1:]:
            duplicates.append(
                {
                    'selected_source': source_tif,
                    'ignored_export_dir': str(dup['export_dir']),
                    'ignored_collage_name': dup['meta'].get('collage_name'),
                    'ignored_replicate_index': dup['meta'].get('replicate_index'),
                    'ignored_selection_mode': dup['meta'].get('selection_mode'),
                    'kept_export_dir': str(chosen['export_dir']),
                    'kept_collage_name': chosen['meta'].get('collage_name'),
                    'kept_replicate_index': chosen['meta'].get('replicate_index'),
                    'kept_selection_mode': chosen['meta'].get('selection_mode'),
                }
            )

    canonical.sort(
        key=lambda e: (
            app81.CONDITION_ORDER.index(e['meta']['density']),
            app81.parse_date_dir(e['meta']['date'])[1],
            app81.natural_key(Path(e['selected_source'])),
        )
    )
    return canonical, duplicates


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_signal_png(source_tif: Path, dest: Path) -> None:
    gray = backfill.load_source_gray(source_tif)
    signal = backfill.normalize_u8(gray)
    cv2.imwrite(str(dest), signal)


def process_canonical_record(entry: dict[str, Any], out_dir: Path, relative_day: int, overwrite: bool) -> dict[str, Any]:
    meta = entry['meta']
    export_dir = entry['export_dir']
    source_tif = Path(entry['selected_source']).resolve()
    condition = meta['density']
    date_key = meta['date']
    stage = app81.stage_and_diameters(condition, relative_day)['stage']
    stem = f'{date_key}_{source_tif.stem}'
    run_dir = out_dir / 'runs' / condition / date_key
    run_dir.mkdir(parents=True, exist_ok=True)

    mask_path = run_dir / f'{stem}_mask_16bit.png'
    rgb_path = run_dir / f'{stem}_instance_rgb.png'
    overlay_path = run_dir / f'{stem}_overlay.png'
    signal_path = run_dir / f'{stem}_signal.png'
    stats_path = run_dir / f'{stem}_segmentation_stats.json'
    metric_path = run_dir / f'{stem}_metrics.json'
    source_link = run_dir / f'{stem}_source.tif'

    if not overwrite and metric_path.exists() and stats_path.exists() and signal_path.exists():
        try:
            return read_json(metric_path)
        except Exception:
            pass

    ensure_symlink(export_dir / 'instance_labels_16bit.png', mask_path)
    ensure_symlink(export_dir / 'instance_mask_rgb.png', rgb_path)
    overlay_src = export_dir / 'overlay.png'
    if overlay_src.exists():
        ensure_symlink(overlay_src, overlay_path)
    ensure_symlink(source_tif, source_link)
    build_signal_png(source_tif, signal_path)

    labels = backfill.load_labels(mask_path)
    signal_gray = backfill.load_gray_png(signal_path)
    shape_metrics = app81.aggregate_segmentation_metrics(labels, signal_gray)

    stats = {
        'source_tif': str(source_tif),
        'condition': condition,
        'relative_day': relative_day,
        'stage': stage,
        'mask_count': int(labels.max()),
        'collage_name': meta['collage_name'],
        'selected_source_relative': meta.get('selected_source_relative'),
        'slot': int(meta['slot']),
        'panel_row': int(meta['panel_row']),
        'panel_col': int(meta['panel_col']),
        'source_bbox_in_collage': meta['source_bbox_in_collage'],
        'selection_mode': meta.get('selection_mode'),
        'export_dir': str(export_dir),
        'final_result_dir': meta['final_result_dir'],
        'duplicate_count_for_source': int(entry.get('duplicate_count', 0)),
        'duplicate_exports_for_source': entry.get('duplicate_exports', []),
    }
    write_json(stats_path, stats)

    metric = {
        'condition': condition,
        'date_key': date_key,
        'image_name': source_tif.name,
        'source_tif': str(source_tif),
        'stage': stage,
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
        'overlay_path': str(overlay_path) if overlay_src.exists() else '',
        'signal_path': str(signal_path),
        'stats_path': str(stats_path),
    }
    write_json(metric_path, metric)
    return metric


def run_plot(script: Path, daily_csv: Path) -> list[str]:
    cmd = [sys.executable, str(script), '--daily-csv', str(daily_csv)]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    args = parse_args()
    export_root = Path(args.export_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    canonical, duplicates = load_canonical_records(export_root)
    dates = [app81.parse_date_dir(item['meta']['date'])[1] for item in canonical]
    day0 = min(dates)

    source_rows: list[dict[str, Any]] = []
    for entry in canonical:
        dt = app81.parse_date_dir(entry['meta']['date'])[1]
        relative_day = (dt - day0).days
        metric = process_canonical_record(entry, out_dir, relative_day, args.overwrite)
        source_rows.append(
            {
                'selected_source': entry['selected_source'],
                'date_key': entry['meta']['date'],
                'condition': entry['meta']['density'],
                'image_name': Path(entry['selected_source']).name,
                'relative_day': relative_day,
                'collage_name': entry['meta']['collage_name'],
                'replicate_index': entry['meta']['replicate_index'],
                'selection_mode': entry['meta']['selection_mode'],
                'export_dir': str(entry['export_dir']),
                'final_result_dir': entry['meta']['final_result_dir'],
                'metric_path': metric['stats_path'].replace('_segmentation_stats.json', '_metrics.json'),
                'mask_path': metric['mask_path'],
                'instance_rgb_path': metric['instance_rgb_path'],
                'overlay_path': metric['overlay_path'],
                'signal_path': metric['signal_path'],
                'stats_path': metric['stats_path'],
                'duplicate_count_for_source': entry.get('duplicate_count', 0),
            }
        )

    db_dir = out_dir / 'database'
    db_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        db_dir / 'source_image_database.csv',
        source_rows,
        [
            'selected_source', 'date_key', 'condition', 'image_name', 'relative_day',
            'collage_name', 'replicate_index', 'selection_mode', 'export_dir', 'final_result_dir',
            'metric_path', 'mask_path', 'instance_rgb_path', 'overlay_path', 'signal_path', 'stats_path',
            'duplicate_count_for_source',
        ],
    )
    write_json(db_dir / 'source_image_database.json', source_rows)
    write_csv(
        db_dir / 'ignored_backfill_duplicates.csv',
        duplicates,
        [
            'selected_source',
            'ignored_export_dir', 'ignored_collage_name', 'ignored_replicate_index', 'ignored_selection_mode',
            'kept_export_dir', 'kept_collage_name', 'kept_replicate_index', 'kept_selection_mode',
        ],
    )
    write_json(db_dir / 'ignored_backfill_duplicates.json', duplicates)

    metrics = backfill.load_metrics(out_dir)
    backfill.apply_norms(metrics)
    quant_dir = out_dir / 'profiling' / 'quantification'
    quant_dir.mkdir(parents=True, exist_ok=True)
    per_image_csv = quant_dir / 'per_image_metrics.csv'
    daily_csv = quant_dir / 'daily_summary.csv'
    fields = backfill.write_per_image_csv(metrics, per_image_csv)
    metric_fields, summary_rows = backfill.write_daily_summary(metrics, daily_csv)

    figure_outputs: dict[str, list[str]] = {}
    figure_outputs['overview_metrics'] = run_plot(APP81_DIR / 'plot_app81_main_density_metrics.py', daily_csv)
    figure_outputs['metric_groups'] = run_plot(APP81_DIR / 'plot_app81_main_density_metric_groups.py', daily_csv)
    figure_outputs['full_metric_groups'] = run_plot(APP81_DIR / 'plot_app81_main_density_full_metric_groups.py', daily_csv)

    manifest = {
        'export_root': str(export_root),
        'out_dir': str(out_dir),
        'canonical_unique_sources': len(canonical),
        'ignored_duplicate_exports': len(duplicates),
        'day0': str(day0),
        'source_image_database_csv': str(db_dir / 'source_image_database.csv'),
        'ignored_backfill_duplicates_csv': str(db_dir / 'ignored_backfill_duplicates.csv'),
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
        'all_metric_fields': metric_fields,
        'per_image_fields': fields,
        'n_daily_rows': len(summary_rows),
        'figure_outputs': figure_outputs,
    }
    write_json(out_dir / 'backfill_manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
