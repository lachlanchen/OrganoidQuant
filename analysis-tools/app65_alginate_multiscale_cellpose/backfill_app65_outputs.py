#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import run_app65_all_conditions_large_recovery as app65  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--out-dir', required=True)
    p.add_argument('--plot', action='store_true')
    p.add_argument('--allow-partial', action='store_true')
    return p.parse_args()


def load_metrics(out_dir: Path) -> list[dict]:
    runs_dir = out_dir / 'runs'
    metrics: list[dict] = []
    if not runs_dir.exists():
        return metrics
    for metric_path in sorted(runs_dir.rglob('*_metrics.json')):
        data = json.loads(metric_path.read_text(encoding='utf-8'))
        condition = data['condition']
        date_key = data['date_key']
        date_label, dt = app65.parse_date_dir(date_key)
        relative_day = (dt - app65.date(2025, 11, 19)).days
        row = dict(data)
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
