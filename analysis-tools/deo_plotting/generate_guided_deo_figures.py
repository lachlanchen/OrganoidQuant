#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from itertools import combinations

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import f_oneway, ttest_ind


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str


@dataclass(frozen=True)
class FocusSpec:
    day: int
    metric: str
    label: str


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    group_field: str
    group_order: tuple[str, ...]
    group_labels: dict[str, str]
    group_colors: dict[str, str]
    group_markers: dict[str, str]
    primary_metrics: tuple[MetricSpec, ...]
    supportive_metrics: tuple[MetricSpec, ...]
    full_metrics: tuple[MetricSpec, ...]
    focused: tuple[FocusSpec, ...]
    enable_stats: bool
    show_plot_stats: bool
    infer_name_tokens: tuple[str, ...]


CONFIGS: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        key='app81',
        group_field='condition',
        group_order=('low', 'middle', 'high'),
        group_labels={'low': 'Low density', 'middle': 'Middle density', 'high': 'High density'},
        group_colors={'low': '#2C6FB7', 'middle': '#222222', 'high': '#C73832'},
        group_markers={'low': 'o', 'middle': 's', 'high': 'D'},
        primary_metrics=(
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
        ),
        supportive_metrics=(
            MetricSpec('average_area_px', 'Average area (px)'),
            MetricSpec('average_perimeter_px', 'Average perimeter (px)'),
            MetricSpec('roundness_deviation_norm', 'Roundness deviation (norm)'),
            MetricSpec('normalized_edge_over_count_curvature', 'Normalized edge / (count * curvature)'),
            MetricSpec('roundness', 'Roundness'),
        ),
        full_metrics=(
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('average_area_px', 'Average area (px)'),
            MetricSpec('average_perimeter_px', 'Average perimeter (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
            MetricSpec('roundness_deviation_norm', 'Roundness deviation (norm)'),
            MetricSpec('roundness', 'Roundness'),
            MetricSpec('normalized_edge_over_count_curvature', 'Normalized edge / (count * curvature)'),
        ),
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
        supportive_metrics=(
            MetricSpec('average_area_px', 'Average area (px)'),
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('wall_darkness_mean', 'Wall darkness mean'),
            MetricSpec('core_darkness_mean', 'Core darkness mean'),
            MetricSpec('normalized_edge_over_count_curvature', 'Normalized edge / (count * curvature)'),
        ),
        full_metrics=(
            MetricSpec('average_perimeter_px', 'Average perimeter (px)'),
            MetricSpec('average_area_px', 'Average area (px)'),
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('wall_darkness_p90', 'Wall darkness P90'),
            MetricSpec('wall_darkness_mean', 'Wall darkness mean'),
            MetricSpec('core_darkness_mean', 'Core darkness mean'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
            MetricSpec('normalized_edge_over_count_curvature', 'Normalized edge / (count * curvature)'),
        ),
        focused=(
            FocusSpec(6, 'average_perimeter_px', 'Growth D6'),
            FocusSpec(7, 'average_area_px', 'Growth D7'),
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
        supportive_metrics=(
            MetricSpec('average_perimeter_px', 'Average perimeter (px)'),
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
            MetricSpec('normalized_edge_over_count_curvature', 'Normalized edge / (count * curvature)'),
            MetricSpec('area_normalized_center_weighted_edge_instance_mean', 'Area-normalized center-weighted edge'),
        ),
        full_metrics=(
            MetricSpec('average_perimeter_px', 'Average perimeter (px)'),
            MetricSpec('average_area_px', 'Average area (px)'),
            MetricSpec('total_area_px', 'Total area (px)'),
            MetricSpec('organoid_darkness_p90', 'Darkness P90'),
            MetricSpec('peripheral_over_central', 'Peripheral / Central'),
            MetricSpec('center_weighted_edge_sum', 'Center-weighted edge sum'),
            MetricSpec('normalized_edge_over_count_curvature', 'Normalized edge / (count * curvature)'),
            MetricSpec('area_normalized_center_weighted_edge_instance_mean', 'Area-normalized center-weighted edge'),
        ),
        focused=(
            FocusSpec(5, 'average_area_px', 'Growth D5'),
            FocusSpec(5, 'organoid_darkness_p90', 'Differentiation D5'),
            FocusSpec(6, 'center_weighted_edge_sum', 'Fusion D6'),
            FocusSpec(7, 'organoid_darkness_p90', 'Differentiation D7'),
        ),
        enable_stats=True,
        show_plot_stats=True,
        infer_name_tokens=('app80_all_concentrations_multiscale_large_recovery', 'app80'),
    ),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Generate guidance-driven standard and polished DEO figures.')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--suffix', default='v2')
    return p.parse_args()


def infer_config(root: Path) -> DatasetConfig:
    root_s = str(root)
    for cfg in CONFIGS:
        if any(token in root_s for token in cfg.infer_name_tokens):
            return cfg
    raise SystemExit(f'Could not infer dataset config from root: {root}')


def star_text(p_value: float | None) -> str:
    if p_value is None or pd.isna(p_value):
        return ''
    if p_value < 1e-4:
        return '****'
    if p_value < 1e-3:
        return '***'
    if p_value < 1e-2:
        return '**'
    if p_value < 5e-2:
        return '*'
    return ''


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_df(root: Path, cfg: DatasetConfig) -> pd.DataFrame:
    per_image = root / 'profiling' / 'quantification' / 'per_image_metrics.csv'
    df = pd.read_csv(per_image)
    df = df.loc[df[cfg.group_field].isin(cfg.group_order)].copy()
    df['relative_day'] = df['relative_day'].astype(int)
    return df


def summarize_metric(df: pd.DataFrame, cfg: DatasetConfig, metric: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (group, day), sub in df.groupby([cfg.group_field, 'relative_day'], observed=True):
        vals = sub[metric].dropna().to_numpy(dtype=float)
        n = int(vals.size)
        mean = float(vals.mean()) if n else math.nan
        std = float(vals.std(ddof=1)) if n > 1 else math.nan
        sem = float(std / math.sqrt(n)) if n > 1 else math.nan
        rows.append({
            cfg.group_field: group,
            'relative_day': int(day),
            'n': n,
            'mean': mean,
            'std': std,
            'sem': sem,
        })
    return pd.DataFrame(rows)


def global_tests(df: pd.DataFrame, cfg: DatasetConfig, metrics: Iterable[MetricSpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not cfg.enable_stats:
        return pd.DataFrame(columns=['metric', 'relative_day', 'method', 'p_value', 'stars', 'group_ns'])
    for spec in metrics:
        metric = spec.key
        for day, subday in df.groupby('relative_day', observed=True):
            groups = []
            ns: dict[str, int] = {}
            for group in cfg.group_order:
                vals = subday.loc[subday[cfg.group_field] == group, metric].dropna().to_numpy(dtype=float)
                groups.append(vals)
                ns[group] = int(vals.size)
            p_value = math.nan
            method = ''
            if int(day) > 1 and all(len(g) >= 2 for g in groups):
                method = 'anova'
                p_value = float(f_oneway(*groups).pvalue)
            rows.append({
                'metric': metric,
                'relative_day': int(day),
                'method': method,
                'p_value': p_value,
                'stars': star_text(p_value),
                'group_ns': json.dumps(ns, ensure_ascii=False),
            })
    return pd.DataFrame(rows)


def pairwise_vs_control(df: pd.DataFrame, cfg: DatasetConfig, metric: str, day: int) -> list[dict[str, object]]:
    if not cfg.enable_stats:
        return []
    control_group = cfg.group_order[0]
    control = df.loc[(df[cfg.group_field] == control_group) & (df['relative_day'] == day), metric].dropna().to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for group in cfg.group_order[1:]:
        vals = df.loc[(df[cfg.group_field] == group) & (df['relative_day'] == day), metric].dropna().to_numpy(dtype=float)
        p_value = math.nan
        if day > 1 and len(control) >= 2 and len(vals) >= 2:
            p_value = float(ttest_ind(control, vals, equal_var=False, nan_policy='omit').pvalue)
        rows.append({
            'metric': metric,
            'relative_day': int(day),
            'group_a': control_group,
            'group_b': group,
            'p_value': p_value,
            'stars': star_text(p_value),
            'n_control': int(len(control)),
            'n_other': int(len(vals)),
        })
    return rows


def pairwise_all_groups(df: pd.DataFrame, cfg: DatasetConfig, metric: str, day: int) -> list[dict[str, object]]:
    if not cfg.enable_stats:
        return []
    rows: list[dict[str, object]] = []
    for group_a, group_b in combinations(cfg.group_order, 2):
        vals_a = df.loc[(df[cfg.group_field] == group_a) & (df['relative_day'] == day), metric].dropna().to_numpy(dtype=float)
        vals_b = df.loc[(df[cfg.group_field] == group_b) & (df['relative_day'] == day), metric].dropna().to_numpy(dtype=float)
        p_value = math.nan
        if day > 1 and len(vals_a) >= 2 and len(vals_b) >= 2:
            p_value = float(ttest_ind(vals_a, vals_b, equal_var=False, nan_policy='omit').pvalue)
        rows.append({
            'metric': metric,
            'relative_day': int(day),
            'group_a': group_a,
            'group_b': group_b,
            'p_value': p_value,
            'stars': star_text(p_value),
            'n_group_a': int(len(vals_a)),
            'n_group_b': int(len(vals_b)),
        })
    return rows


def x_mapping(df: pd.DataFrame) -> tuple[list[int], dict[int, int], list[str]]:
    days = sorted(int(v) for v in df['relative_day'].dropna().unique().tolist())
    xpos = {day: idx for idx, day in enumerate(days)}
    labels = [f'D{day}' for day in days]
    return days, xpos, labels


def apply_common_axis(ax: plt.Axes, tick_positions: list[int], tick_labels: list[str], polished: bool) -> None:
    ax.set_xticks(tick_positions)
    if len(tick_labels) > 10:
        ax.set_xticklabels(tick_labels, rotation=35, ha='right', fontsize=8)
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


def maybe_sci(ax: plt.Axes, metric: str) -> None:
    if any(token in metric for token in ('area', 'perimeter', 'sum')):
        ax.ticklabel_format(style='scientific', axis='y', scilimits=(0, 0))


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


def plot_timecourse(df: pd.DataFrame, cfg: DatasetConfig, metrics: Iterable[MetricSpec], out_png: Path, out_pdf: Path, tests: pd.DataFrame, polished: bool) -> pd.DataFrame:
    metrics = tuple(metrics)
    fig_w = max(4.0 * len(metrics), 12.0)
    fig, axes = plt.subplots(1, len(metrics), figsize=(fig_w, 4.6))
    if len(metrics) == 1:
        axes = [axes]
    days, xpos, labels = x_mapping(df)
    tick_positions = [xpos[d] for d in days]
    summaries: list[pd.DataFrame] = []
    for ax, spec in zip(axes, metrics):
        summary = summarize_metric(df, cfg, spec.key)
        summary['metric'] = spec.key
        summaries.append(summary)
        for group in cfg.group_order:
            sub = summary.loc[summary[cfg.group_field] == group].sort_values('relative_day')
            if sub.empty:
                continue
            x = [xpos[int(d)] for d in sub['relative_day']]
            ax.errorbar(
                x,
                sub['mean'],
                yerr=sub['sem'].fillna(0.0),
                color=cfg.group_colors[group],
                marker=cfg.group_markers[group],
                markersize=5.5,
                linewidth=1.9,
                elinewidth=1.0,
                capsize=3,
                label=cfg.group_labels[group],
            )
        if cfg.show_plot_stats:
            add_global_stars(ax, summary, tests, spec.key, xpos)
        if not polished:
            ax.set_title(spec.label, fontsize=11, pad=8)
        ax.set_ylabel(spec.label)
        apply_common_axis(ax, tick_positions, labels, polished=polished)
        maybe_sci(ax, spec.key)
    handles, labels_ = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_, loc='upper right', ncol=1, frameon=False, bbox_to_anchor=(0.98, 0.98))
    fig.tight_layout(rect=(0, 0, 0.96, 0.95))
    fig.savefig(out_png, dpi=240, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)
    return pd.concat(summaries, ignore_index=True)


def plot_full_metrics(df: pd.DataFrame, cfg: DatasetConfig, out_png: Path, out_pdf: Path) -> pd.DataFrame:
    metrics = cfg.full_metrics
    n = len(metrics)
    ncols = 3
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(15.5, 4.0 * nrows))
    axes = np.atleast_1d(axes).ravel()
    days, xpos, labels = x_mapping(df)
    tick_positions = [xpos[d] for d in days]
    summaries: list[pd.DataFrame] = []
    for ax, spec in zip(axes, metrics):
        summary = summarize_metric(df, cfg, spec.key)
        summary['metric'] = spec.key
        summaries.append(summary)
        for group in cfg.group_order:
            sub = summary.loc[summary[cfg.group_field] == group].sort_values('relative_day')
            if sub.empty:
                continue
            x = [xpos[int(d)] for d in sub['relative_day']]
            ax.errorbar(
                x,
                sub['mean'],
                yerr=sub['sem'].fillna(0.0),
                color=cfg.group_colors[group],
                marker=cfg.group_markers[group],
                markersize=4.8,
                linewidth=1.6,
                elinewidth=0.9,
                capsize=2.5,
            )
        ax.set_title(spec.label, fontsize=10, pad=6)
        ax.set_ylabel(spec.label)
        apply_common_axis(ax, tick_positions, labels, polished=False)
        maybe_sci(ax, spec.key)
    handles = []
    labels_ = []
    for group in cfg.group_order:
        h, = axes[0].plot([], [], color=cfg.group_colors[group], marker=cfg.group_markers[group], linewidth=1.6, label=cfg.group_labels[group])
        handles.append(h)
        labels_.append(cfg.group_labels[group])
    for ax in axes[n:]:
        ax.axis('off')
    fig.legend(handles, labels_, loc='upper right', ncol=1, frameon=False, bbox_to_anchor=(0.98, 0.98))
    fig.tight_layout(rect=(0, 0, 0.96, 1))
    fig.savefig(out_png, dpi=220, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)
    return pd.concat(summaries, ignore_index=True)


def add_bracket(ax: plt.Axes, x1: float, x2: float, y: float, text: str, h: float) -> None:
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], color='black', linewidth=1.0)
    ax.text((x1 + x2) / 2.0, y + h, text, ha='center', va='bottom', color='black', fontsize=10, fontweight='bold')


def plot_focused(df: pd.DataFrame, cfg: DatasetConfig, out_png: Path, out_pdf: Path, polished: bool) -> pd.DataFrame:
    if not cfg.focused:
        return pd.DataFrame()
    specs = cfg.focused
    n = len(specs)
    ncols = 2 if n > 1 else 1
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(11.0, 4.8 * nrows))
    axes = np.atleast_1d(axes).ravel()
    stats_rows: list[dict[str, object]] = []
    xpos = np.arange(1, len(cfg.group_order) + 1)
    for ax, spec in zip(axes, specs):
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
        pair_stats = pairwise_vs_control(df, cfg, spec.metric, spec.day)
        stats_rows.extend([{**row, 'focus_label': spec.label} for row in pair_stats])
        if cfg.show_plot_stats and pair_stats:
            ymax = max(maxima) if maxima else 1.0
            ymin = min(maxima) if maxima else 0.0
            span = (ymax - ymin) if ymax > ymin else 1.0
            level = ymax + 0.08 * span
            step = 0.10 * span
            for row, other_idx in zip(pair_stats, xpos[1:]):
                if row['stars']:
                    add_bracket(ax, xpos[0], other_idx, level, row['stars'], 0.03 * span)
                    level += step
        if not polished:
            ax.set_title(spec.label, fontsize=11, pad=8)
        ax.set_ylabel(next(m.label for m in cfg.full_metrics if m.key == spec.metric))
        ax.set_xticks(xpos)
        ax.set_xticklabels([cfg.group_labels[g] for g in cfg.group_order], rotation=0)
        ax.grid(False)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_linewidth(0.8)
        ax.spines['bottom'].set_linewidth(0.8)
        maybe_sci(ax, spec.metric)
    for ax in axes[n:]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(out_png, dpi=240, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    plt.close(fig)
    return pd.DataFrame(stats_rows)


def write_df(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def generate(root: Path) -> dict[str, object]:
    return generate_with_suffix(root, 'v2')


def generate_with_suffix(root: Path, suffix: str) -> dict[str, object]:
    cfg = infer_config(root)
    df = load_df(root, cfg)

    fig_root = ensure_dir(root / f'figures-guided-{suffix}')
    polished_root = ensure_dir(root / f'figures-polished-guided-{suffix}')
    stats_root = ensure_dir(fig_root / 'statistics_tables')

    primary_tests = global_tests(df, cfg, cfg.primary_metrics)
    supportive_tests = global_tests(df, cfg, cfg.supportive_metrics)
    primary_pairwise_vs_control_rows: list[dict[str, object]] = []
    primary_pairwise_all_rows: list[dict[str, object]] = []
    for spec in cfg.primary_metrics:
        for day in sorted(int(v) for v in df['relative_day'].dropna().unique().tolist()):
            primary_pairwise_vs_control_rows.extend(pairwise_vs_control(df, cfg, spec.key, day))
            primary_pairwise_all_rows.extend(pairwise_all_groups(df, cfg, spec.key, day))

    primary_summary = plot_timecourse(
        df, cfg, cfg.primary_metrics,
        ensure_dir(fig_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_guided.png',
        ensure_dir(fig_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_guided.pdf',
        primary_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=False,
    )
    supportive_summary = plot_timecourse(
        df, cfg, cfg.supportive_metrics,
        ensure_dir(fig_root / 'supportive_timecourse') / f'{cfg.key}_supportive_metrics_timecourse_guided.png',
        ensure_dir(fig_root / 'supportive_timecourse') / f'{cfg.key}_supportive_metrics_timecourse_guided.pdf',
        supportive_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=False,
    )
    full_summary = plot_full_metrics(
        df, cfg,
        ensure_dir(fig_root / 'full_metric_panels') / f'{cfg.key}_full_metric_panels_guided.png',
        ensure_dir(fig_root / 'full_metric_panels') / f'{cfg.key}_full_metric_panels_guided.pdf',
    )
    focus_stats = plot_focused(
        df, cfg,
        ensure_dir(fig_root / 'focused_day_comparisons') / f'{cfg.key}_focused_day_comparisons_guided.png',
        ensure_dir(fig_root / 'focused_day_comparisons') / f'{cfg.key}_focused_day_comparisons_guided.pdf',
        polished=False,
    )

    polished_primary = plot_timecourse(
        df, cfg, cfg.primary_metrics,
        ensure_dir(polished_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_polished_guided.png',
        ensure_dir(polished_root / 'main_primary_metrics') / f'{cfg.key}_primary_metrics_timecourse_polished_guided.pdf',
        primary_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=True,
    )
    polished_supportive = plot_timecourse(
        df, cfg, cfg.supportive_metrics,
        ensure_dir(polished_root / 'supportive_timecourse') / f'{cfg.key}_supportive_metrics_timecourse_polished_guided.png',
        ensure_dir(polished_root / 'supportive_timecourse') / f'{cfg.key}_supportive_metrics_timecourse_polished_guided.pdf',
        supportive_tests if cfg.show_plot_stats else pd.DataFrame(),
        polished=True,
    )
    polished_focus_stats = plot_focused(
        df, cfg,
        ensure_dir(polished_root / 'focused_day_comparisons') / f'{cfg.key}_focused_day_comparisons_polished_guided.png',
        ensure_dir(polished_root / 'focused_day_comparisons') / f'{cfg.key}_focused_day_comparisons_polished_guided.pdf',
        polished=True,
    )

    write_df(primary_summary, stats_root / 'primary_metric_summary.csv')
    write_df(supportive_summary, stats_root / 'supportive_metric_summary.csv')
    write_df(full_summary, stats_root / 'full_metric_summary.csv')
    write_df(primary_tests, stats_root / 'primary_same_day_global_tests.csv')
    write_df(supportive_tests, stats_root / 'supportive_same_day_global_tests.csv')
    write_df(pd.DataFrame(primary_pairwise_vs_control_rows), stats_root / 'primary_pairwise_vs_control.csv')
    write_df(pd.DataFrame(primary_pairwise_all_rows), stats_root / 'primary_pairwise_all_groups.csv')
    write_df(focus_stats, stats_root / 'focused_pairwise_vs_control.csv')
    write_df(polished_focus_stats, stats_root / 'focused_pairwise_vs_control_polished.csv')

    manifest = {
        'dataset': cfg.key,
        'root': str(root),
        'group_field': cfg.group_field,
        'group_order': list(cfg.group_order),
        'enable_stats': cfg.enable_stats,
        'show_plot_stats': cfg.show_plot_stats,
        'primary_metrics': [m.key for m in cfg.primary_metrics],
        'supportive_metrics': [m.key for m in cfg.supportive_metrics],
        'full_metrics': [m.key for m in cfg.full_metrics],
        'focused_days': [{'day': f.day, 'metric': f.metric, 'label': f.label} for f in cfg.focused],
        'style': {
            'equal_day_spacing': True,
            'x_tick_labels': 'D{relative_day}',
            'grid': False,
            'polished_panel_titles': False,
            'polished_overall_titles': False,
            'black_significance_only': True,
            'x_axis_title': False,
            'long_day_tick_rotation_deg': 35,
        },
        'outputs': {
            'figures_guided': str(fig_root),
            'figures_polished_guided': str(polished_root),
            'statistics_tables': str(stats_root),
        },
    }
    (fig_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (polished_root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    args = parse_args()
    manifest = generate_with_suffix(args.root.resolve(), args.suffix)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
