#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description='Run panel metric prompt over all contact sheets.')
    p.add_argument('--manifest', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/contact_sheet_manifest.json'))
    p.add_argument('--output-root', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/panel_prompt_raw'))
    p.add_argument('--workers', type=int, default=3)
    return p.parse_args()


def is_valid_output(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return False
    return all(k in obj for k in ('fusion_2d', 'size_2d', 'perimeter_2d'))


def run_one(entry: Dict[str, Any], output_root: Path, runner: Path) -> Dict[str, Any]:
    concentration = entry['concentration']
    sample_rank = int(entry['sample_rank'])
    out_dir = output_root / concentration / f'sample_{sample_rank:02d}'
    out_dir.mkdir(parents=True, exist_ok=True)
    output_json = out_dir / 'panel_metrics.json'
    prompt_txt = out_dir / 'panel_prompt.txt'
    log_txt = out_dir / 'panel_prompt.log'

    if is_valid_output(output_json):
        return {'concentration': concentration, 'sample_rank': sample_rank, 'status': 'skipped_existing', 'output_json': str(output_json)}

    cmd = [
        str(runner),
        entry['panel_png'],
        str(entry['rows']),
        str(entry['cols']),
        str(output_json),
        str(prompt_txt),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log_txt.write_text(proc.stdout, encoding='utf-8')
    status = 'ok' if proc.returncode == 0 and is_valid_output(output_json) else 'failed'
    return {
        'concentration': concentration,
        'sample_rank': sample_rank,
        'status': status,
        'returncode': proc.returncode,
        'output_json': str(output_json),
        'log_txt': str(log_txt),
    }


def main() -> int:
    args = parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    runner = Path(__file__).resolve().parent / 'run_panel_metric_prompt.sh'

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, panel, output_root, runner) for panel in manifest['panels']]
        for fut in as_completed(futs):
            result = fut.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=False))

    results.sort(key=lambda x: (x['concentration'], x['sample_rank']))
    (output_root / 'batch_status.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    failures = [r for r in results if r['status'] == 'failed']
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
