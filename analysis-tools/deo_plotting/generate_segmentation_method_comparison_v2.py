#!/usr/bin/env python3
"""Generate expanded segmentation comparison figures and proxy benchmarks.

This v2 package is intentionally isolated from the original comparison output.
It writes a complete manuscript-ready asset bundle to:

    publication/aaps-organoid/segmentation_method_comparison_v2/

The image grids are text-free. Captions, row/column definitions, and benchmark
tables are generated as separate TeX/CSV/JSON assets for traceability.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

import numpy as np
from PIL import Image, ImageDraw, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "publication/aaps-organoid/segmentation_method_comparison_v2"
FIGURE_DIR = OUTPUT_ROOT / "figures"
TABLE_DIR = OUTPUT_ROOT / "tables"


@dataclass(frozen=True)
class Panel:
    method: str
    label: str
    overlay_path: Path
    mask_path: Path | None = None
    raw: bool = False
    reference: bool = False


@dataclass(frozen=True)
class Row:
    sample_id: str
    description: str
    panels: tuple[Panel, ...]


@dataclass(frozen=True)
class FigureSpec:
    dataset: str
    key: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    cell_width: int = 560
    cell_height: int = 398
    gutter: int = 14
    margin: int = 24


def p(relative: str) -> Path:
    return PROJECT_ROOT / relative


def app80_rows() -> tuple[Row, ...]:
    rows: list[Row] = []
    samples = [
        ("05-十二月-2025", "10x00", "5 Dec 2025"),
        ("07-十二月-2025", "10X00", "7 Dec 2025"),
        ("08-十二月-2025", "10x00", "8 Dec 2025"),
        ("09-十二月-2025", "10x00", "9 Dec 2025"),
        ("10-十二月-2025", "10x00", "10 Dec 2025"),
        ("11-十二月-2025", "10x00", "11 Dec 2025"),
        ("12-十二月-2025", "10x00", "12 Dec 2025"),
    ]
    for date_key, image_id, date_label in samples:
        old_dir = f"{date_key}__{image_id}"
        final_stem = f"{date_key}_{image_id}"
        rows.append(
            Row(
                sample_id=f"app80_10uM_{date_key}_{image_id}",
                description=f"App80, 10 uM Y-27632, {date_label}, {image_id}",
                panels=(
                    Panel(
                        "raw",
                        "Raw",
                        p(f"DEO/App80 DEO/10uM/{date_key}/{image_id}.tif"),
                        raw=True,
                    ),
                    Panel(
                        "prompted_watershed",
                        "Prompted watershed",
                        p(
                            "analysis-output/archived-outputs/"
                            f"app80_10uM_first_replicate_prompted_watershed/{old_dir}/"
                            "watershed_overlay.png"
                        ),
                        p(
                            "analysis-output/archived-outputs/"
                            f"app80_10uM_first_replicate_prompted_watershed/{old_dir}/"
                            "watershed_labels_16bit.png"
                        ),
                    ),
                    Panel(
                        "cpsam",
                        "CPSAM",
                        p(
                            "analysis-output/archived-outputs/"
                            f"app80_10uM_first_replicate_cpsam/runs/{old_dir}/"
                            "cpsam_overlay.png"
                        ),
                        p(
                            "analysis-output/archived-outputs/"
                            f"app80_10uM_first_replicate_cpsam/runs/{old_dir}/"
                            "cpsam_labels_16bit.png"
                        ),
                    ),
                    Panel(
                        "final_multiscale_large_recovery",
                        "Final multiscale",
                        p(
                            "analysis-output/app80_all_concentrations_multiscale_large_recovery/"
                            f"runs/10uM/{date_key}/{final_stem}_overlay.png"
                        ),
                        p(
                            "analysis-output/app80_all_concentrations_multiscale_large_recovery/"
                            f"runs/10uM/{date_key}/{final_stem}_mask_16bit.png"
                        ),
                        reference=True,
                    ),
                ),
            )
        )
    return tuple(rows)


def app65_rows() -> tuple[Row, ...]:
    rows: list[Row] = []
    date_key = "29-十一月-2025"
    for image_id in ("10x00", "10x01", "10x14", "10x15", "10x16", "10x17"):
        final_stem = f"{date_key}_0.02% Alginate {image_id}"
        threshold_root = (
            "analysis-output/archived/test_app65_alginate/"
            "test_app65_alginate_custom_cellpose/runs/0.02% Alginate/"
            f"{date_key}/{final_stem}_threshold_hint_cellpose"
        )
        rows.append(
            Row(
                sample_id=f"app65_0p02_alginate_{date_key}_{image_id}",
                description=f"App65, 0.02% alginate, 29 Nov 2025, {image_id}",
                panels=(
                    Panel(
                        "raw",
                        "Raw",
                        p(f"DEO/App65 DEO+Alginate/{date_key}/0.02% Alginate {image_id}.tif"),
                        raw=True,
                    ),
                    Panel(
                        "old_multiscale_large_recovery",
                        "Old multiscale",
                        p(
                            "analysis-output/archived-outputs/"
                            "app65_alginate_multiscale_large_recovery/runs/"
                            f"0.02% Alginate/{date_key}/{final_stem}_overlay.png"
                        ),
                        p(
                            "analysis-output/archived-outputs/"
                            "app65_alginate_multiscale_large_recovery/runs/"
                            f"0.02% Alginate/{date_key}/{final_stem}_mask_16bit.png"
                        ),
                    ),
                    Panel(
                        "threshold_hint_cellpose",
                        "Threshold-hinted Cellpose",
                        p(f"{threshold_root}/step06_final/step52_final_overlay.png"),
                        p(f"{threshold_root}/step06_final/step50_final_mask_16bit.png"),
                    ),
                    Panel(
                        "final_direct_brightfield",
                        "Final direct brightfield",
                        p(
                            "analysis-output/app65_alginate_v3_direct_brightfield/runs/"
                            f"0.02% Alginate/{date_key}/{final_stem}_overlay.png"
                        ),
                        p(
                            "analysis-output/app65_alginate_v3_direct_brightfield/runs/"
                            f"0.02% Alginate/{date_key}/{final_stem}_mask_16bit.png"
                        ),
                        reference=True,
                    ),
                ),
            )
        )
    return tuple(rows)


def app81_rows() -> tuple[Row, ...]:
    rows: list[Row] = []
    low_examples = [
        (
            "low",
            "14-十月-2025",
            "14-十月-2025_10X low",
            "14 Oct 2025",
            "10X low",
            "test_app81_grsai_clean_fill_v10_low_final_check/source_pngs/low/14-十月-2025_10X low_source.png",
            "test_app81_grsai_clean_fill_v10_low_final_check/generated_masks/low/14-十月-2025/14-十月-2025_10X low",
            "14-十月-2025/10X low/from_low_batch_2_replicate_01_10x_stitched",
        ),
        (
            "low",
            "15-十月-2025",
            "15-十月-2025_10x low",
            "15 Oct 2025",
            "10x low",
            "test_app81_grsai_clean_fill_v10_low_final_check/source_pngs/low/15-十月-2025_10x low_source.png",
            "test_app81_grsai_clean_fill_v10_low_final_check/generated_masks/low/15-十月-2025/15-十月-2025_10x low",
            "15-十月-2025/10x low/from_low_batch_1_replicate_01_10x_stitched",
        ),
        (
            "low",
            "16-十月-2025",
            "16-十月-2025_10x low",
            "16 Oct 2025",
            "10x low",
            "test_app81_grsai_clean_fill_v10_low_final_check/source_pngs/low/16-十月-2025_10x low_source.png",
            "test_app81_grsai_clean_fill_v10_low_final_check/generated_masks/low/16-十月-2025/16-十月-2025_10x low",
            "16-十月-2025/10x low/from_low_batch_2_replicate_01_10x_stitched",
        ),
    ]
    middle_examples = [
        (
            "middle",
            "18-十月-2025",
            "18-十月-2025_10X middle",
            "18 Oct 2025",
            "10X middle",
            "test_app81_grsai_masks_v1/source_pngs/18-十月-2025_10X_middle_source.png",
            "test_app81_grsai_masks_v1/generated_masks/18-十月-2025_10X_middle",
            "18-十月-2025/10X middle/from_middle_batch_2_replicate_01_10x_stitched",
        ),
        (
            "middle",
            "29-十月-2025",
            "29-十月-2025_10X middle10",
            "29 Oct 2025",
            "10X middle10",
            "test_app81_grsai_masks_v1/source_pngs/29-十月-2025_10X_middle10_source.png",
            "test_app81_grsai_masks_v1/generated_masks/29-十月-2025_10X_middle10",
            "29-十月-2025/10X middle10/from_middle_batch_2_replicate_01_10x_stitched",
        ),
    ]
    for density, date_key, image_stem, date_label, image_label, source_rel, grsai_rel, final_rel in (
        low_examples + middle_examples
    ):
        source = p(f"analysis-output/archived/test_app81/{source_rel}")
        grsai_root = p(f"analysis-output/archived/test_app81/{grsai_rel}")
        final_root = p(
            "analysis-output/archived/app81_density_stitched/"
            f"app81_density_stitched_cellpose_v5_final_single_exports_v2/{final_rel}"
        )
        rows.append(
            Row(
                sample_id=f"app81_{density}_{date_key}_{image_stem}",
                description=f"App81, {density} density, {date_label}, {image_label}",
                panels=(
                    Panel("raw", "Raw", source, raw=True),
                    Panel(
                        "threshold_hint_cellpose",
                        "Threshold-hinted Cellpose",
                        p(
                            "analysis-output/archived/app81_main_density/"
                            f"app81_main_density_custom_threshold_hint/runs/{density}/"
                            f"{date_key}/{image_stem}_overlay.png"
                        ),
                        p(
                            "analysis-output/archived/app81_main_density/"
                            f"app81_main_density_custom_threshold_hint/runs/{density}/"
                            f"{date_key}/{image_stem}_mask_16bit.png"
                        ),
                    ),
                    Panel(
                        "resized_multiscale_cellpose",
                        "Resized multiscale Cellpose",
                        p(
                            "analysis-output/archived/app81_main_density/"
                            f"app81_main_density_resized_multiscale_v1/runs/{density}/"
                            f"{date_key}/{image_stem}_overlay.png"
                        ),
                        p(
                            "analysis-output/archived/app81_main_density/"
                            f"app81_main_density_resized_multiscale_v1/runs/{density}/"
                            f"{date_key}/{image_stem}_mask_16bit.png"
                        ),
                    ),
                    Panel(
                        "image_generation",
                        "Image-generation mask",
                        grsai_root / "generated_overlay.png",
                        grsai_root / "generated_instance_mask_flat.png",
                    ),
                    Panel(
                        "final_stitched_hybrid",
                        "Final stitched hybrid",
                        final_root / "overlay.png",
                        final_root / "instance_labels_16bit.png",
                        reference=True,
                    ),
                ),
            )
        )
    return tuple(rows)


FIGURES = (
    FigureSpec(
        dataset="App80",
        key="app80_method_comparison_v2_no_text",
        columns=("raw", "prompted watershed", "CPSAM", "final multiscale"),
        rows=app80_rows(),
    ),
    FigureSpec(
        dataset="App65",
        key="app65_method_comparison_v2_no_text",
        columns=("raw", "old multiscale", "threshold-hinted Cellpose", "final direct brightfield"),
        rows=app65_rows(),
    ),
    FigureSpec(
        dataset="App81",
        key="app81_method_comparison_v2_no_text",
        columns=(
            "raw",
            "threshold-hinted Cellpose",
            "resized multiscale Cellpose",
            "image-generation mask",
            "final stitched hybrid",
        ),
        rows=app81_rows(),
    ),
)


def _scale_to_uint8(array: np.ndarray) -> np.ndarray:
    if array.dtype == np.uint8:
        return array
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [0.5, 99.5])
    if hi <= lo:
        lo, hi = float(finite.min()), float(finite.max())
    if hi <= lo:
        return np.zeros(array.shape, dtype=np.uint8)
    clipped = np.clip(array.astype(np.float32), lo, hi)
    return ((clipped - lo) / (hi - lo) * 255).astype(np.uint8)


def load_display_image(path: Path, *, raw: bool = False) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        image.seek(0)
        array = np.asarray(image)
    if array.ndim == 2:
        array_u8 = _scale_to_uint8(array)
        rgb = np.stack([array_u8, array_u8, array_u8], axis=-1)
    elif array.ndim == 3:
        rgb = _scale_to_uint8(array[..., :3])
    else:
        raise ValueError(f"Unsupported image shape for {path}: {array.shape}")
    image = Image.fromarray(rgb, mode="RGB")
    return ImageOps.autocontrast(image, cutoff=0.15) if raw else image


def fit_panel(image: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)


def render_figure(spec: FigureSpec) -> dict:
    if any(len(row.panels) != len(spec.columns) for row in spec.rows):
        raise ValueError(f"{spec.key}: row width does not match columns")

    width = spec.margin * 2 + len(spec.columns) * spec.cell_width + (len(spec.columns) - 1) * spec.gutter
    height = spec.margin * 2 + len(spec.rows) * spec.cell_height + (len(spec.rows) - 1) * spec.gutter
    canvas = Image.new("RGB", (width, height), (252, 252, 250))
    draw = ImageDraw.Draw(canvas)

    sources: list[dict[str, str]] = []
    for row_idx, row in enumerate(spec.rows):
        y = spec.margin + row_idx * (spec.cell_height + spec.gutter)
        for col_idx, panel in enumerate(row.panels):
            x = spec.margin + col_idx * (spec.cell_width + spec.gutter)
            image = fit_panel(load_display_image(panel.overlay_path, raw=panel.raw), spec.cell_width, spec.cell_height)
            canvas.paste(image, (x, y))
            draw.rectangle(
                [x, y, x + spec.cell_width - 1, y + spec.cell_height - 1],
                outline=(212, 216, 218),
                width=2,
            )
            sources.append(
                {
                    "dataset": spec.dataset,
                    "figure": spec.key,
                    "row": str(row_idx + 1),
                    "column": str(col_idx + 1),
                    "sample_id": row.sample_id,
                    "description": row.description,
                    "method": panel.method,
                    "label": panel.label,
                    "overlay_path": str(panel.overlay_path),
                    "mask_path": str(panel.mask_path) if panel.mask_path else "",
                    "reference": str(panel.reference),
                }
            )

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    png_path = FIGURE_DIR / f"{spec.key}.png"
    pdf_path = FIGURE_DIR / f"{spec.key}.pdf"
    canvas.save(png_path, optimize=True)
    canvas.save(pdf_path, "PDF", resolution=300)
    return {"dataset": spec.dataset, "key": spec.key, "png": str(png_path), "pdf": str(pdf_path), "sources": sources}


def labels_from_mask(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        image.seek(0)
        array = np.asarray(image)

    if array.ndim == 2:
        labels = array.astype(np.int32)
        if labels.max(initial=0) <= 1:
            labels = connected_component_labels(labels > 0)
        return labels

    rgb = array[..., :3].astype(np.uint8)
    flat = rgb.reshape(-1, 3)
    colors, inverse = np.unique(flat, axis=0, return_inverse=True)
    labels = np.zeros(flat.shape[0], dtype=np.int32)
    next_label = 1
    for color_index, color in enumerate(colors):
        # Background in generated masks is black. Also ignore near-white canvas.
        if int(color.max()) < 16:
            continue
        if int(color.min()) > 245:
            continue
        labels[inverse == color_index] = next_label
        next_label += 1
    labels = labels.reshape(rgb.shape[:2])
    if next_label <= 2:
        labels = connected_component_labels(labels > 0)
    return labels.astype(np.int32)


def connected_component_labels(binary: np.ndarray) -> np.ndarray:
    binary_u8 = binary.astype(np.uint8)
    try:
        import cv2  # type: ignore

        _, labels = cv2.connectedComponents(binary_u8, connectivity=8)
        return labels.astype(np.int32)
    except Exception:
        from scipy import ndimage  # type: ignore

        labels, _ = ndimage.label(binary_u8, structure=np.ones((3, 3), dtype=np.uint8))
        return labels.astype(np.int32)


def resize_labels(labels: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    if labels.shape == target_shape:
        return labels
    image = Image.fromarray(labels.astype(np.uint16))
    resized = image.resize((target_shape[1], target_shape[0]), Image.Resampling.NEAREST)
    return np.asarray(resized).astype(np.int32)


def label_stats(labels: np.ndarray) -> dict[str, float]:
    binary = labels > 0
    image_area = int(binary.size)
    mask_area = int(binary.sum())
    positive = labels[labels > 0]
    unique, counts = np.unique(positive, return_counts=True) if positive.size else (np.array([]), np.array([]))

    component_labels = connected_component_labels(binary)
    component_values, component_counts = (
        np.unique(component_labels[component_labels > 0], return_counts=True)
        if mask_area
        else (np.array([]), np.array([]))
    )
    small_threshold = max(64, int(image_area * 0.0005))
    small_area = int(component_counts[component_counts < small_threshold].sum()) if component_counts.size else 0

    edge_area = 0
    if component_values.size:
        edge_ids = set(np.unique(component_labels[0, :]).tolist())
        edge_ids.update(np.unique(component_labels[-1, :]).tolist())
        edge_ids.update(np.unique(component_labels[:, 0]).tolist())
        edge_ids.update(np.unique(component_labels[:, -1]).tolist())
        edge_ids.discard(0)
        if edge_ids:
            edge_area = int(sum(component_counts[component_values == edge_id][0] for edge_id in edge_ids))

    largest = int(counts.max()) if counts.size else 0
    return {
        "instance_count": float(len(unique)),
        "mask_area_px": float(mask_area),
        "mask_fraction": float(mask_area / image_area) if image_area else 0.0,
        "median_instance_area_px": float(median(counts.tolist())) if counts.size else 0.0,
        "largest_object_fraction": float(largest / mask_area) if mask_area else 0.0,
        "small_fragment_area_fraction": float(small_area / mask_area) if mask_area else 0.0,
        "edge_touch_area_fraction": float(edge_area / mask_area) if mask_area else 0.0,
    }


def dice(binary_a: np.ndarray, binary_b: np.ndarray) -> float:
    area_a = int(binary_a.sum())
    area_b = int(binary_b.sum())
    if area_a + area_b == 0:
        return 1.0
    inter = int(np.logical_and(binary_a, binary_b).sum())
    return 2.0 * inter / (area_a + area_b)


def benchmark_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for spec in FIGURES:
        for row in spec.rows:
            references = [panel for panel in row.panels if panel.reference and panel.mask_path]
            if len(references) != 1:
                raise ValueError(f"{row.sample_id}: expected exactly one reference mask")
            ref_panel = references[0]
            ref_labels = labels_from_mask(ref_panel.mask_path)  # type: ignore[arg-type]
            ref_shape = ref_labels.shape
            ref_stats = label_stats(ref_labels)
            ref_binary = ref_labels > 0

            for panel in row.panels:
                if panel.mask_path is None:
                    continue
                labels = resize_labels(labels_from_mask(panel.mask_path), ref_shape)
                stats = label_stats(labels)
                binary = labels > 0
                ref_area = max(ref_stats["mask_area_px"], 1.0)
                rows.append(
                    {
                        "dataset": spec.dataset,
                        "sample_id": row.sample_id,
                        "sample_description": row.description,
                        "method": panel.method,
                        "method_label": panel.label,
                        "is_reference": panel.reference,
                        "dice_to_final": dice(binary, ref_binary),
                        "area_ratio_to_final": stats["mask_area_px"] / ref_area,
                        "instance_count": int(stats["instance_count"]),
                        "final_instance_count": int(ref_stats["instance_count"]),
                        "instance_count_delta_vs_final": int(stats["instance_count"] - ref_stats["instance_count"]),
                        "mask_fraction": stats["mask_fraction"],
                        "median_instance_area_px": stats["median_instance_area_px"],
                        "largest_object_fraction": stats["largest_object_fraction"],
                        "small_fragment_area_fraction": stats["small_fragment_area_fraction"],
                        "edge_touch_area_fraction": stats["edge_touch_area_fraction"],
                        "mask_path": str(panel.mask_path),
                        "reference_mask_path": str(ref_panel.mask_path),
                    }
                )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize_benchmarks(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["dataset"]), str(row["method"]), str(row["method_label"]))].append(row)

    summary: list[dict[str, object]] = []
    for (dataset, method, method_label), items in sorted(grouped.items()):
        dice_values = [float(item["dice_to_final"]) for item in items]
        area_ratios = [float(item["area_ratio_to_final"]) for item in items]
        count_deltas = [float(item["instance_count_delta_vs_final"]) for item in items]
        small_frag = [float(item["small_fragment_area_fraction"]) for item in items]
        edge_touch = [float(item["edge_touch_area_fraction"]) for item in items]
        largest = [float(item["largest_object_fraction"]) for item in items]
        summary.append(
            {
                "dataset": dataset,
                "method": method,
                "method_label": method_label,
                "n_samples": len(items),
                "mean_dice_to_final": mean(dice_values),
                "median_area_ratio_to_final": median(area_ratios),
                "median_instance_count_delta_vs_final": median(count_deltas),
                "median_small_fragment_area_fraction": median(small_frag),
                "median_edge_touch_area_fraction": median(edge_touch),
                "median_largest_object_fraction": median(largest),
            }
        )
    order = {
        ("App80", "prompted_watershed"): 1,
        ("App80", "cpsam"): 2,
        ("App80", "final_multiscale_large_recovery"): 3,
        ("App65", "old_multiscale_large_recovery"): 4,
        ("App65", "threshold_hint_cellpose"): 5,
        ("App65", "final_direct_brightfield"): 6,
        ("App81", "threshold_hint_cellpose"): 7,
        ("App81", "resized_multiscale_cellpose"): 8,
        ("App81", "image_generation"): 9,
        ("App81", "final_stitched_hybrid"): 10,
    }
    summary.sort(key=lambda item: order.get((str(item["dataset"]), str(item["method"])), 999))
    return summary


def tex_escape(value: object) -> str:
    text = str(value)
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
    )


def write_summary_table(summary: list[dict[str, object]]) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\begin{table}[p]",
        r"\centering",
        r"\small",
        r"\caption{Proxy benchmarking against the final AAPS-selected mask. Dice and area ratio are computed after nearest-neighbour resizing to the final mask grid when required. These values are QC/proxy metrics, not manual ground-truth accuracy.}",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        r"Dataset & Method & n & Dice & Area ratio & $\Delta$ count & Small frag. & Edge touch \\",
        r"\midrule",
    ]
    for item in summary:
        lines.append(
            f"{tex_escape(item['dataset'])} & {tex_escape(item['method_label'])} & "
            f"{int(item['n_samples'])} & "
            f"{float(item['mean_dice_to_final']):.2f} & "
            f"{float(item['median_area_ratio_to_final']):.2f} & "
            f"{float(item['median_instance_count_delta_vs_final']):+.0f} & "
            f"{100 * float(item['median_small_fragment_area_fraction']):.1f}\\% & "
            f"{100 * float(item['median_edge_touch_area_fraction']):.1f}\\% \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    (TABLE_DIR / "benchmark_summary_table.tex").write_text("\n".join(lines), encoding="utf-8")


def score_row(item: dict[str, object]) -> list[float]:
    dice_score = float(item["mean_dice_to_final"])
    area_ratio = max(float(item["median_area_ratio_to_final"]), 1e-6)
    area_score = max(0.0, 1.0 - min(abs(math.log2(area_ratio)), 2.0) / 2.0)
    count_delta = abs(float(item["median_instance_count_delta_vs_final"]))
    n_samples = max(float(item["n_samples"]), 1.0)
    count_score = max(0.0, 1.0 - min(count_delta / (6.0 * n_samples), 1.0))
    fragment_score = max(0.0, 1.0 - float(item["median_small_fragment_area_fraction"]))
    edge_score = max(0.0, 1.0 - float(item["median_edge_touch_area_fraction"]))
    largest = float(item["median_largest_object_fraction"])
    merge_score = max(0.0, 1.0 - max(0.0, largest - 0.70) / 0.30)
    return [dice_score, area_score, count_score, fragment_score, edge_score, merge_score]


def render_benchmark_heatmap(summary: list[dict[str, object]]) -> None:
    cell = 62
    gutter = 10
    margin = 28
    rows = len(summary)
    cols = 6
    width = margin * 2 + cols * cell + (cols - 1) * gutter
    height = margin * 2 + rows * cell + (rows - 1) * gutter
    canvas = Image.new("RGB", (width, height), (252, 252, 250))
    draw = ImageDraw.Draw(canvas)

    low = np.array([183, 55, 63], dtype=np.float32)
    mid = np.array([245, 239, 205], dtype=np.float32)
    high = np.array([20, 125, 114], dtype=np.float32)
    for row_idx, item in enumerate(summary):
        y = margin + row_idx * (cell + gutter)
        for col_idx, value in enumerate(score_row(item)):
            x = margin + col_idx * (cell + gutter)
            value = max(0.0, min(1.0, value))
            if value < 0.5:
                t = value / 0.5
                color = low * (1 - t) + mid * t
            else:
                t = (value - 0.5) / 0.5
                color = mid * (1 - t) + high * t
            draw.rounded_rectangle(
                [x, y, x + cell, y + cell],
                radius=9,
                fill=tuple(int(c) for c in color),
                outline=(245, 245, 242),
                width=2,
            )
    png_path = FIGURE_DIR / "proxy_benchmark_heatmap_v2_no_text.png"
    pdf_path = FIGURE_DIR / "proxy_benchmark_heatmap_v2_no_text.pdf"
    canvas.save(png_path, optimize=True)
    canvas.save(pdf_path, "PDF", resolution=300)


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    rendered = [render_figure(spec) for spec in FIGURES]
    benchmark = benchmark_rows()
    summary = summarize_benchmarks(benchmark)
    write_csv(TABLE_DIR / "benchmark_per_sample.csv", benchmark)
    write_csv(TABLE_DIR / "benchmark_summary.csv", summary)
    write_summary_table(summary)
    render_benchmark_heatmap(summary)

    manifest = {
        "generated_by": str(Path(__file__).relative_to(PROJECT_ROOT)),
        "output_root": str(OUTPUT_ROOT),
        "figures": rendered,
        "benchmark_tables": {
            "per_sample_csv": str(TABLE_DIR / "benchmark_per_sample.csv"),
            "summary_csv": str(TABLE_DIR / "benchmark_summary.csv"),
            "summary_tex": str(TABLE_DIR / "benchmark_summary_table.tex"),
        },
    }
    (OUTPUT_ROOT / "segmentation_method_comparison_v2_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT_ROOT)
    for item in rendered:
        print(item["png"])
        print(item["pdf"])
    print(TABLE_DIR / "benchmark_summary.csv")


if __name__ == "__main__":
    main()
