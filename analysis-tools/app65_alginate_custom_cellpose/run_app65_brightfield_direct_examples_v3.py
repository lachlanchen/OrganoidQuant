#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
import sys

REPO = Path('/home/lachlan/ProjectsLFS/Zhengyu')
SCRIPT = REPO / 'analysis-tools/app65_alginate_custom_cellpose/test_app65_brightfield_direct_cellpose_v3.py'
RAW_BASE = REPO / 'DEO/App65 DEO+Alginate/29-十一月-2025'
OLD_BASE = REPO / 'analysis-output/app65_alginate_multiscale_large_recovery/runs/0.02% Alginate/29-十一月-2025'
DEFAULT_OUT_BASE = REPO / 'analysis-output/test_app65_alginate_custom_cellpose_v3_direct_brightfield/runs/0.02% Alginate/29-十一月-2025'
DEFAULT_STEMS = [
    '0.02% Alginate 10x00',
    '0.02% Alginate 10x01',
    '0.02% Alginate 10x14',
    '0.02% Alginate 10x15',
    '0.02% Alginate 10x16',
    '0.02% Alginate 10x17',
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Run the App65 v3 direct brightfield test set.')
    p.add_argument('--out-base', default=str(DEFAULT_OUT_BASE))
    p.add_argument('--stems', default='|'.join(DEFAULT_STEMS), help='Image stems separated by |')
    return p.parse_args()


def old_source_counts(stats_path: Path) -> dict[str, int]:
    data = json.loads(stats_path.read_text())
    out: dict[str, int] = {}
    for item in data.get('merged_candidates', []):
        src = item.get('source', 'unknown')
        out[src] = out.get(src, 0) + 1
    return out


def main() -> int:
    args = parse_args()
    stems = [s for s in args.stems.split('|') if s]
    out_base = Path(args.out_base).resolve()
    out_base.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for stem in stems:
        tif = RAW_BASE / f'{stem}.tif'
        out_dir = out_base / f'29-十一月-2025_{stem}_brightfield_direct_cellpose_v3'
        cmd = [sys.executable, str(SCRIPT), '--tif', str(tif), '--out-dir', str(out_dir)]
        subprocess.run(cmd, check=True)

        old_metrics = json.loads((OLD_BASE / f'29-十一月-2025_{stem}_metrics.json').read_text())
        old_stats_path = OLD_BASE / f'29-十一月-2025_{stem}_segmentation_stats.json'
        new_summary_path = out_dir / 'step05_final/step56_final_summary.json'
        new_summary = json.loads(new_summary_path.read_text())
        old_sources = old_source_counts(old_stats_path)

        rows.append({
            'image_stem': stem,
            'source_tif': str(tif),
            'old_count': old_metrics.get('count'),
            'new_count': new_summary.get('final_count'),
            'old_source_counts': json.dumps(old_sources, ensure_ascii=False, sort_keys=True),
            'new_candidate_count_before_merge': new_summary.get('candidate_count_before_merge'),
            'new_output_dir': str(out_dir),
            'new_overlay_path': str(out_dir / 'step05_final/step52_final_overlay.png'),
            'new_mask_path': str(out_dir / 'step05_final/step50_final_mask_16bit.png'),
        })

    summary_csv = out_base / 'comparison_summary.csv'
    with summary_csv.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        'dataset': 'App65 0.02% Alginate 29-十一月-2025 v3 direct brightfield custom segmentation test',
        'script': str(SCRIPT),
        'raw_base': str(RAW_BASE),
        'old_output_base': str(OLD_BASE),
        'output_base': str(out_base),
        'images': stems,
        'summary_csv': str(summary_csv),
        'difference': 'direct brightfield multibranch Cellpose; no hint envelope used',
    }
    (out_base / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output_base': str(out_base), 'summary_csv': str(summary_csv), 'image_count': len(rows)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
