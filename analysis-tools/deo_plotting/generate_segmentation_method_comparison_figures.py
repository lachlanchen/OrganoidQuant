#!/usr/bin/env python3
"""Generate no-text segmentation-method comparison figures for the AAPS paper.

The figures are intentionally text-free. Captions in the accompanying TeX file
define the row/column meaning so the raster/PDF assets can be edited or relabeled
in Illustrator without embedded text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEX_ROOT = PROJECT_ROOT / "publication/aaps-organoid"
FIGURE_DIR = TEX_ROOT / "figures"
SOURCE_MANIFEST = TEX_ROOT / "segmentation_method_comparison_sources.json"


@dataclass(frozen=True)
class Panel:
    method: str
    path: Path
    raw: bool = False


@dataclass(frozen=True)
class Row:
    sample_id: str
    description: str
    panels: tuple[Panel, ...]


@dataclass(frozen=True)
class FigureSpec:
    key: str
    caption_short: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    cell_width: int = 720
    cell_height: int = 512
    gutter: int = 18
    margin: int = 28


def p(relative: str) -> Path:
    return PROJECT_ROOT / relative


APP80 = FigureSpec(
    key="segmentation_method_comparison_app80_no_text",
    caption_short="App80 Y-27632 segmentation method comparison",
    columns=(
        "raw brightfield image",
        "early prompted watershed",
        "early CPSAM/SAM-style proposal",
        "final AAPS multiscale large-recovery segmentation",
    ),
    rows=(
        Row(
            sample_id="app80_10uM_2025-12-05_10x00",
            description="App80, 10 uM Y-27632, 5 Dec 2025, 10x00",
            panels=(
                Panel("raw", p("DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"), raw=True),
                Panel(
                    "prompted_watershed",
                    p(
                        "analysis-output/archived-outputs/"
                        "app80_10uM_first_replicate_prompted_watershed/"
                        "05-十二月-2025__10x00/watershed_overlay.png"
                    ),
                ),
                Panel(
                    "cpsam",
                    p(
                        "analysis-output/archived-outputs/"
                        "app80_10uM_first_replicate_cpsam/runs/"
                        "05-十二月-2025__10x00/cpsam_overlay.png"
                    ),
                ),
                Panel(
                    "final_multiscale_large_recovery",
                    p(
                        "analysis-output/app80_all_concentrations_multiscale_large_recovery/"
                        "runs/10uM/05-十二月-2025/05-十二月-2025_10x00_overlay.png"
                    ),
                ),
            ),
        ),
        Row(
            sample_id="app80_10uM_2025-12-10_10x00",
            description="App80, 10 uM Y-27632, 10 Dec 2025, 10x00",
            panels=(
                Panel("raw", p("DEO/App80 DEO/10uM/10-十二月-2025/10x00.tif"), raw=True),
                Panel(
                    "prompted_watershed",
                    p(
                        "analysis-output/archived-outputs/"
                        "app80_10uM_first_replicate_prompted_watershed/"
                        "10-十二月-2025__10x00/watershed_overlay.png"
                    ),
                ),
                Panel(
                    "cpsam",
                    p(
                        "analysis-output/archived-outputs/"
                        "app80_10uM_first_replicate_cpsam/runs/"
                        "10-十二月-2025__10x00/cpsam_overlay.png"
                    ),
                ),
                Panel(
                    "final_multiscale_large_recovery",
                    p(
                        "analysis-output/app80_all_concentrations_multiscale_large_recovery/"
                        "runs/10uM/10-十二月-2025/10-十二月-2025_10x00_overlay.png"
                    ),
                ),
            ),
        ),
        Row(
            sample_id="app80_10uM_2025-12-12_10x00",
            description="App80, 10 uM Y-27632, 12 Dec 2025, 10x00",
            panels=(
                Panel("raw", p("DEO/App80 DEO/10uM/12-十二月-2025/10x00.tif"), raw=True),
                Panel(
                    "prompted_watershed",
                    p(
                        "analysis-output/archived-outputs/"
                        "app80_10uM_first_replicate_prompted_watershed/"
                        "12-十二月-2025__10x00/watershed_overlay.png"
                    ),
                ),
                Panel(
                    "cpsam",
                    p(
                        "analysis-output/archived-outputs/"
                        "app80_10uM_first_replicate_cpsam/runs/"
                        "12-十二月-2025__10x00/cpsam_overlay.png"
                    ),
                ),
                Panel(
                    "final_multiscale_large_recovery",
                    p(
                        "analysis-output/app80_all_concentrations_multiscale_large_recovery/"
                        "runs/10uM/12-十二月-2025/12-十二月-2025_10x00_overlay.png"
                    ),
                ),
            ),
        ),
    ),
)


APP65 = FigureSpec(
    key="segmentation_method_comparison_app65_no_text",
    caption_short="App65 alginate segmentation method comparison",
    columns=(
        "raw brightfield image",
        "old multiscale Cellpose recovery",
        "threshold-hinted Cellpose test",
        "final AAPS direct-brightfield segmentation",
    ),
    rows=(
        Row(
            sample_id="app65_0p02_alginate_2025-11-29_10x00",
            description="App65, 0.02% alginate, 29 Nov 2025, 10x00",
            panels=(
                Panel(
                    "raw",
                    p("DEO/App65 DEO+Alginate/29-十一月-2025/0.02% Alginate 10x00.tif"),
                    raw=True,
                ),
                Panel(
                    "old_multiscale_large_recovery",
                    p(
                        "analysis-output/archived-outputs/"
                        "app65_alginate_multiscale_large_recovery/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x00_overlay.png"
                    ),
                ),
                Panel(
                    "threshold_hint_cellpose",
                    p(
                        "analysis-output/archived/test_app65_alginate/"
                        "test_app65_alginate_custom_cellpose/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x00_threshold_hint_cellpose/"
                        "step06_final/step52_final_overlay.png"
                    ),
                ),
                Panel(
                    "final_direct_brightfield",
                    p(
                        "analysis-output/app65_alginate_v3_direct_brightfield/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x00_overlay.png"
                    ),
                ),
            ),
        ),
        Row(
            sample_id="app65_0p02_alginate_2025-11-29_10x14",
            description="App65, 0.02% alginate, 29 Nov 2025, 10x14",
            panels=(
                Panel(
                    "raw",
                    p("DEO/App65 DEO+Alginate/29-十一月-2025/0.02% Alginate 10x14.tif"),
                    raw=True,
                ),
                Panel(
                    "old_multiscale_large_recovery",
                    p(
                        "analysis-output/archived-outputs/"
                        "app65_alginate_multiscale_large_recovery/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x14_overlay.png"
                    ),
                ),
                Panel(
                    "threshold_hint_cellpose",
                    p(
                        "analysis-output/archived/test_app65_alginate/"
                        "test_app65_alginate_custom_cellpose/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x14_threshold_hint_cellpose/"
                        "step06_final/step52_final_overlay.png"
                    ),
                ),
                Panel(
                    "final_direct_brightfield",
                    p(
                        "analysis-output/app65_alginate_v3_direct_brightfield/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x14_overlay.png"
                    ),
                ),
            ),
        ),
        Row(
            sample_id="app65_0p02_alginate_2025-11-29_10x15",
            description="App65, 0.02% alginate, 29 Nov 2025, 10x15",
            panels=(
                Panel(
                    "raw",
                    p("DEO/App65 DEO+Alginate/29-十一月-2025/0.02% Alginate 10x15.tif"),
                    raw=True,
                ),
                Panel(
                    "old_multiscale_large_recovery",
                    p(
                        "analysis-output/archived-outputs/"
                        "app65_alginate_multiscale_large_recovery/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x15_overlay.png"
                    ),
                ),
                Panel(
                    "threshold_hint_cellpose",
                    p(
                        "analysis-output/archived/test_app65_alginate/"
                        "test_app65_alginate_custom_cellpose/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x15_threshold_hint_cellpose/"
                        "step06_final/step52_final_overlay.png"
                    ),
                ),
                Panel(
                    "final_direct_brightfield",
                    p(
                        "analysis-output/app65_alginate_v3_direct_brightfield/runs/"
                        "0.02% Alginate/29-十一月-2025/"
                        "29-十一月-2025_0.02% Alginate 10x15_overlay.png"
                    ),
                ),
            ),
        ),
    ),
)


APP81 = FigureSpec(
    key="segmentation_method_comparison_app81_no_text",
    caption_short="App81 density segmentation method-routing comparison",
    columns=(
        "raw brightfield image",
        "threshold-hinted Cellpose",
        "resized multiscale Cellpose",
        "image-generation-assisted mask",
        "final stitched AAPS-selected hybrid",
    ),
    rows=(
        Row(
            sample_id="app81_low_2025-10-14_10x_low",
            description="App81, low density, 14 Oct 2025, 10X low",
            panels=(
                Panel(
                    "raw",
                    p(
                        "analysis-output/archived/test_app81/"
                        "test_app81_grsai_clean_fill_v10_low_final_check/source_pngs/"
                        "low/14-十月-2025_10X low_source.png"
                    ),
                    raw=True,
                ),
                Panel(
                    "threshold_hint_cellpose",
                    p(
                        "analysis-output/archived/app81_main_density/"
                        "app81_main_density_custom_threshold_hint/runs/low/"
                        "14-十月-2025/14-十月-2025_10X low_overlay.png"
                    ),
                ),
                Panel(
                    "resized_multiscale_cellpose",
                    p(
                        "analysis-output/archived/app81_main_density/"
                        "app81_main_density_resized_multiscale_v1/runs/low/"
                        "14-十月-2025/14-十月-2025_10X low_overlay.png"
                    ),
                ),
                Panel(
                    "nanobanana_image_generation",
                    p(
                        "analysis-output/archived/test_app81/"
                        "test_app81_grsai_clean_fill_v10_low_final_check/generated_masks/"
                        "low/14-十月-2025/14-十月-2025_10X low/generated_overlay.png"
                    ),
                ),
                Panel(
                    "final_stitched_hybrid",
                    p(
                        "analysis-output/archived/app81_density_stitched/"
                        "app81_density_stitched_cellpose_v5_final_single_exports_v2/"
                        "14-十月-2025/10X low/"
                        "from_low_batch_2_replicate_01_10x_stitched/overlay.png"
                    ),
                ),
            ),
        ),
        Row(
            sample_id="app81_low_2025-10-15_10x_low",
            description="App81, low density, 15 Oct 2025, 10x low",
            panels=(
                Panel(
                    "raw",
                    p(
                        "analysis-output/archived/test_app81/"
                        "test_app81_grsai_clean_fill_v10_low_final_check/source_pngs/"
                        "low/15-十月-2025_10x low_source.png"
                    ),
                    raw=True,
                ),
                Panel(
                    "threshold_hint_cellpose",
                    p(
                        "analysis-output/archived/app81_main_density/"
                        "app81_main_density_custom_threshold_hint/runs/low/"
                        "15-十月-2025/15-十月-2025_10x low_overlay.png"
                    ),
                ),
                Panel(
                    "resized_multiscale_cellpose",
                    p(
                        "analysis-output/archived/app81_main_density/"
                        "app81_main_density_resized_multiscale_v1/runs/low/"
                        "15-十月-2025/15-十月-2025_10x low_overlay.png"
                    ),
                ),
                Panel(
                    "nanobanana_image_generation",
                    p(
                        "analysis-output/archived/test_app81/"
                        "test_app81_grsai_clean_fill_v10_low_final_check/generated_masks/"
                        "low/15-十月-2025/15-十月-2025_10x low/generated_overlay.png"
                    ),
                ),
                Panel(
                    "final_stitched_hybrid",
                    p(
                        "analysis-output/archived/app81_density_stitched/"
                        "app81_density_stitched_cellpose_v5_final_single_exports_v2/"
                        "15-十月-2025/10x low/"
                        "from_low_batch_1_replicate_01_10x_stitched/overlay.png"
                    ),
                ),
            ),
        ),
        Row(
            sample_id="app81_low_2025-10-16_10x_low",
            description="App81, low density, 16 Oct 2025, 10x low",
            panels=(
                Panel(
                    "raw",
                    p(
                        "analysis-output/archived/test_app81/"
                        "test_app81_grsai_clean_fill_v10_low_final_check/source_pngs/"
                        "low/16-十月-2025_10x low_source.png"
                    ),
                    raw=True,
                ),
                Panel(
                    "threshold_hint_cellpose",
                    p(
                        "analysis-output/archived/app81_main_density/"
                        "app81_main_density_custom_threshold_hint/runs/low/"
                        "16-十月-2025/16-十月-2025_10x low_overlay.png"
                    ),
                ),
                Panel(
                    "resized_multiscale_cellpose",
                    p(
                        "analysis-output/archived/app81_main_density/"
                        "app81_main_density_resized_multiscale_v1/runs/low/"
                        "16-十月-2025/16-十月-2025_10x low_overlay.png"
                    ),
                ),
                Panel(
                    "nanobanana_image_generation",
                    p(
                        "analysis-output/archived/test_app81/"
                        "test_app81_grsai_clean_fill_v10_low_final_check/generated_masks/"
                        "low/16-十月-2025/16-十月-2025_10x low/generated_overlay.png"
                    ),
                ),
                Panel(
                    "final_stitched_hybrid",
                    p(
                        "analysis-output/archived/app81_density_stitched/"
                        "app81_density_stitched_cellpose_v5_final_single_exports_v2/"
                        "16-十月-2025/10x low/"
                        "from_low_batch_2_replicate_01_10x_stitched/overlay.png"
                    ),
                ),
            ),
        ),
    ),
)


FIGURES = (APP80, APP65, APP81)


def _scale_to_uint8(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array)
    if array.dtype == np.uint8:
        return array

    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)

    lo, hi = np.percentile(finite, [0.5, 99.5])
    if hi <= lo:
        hi = float(finite.max())
        lo = float(finite.min())
    if hi <= lo:
        return np.zeros(array.shape, dtype=np.uint8)

    clipped = np.clip(array.astype(np.float32), lo, hi)
    return ((clipped - lo) / (hi - lo) * 255).astype(np.uint8)


def load_image(path: Path, *, raw: bool) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(path)

    with Image.open(path) as image:
        image.seek(0)
        array = np.asarray(image)

    if array.ndim == 2:
        array_u8 = _scale_to_uint8(array)
        rgb = np.stack([array_u8] * 3, axis=-1)
    elif array.ndim == 3:
        if array.shape[2] >= 3:
            rgb = _scale_to_uint8(array[..., :3])
        else:
            array_u8 = _scale_to_uint8(array[..., 0])
            rgb = np.stack([array_u8] * 3, axis=-1)
    else:
        raise ValueError(f"Unsupported image shape for {path}: {array.shape}")

    result = Image.fromarray(rgb, mode="RGB")
    if raw:
        result = ImageOps.autocontrast(result, cutoff=0.15)
    return result


def fit_panel(image: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def render_figure(spec: FigureSpec) -> dict:
    if any(len(row.panels) != len(spec.columns) for row in spec.rows):
        raise ValueError(f"{spec.key}: every row must have {len(spec.columns)} panels")

    canvas_width = (
        spec.margin * 2
        + spec.cell_width * len(spec.columns)
        + spec.gutter * (len(spec.columns) - 1)
    )
    canvas_height = (
        spec.margin * 2
        + spec.cell_height * len(spec.rows)
        + spec.gutter * (len(spec.rows) - 1)
    )
    canvas = Image.new("RGB", (canvas_width, canvas_height), (252, 252, 250))
    draw = ImageDraw.Draw(canvas)

    used_sources: list[dict[str, str]] = []
    for row_idx, row in enumerate(spec.rows):
        y = spec.margin + row_idx * (spec.cell_height + spec.gutter)
        for col_idx, panel in enumerate(row.panels):
            x = spec.margin + col_idx * (spec.cell_width + spec.gutter)
            image = fit_panel(load_image(panel.path, raw=panel.raw), spec.cell_width, spec.cell_height)
            canvas.paste(image, (x, y))
            draw.rectangle(
                [x, y, x + spec.cell_width - 1, y + spec.cell_height - 1],
                outline=(215, 218, 220),
                width=2,
            )
            used_sources.append(
                {
                    "figure": spec.key,
                    "row": str(row_idx + 1),
                    "column": str(col_idx + 1),
                    "sample_id": row.sample_id,
                    "description": row.description,
                    "method": panel.method,
                    "path": str(panel.path),
                }
            )

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    png_path = FIGURE_DIR / f"{spec.key}.png"
    pdf_path = FIGURE_DIR / f"{spec.key}.pdf"
    canvas.save(png_path, optimize=True)
    canvas.save(pdf_path, "PDF", resolution=300.0)

    return {
        "key": spec.key,
        "caption_short": spec.caption_short,
        "png": str(png_path),
        "pdf": str(pdf_path),
        "columns": list(spec.columns),
        "rows": [
            {
                "sample_id": row.sample_id,
                "description": row.description,
            }
            for row in spec.rows
        ],
        "sources": used_sources,
    }


def main() -> None:
    rendered = [render_figure(spec) for spec in FIGURES]
    SOURCE_MANIFEST.write_text(
        json.dumps(
            {
                "generated_by": str(Path(__file__).relative_to(PROJECT_ROOT)),
                "figures": rendered,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for item in rendered:
        print(item["png"])
        print(item["pdf"])
    print(SOURCE_MANIFEST)


if __name__ == "__main__":
    main()
