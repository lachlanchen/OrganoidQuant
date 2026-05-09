#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile
import io
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle, Rectangle
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
import numpy as np
import pandas as pd
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_requested_0415_figures import (  # noqa: E402
    CONFIGS_0415,
    NO_ERRORBARS_DATASETS,
    add_global_stars,
    global_tests,
    infer_base_config,
    load_df,
    maybe_sci,
    slug,
    summarize_metric,
)
from generate_guided_deo_figures import DatasetConfig, MetricSpec  # noqa: E402

PROJECT_ROOT = Path('/home/lachlan/ProjectsLFS/Zhengyu')
DEFAULT_ROOTS = (
    PROJECT_ROOT / 'analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1',
    PROJECT_ROOT / 'analysis-output/app65_alginate_v3_direct_brightfield',
    PROJECT_ROOT / 'analysis-output/app80_all_concentrations_multiscale_large_recovery',
)
DOCX_PATHS = (
    PROJECT_ROOT / 'publication/DEO_manuscript WZY 260509_2.docx',
    PROJECT_ROOT / 'publication/DEO+Supplementary+information+WZY+20260509.docx',
)
EMU_PER_INCH = 914400
DOCX_FIGURE_WIDTH_IN = 6.36
CURRENT_EXPORT_WIDTH_IN = 14.45
ESTIMATED_SCALE_TO_DOCX = DOCX_FIGURE_WIDTH_IN / CURRENT_EXPORT_WIDTH_IN


@dataclass(frozen=True)
class ExportVariant:
    key: str
    description: str
    base_font_pt: float
    main_figsize: tuple[float, float]
    split_figsize: tuple[float, float]
    figure2_figsize: tuple[float, float]
    max_xticks: int
    xtick_rotation: float
    include_text: bool
    include_legend: bool
    include_stats_text: bool
    line_width: float
    marker_size: float
    spine_width: float
    tick_length: float


VARIANTS: tuple[ExportVariant, ...] = (
    ExportVariant(
        key='option_1_docx_width_arial12',
        description='Native DOCX-width export: 6.36-inch line-figure width with Arial-compatible 12 pt text.',
        base_font_pt=12.0,
        main_figsize=(6.36, 2.85),
        split_figsize=(2.35, 2.65),
        figure2_figsize=(6.36, 3.25),
        max_xticks=5,
        xtick_rotation=50,
        include_text=True,
        include_legend=True,
        include_stats_text=True,
        line_width=1.45,
        marker_size=4.3,
        spine_width=0.95,
        tick_length=3.2,
    ),
    ExportVariant(
        key='option_2_scaled_down_3x_font',
        description='Large-text export for downscaling: current-style wide plot with about 3x current font size so text remains readable after insertion into a DOCX-width figure.',
        base_font_pt=27.0,
        main_figsize=(14.45, 5.65),
        split_figsize=(5.2, 4.9),
        figure2_figsize=(14.45, 7.35),
        max_xticks=5,
        xtick_rotation=55,
        include_text=True,
        include_legend=True,
        include_stats_text=True,
        line_width=3.6,
        marker_size=10.0,
        spine_width=2.1,
        tick_length=7.0,
    ),
    ExportVariant(
        key='option_3_no_text_svg_manual_labels',
        description='Text-free editable SVG/PDF/PNG export: data geometry, axes, lines, markers, and schematic shapes only; labels and legends can be added manually later.',
        base_font_pt=12.0,
        main_figsize=(6.36, 2.65),
        split_figsize=(2.35, 2.35),
        figure2_figsize=(6.36, 3.25),
        max_xticks=0,
        xtick_rotation=0,
        include_text=False,
        include_legend=False,
        include_stats_text=False,
        line_width=1.45,
        marker_size=4.3,
        spine_width=0.95,
        tick_length=3.2,
    ),
)


NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate publication 0509 figure export options.')
    parser.add_argument('--suffix', default='0509_options_v1')
    parser.add_argument('--out-root', type=Path, default=PROJECT_ROOT / 'analysis-output/publication_figure_exports_0509_options_v1')
    parser.add_argument('--root', type=Path, action='append', dest='roots', help='Dataset root. Defaults to App81/App65/App80.')
    return parser.parse_args()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def infer_config(root: Path) -> DatasetConfig:
    root_s = str(root)
    for cfg in CONFIGS_0415:
        if any(token in root_s for token in cfg.infer_name_tokens):
            if cfg.key == 'app65':
                labels = dict(cfg.group_labels)
                labels['0.02% Alginate'] = '0.02%'
                labels['0.05% Alginate'] = '0.05%'
                return replace(cfg, group_labels=labels)
            return cfg
    cfg = infer_base_config(root)
    if cfg.key == 'app65':
        labels = dict(cfg.group_labels)
        labels['0.02% Alginate'] = '0.02%'
        labels['0.05% Alginate'] = '0.05%'
        return replace(cfg, group_labels=labels)
    return cfg


def inspect_docx_figures(docx_paths: Iterable[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for docx_path in docx_paths:
        if not docx_path.exists():
            continue
        try:
            with ZipFile(docx_path) as zf:
                rels_root = ET.fromstring(zf.read('word/_rels/document.xml.rels'))
                rels = {rel.attrib.get('Id'): rel.attrib.get('Target') for rel in rels_root}
                document = ET.fromstring(zf.read('word/document.xml'))
                idx = 0
                for drawing in document.findall('.//w:drawing', NS):
                    idx += 1
                    extent = drawing.find('.//wp:extent', NS)
                    blip = drawing.find('.//a:blip', NS)
                    cx = int(extent.attrib.get('cx', 0)) if extent is not None else 0
                    cy = int(extent.attrib.get('cy', 0)) if extent is not None else 0
                    rid = blip.attrib.get(f'{{{NS["r"]}}}embed') if blip is not None else None
                    target = rels.get(rid, '') if rid else ''
                    media_path = 'word/' + target if target and not target.startswith('word/') else target
                    pixels = None
                    if media_path in zf.namelist():
                        try:
                            image = Image.open(io.BytesIO(zf.read(media_path)))
                            pixels = list(image.size)
                        except Exception:
                            pixels = None
                    records.append({
                        'docx': str(docx_path),
                        'figure_index': idx,
                        'target': target,
                        'display_width_in': round(cx / EMU_PER_INCH, 3) if cx else None,
                        'display_height_in': round(cy / EMU_PER_INCH, 3) if cy else None,
                        'display_width_cm': round(cx / EMU_PER_INCH * 2.54, 3) if cx else None,
                        'display_height_cm': round(cy / EMU_PER_INCH * 2.54, 3) if cy else None,
                        'embedded_pixels': pixels,
                    })
        except Exception as exc:
            records.append({'docx': str(docx_path), 'error': str(exc)})
    return records


def inspect_existing_exports(roots: Iterable[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for root in roots:
        cfg = infer_config(root)
        candidates = sorted((root / 'figures-polished-guided-0415/main_primary_metrics').glob(f'{cfg.key}_primary_metrics_timecourse_polished_guided_0415.png'))
        for path in candidates:
            try:
                image = Image.open(path)
                dpi = image.info.get('dpi')
                width_in = image.size[0] / dpi[0] if dpi else None
                height_in = image.size[1] / dpi[1] if dpi else None
                records.append({
                    'dataset': cfg.key,
                    'path': str(path),
                    'pixels': list(image.size),
                    'dpi': list(dpi) if dpi else None,
                    'width_in_from_dpi': round(width_in, 3) if width_in else None,
                    'height_in_from_dpi': round(height_in, 3) if height_in else None,
                    'scale_to_docx_6p36in': round(DOCX_FIGURE_WIDTH_IN / width_in, 3) if width_in else None,
                })
            except Exception as exc:
                records.append({'dataset': cfg.key, 'path': str(path), 'error': str(exc)})
    return records


def set_publication_rc(variant: ExportVariant) -> dict[str, object]:
    return {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Liberation Sans', 'DejaVu Sans'],
        'font.size': variant.base_font_pt,
        'axes.labelsize': variant.base_font_pt,
        'axes.titlesize': variant.base_font_pt,
        'xtick.labelsize': variant.base_font_pt,
        'ytick.labelsize': variant.base_font_pt,
        'legend.fontsize': variant.base_font_pt,
        'svg.fonttype': 'none',
        'pdf.fonttype': 42,
        'ps.fonttype': 42,
        'axes.linewidth': variant.spine_width,
    }


def x_mapping(df: pd.DataFrame) -> tuple[list[int], dict[int, int]]:
    days = sorted(int(v) for v in df['relative_day'].dropna().unique().tolist())
    return days, {day: idx for idx, day in enumerate(days)}


def displayed_ticks(days: list[int], max_xticks: int) -> list[int]:
    if max_xticks <= 0:
        return days
    if len(days) <= max_xticks:
        return days
    idx = np.linspace(0, len(days) - 1, max_xticks)
    selected_indices = sorted({int(round(v)) for v in idx})
    return [days[i] for i in selected_indices]


def style_axis(ax: plt.Axes, variant: ExportVariant, days: list[int], xpos: dict[int, int], ylabel: str, metric: str) -> None:
    selected_days = displayed_ticks(days, variant.max_xticks)
    ax.set_xticks([xpos[d] for d in selected_days])
    if variant.include_text:
        ax.set_xticklabels([f'D{d}' for d in selected_days], rotation=variant.xtick_rotation, ha='right')
        ax.set_ylabel(ylabel)
        maybe_sci(ax, metric)
    else:
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_ylabel('')
        ax.set_xlabel('')
        ax.yaxis.offsetText.set_visible(False)
        ax.xaxis.offsetText.set_visible(False)
    ax.grid(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(variant.spine_width)
    ax.spines['bottom'].set_linewidth(variant.spine_width)
    ax.tick_params(axis='both', width=variant.spine_width, length=variant.tick_length)
    ax.set_facecolor('white')


def draw_series(ax: plt.Axes, cfg: DatasetConfig, group: str, sub: pd.DataFrame, x: list[int], with_errorbars: bool, variant: ExportVariant) -> None:
    common = dict(
        color=cfg.group_colors[group],
        marker=cfg.group_markers[group],
        markersize=variant.marker_size,
        linewidth=variant.line_width,
        label=cfg.group_labels[group] if variant.include_text else '_nolegend_',
    )
    if with_errorbars:
        ax.errorbar(
            x,
            sub['mean'],
            yerr=sub['sem'].fillna(0.0),
            elinewidth=max(0.8, variant.line_width * 0.55),
            capsize=max(2.4, variant.marker_size * 0.55),
            capthick=max(0.8, variant.line_width * 0.5),
            **common,
        )
    else:
        ax.plot(x, sub['mean'], **common)


def save_all_formats(fig: plt.Figure, stem: Path) -> dict[str, str]:
    paths = {
        'png': stem.with_suffix('.png'),
        'pdf': stem.with_suffix('.pdf'),
        'svg': stem.with_suffix('.svg'),
    }
    fig.savefig(paths['png'], dpi=300, bbox_inches='tight')
    fig.savefig(paths['pdf'], bbox_inches='tight')
    fig.savefig(paths['svg'], bbox_inches='tight')
    return {key: str(path) for key, path in paths.items()}


def make_legend(cfg: DatasetConfig, variant: ExportVariant, out_dir: Path, stem: str) -> dict[str, str] | None:
    if not variant.include_legend:
        return None
    handles = [
        Line2D([0], [0], color=cfg.group_colors[g], marker=cfg.group_markers[g], lw=variant.line_width, markersize=variant.marker_size, label=cfg.group_labels[g])
        for g in cfg.group_order
    ]
    ncols = len(handles) if len(handles) <= 3 else min(len(handles), 5)
    width = max(2.2, 0.95 * len(handles)) if variant.base_font_pt < 20 else max(5.5, 1.9 * len(handles))
    height = 0.55 if variant.base_font_pt < 20 else 1.15
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.legend(handles=handles, loc='center', ncol=ncols, frameon=False, handlelength=2.0, columnspacing=1.2)
    fig.tight_layout(pad=0.05)
    outputs = save_all_formats(fig, out_dir / stem)
    plt.close(fig)
    return outputs


def plot_primary(df: pd.DataFrame, cfg: DatasetConfig, variant: ExportVariant, out_dir: Path, suffix: str) -> dict[str, object]:
    metrics = tuple(cfg.primary_metrics)
    days, xpos = x_mapping(df)
    primary_tests = global_tests(df, cfg, cfg.primary_metrics)
    with_errorbars = cfg.key not in NO_ERRORBARS_DATASETS
    fig, axes = plt.subplots(1, len(metrics), figsize=variant.main_figsize)
    axes = np.atleast_1d(axes).tolist()
    summaries = []
    for ax, spec in zip(axes, metrics):
        summary = summarize_metric(df, cfg, spec.key)
        summary['metric'] = spec.key
        summaries.append(summary)
        for group in cfg.group_order:
            sub = summary.loc[summary[cfg.group_field] == group].sort_values('relative_day')
            if sub.empty:
                continue
            x = [xpos[int(day)] for day in sub['relative_day']]
            draw_series(ax, cfg, group, sub, x, with_errorbars=with_errorbars, variant=variant)
        if cfg.show_plot_stats and variant.include_stats_text:
            add_global_stars(ax, summary, primary_tests, spec.key, xpos)
        style_axis(ax, variant, days, xpos, spec.label, spec.key)
    if variant.include_text:
        fig.tight_layout(w_pad=1.0 if variant.base_font_pt < 20 else 1.8)
    else:
        fig.tight_layout(pad=0.2, w_pad=0.5)
    stem = out_dir / f'{cfg.key}_primary_metrics_timecourse_{suffix}_{variant.key}'
    outputs = save_all_formats(fig, stem)
    plt.close(fig)
    legend_outputs = make_legend(cfg, variant, ensure_dir(out_dir / 'legend'), f'{cfg.key}_legend_{suffix}_{variant.key}')
    summary_df = pd.concat(summaries, ignore_index=True)
    summary_path = out_dir / f'{cfg.key}_primary_metric_summary_{suffix}_{variant.key}.csv'
    summary_df.to_csv(summary_path, index=False)
    return {
        'dataset': cfg.key,
        'kind': 'main_primary_metrics',
        'variant': variant.key,
        'outputs': outputs,
        'legend_outputs': legend_outputs,
        'summary_csv': str(summary_path),
    }


def plot_split(df: pd.DataFrame, cfg: DatasetConfig, variant: ExportVariant, out_dir: Path, suffix: str) -> list[dict[str, object]]:
    days, xpos = x_mapping(df)
    primary_tests = global_tests(df, cfg, cfg.primary_metrics)
    with_errorbars = cfg.key not in NO_ERRORBARS_DATASETS
    rows: list[dict[str, object]] = []
    for spec in cfg.primary_metrics:
        fig, ax = plt.subplots(1, 1, figsize=variant.split_figsize)
        summary = summarize_metric(df, cfg, spec.key)
        summary['metric'] = spec.key
        for group in cfg.group_order:
            sub = summary.loc[summary[cfg.group_field] == group].sort_values('relative_day')
            if sub.empty:
                continue
            x = [xpos[int(day)] for day in sub['relative_day']]
            draw_series(ax, cfg, group, sub, x, with_errorbars=with_errorbars, variant=variant)
        if cfg.show_plot_stats and variant.include_stats_text:
            add_global_stars(ax, summary, primary_tests, spec.key, xpos)
        style_axis(ax, variant, days, xpos, spec.label, spec.key)
        if variant.include_text:
            fig.tight_layout(pad=0.18)
        else:
            fig.tight_layout(pad=0.12)
        tag = slug(spec.key)
        stem = out_dir / f'{cfg.key}_{tag}_{suffix}_{variant.key}'
        outputs = save_all_formats(fig, stem)
        plt.close(fig)
        rows.append({
            'dataset': cfg.key,
            'metric': spec.key,
            'label': spec.label,
            'variant': variant.key,
            'outputs': outputs,
        })
    return rows


def draw_figure2_workflow(variant: ExportVariant, out_dir: Path, suffix: str) -> dict[str, object]:
    colors = {
        'teal': '#0E6970',
        'light': '#F6FBFB',
        'blue': '#2C6FB7',
        'red': '#C73832',
        'orange': '#D97706',
        'gray': '#E8EEF2',
        'ink': '#102A43',
    }
    fig, ax = plt.subplots(figsize=variant.figure2_figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    ax.add_patch(FancyBboxPatch((0.015, 0.05), 0.97, 0.88, boxstyle='round,pad=0.01,rounding_size=0.02', facecolor='white', edgecolor=colors['teal'], linewidth=variant.spine_width * 1.2))
    panels = [
        ('A', 'Heterogeneous\nimages', 'Uncontrolled agent\noutputs vary'),
        ('B', 'Dataset +\nmetadata', 'Capture, registry,\nconditions, dates'),
        ('C', 'Vision QC +\nmethod routing', 'Image priors choose\nsegmentation route'),
        ('D', 'Agent-designed\nquantification', 'Growth, differentiation,\nfusion metrics'),
        ('E', 'Reproducible\noutputs', 'Database, overlays,\nplots, conclusions'),
    ]
    x0s = np.linspace(0.05, 0.80, 5)
    w = 0.155
    h = 0.68
    for i, (letter, title, body) in enumerate(panels):
        x0 = float(x0s[i])
        y0 = 0.17
        edge = colors['red'] if i == 0 else colors['blue'] if i < 4 else colors['teal']
        ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle='round,pad=0.012,rounding_size=0.015', facecolor=colors['light'] if i else '#FFF8F6', edgecolor=edge, linewidth=variant.spine_width))
        if variant.include_text:
            title_fs = min(variant.base_font_pt * 0.50, 12.5)
            body_fs = min(variant.base_font_pt * 0.42, 10.5)
            badge_r = 0.013
            ax.add_patch(Circle((x0 + 0.024, y0 + h - 0.042), badge_r, facecolor=colors['ink'], edgecolor='none'))
            ax.text(x0 + 0.024, y0 + h - 0.042, letter, ha='center', va='center', color='white', fontsize=body_fs * 0.9, weight='bold')
            ax.text(x0 + w / 2 + 0.006, y0 + h - 0.052, title, ha='center', va='top', color=colors['ink'], fontsize=title_fs, weight='bold', linespacing=1.02)
            ax.text(x0 + w / 2, y0 + 0.08, body, ha='center', va='bottom', color=colors['ink'], fontsize=body_fs, linespacing=1.04)
        # Graphic glyph area.
        gx, gy = x0 + 0.03, y0 + 0.25
        if i == 0:
            for r in range(3):
                for c in range(3):
                    ax.add_patch(Rectangle((gx + c * 0.032, gy + r * 0.046), 0.026, 0.035, facecolor='#BFC7CC', edgecolor='white', linewidth=0.5))
                    ax.add_patch(Circle((gx + c * 0.032 + 0.013, gy + r * 0.046 + 0.017), 0.008 + 0.002 * ((r + c) % 2), facecolor='#4A5568', alpha=0.75, edgecolor='none'))
            ax.add_patch(FancyBboxPatch((x0 + 0.045, y0 + 0.47), 0.065, 0.055, boxstyle='round,pad=0.004', facecolor='white', edgecolor=colors['red'], linestyle='--', linewidth=variant.spine_width))
            for px in (x0 + 0.065, x0 + 0.095):
                ax.plot([px, px + 0.018], [y0 + 0.47, y0 + 0.42], color=colors['red'], linewidth=variant.spine_width * 0.8)
        elif i == 1:
            ax.add_patch(Rectangle((gx + 0.035, gy + 0.02), 0.06, 0.14, facecolor='white', edgecolor=colors['blue'], linewidth=variant.spine_width))
            for k in range(4):
                ax.plot([gx + 0.045, gx + 0.085], [gy + 0.045 + k * 0.025, gy + 0.045 + k * 0.025], color=colors['blue'], linewidth=variant.spine_width * 0.8)
            for k in range(4):
                ax.add_patch(Rectangle((gx + 0.002, gy + 0.03 + k * 0.035), 0.018, 0.018, facecolor='white', edgecolor=colors['teal'], linewidth=variant.spine_width * 0.75))
        elif i == 2:
            nodes = [(gx + 0.02, gy + 0.04), (gx + 0.055, gy + 0.105), (gx + 0.095, gy + 0.06), (gx + 0.112, gy + 0.13)]
            for a, b in zip(nodes[:-1], nodes[1:]):
                ax.plot([a[0], b[0]], [a[1], b[1]], color=colors['teal'], linewidth=variant.spine_width * 1.0)
            for n in nodes:
                ax.add_patch(Circle(n, 0.011, facecolor='white', edgecolor=colors['teal'], linewidth=variant.spine_width))
            for k, col in enumerate([colors['blue'], colors['orange'], '#7C3AED']):
                ax.add_patch(FancyBboxPatch((gx + 0.025, gy + 0.19 + k * 0.045), 0.095, 0.028, boxstyle='round,pad=0.003', facecolor='white', edgecolor=col, linewidth=variant.spine_width * 0.75))
        elif i == 3:
            ax.add_patch(Rectangle((gx, gy + 0.18), 0.035, 0.035, facecolor='white', edgecolor=colors['blue'], linewidth=variant.spine_width))
            ax.add_patch(Circle((gx + 0.085, gy + 0.205), 0.025, facecolor='white', edgecolor=colors['orange'], linewidth=variant.spine_width))
            for k, col in enumerate([colors['red'], colors['blue'], colors['teal'], colors['orange']]):
                ax.add_patch(FancyBboxPatch((gx + (k % 2) * 0.064, gy + (k // 2) * 0.062), 0.048, 0.044, boxstyle='round,pad=0.003', facecolor='white', edgecolor=col, linewidth=variant.spine_width * 0.75))
        else:
            for k in range(3):
                ax.add_patch(Rectangle((gx + k * 0.038, gy + 0.12), 0.03, 0.055, facecolor='#D7E8F7', edgecolor='white', linewidth=0.5))
                ax.add_patch(Circle((gx + k * 0.038 + 0.015, gy + 0.148), 0.009, facecolor=colors['teal'], alpha=0.75, edgecolor='none'))
            ax.plot([gx + 0.005, gx + 0.12], [gy + 0.04, gy + 0.04], color=colors['ink'], linewidth=variant.spine_width)
            for k, col in enumerate([colors['blue'], colors['red'], colors['orange']]):
                xs = np.linspace(gx + 0.01, gx + 0.11, 20)
                ys = gy + 0.055 + 0.012 * np.sin(np.linspace(0, 2.4, 20) + k * 0.8) + k * 0.013
                ax.plot(xs, ys, color=col, linewidth=variant.spine_width * 0.9)
        if i < 4:
            ax.add_patch(FancyArrowPatch((x0 + w + 0.012, y0 + h / 2), (float(x0s[i + 1]) - 0.012, y0 + h / 2), arrowstyle='-|>', mutation_scale=10 + variant.base_font_pt * 0.65, color='#64748B', linewidth=variant.spine_width))
    ax.add_patch(FancyBboxPatch((0.08, 0.065), 0.84, 0.075, boxstyle='round,pad=0.008,rounding_size=0.012', facecolor='#F7FCFC', edgecolor=colors['teal'], linewidth=variant.spine_width * 0.85))
    if variant.include_text:
        ax.text(0.5, 0.102, 'Guardrails | QC checkpoints | audit trail | reproducible by design', ha='center', va='center', color=colors['teal'], fontsize=variant.base_font_pt * 0.55, weight='bold')
    fig.tight_layout(pad=0.04)
    stem = out_dir / f'figure2_aaps_workflow_{suffix}_{variant.key}'
    outputs = save_all_formats(fig, stem)
    plt.close(fig)
    return {'figure': 'figure2_aaps_workflow', 'variant': variant.key, 'outputs': outputs}


def generate_for_root(root: Path, out_root: Path, suffix: str, variant: ExportVariant) -> dict[str, object]:
    cfg = infer_config(root)
    df = load_df(root, cfg)
    dataset_dir = ensure_dir(out_root / variant.key / cfg.key)
    with plt.rc_context(set_publication_rc(variant)):
        main = plot_primary(df, cfg, variant, ensure_dir(dataset_dir / 'main_primary_metrics'), suffix)
        split = plot_split(df, cfg, variant, ensure_dir(dataset_dir / 'split_primary_individual'), suffix)
    return {'dataset': cfg.key, 'root': str(root), 'variant': variant.key, 'main': main, 'split': split}


def generate_figure2(out_root: Path, suffix: str, variant: ExportVariant) -> dict[str, object]:
    out_dir = ensure_dir(out_root / variant.key / 'figure2_aaps_workflow')
    with plt.rc_context(set_publication_rc(variant)):
        return draw_figure2_workflow(variant, out_dir, suffix)


def main() -> None:
    args = parse_args()
    roots = tuple(path.resolve() for path in (args.roots or DEFAULT_ROOTS))
    out_root = ensure_dir(args.out_root.resolve())

    docx_records = inspect_docx_figures(DOCX_PATHS)
    existing_records = inspect_existing_exports(roots)
    font_path = font_manager.findfont(FontProperties(family=['Arial', 'Liberation Sans', 'DejaVu Sans']), fallback_to_default=True)

    manifest: dict[str, object] = {
        'suffix': args.suffix,
        'out_root': str(out_root),
        'font_request': 'Arial',
        'font_fallback_order': ['Arial', 'Liberation Sans', 'DejaVu Sans'],
        'font_resolved_by_matplotlib': font_path,
        'docx_figure_inspection': docx_records,
        'existing_0415_export_inspection': existing_records,
        'font_size_reasoning': {
            'docx_main_figure_width_in': DOCX_FIGURE_WIDTH_IN,
            'typical_existing_export_width_in': CURRENT_EXPORT_WIDTH_IN,
            'estimated_scale_existing_to_docx': round(ESTIMATED_SCALE_TO_DOCX, 3),
            'current_effective_tick_font_after_docx_scaling_pt': 'Existing tick labels around 8-10 pt become roughly 3.5-4.4 pt when a 14.45 in export is inserted at 6.36 in.',
            'three_x_rationale': 'About 27 pt in the current wide export scales down to roughly 12 pt at DOCX figure width.',
        },
        'variants': [variant.__dict__ for variant in VARIANTS],
        'outputs': [],
    }

    for variant in VARIANTS:
        figure2_record = generate_figure2(out_root, args.suffix, variant)
        manifest['outputs'].append(figure2_record)
        for root in roots:
            manifest['outputs'].append(generate_for_root(root, out_root, args.suffix, variant))

    manifest_path = out_root / f'manifest_{args.suffix}.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    readme = out_root / f'README_{args.suffix}.md'
    readme.write_text(
        '# Publication Figure Export Options\n\n'
        f'Suffix: `{args.suffix}`\n\n'
        'This folder contains three export options for Figure 2 and the App81/App65/App80 primary quantitative figures.\n\n'
        '## Options\n\n'
        '- `option_1_docx_width_arial12`: native DOCX-width export with Arial-compatible 12 pt text.\n'
        '- `option_2_scaled_down_3x_font`: wide export with approximately 3x current font size, intended for downscaling into the DOCX/manuscript figure width.\n'
        '- `option_3_no_text_svg_manual_labels`: no text in the generated figure body, with SVG/PDF/PNG output for manual label editing.\n\n'
        '## Notes\n\n'
        '- The current system resolves Arial to the Matplotlib font path recorded in the manifest.\n'
        '- App65 alginate labels are exported as `0.02%` and `0.05%`, not Low/High alginate.\n'
        '- Main quantitative plots do not contain legends. Legend files are exported separately for text-bearing options.\n'
        '- SVG text remains editable because `svg.fonttype` is set to `none`.\n',
        encoding='utf-8',
    )
    print(json.dumps({'out_root': str(out_root), 'manifest': str(manifest_path), 'readme': str(readme)}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
