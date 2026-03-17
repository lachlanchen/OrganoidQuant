#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description='Run enhanced tile metric extraction over manifest source images.')
    p.add_argument('--manifest', required=True)
    p.add_argument('--output-root', required=True)
    p.add_argument('--workers', type=int, default=2)
    return p.parse_args()


def collect_jobs(manifest_path: Path) -> List[Tuple[str, str, str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    jobs: Dict[str, Tuple[str, str, str, str]] = {}
    for panel in manifest['panels']:
        conc = panel['concentration']
        for slot in panel['slots']:
            if slot['empty'] or not slot['source_tif']:
                continue
            tif = slot['source_tif']
            date_name = slot['date_name'] or 'unknown_date'
            stem = Path(tif).stem
            jobs[tif] = (tif, conc, date_name, stem)
    return sorted(jobs.values(), key=lambda x: (x[1], x[2], x[3]))


def is_valid_metric(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return False
    return all(k in obj for k in ('fusion_0_to_5', 'combined_area_px', 'combined_perimeter_px'))


def run_one(job: Tuple[str, str, str, str], output_root: Path, runner: Path) -> Dict[str, Any]:
    source_tif, conc, date_name, stem = job
    tile_root = output_root / conc / date_name / stem
    tile_root.mkdir(parents=True, exist_ok=True)
    metric_json = tile_root / 'tile_metric.json'
    if is_valid_metric(metric_json):
        return {'source_tif': source_tif, 'concentration': conc, 'date_name': date_name, 'stem': stem, 'status': 'skipped_existing', 'tile_metric_json': str(metric_json)}

    cmd = ['bash', str(runner), source_tif, str(tile_root), str(metric_json)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (tile_root / 'tile_metric_runner.log').write_text(proc.stdout, encoding='utf-8')
    status = 'ok' if proc.returncode == 0 and is_valid_metric(metric_json) else 'failed'
    return {
        'source_tif': source_tif,
        'concentration': conc,
        'date_name': date_name,
        'stem': stem,
        'status': status,
        'returncode': proc.returncode,
        'tile_metric_json': str(metric_json),
    }


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    runner = Path(__file__).resolve().parent / 'run_single_tile_enhanced_metric.sh'

    jobs = collect_jobs(manifest_path)
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, job, output_root, runner) for job in jobs]
        for fut in as_completed(futs):
            result = fut.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))

    results.sort(key=lambda x: (x['concentration'], x['date_name'], x['stem']))
    (output_root / 'batch_status.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    failures = [r for r in results if r['status'] == 'failed']
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
