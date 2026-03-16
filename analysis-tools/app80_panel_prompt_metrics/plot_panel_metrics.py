#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

CONCENTRATION_ORDER = ['No', '10uM', '20uM', '50uM', '100uM']
DAY_ORDER = ['Day0', 'Day2', 'Day3', 'Day4', 'Day5', 'Day6', 'Day7']
DAY_X = {'Day0': 0, 'Day2': 2, 'Day3': 3, 'Day4': 4, 'Day5': 5, 'Day6': 6, 'Day7': 7}
STYLE = {
    'No': {'color': '#111111', 'marker': 'o'},
    '10uM': {'color': '#2c7fb8', 'marker': 's'},
    '20uM': {'color': '#41ab5d', 'marker': '^'},
    '50uM': {'color': '#f16913', 'marker': 'D'},
    '100uM': {'color': '#7a0177', 'marker': 'P'},
}
YLABELS = {
    'fusion': 'Fusion score (0-5)',
    'size': 'Size score (0-100)',
    'perimeter': 'Perimeter score (0-100)',
}
TITLES = {
    'fusion': 'Fusion',
    'size': 'Size',
    'perimeter': 'Perimeter',
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description='Plot App80 panel prompt metrics.')
    p.add_argument('--summary-csv', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/databases/app80_panel_metric_daily_summary.csv'))
    p.add_argument('--pvalues-csv', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/databases/app80_panel_metric_pvalues_vs_no.csv'))
    p.add_argument('--output-root', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics/figures'))
    return p.parse_args()


def setup_axes(ax: plt.Axes) -> None:
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(1.5)
    ax.spines['bottom'].set_linewidth(1.5)
    ax.tick_params(axis='both', width=1.5, length=6, labelsize=11)
    ax.set_facecolor('white')


def add_significance(ax: plt.Axes, metric_df: pd.DataFrame, pval_df: pd.DataFrame, metric: str) -> None:
    metric_p = pval_df[pval_df['metric'] == metric]
    ymax = metric_df['mean'].max() + metric_df['sem'].fillna(0).max()
    base_offset = 0.06 * ymax if ymax > 0 else 0.3
    for conc_idx, conc in enumerate(CONCENTRATION_ORDER):
        if conc == 'No':
            continue
        conc_rows = metric_p[(metric_p['concentration'] == conc) & (metric_p['stars_vs_no'].isin(['*', '**', '***', '****']))]
        for _, row in conc_rows.iterrows():
            day = row['day_label']
            src = metric_df[(metric_df['concentration'] == conc) & (metric_df['day_label'] == day)]
            if src.empty:
                continue
            x = DAY_X[day]
            y = float(src.iloc[0]['mean']) + float(src.iloc[0].get('sem', 0) or 0) + base_offset + 0.05 * conc_idx * base_offset
            ax.text(x, y, row['stars_vs_no'], ha='center', va='bottom', fontsize=10, color=STYLE[conc]['color'])


def plot_metric(ax: plt.Axes, summary: pd.DataFrame, pvalues: pd.DataFrame, metric: str) -> None:
    metric_df = summary[summary['metric'] == metric].copy()
    setup_axes(ax)
    for conc in CONCENTRATION_ORDER:
        sub = metric_df[metric_df['concentration'] == conc].sort_values('day_label')
        if sub.empty:
            continue
        x = [DAY_X[d] for d in sub['day_label']]
        y = sub['mean'].tolist()
        yerr = sub['sem'].fillna(0).tolist()
        style = STYLE[conc]
        ax.errorbar(
            x,
            y,
            yerr=yerr,
            color=style['color'],
            marker=style['marker'],
            markersize=6,
            linewidth=1.8,
            capsize=3,
            label=conc,
        )
    ax.set_title(TITLES[metric], fontsize=14, fontweight='bold')
    ax.set_xlabel('Time after imaging (days)', fontsize=12, fontweight='bold')
    ax.set_ylabel(YLABELS[metric], fontsize=12, fontweight='bold')
    ax.set_xticks([DAY_X[d] for d in DAY_ORDER])
    ax.set_xticklabels(DAY_ORDER)
    add_significance(ax, metric_df, pvalues, metric)


def save_all(fig: plt.Figure, base: Path) -> None:
    fig.savefig(base.with_suffix('.png'), dpi=300, bbox_inches='tight')
    fig.savefig(base.with_suffix('.pdf'), bbox_inches='tight')
    fig.savefig(base.with_suffix('.svg'), bbox_inches='tight')


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(args.summary_csv)
    pvalues = pd.read_csv(args.pvalues_csv)

    for metric in ('fusion', 'size', 'perimeter'):
        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        plot_metric(ax, summary, pvalues, metric)
        ax.legend(frameon=False, fontsize=10, loc='best')
        save_all(fig, output_root / f'app80_{metric}_panel_prompt_publication')
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(18, 4.8), constrained_layout=True)
    for ax, metric in zip(axes, ('fusion', 'size', 'perimeter')):
        plot_metric(ax, summary, pvalues, metric)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=5, frameon=False, loc='upper center', bbox_to_anchor=(0.5, 1.08), fontsize=10)
    save_all(fig, output_root / 'app80_panel_prompt_metrics_combined_publication')
    plt.close(fig)

    (output_root / 'figure_manifest.json').write_text(json.dumps({'output_root': str(output_root)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output_root': str(output_root)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
