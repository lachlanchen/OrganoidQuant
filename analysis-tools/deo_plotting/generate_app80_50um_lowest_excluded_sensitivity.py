#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_guided_deo_figures as guided


ROOT_DEFAULT = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery')


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Generate App80 sensitivity figure excluding the lowest 50uM D6 fusion point.')
    p.add_argument('--root', type=Path, default=ROOT_DEFAULT)
    return p.parse_args()


def main() -> None:
    root = parse_args().root.resolve()
    cfg = guided.infer_config(root)
    if cfg.key != 'app80':
        raise SystemExit('This sensitivity script is only for App80.')

    df = guided.load_df(root, cfg)
    target_metric = 'center_weighted_edge_sum'
    sub = df.loc[(df[cfg.group_field] == '50uM') & (df['relative_day'] == 6), [cfg.group_field, 'relative_day', 'image_name', 'mask_path', 'signal_path', target_metric]].dropna().copy()
    if sub.empty:
        raise SystemExit('No 50uM D6 rows found.')
    drop_idx = sub[target_metric].astype(float).idxmin()
    excluded = df.loc[[drop_idx]].copy()
    filtered = df.drop(index=drop_idx).copy()

    sens_root = root / 'figures-guided-v2' / 'sensitivity_checks'
    sens_polished_root = root / 'figures-polished-guided-v2' / 'sensitivity_checks'
    sens_root.mkdir(parents=True, exist_ok=True)
    sens_polished_root.mkdir(parents=True, exist_ok=True)

    only_focus_cfg = replace(cfg, focused=(guided.FocusSpec(6, target_metric, 'Fusion D6, 50 uM lowest excluded'),), show_plot_stats=True)
    focus_stats = guided.plot_focused(
        filtered,
        only_focus_cfg,
        sens_root / 'app80_fusion_d6_50uM_lowest_excluded_guided.png',
        sens_root / 'app80_fusion_d6_50uM_lowest_excluded_guided.pdf',
        polished=False,
    )
    focus_stats_polished = guided.plot_focused(
        filtered,
        only_focus_cfg,
        sens_polished_root / 'app80_fusion_d6_50uM_lowest_excluded_polished_guided.png',
        sens_polished_root / 'app80_fusion_d6_50uM_lowest_excluded_polished_guided.pdf',
        polished=True,
    )

    excluded_csv = sens_root / 'excluded_point.csv'
    excluded.to_csv(excluded_csv, index=False)
    guided.write_df(focus_stats, sens_root / 'focused_pairwise_vs_control.csv')
    guided.write_df(focus_stats_polished, sens_root / 'focused_pairwise_vs_control_polished.csv')
    manifest = {
        'root': str(root),
        'dataset': 'app80',
        'excluded_rule': 'drop lowest 50uM point at D6 for center_weighted_edge_sum only',
        'excluded_point': excluded.iloc[0].to_dict(),
        'outputs': {
            'guided_png': str(sens_root / 'app80_fusion_d6_50uM_lowest_excluded_guided.png'),
            'guided_pdf': str(sens_root / 'app80_fusion_d6_50uM_lowest_excluded_guided.pdf'),
            'polished_png': str(sens_polished_root / 'app80_fusion_d6_50uM_lowest_excluded_polished_guided.png'),
            'polished_pdf': str(sens_polished_root / 'app80_fusion_d6_50uM_lowest_excluded_polished_guided.pdf'),
            'excluded_csv': str(excluded_csv),
            'pairwise_csv': str(sens_root / 'focused_pairwise_vs_control.csv'),
        },
    }
    (sens_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (sens_polished_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
