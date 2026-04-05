#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path

os.environ.setdefault('TORCHDYNAMO_DISABLE', '1')
os.environ.setdefault('TORCH_DISABLE_DYNAMO', '1')
os.environ.setdefault('PYTORCH_JIT', '0')
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

import cv2
import numpy as np
import torch  # noqa: F401
from cellpose import models

import run_multiscale_dateaware_cellpose as seg


STAGE_SIGNAL_CFG = {
    'early_cluster': {'enabled': True, 'combos': [(80, 11, 0.20), (82, 21, 0.22), (85, 21, 0.25)], 'min_area': 4000, 'max_frac_component': 0.32, 'max_frac_watershed': 0.22},
    'cystic_early': {'enabled': False, 'combos': [], 'min_area': 6000, 'max_frac_component': 0.18, 'max_frac_watershed': 0.16},
    'cystic_mid': {'enabled': False, 'combos': [], 'min_area': 7000, 'max_frac_component': 0.18, 'max_frac_watershed': 0.16},
    'fused_large': {'enabled': True, 'combos': [(80, 21, 0.18), (82, 21, 0.22), (85, 11, 0.20)], 'min_area': 12000, 'max_frac_component': 0.68, 'max_frac_watershed': 0.30},
    'differentiated_irregular': {'enabled': True, 'combos': [(78, 21, 0.18), (82, 21, 0.20), (84, 11, 0.20)], 'min_area': 10000, 'max_frac_component': 0.46, 'max_frac_watershed': 0.26},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--source-tif', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--date-key', default=None)
    p.add_argument('--gpu', action='store_true', default=True)
    return p.parse_args()


def infer_date_key(source_tif: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    parent = source_tif.parent.name
    if parent in seg.DATE_CONFIG:
        return parent
    raise RuntimeError(f'Cannot infer date key from {source_tif}')


def write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def norm_u8(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.dtype == np.uint8:
        return arr
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    out = (arr.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def save_gray(path: Path, arr: np.ndarray) -> None:
    cv2.imwrite(str(path), norm_u8(arr))


def save_binary(path: Path, mask: np.ndarray) -> None:
    img = (mask.astype(np.uint8) * 255) if mask.dtype != np.uint8 else mask
    cv2.imwrite(str(path), img)


def save_labels_16bit(path: Path, labels: np.ndarray) -> None:
    cv2.imwrite(str(path), labels.astype(np.uint16))


def labels_to_rgb(labels: np.ndarray) -> np.ndarray:
    rgb = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    for lab in [int(v) for v in np.unique(labels) if int(v) > 0]:
        rng = np.random.default_rng(lab * 1237 + 17)
        rgb[labels == lab] = rng.integers(40, 256, size=3, dtype=np.uint8)
    return rgb


def overlay_labels(rgb: np.ndarray, labels: np.ndarray, colors: np.ndarray | None = None) -> np.ndarray:
    if colors is None:
        colors = labels_to_rgb(labels)
    overlay = cv2.addWeighted(rgb, 0.72, colors, 0.55, 0)
    edges = cv2.Canny((labels > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (255, 0, 0)
    return overlay


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def compute_hybrid_signal_detailed(gray: np.ndarray) -> dict[str, np.ndarray | int]:
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (3, 3), 0)
    bg = cv2.GaussianBlur(clahe, (31, 31), 0)
    residual = cv2.subtract(bg, blur)
    inv = 255 - blur
    residual_norm = cv2.normalize(residual, None, 0, 255, cv2.NORM_MINMAX)
    inv_norm = cv2.normalize(inv, None, 0, 255, cv2.NORM_MINMAX)
    signal = cv2.addWeighted(inv_norm, 0.45, residual_norm, 0.55, 0)

    gx = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    grad_norm = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    otsu_val, support_raw = cv2.threshold(signal, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    perc = int(np.percentile(signal, 58))
    thr = max(int(otsu_val), perc)
    support_raw = (signal >= thr).astype(np.uint8) * 255
    k1 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    support_open = cv2.morphologyEx(support_raw, cv2.MORPH_OPEN, k1)
    support_final = cv2.morphologyEx(support_open, cv2.MORPH_CLOSE, k2)
    return {
        'clahe': clahe,
        'foreground_blur': blur,
        'background_blur': bg,
        'residual': residual,
        'inverted_foreground': inv,
        'residual_norm': residual_norm,
        'inv_norm': inv_norm,
        'signal': signal,
        'grad_norm': grad_norm,
        'support_raw': support_raw,
        'support_open': support_open,
        'support_final': support_final,
        'otsu_val': int(otsu_val),
        'perc58': int(perc),
        'support_threshold': int(thr),
    }


def trace_candidate(mask: np.ndarray, diameter: int, branch_rank: int, signal: np.ndarray, support: np.ndarray, grad_norm: np.ndarray, stage: str, source: str) -> tuple[seg.Candidate | None, dict]:
    raw_area, raw_perimeter, raw_circularity, raw_fill_ratio = seg.mask_stats(mask)
    info = {
        'source': source,
        'diameter_px': int(diameter),
        'branch_rank': int(branch_rank),
        'raw_area': int(raw_area),
        'raw_perimeter': float(raw_perimeter),
        'raw_circularity': float(raw_circularity),
        'raw_fill_ratio': float(raw_fill_ratio),
    }
    if raw_area <= 0:
        info['kept'] = False
        info['reject_reason'] = 'zero_area'
        return None, info

    min_area = max(1500, int(0.08 * math.pi * (diameter / 2.0) ** 2))
    if source != 'cellpose':
        min_area = max(5000, int(min_area * 0.6))
    info['min_area_threshold'] = int(min_area)
    if raw_area < min_area:
        info['kept'] = False
        info['reject_reason'] = 'below_min_area'
        return None, info

    refined = seg.refine_with_support(mask, support, diameter)
    area, perimeter, circularity, fill_ratio = seg.mask_stats(refined)
    h, w = refined.shape
    img_area = float(h * w)
    huge_frac = area / img_area

    soft_r = max(5, int(round(diameter * 0.05)))
    soft_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * soft_r + 1, 2 * soft_r + 1))
    soft_support = cv2.dilate(support, soft_kernel)
    support_ratio = float((soft_support[refined] > 0).mean()) if area else 0.0
    mean_signal = float(signal[refined].mean() / 255.0) if area else 0.0
    edge = cv2.morphologyEx((refined.astype(np.uint8) * 255), cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    edge_strength = float(grad_norm[edge].mean() / 255.0) if edge.any() else 0.0

    border_touch = bool(refined[0, :].any() or refined[-1, :].any() or refined[:, 0].any() or refined[:, -1].any())
    ys, xs = np.where(refined)
    bbox_w = int(xs.max() - xs.min() + 1) if area else 0
    bbox_h = int(ys.max() - ys.min() + 1) if area else 0
    bbox_cover = max(bbox_w / w if w else 0.0, bbox_h / h if h else 0.0)

    info.update({
        'refined_area': int(area),
        'refined_perimeter': float(perimeter),
        'circularity': float(circularity),
        'fill_ratio': float(fill_ratio),
        'support_ratio': float(support_ratio),
        'mean_signal': float(mean_signal),
        'edge_strength': float(edge_strength),
        'huge_fraction': float(huge_frac),
        'border_touch': bool(border_touch),
        'bbox_cover': float(bbox_cover),
    })

    reject_reason = None
    if source == 'cellpose':
        if huge_frac > 0.48 and support_ratio < 0.55 and mean_signal < 0.55:
            reject_reason = 'cellpose_huge_weak_support'
        elif huge_frac > 0.35 and fill_ratio < 0.16 and support_ratio < 0.65:
            reject_reason = 'cellpose_huge_sparse_weak'
    else:
        if huge_frac > 0.82 or bbox_cover > 0.985:
            reject_reason = 'signal_too_large'
        elif border_touch and huge_frac > 0.22:
            reject_reason = 'signal_border_touch_large'
        elif huge_frac > 0.60 and circularity > 0.88 and fill_ratio > 0.55:
            reject_reason = 'signal_huge_round_fill'

    stage_bonus = {
        'early_cluster': 0.12 if diameter <= 260 else 0.0,
        'cystic_early': 0.08 if 180 <= diameter <= 480 else 0.0,
        'cystic_mid': 0.08 if 200 <= diameter <= 560 else 0.0,
        'fused_large': 0.12 if diameter >= 320 else 0.0,
        'differentiated_irregular': 0.15 if diameter >= 280 else 0.0,
    }.get(stage, 0.0)
    if source == 'signal_component':
        stage_bonus += 0.08 if stage in {'fused_large', 'differentiated_irregular'} else 0.04
    elif source == 'signal_watershed':
        stage_bonus += 0.12 if stage in {'fused_large', 'differentiated_irregular'} else 0.06

    score = (
        1.85 * support_ratio
        + 0.85 * mean_signal
        + 0.65 * edge_strength
        + 0.25 * fill_ratio
        + stage_bonus
        + (0.08 if branch_rank == 1 else 0.0)
    )
    if circularity < 0.25 and stage in {'fused_large', 'differentiated_irregular'}:
        score += 0.06

    info['stage_bonus'] = float(stage_bonus)
    info['score'] = float(score)
    if reject_reason is not None:
        info['kept'] = False
        info['reject_reason'] = reject_reason
        return None, info

    cand = seg.Candidate(
        mask=refined,
        score=score,
        area=area,
        diameter=diameter,
        branch_rank=branch_rank,
        support_ratio=support_ratio,
        mean_signal=mean_signal,
        edge_strength=edge_strength,
        circularity=circularity,
        source=source,
    )
    info['kept'] = True
    info['reject_reason'] = ''
    return cand, info


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def crop_candidate_tile(rgb: np.ndarray, mask: np.ndarray, refined: np.ndarray | None, label_text: str) -> np.ndarray:
    ys, xs = np.where(mask | (refined if refined is not None else mask))
    if ys.size == 0:
        return np.full((220, 220, 3), 255, dtype=np.uint8)
    y0 = max(0, int(ys.min()) - 30)
    y1 = min(rgb.shape[0], int(ys.max()) + 31)
    x0 = max(0, int(xs.min()) - 30)
    x1 = min(rgb.shape[1], int(xs.max()) + 31)
    crop = rgb[y0:y1, x0:x1].copy()
    raw_edge = cv2.Canny((mask[y0:y1, x0:x1].astype(np.uint8) * 255), 50, 150) > 0
    crop[raw_edge] = (255, 80, 80)
    if refined is not None:
        ref_edge = cv2.Canny((refined[y0:y1, x0:x1].astype(np.uint8) * 255), 50, 150) > 0
        crop[ref_edge] = (80, 255, 80)
    scale = min(220 / crop.shape[0], 220 / crop.shape[1])
    resized = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((260, 240, 3), 255, dtype=np.uint8)
    yoff = 35 + (220 - resized.shape[0]) // 2
    xoff = (240 - resized.shape[1]) // 2
    canvas[yoff:yoff + resized.shape[0], xoff:xoff + resized.shape[1]] = resized
    for i, line in enumerate(label_text.split('\n')):
        cv2.putText(canvas, line[:34], (8, 18 + 14 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    return canvas


def save_contact_sheet(path: Path, tiles: list[np.ndarray], cols: int = 4, gap: int = 10) -> None:
    if not tiles:
        return
    h = max(tile.shape[0] for tile in tiles)
    w = max(tile.shape[1] for tile in tiles)
    rows = (len(tiles) + cols - 1) // cols
    canvas = np.full((rows * h + (rows - 1) * gap, cols * w + (cols - 1) * gap, 3), 255, dtype=np.uint8)
    for idx, tile in enumerate(tiles):
        r = idx // cols
        c = idx % cols
        y = r * (h + gap)
        x = c * (w + gap)
        canvas[y:y + tile.shape[0], x:x + tile.shape[1]] = tile
    save_rgb(path, canvas)


def save_manifest(path: Path, source_tif: Path, cfg: dict, out_dir: Path) -> None:
    write_json(path, {
        'source_tif': str(source_tif),
        'date_key': source_tif.parent.name,
        'stage': cfg['stage'],
        'diameters_px': cfg['diameters'],
        'output_dir': str(out_dir),
    })


def main() -> int:
    args = parse_args()
    source_tif = Path(args.source_tif).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    date_key = infer_date_key(source_tif, args.date_key)
    cfg = seg.DATE_CONFIG[date_key]

    step01 = out_dir / 'step01_input'
    step02 = out_dir / 'step02_hybrid_signal'
    step03 = out_dir / 'step03_support_mask'
    step04 = out_dir / 'step04_cellpose_branches'
    step05 = out_dir / 'step05_signal_recovery'
    step06 = out_dir / 'step06_merge'
    step07 = out_dir / 'step07_final'
    for p in (step01, step02, step03, step04, step05, step06, step07):
        p.mkdir(parents=True, exist_ok=True)

    save_manifest(out_dir / 'trace_manifest.json', source_tif, cfg, out_dir)

    rgb, gray = seg.load_rgb_gray(source_tif)
    save_rgb(step01 / 'step01_source_rgb.png', rgb)
    save_gray(step01 / 'step02_source_gray.png', gray)

    detailed = compute_hybrid_signal_detailed(gray)
    save_gray(step02 / 'step03_clahe.png', detailed['clahe'])
    save_gray(step02 / 'step04_foreground_blur.png', detailed['foreground_blur'])
    save_gray(step02 / 'step05_background_blur.png', detailed['background_blur'])
    save_gray(step02 / 'step06_residual.png', detailed['residual'])
    save_gray(step02 / 'step07_inverted_foreground.png', detailed['inverted_foreground'])
    save_gray(step02 / 'step08_residual_norm.png', detailed['residual_norm'])
    save_gray(step02 / 'step09_inverted_norm.png', detailed['inv_norm'])
    save_gray(step02 / 'step10_hybrid_signal.png', detailed['signal'])
    save_gray(step02 / 'step11_gradient_norm.png', detailed['grad_norm'])

    save_binary(step03 / 'step12_support_raw.png', detailed['support_raw'])
    save_binary(step03 / 'step13_support_after_open.png', detailed['support_open'])
    save_binary(step03 / 'step14_support_final.png', detailed['support_final'])
    write_json(step03 / 'support_thresholds.json', {
        'otsu_threshold': detailed['otsu_val'],
        'percentile_58_threshold': detailed['perc58'],
        'final_support_threshold': detailed['support_threshold'],
    })

    signal = detailed['signal']
    support = detailed['support_final']
    grad_norm = detailed['grad_norm']

    model = models.CellposeModel(gpu=args.gpu)
    all_candidates: list[seg.Candidate] = []
    all_candidate_info: list[dict] = []

    for branch_rank, diameter in enumerate(cfg['diameters']):
        branch_dir = step04 / f'branch_{branch_rank:02d}_d{diameter:04d}'
        branch_dir.mkdir(parents=True, exist_ok=True)
        masks, *_ = model.eval(gray, diameter=float(diameter), channels=[0, 0], normalize=True, do_3D=False)
        masks = masks.astype(np.uint16)
        save_labels_16bit(branch_dir / 'step20_raw_cellpose_mask_16bit.png', masks)
        raw_rgb = labels_to_rgb(masks)
        save_rgb(branch_dir / 'step21_raw_instance_rgb.png', raw_rgb)
        save_rgb(branch_dir / 'step22_raw_overlay.png', overlay_labels(rgb, masks, raw_rgb))

        branch_infos: list[dict] = []
        branch_tiles: list[np.ndarray] = []
        kept_masks = []
        kept_labels = np.zeros_like(masks, dtype=np.uint16)
        kept_idx = 0
        for label in range(1, int(masks.max()) + 1):
            raw_mask = masks == label
            cand, info = trace_candidate(raw_mask, diameter, branch_rank, signal, support, grad_norm, cfg['stage'], 'cellpose')
            info['raw_label'] = int(label)
            branch_infos.append(info)
            refined_mask = cand.mask if cand is not None else raw_mask
            title = f"label {label} | area {info['raw_area']}\nkept={info['kept']} | {info['reject_reason'] or 'ok'}\nscore={info.get('score', float('nan')):.3f}"
            branch_tiles.append(crop_candidate_tile(rgb, raw_mask, refined_mask, title))
            if cand is not None:
                kept_idx += 1
                kept_labels[cand.mask] = kept_idx
                all_candidates.append(cand)
                info['global_candidate_index'] = len(all_candidates)
                kept_masks.append(cand.mask)
            all_candidate_info.append(dict(info, branch=f'cellpose_d{diameter}'))

        write_csv(branch_dir / 'step25_candidate_table.csv', branch_infos)
        write_json(branch_dir / 'step25_candidate_table.json', branch_infos)
        save_contact_sheet(branch_dir / 'step26_candidate_contact_sheet.png', branch_tiles, cols=4)
        kept_rgb = labels_to_rgb(kept_labels)
        save_labels_16bit(branch_dir / 'step23_kept_candidate_mask_16bit.png', kept_labels)
        save_rgb(branch_dir / 'step24_kept_candidate_overlay.png', overlay_labels(rgb, kept_labels, kept_rgb))

    stage_cfg = STAGE_SIGNAL_CFG[cfg['stage']]
    signal_branch_rank_base = 10
    if stage_cfg['enabled']:
        for idx, (quantile, close_k, seed_frac) in enumerate(stage_cfg['combos']):
            combo_name = f'recovery_{idx:02d}_q{quantile:02d}_close{close_k:02d}_seed{int(round(seed_frac*100)):02d}'
            rec_dir = step05 / combo_name
            rec_dir.mkdir(parents=True, exist_ok=True)
            thr = int(np.percentile(signal, quantile))
            binary0 = (signal >= thr).astype(np.uint8) * 255
            close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
            open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            binary1 = cv2.morphologyEx(binary0, cv2.MORPH_CLOSE, close_kernel)
            binary2 = cv2.morphologyEx(binary1, cv2.MORPH_OPEN, open_kernel)
            binary3 = seg.clear_border(binary2, margin=20)
            binary4 = seg.fill_holes(binary3)
            binary5 = seg.clear_border(binary4, margin=20)
            save_binary(rec_dir / 'step30_binary_threshold.png', binary0)
            save_binary(rec_dir / 'step31_after_close.png', binary1)
            save_binary(rec_dir / 'step32_after_open.png', binary2)
            save_binary(rec_dir / 'step33_after_clear_border.png', binary3)
            save_binary(rec_dir / 'step34_after_fill_holes.png', binary4)
            save_binary(rec_dir / 'step35_final_binary.png', binary5)
            write_json(rec_dir / 'threshold_params.json', {
                'quantile': quantile,
                'threshold_value': thr,
                'close_kernel': close_k,
                'seed_fraction': seed_frac,
            })

            n, labels_cc, stats, _ = cv2.connectedComponentsWithStats((binary5 > 0).astype(np.uint8), connectivity=8)
            cc_labels = labels_cc.astype(np.uint16)
            save_labels_16bit(rec_dir / 'step36_connected_components_16bit.png', cc_labels)
            save_rgb(rec_dir / 'step37_connected_components_overlay.png', overlay_labels(rgb, cc_labels))

            comp_infos: list[dict] = []
            comp_tiles: list[np.ndarray] = []
            kept_comp = np.zeros_like(cc_labels, dtype=np.uint16)
            kept_comp_idx = 0
            for lab in range(1, n):
                raw_mask = labels_cc == lab
                area = int(stats[lab, cv2.CC_STAT_AREA])
                pseudo_d = int(round(math.sqrt((4.0 * area) / math.pi))) if area > 0 else 0
                cand, info = trace_candidate(raw_mask, pseudo_d, signal_branch_rank_base + idx, signal, support, grad_norm, cfg['stage'], 'signal_component')
                info['component_label'] = int(lab)
                info['component_area_raw'] = int(area)
                comp_infos.append(info)
                refined_mask = cand.mask if cand is not None else raw_mask
                title = f"comp {lab} | area {area}\nkept={info['kept']} | {info['reject_reason'] or 'ok'}\nscore={info.get('score', float('nan')):.3f}"
                comp_tiles.append(crop_candidate_tile(rgb, raw_mask, refined_mask, title))
                if cand is not None:
                    kept_comp_idx += 1
                    kept_comp[cand.mask] = kept_comp_idx
                    all_candidates.append(cand)
                    info['global_candidate_index'] = len(all_candidates)
                all_candidate_info.append(dict(info, branch=combo_name, candidate_family='signal_component'))
            write_csv(rec_dir / 'step38_component_candidate_table.csv', comp_infos)
            save_contact_sheet(rec_dir / 'step39_component_contact_sheet.png', comp_tiles, cols=4)
            save_labels_16bit(rec_dir / 'step40_component_kept_mask_16bit.png', kept_comp)
            save_rgb(rec_dir / 'step41_component_kept_overlay.png', overlay_labels(rgb, kept_comp))

            dist = cv2.distanceTransform((binary5 > 0).astype(np.uint8), cv2.DIST_L2, 5)
            save_gray(rec_dir / 'step42_distance_transform.png', dist)
            if float(dist.max()) > 0.0:
                seeds = (dist > float(dist.max()) * seed_frac).astype(np.uint8) * 255
                seeds = cv2.morphologyEx(seeds, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
            else:
                seeds = np.zeros_like(binary5)
            save_binary(rec_dir / 'step43_seed_mask.png', seeds)

            seed_n, seed_labels = cv2.connectedComponents((seeds > 0).astype(np.uint8))
            if seed_n > 2:
                markers = seed_labels.astype(np.int32) + 1
                unknown = cv2.subtract(binary5, seeds)
                markers[unknown > 0] = 0
                ws = cv2.watershed(cv2.cvtColor(signal, cv2.COLOR_GRAY2RGB), markers)
                ws_labels = np.where(ws > 1, ws - 1, 0).astype(np.uint16)
            else:
                ws = np.zeros_like(binary5, dtype=np.int32)
                ws_labels = np.zeros_like(binary5, dtype=np.uint16)
            save_labels_16bit(rec_dir / 'step44_watershed_labels_16bit.png', ws_labels)
            save_rgb(rec_dir / 'step45_watershed_overlay.png', overlay_labels(rgb, ws_labels))

            ws_infos: list[dict] = []
            ws_tiles: list[np.ndarray] = []
            kept_ws = np.zeros_like(ws_labels, dtype=np.uint16)
            kept_ws_idx = 0
            for lab in range(1, int(ws_labels.max()) + 1):
                raw_mask = ws_labels == lab
                area = int(raw_mask.sum())
                pseudo_d = int(round(math.sqrt((4.0 * area) / math.pi))) if area > 0 else 0
                cand, info = trace_candidate(raw_mask, pseudo_d, signal_branch_rank_base + idx + 3, signal, support, grad_norm, cfg['stage'], 'signal_watershed')
                info['watershed_label'] = int(lab)
                info['watershed_area_raw'] = int(area)
                ws_infos.append(info)
                refined_mask = cand.mask if cand is not None else raw_mask
                title = f"ws {lab} | area {area}\nkept={info['kept']} | {info['reject_reason'] or 'ok'}\nscore={info.get('score', float('nan')):.3f}"
                ws_tiles.append(crop_candidate_tile(rgb, raw_mask, refined_mask, title))
                if cand is not None:
                    kept_ws_idx += 1
                    kept_ws[cand.mask] = kept_ws_idx
                    all_candidates.append(cand)
                    info['global_candidate_index'] = len(all_candidates)
                all_candidate_info.append(dict(info, branch=combo_name, candidate_family='signal_watershed'))
            write_csv(rec_dir / 'step46_watershed_candidate_table.csv', ws_infos)
            save_contact_sheet(rec_dir / 'step47_watershed_contact_sheet.png', ws_tiles, cols=4)
            save_labels_16bit(rec_dir / 'step48_watershed_kept_mask_16bit.png', kept_ws)
            save_rgb(rec_dir / 'step49_watershed_kept_overlay.png', overlay_labels(rgb, kept_ws))

    write_csv(out_dir / 'all_candidate_trace.csv', all_candidate_info)
    write_json(out_dir / 'all_candidate_trace.json', all_candidate_info)

    kept: list[seg.Candidate] = []
    merge_rows: list[dict] = []
    merge_dir = step06
    for idx, cand in enumerate(sorted(all_candidates, key=lambda c: (c.score, c.area), reverse=True), start=1):
        action = 'accepted'
        reason = ''
        replaced_index = None
        best_prev_iou = 0.0
        best_prev_ov = 0.0
        for prev_idx, prev in enumerate(kept):
            ov = seg.overlap_small(cand.mask, prev.mask)
            iou = seg.iou(cand.mask, prev.mask)
            best_prev_iou = max(best_prev_iou, iou)
            best_prev_ov = max(best_prev_ov, ov)
            if ov > 0.80 or iou > 0.60:
                if (
                    cand.score > prev.score * 1.05
                    or (cand.area > prev.area * 1.20 and cand.support_ratio >= prev.support_ratio * 0.90)
                    or (cand.source != 'cellpose' and prev.source == 'cellpose' and cand.area > prev.area * 1.35)
                ):
                    kept[prev_idx] = cand
                    action = 'replaced_previous'
                    replaced_index = prev_idx + 1
                    reason = 'better_overlap_candidate'
                else:
                    action = 'skipped'
                    reason = 'overlap_weaker_than_existing'
                break
            if ov > 0.45 and cand.area < prev.area * 0.25:
                action = 'skipped'
                reason = 'small_fragment_over_large_mask'
                break
        if action == 'accepted':
            kept.append(cand)

        current_labels, current_rgb = seg.build_outputs(rgb, kept)
        current_overlay = overlay_labels(rgb, current_labels, current_rgb)
        save_rgb(merge_dir / f'merge_{idx:03d}_{action}.png', current_overlay)
        merge_rows.append({
            'merge_step': idx,
            'action': action,
            'reason': reason,
            'candidate_source': cand.source,
            'candidate_diameter_px': cand.diameter,
            'candidate_area': cand.area,
            'candidate_score': cand.score,
            'best_overlap_small': best_prev_ov,
            'best_iou': best_prev_iou,
            'replaced_slot': replaced_index,
            'kept_count_after_step': len(kept),
        })

    write_csv(merge_dir / 'step50_merge_trace.csv', merge_rows)
    write_json(merge_dir / 'step50_merge_trace.json', merge_rows)

    final_labels, final_rgb = seg.build_outputs(rgb, kept)
    final_overlay = overlay_labels(rgb, final_labels, final_rgb)
    save_labels_16bit(step07 / 'step60_final_mask_16bit.png', final_labels)
    save_rgb(step07 / 'step61_final_instance_rgb.png', final_rgb)
    save_rgb(step07 / 'step62_final_overlay.png', final_overlay)
    save_gray(step07 / 'step63_final_signal.png', signal)
    final_stats = {
        'source_tif': str(source_tif),
        'stage': cfg['stage'],
        'diameters_px': cfg['diameters'],
        'final_mask_count': int(final_labels.max()),
        'total_candidates_before_merge': len(all_candidates),
        'merge_steps': len(merge_rows),
        'final_kept_candidates': [
            {
                'area': cand.area,
                'score': round(cand.score, 6),
                'diameter_px': cand.diameter,
                'support_ratio': round(cand.support_ratio, 6),
                'mean_signal': round(cand.mean_signal, 6),
                'edge_strength': round(cand.edge_strength, 6),
                'circularity': round(cand.circularity, 6),
                'source': cand.source,
            }
            for cand in sorted(kept, key=lambda c: c.area, reverse=True)
        ],
    }
    write_json(step07 / 'step64_final_trace_summary.json', final_stats)

    gallery_tiles = [
        cv2.resize(rgb, (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(signal, cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(support, cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(final_overlay, (480, 340), interpolation=cv2.INTER_AREA),
    ]
    titles = ['step01 source', 'step10 hybrid signal', 'step14 support final', 'step62 final overlay']
    labeled = []
    for title, tile in zip(titles, gallery_tiles):
        canvas = np.full((380, 480, 3), 255, dtype=np.uint8)
        cv2.putText(canvas, title, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
        canvas[40:40 + tile.shape[0], :tile.shape[1]] = tile
        labeled.append(canvas)
    top = np.concatenate(labeled[:2], axis=1)
    bottom = np.concatenate(labeled[2:], axis=1)
    gallery = np.concatenate([top, np.full((16, top.shape[1], 3), 255, dtype=np.uint8), bottom], axis=0)
    save_rgb(out_dir / 'trace_overview_gallery.png', gallery)

    print(out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
