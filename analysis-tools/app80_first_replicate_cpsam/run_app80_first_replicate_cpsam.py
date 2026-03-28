#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

os.environ.setdefault('TORCH_DISABLE_DYNAMO', '1')

DEFAULT_IMAGES = [
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif',
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/07-十二月-2025/10X00.tif',
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/08-十二月-2025/10x00.tif',
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/09-十二月-2025/10x00.tif',
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/10-十二月-2025/10x00.tif',
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/11-十二月-2025/10x00.tif',
    '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/12-十二月-2025/10x00.tif',
]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_output = repo_root / 'analysis-output/app80_10uM_first_replicate_cpsam'
    p = argparse.ArgumentParser(description='Run Cellpose-SAM on App80 10uM first replicates.')
    p.add_argument('images', nargs='*', default=DEFAULT_IMAGES)
    p.add_argument('--output-dir', default=str(default_output))
    p.add_argument('--device', default='cuda')
    p.add_argument('--resize-max-dim', type=int, default=1536)
    p.add_argument('--min-area-px', type=int, default=160)
    return p.parse_args()


def load_rgb(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if arr is None:
        with Image.open(path) as im:
            return np.array(im.convert('RGB').copy())
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def resize_if_needed(rgb: np.ndarray, max_dim: int) -> Tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    cur_max = max(h, w)
    if max_dim <= 0 or cur_max <= max_dim:
        return rgb, 1.0
    scale = max_dim / float(cur_max)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return cv2.resize(rgb, new_size, interpolation=cv2.INTER_AREA), scale


def to_gray_u8(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def mask_geometry(mask: np.ndarray) -> Dict[str, float]:
    area = float(mask.sum())
    if area <= 0:
        return {'area': 0.0, 'perimeter': 0.0, 'circularity': 0.0}
    mask_u8 = (mask.astype(np.uint8) * 255)
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = float(sum(cv2.arcLength(cnt, True) for cnt in contours))
    circularity = 0.0
    if perimeter > 0:
        circularity = float(4.0 * math.pi * area / (perimeter * perimeter))
    return {'area': area, 'perimeter': perimeter, 'circularity': circularity}


def stage_limits(stage: str) -> Dict[str, float]:
    if stage == 'cluster':
        return {'max_area_fraction': 0.18, 'dark_floor': 0.24, 'circularity_cut': 0.52}
    if stage == 'differentiated_colon_like':
        return {'max_area_fraction': 0.48, 'dark_floor': 0.18, 'circularity_cut': 0.60}
    return {'max_area_fraction': 0.28, 'dark_floor': 0.22, 'circularity_cut': 0.55}


def stage_params(stage: str) -> Dict[str, float]:
    if stage == 'cluster':
        return {'cellprob_threshold': -2.0, 'flow_threshold': 0.4, 'min_size': 30, 'max_size_fraction': 0.30}
    if stage == 'differentiated_colon_like':
        return {'cellprob_threshold': -1.5, 'flow_threshold': 0.4, 'min_size': 120, 'max_size_fraction': 0.65}
    return {'cellprob_threshold': -2.0, 'flow_threshold': 0.4, 'min_size': 50, 'max_size_fraction': 0.40}


def infer_stage(image_paths: List[Path]) -> Dict[Path, Dict[str, object]]:
    folders = sorted({p.parent.name for p in image_paths})
    rank_map = {name: i + 1 for i, name in enumerate(folders)}
    out = {}
    for p in image_paths:
        rank = rank_map[p.parent.name]
        if rank == 1:
            stage = 'cluster'
        elif rank == len(folders):
            stage = 'differentiated_colon_like'
        else:
            stage = 'cystic'
        out[p] = {'day_rank': rank, 'stage': stage}
    return out


def filter_instances(labels: np.ndarray, gray: np.ndarray, stage: str, min_area_px: int) -> Tuple[np.ndarray, List[Dict[str, object]]]:
    out = np.zeros_like(labels, dtype=np.int32)
    stats: List[Dict[str, object]] = []
    new_id = 0
    dark_thresh = np.percentile(gray, 35)
    lim = stage_limits(stage)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        mask = labels == lid
        area = int(mask.sum())
        if area < min_area_px:
            continue
        geom = mask_geometry(mask)
        area_fraction = area / float(labels.shape[0] * labels.shape[1])
        dark_fraction = float((gray[mask] <= dark_thresh).mean()) if area > 0 else 0.0
        droplet_like = (
            area_fraction > lim['max_area_fraction']
            and geom['circularity'] > lim['circularity_cut']
            and dark_fraction < lim['dark_floor']
        )
        if droplet_like:
            continue
        ys, xs = np.where(mask)
        new_id += 1
        out[mask] = new_id
        stats.append({
            'mask_id': new_id,
            'area_px': area,
            'center_x_px': round(float(xs.mean()), 2),
            'center_y_px': round(float(ys.mean()), 2),
            'bbox_x0': int(xs.min()),
            'bbox_y0': int(ys.min()),
            'bbox_x1': int(xs.max() + 1),
            'bbox_y1': int(ys.max() + 1),
            'perimeter_px': round(geom['perimeter'], 2),
            'circularity': round(geom['circularity'], 4),
            'dark_fraction': round(dark_fraction, 4),
            'area_fraction': round(area_fraction, 4),
            'droplet_like_rejected': False,
        })
    return out, stats


def render_instance_rgb(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    hsv = np.zeros((1, 1, 3), dtype=np.uint8)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        hue = int(((lid * 0.61803398875) % 1.0) * 179)
        hsv[0, 0] = (hue, 180, 240)
        color = tuple(int(c) for c in cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0])
        out[labels == lid] = color
    return out


def render_overlay(source_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    palette = render_instance_rgb(labels)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        mask = (labels == lid).astype(np.uint8)
        colors = palette[mask > 0]
        if colors.size == 0:
            continue
        color = tuple(int(c) for c in colors[0])
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def build_gallery(rows: List[Dict[str, object]], output_dir: Path) -> None:
    strips = []
    for row in rows:
        orig = Image.open(Path(row['source_png'])).convert('RGB').resize((320, 240))
        overlay = Image.open(Path(row['overlay_png'])).convert('RGB').resize((320, 240))
        inst = Image.open(Path(row['instance_png'])).convert('RGB').resize((320, 240))
        flow = Image.open(Path(row['flow_rgb_png'])).convert('RGB').resize((320, 240))
        canvas = Image.new('RGB', (1320, 280), 'white')
        draw = ImageDraw.Draw(canvas)
        canvas.paste(orig, (0, 36))
        canvas.paste(overlay, (335, 36))
        canvas.paste(inst, (670, 36))
        canvas.paste(flow, (1005, 36))
        draw.text((8, 8), f"{row['date_label']} | original", fill=(20,20,20))
        draw.text((343, 8), f"cpsam overlay ({row['filtered_mask_count']})", fill=(20,20,20))
        draw.text((678, 8), 'instance mask', fill=(20,20,20))
        draw.text((1013, 8), 'flow rgb', fill=(20,20,20))
        strips.append(canvas)
    total_h = sum(img.height for img in strips) + 16 * max(0, len(strips)-1)
    gallery = Image.new('RGB', (1320, total_h), 'white')
    y = 0
    for img in strips:
        gallery.paste(img, (0, y))
        y += img.height + 16
    gallery.save(output_dir / 'app80_10uM_first_replicate_cpsam_gallery.png')


def main() -> int:
    args = parse_args()
    image_paths = [Path(x).resolve() for x in args.images]
    output_dir = Path(args.output_dir).resolve()
    runs_dir = output_dir / 'runs'
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    meta_map = infer_stage(image_paths)

    import torch
    from cellpose import models

    gpu = args.device.startswith('cuda') and torch.cuda.is_available()
    model = models.CellposeModel(gpu=gpu, pretrained_model='cpsam')
    summary_rows: List[Dict[str, object]] = []

    for tif_path in image_paths:
        meta = meta_map[tif_path]
        stem = tif_path.parent.name.replace('/', '_') + '__' + tif_path.stem
        run_dir = runs_dir / stem
        run_dir.mkdir(parents=True, exist_ok=True)

        source_png = run_dir / f'{tif_path.stem}.png'
        if not source_png.exists():
            with Image.open(tif_path) as im:
                im.save(source_png, format='PNG')

        source_rgb = load_rgb(source_png)
        working_rgb, scale = resize_if_needed(source_rgb, args.resize_max_dim)
        gray = to_gray_u8(working_rgb)
        input_rgb = np.repeat(gray[..., None], 3, axis=2)
        params = stage_params(str(meta['stage']))
        masks, flows, styles = model.eval(
            input_rgb,
            batch_size=8,
            normalize=True,
            invert=False,
            diameter=None,
            flow_threshold=float(params['flow_threshold']),
            cellprob_threshold=float(params['cellprob_threshold']),
            min_size=int(params['min_size']),
            max_size_fraction=float(params['max_size_fraction']),
            resample=True,
            augment=False,
            tile_overlap=0.1,
            bsize=256,
            compute_masks=True,
        )
        masks = np.asarray(masks)
        if scale != 1.0:
            masks = cv2.resize(masks.astype(np.uint16), (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
        filtered_labels, stats = filter_instances(masks.astype(np.int32), to_gray_u8(source_rgb), str(meta['stage']), args.min_area_px)

        labels_png = run_dir / 'cpsam_labels_16bit.png'
        cv2.imwrite(str(labels_png), filtered_labels.astype(np.uint16))
        instance_rgb = render_instance_rgb(filtered_labels)
        instance_png = run_dir / 'cpsam_instance_rgb.png'
        Image.fromarray(instance_rgb).save(instance_png)
        overlay = render_overlay(source_rgb, filtered_labels)
        overlay_png = run_dir / 'cpsam_overlay.png'
        Image.fromarray(overlay).save(overlay_png)

        flow_rgb = np.asarray(flows[0]) if isinstance(flows, (list, tuple)) and len(flows) > 0 else np.zeros_like(working_rgb)
        if flow_rgb.ndim == 2:
            flow_rgb = np.repeat(flow_rgb[..., None], 3, axis=2)
        if flow_rgb.shape[:2] != working_rgb.shape[:2]:
            flow_rgb = cv2.resize(flow_rgb, (working_rgb.shape[1], working_rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
        if scale != 1.0:
            flow_rgb = cv2.resize(flow_rgb, (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
        flow_rgb_png = run_dir / 'cpsam_flow_rgb.png'
        Image.fromarray(flow_rgb.astype(np.uint8)).save(flow_rgb_png)

        stats_json = run_dir / 'cpsam_mask_stats.json'
        stats_json.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest = {
            'source_tif': str(tif_path),
            'date_label': tif_path.parent.name,
            'day_rank': int(meta['day_rank']),
            'stage': str(meta['stage']),
            'device': 'cuda' if gpu else 'cpu',
            'model': 'cpsam',
            'working_scale': scale,
            'filtered_mask_count': len(stats),
            'source_png': str(source_png),
            'overlay_png': str(overlay_png),
            'instance_png': str(instance_png),
            'labels_png': str(labels_png),
            'flow_rgb_png': str(flow_rgb_png),
            'mask_stats_json': str(stats_json),
        }
        (run_dir / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        summary_rows.append(manifest)
        print(json.dumps({'date': tif_path.parent.name, 'stage': meta['stage'], 'filtered_mask_count': len(stats)}, ensure_ascii=False), flush=True)

    summary_rows.sort(key=lambda r: int(r['day_rank']))
    with (output_dir / 'batch_manifest.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    (output_dir / 'batch_manifest.json').write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    build_gallery(summary_rows, output_dir)
    (output_dir / 'README.md').write_text(
        '# App80 10uM First Replicate Cellpose-SAM\n\n'
        f'- Images processed: {len(summary_rows)}\n'
        '- Output gallery: [app80_10uM_first_replicate_cpsam_gallery.png](app80_10uM_first_replicate_cpsam_gallery.png)\n',
        encoding='utf-8'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
