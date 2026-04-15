#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from generate_guided_deo_figures import (
    DatasetConfig,
    FocusSpec,
    MetricSpec,
    ensure_dir,
    global_tests,
    infer_config as infer_base_config,
    load_df,
    maybe_sci,
    pairwise_vs_control,
    star_text,
    summarize_metric,
    write_df,
)


CONFIGS_0415: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        key='app81',
        group_field='condition',
        group_order=('low', 'middle', 'high'),
        group_labels={'low': 'Low density', 'middle': 'Middle density', 'high': 'High density'},
        group_colors={'low': '#222222', 'middle': '#2C6FB7', 'high': '#C73832'},
        group_markers={'low': 'o', 'middle': 's', 'high': 'D'},
        primary_metrics=(
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
        ),
        supportive_metrics=(),
        full_metrics=(),
        focused=(),
        enable_stats=True,
        show_plot_stats=False,
        infer_name_tokens=('app81_density_stitched_cellpose_v5_final_metrics_v1', 'app81'),
    ),
    DatasetConfig(
        key='app65',
        group_field='condition',
        group_order=('No', '0.02% Alginate', '0.05% Alginate'),
        group_labels={'No': 'Control', '0.02% Alginate': 'Low Alginate', '0.05% Alginate': 'High Alginate'},
        group_colors={'No': '#222222', '0.02% Alginate': '#2C6FB7', '0.05% Alginate': '#C73832'},
        group_markers={'No': 'o', '0.02% Alginate': 's', '0.05% Alginate': 'D'},
        primary_metrics=(
            MetricSpec('average_perimeter_px', 'Average perimeter (px)'),
            MetricSpec('wall_darkness_p90', 'Wall darkness P90'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
        ),
        supportive_metrics=(),
        full_metrics=(),
        focused=(
            FocusSpec(6, 'average_perimeter_px', 'Growth D6'),
            FocusSpec(6, 'peripheral_over_central', 'Fusion D6'),
            FocusSpec(11, 'wall_darkness_p90', 'Differentiation D11'),
        ),
        enable_stats=True,
        show_plot_stats=True,
        infer_name_tokens=('app65_alginate_v3_direct_brightfield', 'app65'),
    ),
    DatasetConfig(
        key='app80',
        group_field='concentration',
        group_order=('No', '10uM', '20uM', '50uM', '100uM'),
        group_labels={'No': 'Control', '10uM': '10 uM', '20uM': '20 uM', '50uM': '50 uM', '100uM': '100 uM'},
        group_colors={'No': '#222222', '10uM': '#2C6FB7', '20uM': '#3FA7A3', '50uM': '#D97706', '100uM': '#C73832'},
        group_markers={'No': 'o', '10uM': 's', '20uM': '^', '50uM': 'D', '100uM': 'P'},
        primary_metrics=(
            MetricSpec('average_area_px', 'Average area (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('center_weighted_edge_sum', 'Center-weighted edge sum'),
        ),
        supportive_metrics=(),
        full_metrics=(),
        focused=(
            FocusSpec(6, 'center_weighted_edge_sum', 'Fusion D6'),
        ),
        enable_stats=True,
        show_plot_stats=True,
        infer_name_tokens=('app80_all_concentrations_multiscale_large_recovery', 'app80'),
    ),
)


NO_ERRORBARS_DATASETS = {'app81'}



@dataclass(frozen=True)
class LegendPolicy:
    rect_right: float
    anchor_x: float
    anchor_y: float
    loc: str
    outside: bool


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Generate requested 0415 DEO figures.')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--suffix', default='0415')
    return p.parse_args()


def infer_config(root: Path) -> DatasetConfig:
    root_s = str(root)
    for cfg in CONFIGS_0415:
        if any(token in root_s for token in cfg.infer_name_tokens):
            return cfg
    return infer_base_config(root)


def legend_policy(cfg: DatasetConfig) -> LegendPolicy:
    if cfg.key == 'app80':
        return LegendPolicy(rect_right=0.79, anchor_x=0.81, anchor_y=0.98, loc='upper left', outside=True)
    return LegendPolicy(rect_right=0.84, anchor_x=0.86, anchor_y=0.98, loc='upper left', outside=True)


def x_mapping(df: pd.DataFrame) -> tuple[list[int], dict[int, int], list[str]]:
    days = sorted(int(v) for v in df['relative_day'].dropna().unique().tolist())
    xpos = {day: idx for idx, day in enumerate(days)}
    labels = [f'D{day}' for day in days]
    return days, xpos, labels


def apply_common_axis(ax: plt.Axes, tick_positions: list[int], tick_labels: list[str], polished: bool) -> None:
    ax.set_xticks(tick_positions)
    if len(tick_labels) > 12:
        ax.set_xticklabels(tick_labels, rotation=50, ha='right', fontsize=8)
    elif len(tick_labels) > 9:
        ax.set_xticklabels(tick_labels, rotation=35, ha='right', fontsize=8.5)
    else:
        ax.set_xticklabels(tick_labels, rotation=0, fontsize=9)
    ax.grid(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(0.8)
    ax.spines['bottom'].set_linewidth(0.8)
    ax.tick_params(axis='both', width=0.8, length=3)
    if polished:
        ax.set_facecolor('white')


def add_global_stars(ax: plt.Axes, summary: pd.DataFrame, tests: pd.DataFrame, metric: str, xpos: dict[int, int]) -> None:
    if tests.empty:
        return
    subtests = tests.loc[tests['metric'] == metric]
    if subtests.empty:
        return
    y0, y1 = ax.get_ylim()
    span = (y1 - y0) if y1 > y0 else 1.0
    pad = 0.06 * span
    for _, row in subtests.iterrows():
        stars = row['stars']
        if not stars:
            continue
        day = int(row['relative_day'])
        sub = summary.loc[summary['relative_day'] == day]
        if sub.empty:
            continue
        local_y = np.nanmax(sub['mean'].to_numpy(dtype=float) + np.nan_to_num(sub['sem'].to_numpy(dtype=float), nan=0.0))
        ax.text(xpos[day], local_y + pad, stars, ha='center', va='bottom', color='black', fontsize=11, fontweight='bold')


def draw_series(ax: plt.Axes, cfg: DatasetConfig, group: str, sub: pd.DataFrame, x: list[int], with_errorbars: bool) -> None:
    common = dict(
        color=cfg.group_colors[group],
        marker=cfg.group_markers[group],
        markersize=5.5,
        linewidth=1.9,
        label=cfg.group_labels[group],
    )
    if with_errorbars:
        ax.errorbar(
            x,
            sub['mean'],
            yerr=sub['sem'].fillna(0.0),
            elinewidth=1.0,
            capsize=3,
            **common,
        )
    else:
        ax.plot(x, sub['mean'], **common)


def place_legend(fig: plt.Figure, axes: list[plt.Axes], cfg: DatasetConfig) -> None:
    handles, labels = axes[0].get_legend_handles_labels()
    if not handles:
        return
    lp = legend_policy(cfg)
    fig.legend(handles, labels, loc=lp.loc, ncol=1, frameon=False, bbox_to_anchor=(lp.anchor_x, lp.anchor_y), borderaxespad=0.0)


def save_png_pdf(fig: plt.Figure, png: Path, pdf: Path) -> None:
    fig.savefig(png, dpi=240, bbox_inches='tight')
    fig.savefig(pdf, bbox_inches='tight')



def plot_primary_split(df: pd.DataFrame, cfg: DatasetConfig, out_dir: Path, tests: pd.DataFrame, polished: bool, suffix: str) -> pd.DataFrame:
    days, xpos, labels = x_mapping(df)
    tick_positions = [xpos[d] for d in days]
    with_errorbars = cfg.key not in NO_ERRORBARS_DATASETS
    summaries = []
    rows = []
    for spec in cfg.primary_metrics:
        fig, ax = plt.subplots(1, 1, figsize=(6.6, 4.8))
        summary = summarize_metric(df, cfg, spec.key)
        summary['metric'] = spec.key
        summaries.append(summary)
        for group in cfg.group_order:
            sub = summary.loc[summary[cfg.group_field] == group].sort_values('relative_day')
            if sub.empty:
                continue
            x = [xpos[int(d)] for d in sub['relative_day']]
            draw_series(ax, cfg, group, sub, x, with_errorbars=with_errorbars)
        if cfg.show_plot_stats:
            add_global_stars(ax, summary, tests, spec.key, xpos)
        if not polished:
            ax.set_title(spec.label, fontsize=11, pad=8)
        ax.set_ylabel(spec.label)
        apply_common_axis(ax, tick_positions, labels, polished=polished)
        maybe_sci(ax, spec.key)
        handles, labels_ = ax.get_legend_handles_labels()
        fig.legend(handles, labels_, loc='upper left', ncol=1, frameon=False, bbox_to_anchor=(0.81, 0.98), borderaxespad=0.0)
        fig.tight_layout(rect=(0, 0, 0.79, 0.95))
        tag = slug(spec.key)
        kind = 'polished_guided' if polished else 'guided'
        png = out_dir / f'{cfg.key}_{tag}_{kind}_{suffix}.png'
        pdf = out_dir / f'{cfg.key}_{tag}_{kind}_{suffix}.pdf'
        save_png_pdf(fig, png, pdf)
        plt.close(fig)
        rows.append({
            'metric': spec.key,
            'label': spec.label,
            'png': str(png),
            'pdf': str(pdf),
            'legend_location': 'outside_right_margin',
        })
    return pd.DataFrame(rows)


def plot_primary(df: pd.DataFrame, cfg: DatasetConfig, out_png: Path, out_pdf: Path, tests: pd.DataFrame, polished: bool) -> pd.DataFrame:
    metrics = tuple(cfg.primary_metrics)
    days, xpos, labels = x_mapping(df)
    tick_positions = [xpos[d] for d in days]
    width = 15.0 if len(days) > 12 else 13.0
    fig, axes = plt.subplots(1, len(metrics), figsize=(width, 4.8))
    axes = np.atleast_1d(axes).tolist()
    summaries: list[pd.DataFrame] = []
    with_errorbars = cfg.key not in NO_ERRORBARS_DATASETS
    for ax, spec in zip(axes, metrics):
        summary = summarize_metric(df, cfg, spec.key)
        summary['metric'] = spec.key
        summaries.append(summary)
        for group in cfg.group_order:
            sub = summary.loc[summary[cfg.group_field] == group].sort_values('relative_day')
            if sub.empty:
                continue
            x = [xpos[int(d)] for d in sub['relative_day']]
            draw_series(ax, cfg, group, sub, x, with_errorbars=with_errorbars)
        if cfg.show_plot_stats:
            add_global_stars(ax, summary, tests, spec.key, xpos)
        if not polished:
            ax.set_title(spec.label, fontsize=11, pad=8)
        ax.set_ylabel(spec.label)
        apply_common_axis(ax, tick_positions, labels, polished=polished)
        maybe_sci(ax, spec.key)
    place_legend(fig, axes, cfg)
    lp = legend_policy(cfg)
    fig.tight_layout(rect=(0, 0, lp.rect_right, 0.95))
    save_png_pdf(fig, out_png, out_pdf)
    plt.close(fig)
    return pd.concat(summaries, ignore_index=True)


def plot_single_focus(df: pd.DataFrame, cfg: DatasetConfig, spec: FocusSpec, out_png: Path, out_pdf: Path, polished: bool) -> pd.DataFrame:
    fig, ax = plt.subplots(1, 1, figsize=(5.6, 4.9))
    xpos = np.arange(1, len(cfg.group_order) + 1)
    groups = []
    maxima = []
    for group in cfg.group_order:
        vals = df.loc[(df[cfg.group_field] == group) & (df['relative_day'] == spec.day), spec.metric].dropna().to_numpy(dtype=float)
        groups.append(vals)
        maxima.extend(vals.tolist())
    bp = ax.boxplot(
        groups,
        positions=xpos,
        widths=0.58,
        patch_artist=True,
        showfliers=False,
        medianprops={'color': 'black', 'linewidth': 1.1},
        whiskerprops={'color': 'black', 'linewidth': 0.9},
        capprops={'color': 'black', 'linewidth': 0.9},
        boxprops={'linewidth': 0.9, 'edgecolor': 'black'},
    )
    for patch, group in zip(bp['boxes'], cfg.group_order):
        patch.set_facecolor(cfg.group_colors[group])
        patch.set_alpha(0.55)
    for idx, (group, vals) in enumerate(zip(cfg.group_order, groups), start=1):
        if len(vals) == 0:
            continue
        jitter = np.linspace(-0.08, 0.08, len(vals)) if len(vals) > 1 else np.array([0.0])
        ax.scatter(np.full(len(vals), idx) + jitter, vals, s=18, color=cfg.group_colors[group], alpha=0.82, zorder=3)
    stats_rows = pairwise_vs_control(df, cfg, spec.metric, spec.day)
    if cfg.show_plot_stats and stats_rows:
        ymax = max(maxima) if maxima else 1.0
        ymin = min(maxima) if maxima else 0.0
        span = (ymax - ymin) if ymax > ymin else 1.0
        level = ymax + 0.08 * span
        step = 0.10 * span
        for row, other_idx in zip(stats_rows, xpos[1:]):
            if row['stars']:
                ax.plot([xpos[0], xpos[0], other_idx, other_idx], [level, level + 0.03 * span, level + 0.03 * span, level], color='black', linewidth=1.0)
                ax.text((xpos[0] + other_idx) / 2.0, level + 0.03 * span, row['stars'], ha='center', va='bottom', color='black', fontsize=10, fontweight='bold')
                level += step
    if not polished:
        ax.set_title(spec.label, fontsize=11, pad=8)
    ylabel = next(m.label for m in cfg.primary_metrics if m.key == spec.metric)
    ax.set_ylabel(ylabel)
    ax.set_xticks(xpos)
    ax.set_xticklabels([cfg.group_labels[g] for g in cfg.group_order], rotation=20 if len(cfg.group_order) > 3 else 0, ha='right' if len(cfg.group_order) > 3 else 'center')
    ax.grid(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(0.8)
    ax.spines['bottom'].set_linewidth(0.8)
    maybe_sci(ax, spec.metric)
    fig.tight_layout()
    save_png_pdf(fig, out_png, out_pdf)
    plt.close(fig)
    out = pd.DataFrame(stats_rows)
    if not out.empty:
        out['focus_label'] = spec.label
    return out


def slug(text: str) -> str:
    return text.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '').replace('%', 'pct')


def generate(root: Path, suffix: str) -> dict[str, object]:
    cfg = infer_config(root)
    df = load_df(root, cfg)
    fig_root = ensure_dir(root / f'figures-guided-{suffix}')
    polished_root = ensure_dir(root / f'figures-polished-guided-{suffix}')
    stats_root = ensure_dir(fig_root / 'statistics_tables')

    primary_tests = global_tests(df, cfg, cfg.primary_metrics)
    primary_summary = plot_primary(
        df, cfg,
        ensure_dir(fig_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_guided_{suffix}.png',
        ensure_dir(fig_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_guided_{suffix}.pdf',
        primary_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=False,
    )
    polished_primary = plot_primary(
        df, cfg,
        ensure_dir(polished_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_polished_guided_{suffix}.png',
        ensure_dir(polished_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_polished_guided_{suffix}.pdf',
        primary_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=True,
    )

    split_summary = plot_primary_split(
        df, cfg,
        ensure_dir(fig_root / 'split_primary_individual'),
        primary_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=False,
        suffix=suffix,
    )
    polished_split_summary = plot_primary_split(
        df, cfg,
        ensure_dir(polished_root / 'split_primary_individual'),
        primary_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=True,
        suffix=suffix,
    )

    focus_rows = []
    polished_focus_rows = []
    if cfg.focused:
        focus_dir = ensure_dir(fig_root / 'focused_day_individual')
        polished_focus_dir = ensure_dir(polished_root / 'focused_day_individual')
        for spec in cfg.focused:
            tag = f'd{spec.day}_{slug(spec.metric)}'
            focus_rows.append(
                plot_single_focus(
                    df, cfg, spec,
                    focus_dir / f'{cfg.key}_{tag}_guided_{suffix}.png',
                    focus_dir / f'{cfg.key}_{tag}_guided_{suffix}.pdf',
                    polished=False,
                )
            )
            polished_focus_rows.append(
                plot_single_focus(
                    df, cfg, spec,
                    polished_focus_dir / f'{cfg.key}_{tag}_polished_guided_{suffix}.png',
                    polished_focus_dir / f'{cfg.key}_{tag}_polished_guided_{suffix}.pdf',
                    polished=True,
                )
            )

    focus_df = pd.concat([r for r in focus_rows if not r.empty], ignore_index=True) if focus_rows else pd.DataFrame()
    polished_focus_df = pd.concat([r for r in polished_focus_rows if not r.empty], ignore_index=True) if polished_focus_rows else pd.DataFrame()

    write_df(primary_summary, stats_root / f'primary_metric_summary_{suffix}.csv')
    write_df(primary_tests, stats_root / f'primary_same_day_global_tests_{suffix}.csv')
    write_df(split_summary, stats_root / f'primary_split_outputs_{suffix}.csv')
    write_df(polished_split_summary, stats_root / f'primary_split_outputs_polished_{suffix}.csv')
    write_df(focus_df, stats_root / f'focused_pairwise_vs_control_{suffix}.csv')
    write_df(polished_focus_df, stats_root / f'focused_pairwise_vs_control_polished_{suffix}.csv')

    manifest = {
        'dataset': cfg.key,
        'root': str(root),
        'suffix': suffix,
        'primary_metrics': [m.key for m in cfg.primary_metrics],
        'focused_days': [{'day': f.day, 'metric': f.metric, 'label': f.label} for f in cfg.focused],
        'style': {
            'legend_location': 'outside_right_margin',
            'legend_reason': '0415 screenshot review showed top-right in-figure placement collides with rightmost panel titles and significance stars.',
            'app81_error_bars_removed': cfg.key == 'app81',
            'x_tick_labels': 'D{relative_day}',
            'equal_day_spacing': True,
            'grid': False,
            'split_panel_note': False,
        },
        'outputs': {
            'figures_guided': str(fig_root),
            'figures_polished_guided': str(polished_root),
            'split_primary_guided': str(fig_root / 'split_primary_individual'),
            'split_primary_polished_guided': str(polished_root / 'split_primary_individual'),
            'statistics_tables': str(stats_root),
        },
    }
    (fig_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (polished_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    args = parse_args()
    manifest = generate(args.root.resolve(), args.suffix)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
