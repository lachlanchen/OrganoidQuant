#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import f_oneway, ttest_ind


@dataclass(frozen=True)
class DatasetConfig:
    dataset_key: str
    input_csv: str
    output_root: str
    condition_col: str
    condition_order: Sequence[str]
    baseline: str
    selected_metrics: Sequence[str]
    focused_days: Sequence[int]
    title: str


DATASETS: Dict[str, DatasetConfig] = {
    'app80': DatasetConfig(
        dataset_key='app80',
        input_csv='analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv',
        output_root='analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/statistical_primary_metrics',
        condition_col='concentration',
        condition_order=['No', '10uM', '20uM', '50uM', '100uM'],
        baseline='No',
        selected_metrics=[
            'average_perimeter_px',
            'total_area_px',
            'normalized_edge_over_count_curvature',
            'center_weighted_edge_sum',
            'organoid_darkness_p90',
            'roundness_deviation_norm',
        ],
        focused_days=[6],
        title='App80 Y-27632',
    ),
    'app65': DatasetConfig(
        dataset_key='app65',
        input_csv='analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv',
        output_root='analysis-output/app65_alginate_multiscale_large_recovery/figures/statistical_primary_metrics',
        condition_col='condition',
        condition_order=['No', '0.02% Alginate', '0.05% Alginate'],
        baseline='No',
        selected_metrics=[
            'average_perimeter_px',
            'total_area_px',
            'normalized_edge_over_count_curvature',
            'peripheral_over_central',
            'organoid_darkness_p90',
            'core_darkness_mean',
            'roundness_deviation_norm',
        ],
        focused_days=[7, 13],
        title='App65 Alginate',
    ),
    'app81': DatasetConfig(
        dataset_key='app81',
        input_csv='analysis-output/app81_main_density_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv',
        output_root='analysis-output/app81_main_density_multiscale_large_recovery/figures/statistical_primary_metrics',
        condition_col='condition',
        condition_order=['low', 'middle', 'high'],
        baseline='low',
        selected_metrics=[
            'average_perimeter_px',
            'total_area_px',
            'normalized_edge_over_count_curvature',
            'roundness',
            'curvature',
            'roundness_deviation_norm',
        ],
        focused_days=[],
        title='App81 Density A',
    ),
    'densityB': DatasetConfig(
        dataset_key='densityB',
        input_csv='analysis-output/test2025_density_B_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv',
        output_root='analysis-output/test2025_density_B_multiscale_large_recovery/figures/statistical_primary_metrics',
        condition_col='condition',
        condition_order=['low', 'middle', 'high'],
        baseline='low',
        selected_metrics=[
            'average_perimeter_px',
            'total_area_px',
            'normalized_edge_over_count_curvature',
            'roundness',
            'curvature',
            'roundness_deviation_norm',
        ],
        focused_days=[],
        title='Density B Pre-Experiment',
    ),
}

STYLE = {
    'No': {'color': '#111111', 'marker': 'o'},
    '10uM': {'color': '#2c7fb8', 'marker': 's'},
    '20uM': {'color': '#41ab5d', 'marker': '^'},
    '50uM': {'color': '#f16913', 'marker': 'D'},
    '100uM': {'color': '#7a0177', 'marker': 'P'},
    '0.02% Alginate': {'color': '#2b8cbe', 'marker': 's'},
    '0.05% Alginate': {'color': '#e34a33', 'marker': 'D'},
    'low': {'color': '#1b9e77', 'marker': 'o'},
    'middle': {'color': '#d95f02', 'marker': 's'},
    'high': {'color': '#7570b3', 'marker': '^'},
}

METRIC_LABELS = {
    'average_perimeter_px': 'Perimeter (px)',
    'total_area_px': 'Area (px)',
    'normalized_edge_over_count_curvature': 'Normalized edge / (count * curvature)',
    'center_weighted_edge_sum': 'Center-weighted edge sum',
    'organoid_darkness_p90': 'Darkness P90',
    'roundness_deviation_norm': 'Roundness deviation (norm)',
    'peripheral_over_central': 'Peripheral / central internal edge',
    'core_darkness_mean': 'Core darkness mean',
    'roundness': 'Roundness',
    'curvature': 'Curvature',
}

METRIC_GROUP = {
    'average_perimeter_px': 'Growth',
    'total_area_px': 'Growth',
    'normalized_edge_over_count_curvature': 'Fusion',
    'center_weighted_edge_sum': 'Fusion',
    'peripheral_over_central': 'Fusion',
    'organoid_darkness_p90': 'Differentiation',
    'core_darkness_mean': 'Differentiation',
    'roundness_deviation_norm': 'Differentiation',
    'roundness': 'Differentiation',
    'curvature': 'Differentiation',
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Plot selected DEO metric statistics without rerunning segmentation.')
    p.add_argument('--dataset', action='append', choices=sorted(DATASETS), help='Dataset key to render. Repeatable. Defaults to all.')
    return p.parse_args()


def stars(p: float | None) -> str:
    if p is None or pd.isna(p):
        return ''
    if p < 1e-4:
        return '****'
    if p < 1e-3:
        return '***'
    if p < 1e-2:
        return '**'
    if p < 5e-2:
        return '*'
    return ''


def ensure_dirs(root: Path) -> Dict[str, Path]:
    dirs = {
        'root': root,
        'timecourse': root / 'longitudinal_errorbar_stats',
        'tables': root / 'same_day_statistics_tables',
        'focused': root / 'focused_day_comparisons',
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def summarize(df: pd.DataFrame, condition_col: str, metrics: Sequence[str]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for metric in metrics:
        if metric not in df.columns:
            continue
        for (cond, day, date_label), sub in df.groupby([condition_col, 'relative_day', 'date_label'], observed=True):
            vals = sub[metric].dropna()
            n = int(len(vals))
            mean = float(vals.mean()) if n else math.nan
            std = float(vals.std(ddof=1)) if n > 1 else math.nan
            sem = float(std / math.sqrt(n)) if n > 1 else math.nan
            rows.append({
                condition_col: cond,
                'relative_day': int(day),
                'date_label': date_label,
                'metric': metric,
                'n': n,
                'mean': mean,
                'std': std,
                'sem': sem,
            })
    return pd.DataFrame(rows)


def global_tests(df: pd.DataFrame, condition_col: str, metrics: Sequence[str], cond_order: Sequence[str]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for metric in metrics:
        if metric not in df.columns:
            continue
        for day, subday in df.groupby('relative_day', observed=True):
            groups = []
            info = []
            for cond in cond_order:
                vals = subday.loc[subday[condition_col] == cond, metric].dropna()
                if len(vals) > 0:
                    groups.append(vals.values)
                    info.append((cond, len(vals)))
            method = ''
            p = math.nan
            if len(groups) >= 3 and all(len(g) >= 2 for g in groups):
                method = 'anova'
                p = float(f_oneway(*groups).pvalue)
            elif len(groups) == 2 and all(len(g) >= 2 for g in groups):
                method = 'welch_ttest'
                p = float(ttest_ind(groups[0], groups[1], equal_var=False, nan_policy='omit').pvalue)
            rows.append({
                'metric': metric,
                'relative_day': int(day),
                'date_label': subday['date_label'].iloc[0],
                'method': method,
                'p_value': p,
                'stars': stars(p),
                'groups_tested': len(groups),
                'group_ns': json.dumps({c: n for c, n in info}, ensure_ascii=False),
            })
    return pd.DataFrame(rows)


def pairwise_tests(df: pd.DataFrame, condition_col: str, metrics: Sequence[str], cond_order: Sequence[str], baseline: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    vs_rows: List[Dict[str, object]] = []
    all_rows: List[Dict[str, object]] = []
    for metric in metrics:
        if metric not in df.columns:
            continue
        for day, subday in df.groupby('relative_day', observed=True):
            date_label = subday['date_label'].iloc[0]
            for i, cond_a in enumerate(cond_order):
                vals_a = subday.loc[subday[condition_col] == cond_a, metric].dropna()
                for cond_b in cond_order[i + 1:]:
                    vals_b = subday.loc[subday[condition_col] == cond_b, metric].dropna()
                    p = math.nan
                    if len(vals_a) >= 2 and len(vals_b) >= 2:
                        p = float(ttest_ind(vals_a, vals_b, equal_var=False, nan_policy='omit').pvalue)
                    row = {
                        'metric': metric,
                        'relative_day': int(day),
                        'date_label': date_label,
                        'group_a': cond_a,
                        'group_b': cond_b,
                        'p_value': p,
                        'stars': stars(p),
                        'n_a': int(len(vals_a)),
                        'n_b': int(len(vals_b)),
                    }
                    all_rows.append(row)
                    if cond_a == baseline or cond_b == baseline:
                        baseline_group = cond_a if cond_a == baseline else cond_b
                        other = cond_b if cond_a == baseline else cond_a
                        other_vals = vals_b if cond_a == baseline else vals_a
                        vs_rows.append({
                            'metric': metric,
                            'relative_day': int(day),
                            'date_label': date_label,
                            'baseline': baseline_group,
                            'comparison_group': other,
                            'p_value': p,
                            'stars': stars(p),
                            'n_baseline': int(len(vals_a if cond_a == baseline else vals_b)),
                            'n_group': int(len(other_vals)),
                        })
    return pd.DataFrame(vs_rows), pd.DataFrame(all_rows)


def setup_axis(ax: plt.Axes) -> None:
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(1.2)
    ax.spines['bottom'].set_linewidth(1.2)
    ax.tick_params(axis='both', width=1.2, length=5, labelsize=9)
    ax.grid(axis='y', color='#e6e6e6', linewidth=0.8)
    ax.set_facecolor('white')


def day_ticks(summary: pd.DataFrame) -> tuple[List[int], List[str]]:
    day_map = summary[['relative_day', 'date_label']].drop_duplicates().sort_values('relative_day')
    ticks = day_map['relative_day'].astype(int).tolist()
    labels = [f'D{d}' for d in ticks]
    return ticks, labels


def add_timecourse_stars(ax: plt.Axes, metric: str, summary: pd.DataFrame, pvals: pd.DataFrame, condition_col: str, cond_order: Sequence[str], baseline: str) -> None:
    metric_df = summary[summary['metric'] == metric]
    if metric_df.empty:
        return
    ymax = float(np.nanmax(metric_df['mean'].values)) if metric_df['mean'].notna().any() else 0.0
    ymin = float(np.nanmin(metric_df['mean'].values)) if metric_df['mean'].notna().any() else 0.0
    yrange = max(ymax - ymin, abs(ymax), 1.0)
    base_offset = 0.05 * yrange
    metric_p = pvals[(pvals['metric'] == metric) & (pvals['stars'] != '')]
    for idx, cond in enumerate(cond_order):
        if cond == baseline:
            continue
        subp = metric_p[metric_p['comparison_group'] == cond]
        for _, row in subp.iterrows():
            src = metric_df[(metric_df[condition_col] == cond) & (metric_df['relative_day'] == row['relative_day'])]
            if src.empty:
                continue
            y = float(src.iloc[0]['mean']) + (0 if pd.isna(src.iloc[0]['sem']) else float(src.iloc[0]['sem']))
            y += base_offset * (1 + 0.5 * idx)
            ax.text(int(row['relative_day']), y, row['stars'], ha='center', va='bottom', fontsize=9, color=STYLE[cond]['color'])


def plot_timecourse(config: DatasetConfig, summary: pd.DataFrame, pvals_vs_base: pd.DataFrame, dirs: Dict[str, Path]) -> None:
    metrics = [m for m in config.selected_metrics if m in summary['metric'].unique()]
    n = len(metrics)
    ncols = 2
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 3.9 * nrows), squeeze=False)
    ticks, labels = day_ticks(summary)
    for ax, metric in zip(axes.flat, metrics):
        setup_axis(ax)
        metric_df = summary[summary['metric'] == metric].copy()
        for cond in config.condition_order:
            sub = metric_df[metric_df[config.condition_col] == cond].sort_values('relative_day')
            if sub.empty:
                continue
            style = STYLE[cond]
            ax.errorbar(
                sub['relative_day'],
                sub['mean'],
                yerr=sub['sem'].fillna(0),
                color=style['color'],
                marker=style['marker'],
                markersize=5,
                linewidth=1.8,
                capsize=3,
                label=cond,
            )
        add_timecourse_stars(ax, metric, summary, pvals_vs_base, config.condition_col, config.condition_order, config.baseline)
        ax.set_title(f"{METRIC_GROUP.get(metric, 'Metric')}: {METRIC_LABELS.get(metric, metric)}", fontsize=11, fontweight='bold')
        ax.set_xlabel('Relative day', fontsize=10, fontweight='bold')
        ax.set_ylabel(METRIC_LABELS.get(metric, metric), fontsize=10, fontweight='bold')
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels)
    for ax in axes.flat[n:]:
        ax.axis('off')
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=min(len(labels), 5), frameon=False, loc='upper center', bbox_to_anchor=(0.5, 1.01), fontsize=10)
    fig.suptitle(f'{config.title}: selected primary metrics with mean±SEM and same-day stars', fontsize=14, fontweight='bold', y=1.04)
    fig.tight_layout()
    base = dirs['timecourse'] / f'{config.dataset_key}_selected_primary_metrics_timecourse_stats'
    fig.savefig(base.with_suffix('.png'), dpi=300, bbox_inches='tight')
    fig.savefig(base.with_suffix('.pdf'), bbox_inches='tight')
    plt.close(fig)


def draw_bracket(ax: plt.Axes, x1: float, x2: float, y: float, h: float, text: str, color: str) -> None:
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], color=color, linewidth=1.2)
    ax.text((x1 + x2) / 2, y + h, text, ha='center', va='bottom', fontsize=9, color=color)


def focused_day_labels(df: pd.DataFrame) -> Dict[int, str]:
    return {int(day): label for day, label in df[['relative_day', 'date_label']].drop_duplicates().values.tolist()}


def plot_focused_days(config: DatasetConfig, df: pd.DataFrame, summary: pd.DataFrame, pvals_vs_base: pd.DataFrame, global_p: pd.DataFrame, dirs: Dict[str, Path]) -> None:
    if not config.focused_days:
        return
    metrics = [m for m in config.selected_metrics if m in df.columns]
    if not metrics:
        return
    day_label_map = focused_day_labels(df)
    nrows = len(config.focused_days)
    ncols = len(metrics)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.6 * ncols, 4.2 * nrows), squeeze=False)
    for row_idx, day in enumerate(config.focused_days):
        subday = df[df['relative_day'] == day].copy()
        for col_idx, metric in enumerate(metrics):
            ax = axes[row_idx][col_idx]
            setup_axis(ax)
            values_by_cond = []
            positions = []
            for cond_idx, cond in enumerate(config.condition_order):
                vals = subday.loc[subday[config.condition_col] == cond, metric].dropna().values
                if len(vals) == 0:
                    continue
                pos = cond_idx + 1
                positions.append(pos)
                values_by_cond.append(vals)
                ax.boxplot(vals, positions=[pos], widths=0.55, patch_artist=True,
                           boxprops=dict(facecolor='white', edgecolor=STYLE[cond]['color'], linewidth=1.2),
                           medianprops=dict(color=STYLE[cond]['color'], linewidth=1.2),
                           whiskerprops=dict(color=STYLE[cond]['color'], linewidth=1.0),
                           capprops=dict(color=STYLE[cond]['color'], linewidth=1.0),
                           showfliers=False)
                jitter = np.linspace(-0.08, 0.08, num=len(vals)) if len(vals) > 1 else np.array([0.0])
                ax.scatter(np.full(len(vals), pos) + jitter, vals, s=18, color=STYLE[cond]['color'], alpha=0.75, zorder=3)
                mean = float(np.mean(vals))
                sem = float(np.std(vals, ddof=1) / math.sqrt(len(vals))) if len(vals) > 1 else 0.0
                ax.errorbar([pos], [mean], yerr=[sem], color=STYLE[cond]['color'], marker='_', markersize=18, linewidth=1.5, capsize=3, zorder=4)
            ax.set_xticks(range(1, len(config.condition_order) + 1))
            ax.set_xticklabels(config.condition_order, rotation=25, ha='right')
            ax.set_title(METRIC_LABELS.get(metric, metric), fontsize=10, fontweight='bold')
            if col_idx == 0:
                dlabel = day_label_map.get(day, f'D{day}')
                ax.set_ylabel(f'D{day} ({dlabel})\n{METRIC_GROUP.get(metric, "Metric")}', fontsize=10, fontweight='bold')
            else:
                ax.set_ylabel('')
            g = global_p[(global_p['metric'] == metric) & (global_p['relative_day'] == day)]
            if not g.empty and isinstance(g.iloc[0]['method'], str) and g.iloc[0]['method']:
                p = g.iloc[0]['p_value']
                if pd.notna(p):
                    ax.text(0.02, 0.98, f"{g.iloc[0]['method']}: p={p:.3g}", transform=ax.transAxes, ha='left', va='top', fontsize=8)
            pv = pvals_vs_base[(pvals_vs_base['metric'] == metric) & (pvals_vs_base['relative_day'] == day) & (pvals_vs_base['stars'] != '')]
            if not pv.empty:
                ymax = np.nanmax([np.nanmax(v) for v in values_by_cond]) if values_by_cond else 1.0
                ymin = np.nanmin([np.nanmin(v) for v in values_by_cond]) if values_by_cond else 0.0
                yrange = max(ymax - ymin, abs(ymax), 1.0)
                level = ymax + 0.08 * yrange
                for idx, (_, prow) in enumerate(pv.iterrows()):
                    try:
                        x1 = config.condition_order.index(config.baseline) + 1
                        x2 = config.condition_order.index(prow['comparison_group']) + 1
                    except ValueError:
                        continue
                    draw_bracket(ax, x1, x2, level + idx * 0.10 * yrange, 0.03 * yrange, prow['stars'], STYLE[prow['comparison_group']]['color'])
        
    fig.suptitle(f'{config.title}: focused same-day comparisons', fontsize=14, fontweight='bold', y=1.01)
    fig.tight_layout()
    base = dirs['focused'] / f'{config.dataset_key}_focused_day_selected_metric_comparisons'
    fig.savefig(base.with_suffix('.png'), dpi=300, bbox_inches='tight')
    fig.savefig(base.with_suffix('.pdf'), bbox_inches='tight')
    plt.close(fig)


def write_tables(config: DatasetConfig, summary: pd.DataFrame, global_p: pd.DataFrame, pvals_vs_base: pd.DataFrame, pvals_all: pd.DataFrame, dirs: Dict[str, Path]) -> None:
    summary.to_csv(dirs['tables'] / 'selected_metric_summary.csv', index=False)
    global_p.to_csv(dirs['tables'] / 'same_day_global_tests.csv', index=False)
    pvals_vs_base.to_csv(dirs['tables'] / 'same_day_pairwise_vs_baseline.csv', index=False)
    pvals_all.to_csv(dirs['tables'] / 'same_day_pairwise_all_pairs.csv', index=False)
    if config.focused_days:
        focused_summary = summary[summary['relative_day'].isin(config.focused_days)].copy()
        focused_global = global_p[global_p['relative_day'].isin(config.focused_days)].copy()
        focused_base = pvals_vs_base[pvals_vs_base['relative_day'].isin(config.focused_days)].copy()
        focused_all = pvals_all[pvals_all['relative_day'].isin(config.focused_days)].copy()
        focused_summary.to_csv(dirs['focused'] / 'focused_day_selected_metric_summary.csv', index=False)
        focused_global.to_csv(dirs['focused'] / 'focused_day_global_tests.csv', index=False)
        focused_base.to_csv(dirs['focused'] / 'focused_day_pairwise_vs_baseline.csv', index=False)
        focused_all.to_csv(dirs['focused'] / 'focused_day_pairwise_all_pairs.csv', index=False)
    manifest = {
        'dataset': config.dataset_key,
        'title': config.title,
        'baseline': config.baseline,
        'condition_order': list(config.condition_order),
        'selected_metrics': list(config.selected_metrics),
        'focused_days': list(config.focused_days),
        'input_csv': str(Path(config.input_csv).resolve()),
        'output_root': str(dirs['root'].resolve()),
        'statistical_methods': {
            'same_day_global': 'one-way ANOVA when >=3 groups with n>=2 each; Welch t-test when exactly 2 groups with n>=2 each',
            'pairwise': 'Welch two-sample t-test',
            'plot_stars': 'pairwise vs baseline same-day p-values',
        },
    }
    (dirs['root'] / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def run_dataset(config: DatasetConfig) -> None:
    df = pd.read_csv(config.input_csv)
    present_metrics = [m for m in config.selected_metrics if m in df.columns]
    keep_cols = [config.condition_col, 'relative_day', 'date_label'] + present_metrics
    df = df[keep_cols].copy()
    df = df[df[config.condition_col].isin(config.condition_order)].copy()
    summary = summarize(df, config.condition_col, present_metrics)
    global_p = global_tests(df, config.condition_col, present_metrics, config.condition_order)
    pvals_vs_base, pvals_all = pairwise_tests(df, config.condition_col, present_metrics, config.condition_order, config.baseline)
    dirs = ensure_dirs(Path(config.output_root))
    write_tables(config, summary, global_p, pvals_vs_base, pvals_all, dirs)
    plot_timecourse(config, summary, pvals_vs_base, dirs)
    plot_focused_days(config, df, summary, pvals_vs_base, global_p, dirs)
    print(json.dumps({
        'dataset': config.dataset_key,
        'output_root': str(dirs['root'].resolve()),
        'metrics': present_metrics,
        'rows': int(len(df)),
    }, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    targets = args.dataset or list(DATASETS.keys())
    for key in targets:
        run_dataset(DATASETS[key])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
