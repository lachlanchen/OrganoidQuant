#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont


SVG_NS = {"svg": "http://www.w3.org/2000/svg", "xlink": "http://www.w3.org/1999/xlink"}
SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
TRANSLATE_SCALE_RE = re.compile(r"translate\(([-0-9.]+)\s+([-0-9.]+)\)\s*scale\(([-0-9.]+)\)")


@dataclass
class Tile:
    orig_id: str
    image_id: str
    x: float
    y: float
    scale: float
    width: int
    height: int
    mime_type: str
    data: bytes
    row_index: int | None = None
    col_index: int | None = None
    panel: str | None = None
    row_label: str | None = None
    col_label: str | None = None
    output_path: Path | None = None


def safe_name(text: str) -> str:
    text = text.strip().replace("μ", "u")
    text = SAFE_RE.sub("_", text)
    return text.strip("_") or "unnamed"


def cluster_positions(values: list[float], tolerance: float) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters:
            clusters.append([value])
            continue
        current = clusters[-1]
        center = sum(current) / len(current)
        if abs(value - center) <= tolerance:
            current.append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def nearest_index(value: float, centers: list[float]) -> int:
    return min(range(len(centers)), key=lambda idx: abs(value - centers[idx]))


def parse_data_uri(uri: str) -> tuple[str, bytes]:
    if not uri.startswith("data:"):
        raise ValueError("Only embedded data URIs are supported")
    header, payload = uri.split(",", 1)
    mime_type = header[5:].split(";", 1)[0]
    if ";base64" not in header:
        raise ValueError("Only base64 data URIs are supported")
    return mime_type, base64.b64decode(payload)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_tiles(svg_path: Path) -> list[Tile]:
    root = ET.parse(svg_path).getroot()
    tiles: list[Tile] = []
    for group in root.findall(".//svg:g", SVG_NS):
        group_id = group.attrib.get("id", "")
        image = group.find("svg:image", SVG_NS)
        if image is None:
            continue
        transform = image.attrib.get("transform", "")
        match = TRANSLATE_SCALE_RE.search(transform)
        if not match:
            continue
        x, y, scale = map(float, match.groups())
        href = image.attrib.get(f"{{{SVG_NS['xlink']}}}href") or image.attrib.get("href")
        if not href:
            continue
        mime_type, data = parse_data_uri(href)
        width = int(image.attrib.get("width", 0))
        height = int(image.attrib.get("height", 0))
        tiles.append(
            Tile(
                orig_id=group_id,
                image_id=image.attrib.get("id", ""),
                x=x,
                y=y,
                scale=scale,
                width=width,
                height=height,
                mime_type=mime_type,
                data=data,
            )
        )
    if not tiles:
        raise RuntimeError(f"No embedded image tiles found in {svg_path}")
    return tiles


def assign_grid_and_panels(tiles: list[Tile], config: dict[str, Any]) -> None:
    tolerance = float(config.get("position_tolerance", 3.0))
    y_centers = cluster_positions([tile.y for tile in tiles], tolerance)
    x_centers = cluster_positions([tile.x for tile in tiles], tolerance)
    for tile in tiles:
        tile.row_index = nearest_index(tile.y, y_centers)
        tile.col_index = nearest_index(tile.x, x_centers)

    panel_rows = config["panel_rows"]
    row_labels = config["row_labels"]
    panel_columns = config["panel_columns"]

    for tile in tiles:
        matched_panel = None
        local_row_index = None
        for panel_name, rows in panel_rows.items():
            if tile.row_index in rows:
                matched_panel = panel_name
                local_row_index = rows.index(tile.row_index)
                break
        if matched_panel is None or local_row_index is None:
            raise RuntimeError(f"Could not assign tile {tile.orig_id} at row index {tile.row_index} to a panel")
        local_columns = panel_columns[matched_panel]
        if tile.col_index >= len(local_columns):
            raise RuntimeError(
                f"Tile {tile.orig_id} column index {tile.col_index} exceeds configured columns for panel {matched_panel}"
            )
        tile.panel = matched_panel
        tile.row_label = row_labels[local_row_index]
        tile.col_label = local_columns[tile.col_index]


def write_tile_outputs(tiles: list[Tile], output_root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for tile in sorted(tiles, key=lambda item: (item.panel or "", item.row_index or -1, item.col_index or -1, item.orig_id)):
        assert tile.panel and tile.row_label and tile.col_label
        panel_dir = output_root / f"panel_{tile.panel}"
        row_dir = panel_dir / safe_name(tile.row_label)
        row_dir.mkdir(parents=True, exist_ok=True)
        ext = ".png" if tile.mime_type.endswith("png") else ".bin"
        filename = f"{safe_name(tile.col_label)}__orig_{safe_name(tile.orig_id)}{ext}"
        output_path = row_dir / filename
        output_path.write_bytes(tile.data)
        tile.output_path = output_path
        records.append(
            {
                "panel": tile.panel,
                "row_index": tile.row_index,
                "col_index": tile.col_index,
                "row_label": tile.row_label,
                "col_label": tile.col_label,
                "orig_id": tile.orig_id,
                "image_id": tile.image_id,
                "x": tile.x,
                "y": tile.y,
                "scale": tile.scale,
                "width": tile.width,
                "height": tile.height,
                "mime_type": tile.mime_type,
                "output_path": str(output_path.relative_to(output_root)),
            }
        )
    return records


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def build_contact_sheet(panel: str, tiles: list[Tile], output_root: Path, config: dict[str, Any]) -> None:
    panel_tiles = [tile for tile in tiles if tile.panel == panel]
    if not panel_tiles:
        return

    row_labels = config["row_labels"]
    col_labels = config["panel_columns"][panel]
    first_image = Image.open(BytesIO(panel_tiles[0].data))
    tile_width, tile_height = first_image.size

    margin_left = 220
    margin_top = 120
    gutter_x = 24
    gutter_y = 24
    canvas_width = margin_left + len(col_labels) * tile_width + max(0, len(col_labels) - 1) * gutter_x + 40
    canvas_height = margin_top + len(row_labels) * tile_height + max(0, len(row_labels) - 1) * gutter_y + 40

    sheet = Image.new("RGB", (canvas_width, canvas_height), color="white")
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(30)
    header_font = load_font(22)
    label_font = load_font(24)
    draw.text((24, 24), f"Panel {panel}", fill="black", font=title_font)

    for col_index, col_label in enumerate(col_labels):
        x = margin_left + col_index * (tile_width + gutter_x)
        bbox = draw.textbbox((0, 0), col_label, font=header_font)
        text_w = bbox[2] - bbox[0]
        draw.text((x + (tile_width - text_w) / 2, 70), col_label, fill="black", font=header_font)

    for row_index, row_label in enumerate(row_labels):
        y = margin_top + row_index * (tile_height + gutter_y)
        bbox = draw.textbbox((0, 0), row_label, font=label_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((margin_left - text_w - 24, y + (tile_height - text_h) / 2), row_label, fill="black", font=label_font)

    for tile in panel_tiles:
        assert tile.output_path is not None
        local_row_index = config["panel_rows"][panel].index(tile.row_index)
        x = margin_left + tile.col_index * (tile_width + gutter_x)
        y = margin_top + local_row_index * (tile_height + gutter_y)
        image = Image.open(tile.output_path).convert("RGB")
        sheet.paste(image, (x, y))
        draw.rectangle((x, y, x + tile_width - 1, y + tile_height - 1), outline="#666666", width=1)

    sheet.save(output_root / f"panel_{panel}_contact_sheet.png")


def write_manifest(output_root: Path, config: dict[str, Any], records: list[dict[str, Any]]) -> None:
    manifest = {
        "figure_name": config["figure_name"],
        "source_svg": config["source_svg"],
        "row_labels": config["row_labels"],
        "panel_rows": config["panel_rows"],
        "panel_columns": config["panel_columns"],
        "tile_count": len(records),
        "tiles": records,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    with (output_root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export embedded microscopy tiles from an Illustrator SVG into panel-aware folders")
    parser.add_argument("config", type=Path, help="Path to JSON config")
    parser.add_argument("--output-root", type=Path, default=None, help="Override output root")
    args = parser.parse_args()

    config = load_config(args.config)
    source_svg = Path(config["source_svg"])
    if not source_svg.exists():
        raise FileNotFoundError(source_svg)

    output_root = args.output_root or Path(config["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)

    tiles = parse_tiles(source_svg)
    assign_grid_and_panels(tiles, config)
    records = write_tile_outputs(tiles, output_root, config)
    build_contact_sheet("A", tiles, output_root, config)
    build_contact_sheet("B", tiles, output_root, config)
    write_manifest(output_root, config, records)
    print(json.dumps({"output_root": str(output_root), "tile_count": len(records)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
