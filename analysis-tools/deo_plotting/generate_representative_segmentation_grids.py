#!/usr/bin/env python3
"""Create representative segmentation-overlay contact sheets for DEO datasets.

The input for each experiment is the finalized per-image database produced by the
segmentation/quantification pipeline. The output is one fixed-size grid per
experiment plus a CSV manifest of every panel used in the grid.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP81_FINAL_SINGLE_EXPORT_ROOT = (
    PROJECT_ROOT
    / "analysis-output/archived/app81_density_stitched/"
    "app81_density_stitched_cellpose_v5_final_single_exports_v2"
)


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    display_name: str
    root: Path
    group_col: str
    group_order: tuple[str, ...]
    group_labels: dict[str, str]
    output_prefix: str


DATASETS: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        key="app80",
        display_name="App80 Y-27632",
        root=PROJECT_ROOT / "analysis-output/app80_all_concentrations_multiscale_large_recovery",
        group_col="concentration",
        group_order=("No", "10uM", "20uM", "50uM", "100uM"),
        group_labels={
            "No": "Control",
            "10uM": "10 uM",
            "20uM": "20 uM",
            "50uM": "50 uM",
            "100uM": "100 uM",
        },
        output_prefix="app80_y27632",
    ),
    DatasetConfig(
        key="app65",
        display_name="App65 Alginate",
        root=PROJECT_ROOT / "analysis-output/app65_alginate_v3_direct_brightfield",
        group_col="condition",
        group_order=("No", "0.02% Alginate", "0.05% Alginate"),
        group_labels={
            "No": "Control",
            "0.02% Alginate": "0.02%",
            "0.05% Alginate": "0.05%",
        },
        output_prefix="app65_alginate",
    ),
    DatasetConfig(
        key="app81",
        display_name="App81 Density",
        root=PROJECT_ROOT / "analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1",
        group_col="condition",
        group_order=("low", "middle", "high"),
        group_labels={
            "low": "Low density",
            "middle": "Middle density",
            "high": "High density",
        },
        output_prefix="app81_density",
    ),
)


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def absolute_path(path_value: str) -> Path:
    path = Path(str(path_value))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def build_app81_final_overlay_index() -> dict[str, str]:
    """Map App81 source TIFFs to final stitched single-image overlays."""

    index: dict[str, str] = {}
    if not APP81_FINAL_SINGLE_EXPORT_ROOT.exists():
        return index

    metadata_files = sorted(APP81_FINAL_SINGLE_EXPORT_ROOT.glob("*/*/from_*/panel_export_metadata.json"))
    for metadata_path in metadata_files:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        source = metadata.get("selected_source")
        overlay_path = metadata_path.parent / "overlay.png"
        if source and overlay_path.exists():
            index.setdefault(str(source), str(overlay_path))

    return index


def resolve_overlay_path(row: pd.Series, config: DatasetConfig, app81_overlay_index: dict[str, str]) -> str:
    overlay_path = absolute_path(row["overlay_path"])
    if overlay_path.exists():
        return str(overlay_path)

    if config.key != "app81":
        return str(overlay_path)

    source_tif = str(row.get("source_tif", ""))
    if source_tif in app81_overlay_index:
        return app81_overlay_index[source_tif]

    # Final App81 exports were created from stitched panels and archived outside
    # the active metrics folder. Use date/image-name lookup as a secondary guard.
    image_stem = Path(str(row["image_name"])).stem
    date_key = str(row["date_key"])
    candidates = sorted((APP81_FINAL_SINGLE_EXPORT_ROOT / date_key / image_stem).glob("from_*/overlay.png"))
    if candidates:
        return str(candidates[0])

    return str(overlay_path)


def load_dataset_database(config: DatasetConfig) -> pd.DataFrame:
    db_path = config.root / "database/source_image_database.csv"
    if not db_path.exists():
        raise FileNotFoundError(f"Missing database: {db_path}")

    df = pd.read_csv(db_path)
    required = {
        "image_name",
        "date_key",
        "date_label",
        "relative_day",
        "overlay_path",
        config.group_col,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{db_path} is missing columns: {missing}")

    df = df.copy()
    app81_overlay_index = build_app81_final_overlay_index() if config.key == "app81" else {}
    df["overlay_abs_path"] = df.apply(
        lambda row: resolve_overlay_path(row, config, app81_overlay_index),
        axis=1,
    )
    df["overlay_exists"] = df["overlay_abs_path"].map(lambda value: Path(value).exists())
    df = df[df["overlay_exists"]].copy()

    if "count" in df.columns:
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0)
    else:
        df["count"] = 0

    for col in ("total_area_px", "average_area_px", "average_perimeter_px"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    group_rank = {name: idx for idx, name in enumerate(config.group_order)}
    df = df[df[config.group_col].isin(group_rank)].copy()
    df["group_rank"] = df[config.group_col].map(group_rank).astype(int)
    df["relative_day"] = pd.to_numeric(df["relative_day"], errors="coerce").fillna(0).astype(int)
    df["image_name"] = df["image_name"].astype(str)
    df["date_label"] = df["date_label"].astype(str)
    df["replicate_index"] = (
        df.sort_values(["group_rank", "relative_day", "date_key", "image_name"])
        .groupby([config.group_col, "date_key"])
        .cumcount()
        + 1
    )

    return df.sort_values(["group_rank", "relative_day", "date_key", "replicate_index", "image_name"])


def row_priority_score(group_day: pd.DataFrame) -> pd.Series:
    metric = None
    for candidate in ("total_area_px", "average_area_px", "count"):
        if candidate in group_day.columns and group_day[candidate].notna().any():
            metric = pd.to_numeric(group_day[candidate], errors="coerce")
            break

    if metric is None:
        return pd.Series(0.0, index=group_day.index)

    median = metric.median()
    if pd.isna(median):
        return pd.Series(0.0, index=group_day.index)
    return (metric - median).abs().fillna(metric.max() if not metric.empty else 0)


def select_representative_rows(
    df: pd.DataFrame,
    config: DatasetConfig,
    max_panels: int,
) -> pd.DataFrame:
    """Balanced group/date selection, adding more replicates only after coverage."""

    buckets: list[pd.DataFrame] = []

    for _, group_day in df.groupby([config.group_col, "relative_day", "date_key"], sort=False):
        preferred = group_day[group_day["count"] > 0].copy()
        if preferred.empty:
            preferred = group_day.copy()
        preferred = preferred.copy()
        preferred["representative_score"] = row_priority_score(preferred)
        preferred = preferred.sort_values(
            ["representative_score", "replicate_index", "image_name"],
            ascending=[True, True, True],
        )
        buckets.append(preferred)

    selected_indices: list[int] = []
    max_bucket_len = max((len(bucket) for bucket in buckets), default=0)

    for replicate_round in range(max_bucket_len):
        for bucket in buckets:
            if replicate_round < len(bucket):
                selected_indices.append(int(bucket.index[replicate_round]))
                if len(selected_indices) >= max_panels:
                    break
        if len(selected_indices) >= max_panels:
            break

    selected = df.loc[selected_indices].copy()
    selected["grid_panel_index"] = range(1, len(selected) + 1)
    selected["grid_row"] = (selected["grid_panel_index"] - 1) // 9 + 1
    selected["grid_col"] = (selected["grid_panel_index"] - 1) % 9 + 1
    selected["display_group"] = selected[config.group_col].map(config.group_labels).fillna(
        selected[config.group_col].astype(str)
    )
    selected["display_replicate"] = selected.apply(
        lambda row: infer_replicate_label(str(row["image_name"]), int(row["replicate_index"])),
        axis=1,
    )
    return selected


def infer_replicate_label(image_name: str, fallback_index: int) -> str:
    """Use the microscope image suffix when present, otherwise fall back to rank."""

    stem = Path(image_name).stem.strip()
    trailing_digits = re.search(r"(\d+)\s*$", stem)
    if trailing_digits:
        return f"R{int(trailing_digits.group(1)):02d}"
    return f"R{fallback_index:02d}"


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text

    ellipsis = "..."
    trimmed = text
    while trimmed and draw.textlength(trimmed + ellipsis, font=font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def make_tile(
    row: pd.Series,
    tile_size: int,
    label_height: int,
    label_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> Image.Image:
    panel = Image.new("RGB", (tile_size, tile_size + label_height), "white")

    with Image.open(row["overlay_abs_path"]) as image:
        image = image.convert("RGB")
        image = ImageOps.contain(image, (tile_size, tile_size), method=Image.Resampling.LANCZOS)

    x = (tile_size - image.width) // 2
    y = (tile_size - image.height) // 2
    panel.paste(image, (x, y))

    draw = ImageDraw.Draw(panel)
    label_y = tile_size
    draw.rectangle((0, label_y, tile_size, tile_size + label_height), fill=(250, 250, 247))
    draw.line((0, label_y, tile_size, label_y), fill=(25, 25, 25), width=1)

    line_1 = f"D{int(row['relative_day'])} | {row['date_label']}"
    line_2 = f"{row['display_group']} | {row['display_replicate']}"
    line_1 = fit_text(draw, line_1, label_font, tile_size - 12)
    line_2 = fit_text(draw, line_2, small_font, tile_size - 12)
    draw.text((6, label_y + 5), line_1, fill=(20, 20, 20), font=label_font)
    draw.text((6, label_y + 27), line_2, fill=(65, 65, 65), font=small_font)
    return panel


def make_grid(
    selected: pd.DataFrame,
    config: DatasetConfig,
    output_dir: Path,
    *,
    grid_rows: int,
    grid_cols: int,
    tile_size: int,
    label_height: int,
    gutter: int,
) -> tuple[Path, Path]:
    canvas_width = grid_cols * tile_size + (grid_cols + 1) * gutter
    tile_total_height = tile_size + label_height
    canvas_height = grid_rows * tile_total_height + (grid_rows + 1) * gutter

    canvas = Image.new("RGB", (canvas_width, canvas_height), (18, 18, 18))
    label_font = load_font(18, bold=True)
    small_font = load_font(16)

    for _, row in selected.iterrows():
        panel_index = int(row["grid_panel_index"]) - 1
        grid_row = panel_index // grid_cols
        grid_col = panel_index % grid_cols
        tile = make_tile(row, tile_size, label_height, label_font, small_font)
        x = gutter + grid_col * (tile_size + gutter)
        y = gutter + grid_row * (tile_total_height + gutter)
        canvas.paste(tile, (x, y))

    # Keep empty panels explicit when a dataset has fewer than 81 available overlays.
    for panel_index in range(len(selected), grid_rows * grid_cols):
        grid_row = panel_index // grid_cols
        grid_col = panel_index % grid_cols
        x = gutter + grid_col * (tile_size + gutter)
        y = gutter + grid_row * (tile_total_height + gutter)
        blank = Image.new("RGB", (tile_size, tile_total_height), (245, 245, 242))
        draw = ImageDraw.Draw(blank)
        draw.text(
            (tile_size // 2, tile_total_height // 2),
            "blank",
            fill=(145, 145, 145),
            font=small_font,
            anchor="mm",
        )
        canvas.paste(blank, (x, y))

    output_dir.mkdir(parents=True, exist_ok=True)
    grid_suffix = f"{grid_rows}x{grid_cols}"
    png_path = output_dir / f"{config.output_prefix}_representative_segmentation_overlay_grid_{grid_suffix}.png"
    pdf_path = output_dir / f"{config.output_prefix}_representative_segmentation_overlay_grid_{grid_suffix}.pdf"
    canvas.save(png_path)
    canvas.save(pdf_path, "PDF", resolution=300)
    return png_path, pdf_path


def write_selection_csv(selected: pd.DataFrame, config: DatasetConfig, output_dir: Path) -> Path:
    csv_path = output_dir / f"{config.output_prefix}_selected_panels.csv"
    columns = [
        "grid_panel_index",
        "grid_row",
        "grid_col",
        config.group_col,
        "display_group",
        "date_key",
        "date_label",
        "relative_day",
        "replicate_index",
        "display_replicate",
        "image_name",
        "count",
        "total_area_px",
        "average_area_px",
        "overlay_path",
        "overlay_abs_path",
        "source_tif",
    ]
    selected_columns = [col for col in columns if col in selected.columns]
    selected[selected_columns].to_csv(csv_path, index=False)
    return csv_path


def generate_all(
    output_root: Path,
    *,
    grid_rows: int,
    grid_cols: int,
    tile_size: int,
    label_height: int,
    gutter: int,
) -> dict[str, dict[str, str | int]]:
    manifest: dict[str, dict[str, str | int]] = {}
    max_panels = grid_rows * grid_cols

    for config in DATASETS:
        df = load_dataset_database(config)
        selected = select_representative_rows(df, config, max_panels=max_panels)
        dataset_output_dir = output_root / config.key
        png_path, pdf_path = make_grid(
            selected,
            config,
            dataset_output_dir,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            tile_size=tile_size,
            label_height=label_height,
            gutter=gutter,
        )
        csv_path = write_selection_csv(selected, config, dataset_output_dir)
        manifest[config.key] = {
            "display_name": config.display_name,
            "input_database": str(config.root / "database/source_image_database.csv"),
            "available_overlay_count": int(len(df)),
            "selected_panel_count": int(len(selected)),
            "grid_rows": grid_rows,
            "grid_cols": grid_cols,
            "png": str(png_path),
            "pdf": str(pdf_path),
            "selection_csv": str(csv_path),
        }

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "representative_segmentation_grids_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "analysis-output/representative_segmentation_overlay_grids_v1",
        help="Folder where the representative grid outputs will be written.",
    )
    parser.add_argument("--grid-rows", type=int, default=7)
    parser.add_argument("--grid-cols", type=int, default=9)
    parser.add_argument("--tile-size", type=int, default=300)
    parser.add_argument("--label-height", type=int, default=54)
    parser.add_argument("--gutter", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_all(
        args.output_root,
        grid_rows=args.grid_rows,
        grid_cols=args.grid_cols,
        tile_size=args.tile_size,
        label_height=args.label_height,
        gutter=args.gutter,
    )
    for key, info in manifest.items():
        print(
            f"{key}: selected {info['selected_panel_count']}/{info['available_overlay_count']} panels -> "
            f"{info['png']}"
        )


if __name__ == "__main__":
    main()
