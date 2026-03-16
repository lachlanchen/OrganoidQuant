#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
from PIL import Image, ImageDraw, ImageFont

VALID_RE = re.compile(r'(?:^|[^0-9])(?:10[xX](\d{2})|No 10x(\d{2}))\.tif$')
DATE_RE = re.compile(r'^(\d{2})-')


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description='Build metadata-blind App80 contact sheets.')
    p.add_argument('--app80-root', default=str(repo_root / 'DEO/App80 DEO'))
    p.add_argument('--output-root', default=str(repo_root / 'analysis-output/app80_panel_prompt_metrics'))
    p.add_argument('--max-samples-per-concentration', type=int, default=10)
    p.add_argument('--columns', type=int, default=4)
    p.add_argument('--tile-width', type=int, default=320)
    p.add_argument('--tile-height', type=int, default=320)
    return p.parse_args()


def extract_sample_number(path: Path) -> Optional[int]:
    m = VALID_RE.search(path.name)
    if not m:
        return None
    token = m.group(1) or m.group(2)
    return int(token)


def extract_day_of_month(date_dir_name: str) -> int:
    m = DATE_RE.match(date_dir_name)
    if not m:
        raise ValueError(f'Cannot parse day from {date_dir_name}')
    return int(m.group(1))


def list_valid_images(date_dir: Path) -> List[Path]:
    files: List[Tuple[int, str, Path]] = []
    for path in date_dir.iterdir():
        if not path.is_file():
            continue
        sample_no = extract_sample_number(path)
        if sample_no is None:
            continue
        files.append((sample_no, path.name.lower(), path))
    files.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in files]


def load_tile(src: Path, tile_w: int, tile_h: int) -> Image.Image:
    arr = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError(f'Failed to read TIFF: {src}')
    rgb = Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
    w, h = rgb.size
    crop_side = int(min(w, h) * 0.72)
    cx = w // 2
    cy = h // 2
    half = crop_side // 2
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(w, x0 + crop_side)
    y1 = min(h, y0 + crop_side)
    cropped = rgb.crop((x0, y0, x1, y1))
    return cropped.resize((tile_w, tile_h), Image.Resampling.LANCZOS)


def blank_tile(tile_w: int, tile_h: int) -> Image.Image:
    img = Image.new('RGB', (tile_w, tile_h), (24, 24, 24))
    draw = ImageDraw.Draw(img)
    for offset in range(-tile_h, tile_w, 28):
        draw.line((offset, 0, offset + tile_h, tile_h), fill=(60, 60, 60), width=2)
    font = ImageFont.load_default()
    draw.rectangle((90, tile_h // 2 - 20, tile_w - 90, tile_h // 2 + 20), fill=(0, 0, 0))
    draw.text((tile_w // 2 - 18, tile_h // 2 - 5), 'EMPTY', fill=(255, 255, 255), font=font)
    return img


def draw_label(tile: Image.Image, text: str) -> Image.Image:
    out = tile.copy()
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    box_w = 58
    box_h = 18
    draw.rectangle((6, 6, 6 + box_w, 6 + box_h), fill=(0, 0, 0))
    draw.text((11, 9), text, fill=(255, 255, 255), font=font)
    return out


def build_panel(slots: List[Dict[str, Any]], rows: int, cols: int, tile_w: int, tile_h: int) -> Image.Image:
    panel = Image.new('RGB', (cols * tile_w, rows * tile_h), (30, 30, 30))
    for slot in slots:
        row = slot['row']
        col = slot['col']
        tile = slot['tile_image']
        panel.paste(tile, (col * tile_w, row * tile_h))
    return panel


def main() -> int:
    args = parse_args()
    app80_root = Path(args.app80_root).resolve()
    output_root = Path(args.output_root).resolve()
    contact_root = output_root / 'contact_sheets'
    tile_root = output_root / 'panel_tiles'
    output_root.mkdir(parents=True, exist_ok=True)
    contact_root.mkdir(parents=True, exist_ok=True)
    tile_root.mkdir(parents=True, exist_ok=True)

    concentrations = [p for p in sorted(app80_root.iterdir(), key=lambda p: p.name) if p.is_dir()]
    manifest: Dict[str, Any] = {
        'app80_root': str(app80_root),
        'max_samples_per_concentration': args.max_samples_per_concentration,
        'columns': args.columns,
        'tile_width': args.tile_width,
        'tile_height': args.tile_height,
        'panels': [],
    }

    for conc_dir in concentrations:
        date_dirs = [p for p in sorted(conc_dir.iterdir(), key=lambda p: p.name) if p.is_dir()]
        day0 = min(extract_day_of_month(p.name) for p in date_dirs)
        date_entries: List[Dict[str, Any]] = []
        for date_dir in date_dirs:
            valid_images = list_valid_images(date_dir)
            if not valid_images:
                continue
            dom = extract_day_of_month(date_dir.name)
            date_entries.append(
                {
                    'date_dir': date_dir,
                    'date_name': date_dir.name,
                    'day_of_month': dom,
                    'relative_day': dom - day0,
                    'day_label': f'Day{dom - day0}',
                    'valid_images': valid_images,
                }
            )
        if not date_entries:
            continue

        common_n = min(args.max_samples_per_concentration, min(len(x['valid_images']) for x in date_entries))
        rows = math.ceil(len(date_entries) / args.columns)
        cols = args.columns

        for sample_rank in range(common_n):
            slots: List[Dict[str, Any]] = []
            sample_dir = tile_root / conc_dir.name / f'sample_{sample_rank:02d}'
            sample_dir.mkdir(parents=True, exist_ok=True)

            for slot_index in range(rows * cols):
                row = slot_index // cols
                col = slot_index % cols
                slot_id = f'slot_{slot_index + 1:02d}'
                if slot_index < len(date_entries):
                    entry = date_entries[slot_index]
                    src_tif = entry['valid_images'][sample_rank]
                    tile = draw_label(load_tile(src_tif, args.tile_width, args.tile_height), slot_id.upper())
                    tile_png = sample_dir / f'{slot_id}.png'
                    tile.save(tile_png)
                    slots.append(
                        {
                            'slot_id': slot_id,
                            'row': row,
                            'col': col,
                            'empty': False,
                            'date_name': entry['date_name'],
                            'day_label': entry['day_label'],
                            'relative_day': entry['relative_day'],
                            'source_tif': str(src_tif),
                            'tile_png': str(tile_png),
                            'tile_image': tile,
                        }
                    )
                else:
                    tile = draw_label(blank_tile(args.tile_width, args.tile_height), slot_id.upper())
                    tile_png = sample_dir / f'{slot_id}.png'
                    tile.save(tile_png)
                    slots.append(
                        {
                            'slot_id': slot_id,
                            'row': row,
                            'col': col,
                            'empty': True,
                            'date_name': None,
                            'day_label': None,
                            'relative_day': None,
                            'source_tif': None,
                            'tile_png': str(tile_png),
                            'tile_image': tile,
                        }
                    )

            panel_image = build_panel(slots, rows, cols, args.tile_width, args.tile_height)
            panel_dir = contact_root / conc_dir.name
            panel_dir.mkdir(parents=True, exist_ok=True)
            panel_png = panel_dir / f'sample_{sample_rank:02d}.png'
            panel_image.save(panel_png)

            for slot in slots:
                slot.pop('tile_image', None)

            manifest['panels'].append(
                {
                    'concentration': conc_dir.name,
                    'sample_rank': sample_rank,
                    'rows': rows,
                    'cols': cols,
                    'panel_png': str(panel_png),
                    'slots': slots,
                }
            )

    manifest_path = output_root / 'contact_sheet_manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'manifest_path': str(manifest_path), 'panel_count': len(manifest['panels'])}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
