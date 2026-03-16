#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from scipy.stats import ttest_ind


METRICS = ['fusion', 'size', 'perimeter']
CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']
DAY_ORDER = ['Day0', 'Day2', 'Day3', 'Day4', 'Day5', 'Day6', 'Day7']


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description='Aggregate panel prompt outputs into App80 databases.')
    p.add_argument('--manifest', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/contact_sheet_manifest.json'))
    p.add_argument('--raw-root', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/panel_prompt_raw'))
    p.add_argument('--output-root', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/databases'))
    return p.parse_args()


def stars(p: float | None) -> str:
    if p is None or pd.isna(p):
        return ''
    if p < 0.0001:
        return '****'
    if p < 0.001:
        return '***'
    if p < 0.01:
        return '**'
    if p < 0.05:
        return '*'
    return 'ns'


def main() -> int:
    args = parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    raw_root = Path(args.raw_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    panel_rows: List[Dict[str, Any]] = []

    for panel in manifest['panels']:
        concentration = panel['concentration']
        sample_rank = int(panel['sample_rank'])
        raw_json = raw_root / concentration / f'sample_{sample_rank:02d}' / 'panel_metrics.json'
        if not raw_json.is_file():
            continue
        raw = json.loads(raw_json.read_text(encoding='utf-8'))
        panel_rows.append(
            {
                'concentration': concentration,
                'sample_rank': sample_rank,
                'panel_png': panel['panel_png'],
                'raw_json': str(raw_json),
                'rows': raw['rows'],
                'cols': raw['cols'],
                'panel_note': raw.get('panel_note', ''),
            }
        )
        slot_map = {(slot['row'], slot['col']): slot for slot in panel['slots']}
        for row_idx in range(raw['rows']):
            for col_idx in range(raw['cols']):
                slot = slot_map[(row_idx, col_idx)]
                rows.append(
                    {
                        'concentration': concentration,
                        'sample_rank': sample_rank,
                        'slot_id': slot['slot_id'],
                        'row_idx': row_idx,
                        'col_idx': col_idx,
                        'empty': bool(slot['empty']),
                        'date_name': slot['date_name'],
                        'day_label': slot['day_label'],
                        'relative_day': slot['relative_day'],
                        'source_tif': slot['source_tif'],
                        'tile_png': slot['tile_png'],
                        'panel_png': panel['panel_png'],
                        'raw_json': str(raw_json),
                        'fusion': raw['fusion_2d'][row_idx][col_idx],
                        'size': raw['size_2d'][row_idx][col_idx],
                        'perimeter': raw['perimeter_2d'][row_idx][col_idx],
                    }
                )

    long_df = pd.DataFrame(rows)
    panel_df = pd.DataFrame(panel_rows)
    long_df.to_csv(output_root / 'app80_panel_metric_long.csv', index=False)
    panel_df.to_csv(output_root / 'app80_panel_metric_panels.csv', index=False)

    nonempty = long_df[(~long_df['empty']) & long_df['day_label'].notna()].copy()
    nonempty['concentration'] = pd.Categorical(nonempty['concentration'], categories=CONCENTRATION_ORDER, ordered=True)
    nonempty['day_label'] = pd.Categorical(nonempty['day_label'], categories=DAY_ORDER, ordered=True)

    summary_parts = []
    for metric in METRICS:
        grp = nonempty.groupby(['concentration', 'day_label'], observed=True)[metric]
        part = grp.agg(['mean', 'std', 'count']).reset_index()
        part['sem'] = part['std'] / part['count'].pow(0.5)
        part['metric'] = metric
        summary_parts.append(part)
    summary_df = pd.concat(summary_parts, ignore_index=True)
    summary_df.to_csv(output_root / 'app80_panel_metric_daily_summary.csv', index=False)

    pval_rows: List[Dict[str, Any]] = []
    for metric in METRICS:
        for day in DAY_ORDER:
            ref = nonempty[(nonempty['concentration'] == 'No') & (nonempty['day_label'] == day)][metric].dropna()
            for conc in CONCENTRATION_ORDER:
                if conc == 'No':
                    continue
                vals = nonempty[(nonempty['concentration'] == conc) & (nonempty['day_label'] == day)][metric].dropna()
                p = None
                if len(ref) >= 2 and len(vals) >= 2:
                    p = float(ttest_ind(ref, vals, equal_var=False, nan_policy='omit').pvalue)
                pval_rows.append(
                    {
                        'metric': metric,
                        'day_label': day,
                        'concentration': conc,
                        'p_vs_no': p,
                        'stars_vs_no': stars(p),
                        'n_no': int(len(ref)),
                        'n_group': int(len(vals)),
                    }
                )
    pval_df = pd.DataFrame(pval_rows)
    pval_df.to_csv(output_root / 'app80_panel_metric_pvalues_vs_no.csv', index=False)
    print(json.dumps({
        'long_csv': str(output_root / 'app80_panel_metric_long.csv'),
        'summary_csv': str(output_root / 'app80_panel_metric_daily_summary.csv'),
        'pvalues_csv': str(output_root / 'app80_panel_metric_pvalues_vs_no.csv'),
        'rows': int(len(nonempty)),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
