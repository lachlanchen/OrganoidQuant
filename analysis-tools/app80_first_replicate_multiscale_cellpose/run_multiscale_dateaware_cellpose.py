#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import tifffile
from cellpose import models

DATE_CONFIG = {
    '05-十二月-2025': {'stage': 'early_cluster', 'diameters': [120, 180, 260]},
    '07-十二月-2025': {'stage': 'cystic_early', 'diameters': [180, 320, 480]},
    '08-十二月-2025': {'stage': 'cystic_mid', 'diameters': [220, 380, 560]},
    '09-十二月-2025': {'stage': 'cystic_mid', 'diameters': [200, 340, 520]},
    '10-十二月-2025': {'stage': 'fused_large', 'diameters': [320, 560, 760]},
    '11-十二月-2025': {'stage': 'fused_large', 'diameters': [360, 620, 840]},
    '12-十二月-2025': {'stage': 'differentiated_irregular', 'diameters': [280, 520, 760]},
}


@dataclass
class Candidate:
    mask: np.ndarray
    score: float
    area: int
    diameter: int
    branch_rank: int
    support_ratio: float
    mean_signal: float
    edge_strength: float
    circularity: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-dir', required=True)
    p.add_argument('--out-dir', required=True)
    return p.parse_args()


def load_rgb_gray(path: Path) -> tuple[np.ndarray, np.ndarray]:
    arr = tifffile.imread(str(path))
    if arr.ndim == 2:
        gray = arr.astype(np.uint8)
        rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    elif arr.ndim == 3 and arr.shape[-1] in (3, 4):
        rgb = arr[..., :3].astype(np.uint8)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    elif arr.ndim == 3:
        gray = arr[0].astype(np.uint8)
        rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    else:
        raise RuntimeError(f'unsupported shape {arr.shape} for {path}')
    return rgb, gray


def compute_hybrid_signal(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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

    otsu_val, _ = cv2.threshold(signal, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    perc = int(np.percentile(signal, 58))
    thr = max(int(otsu_val), perc)
    support = (signal >= thr).astype(np.uint8) * 255
    k1 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    support = cv2.morphologyEx(support, cv2.MORPH_OPEN, k1)
    support = cv2.morphologyEx(support, cv2.MORPH_CLOSE, k2)
    return signal.astype(np.uint8), support, grad_norm


def mask_stats(mask: np.ndarray) -> tuple[int, float, float, float]:
    area = int(mask.sum())
    contours, _ = cv2.findContours((mask.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = float(sum(cv2.arcLength(c, True) for c in contours))
    if perimeter <= 0 or area <= 0:
        return area, perimeter, 0.0, 0.0
    circularity = float((4.0 * math.pi * area) / (perimeter * perimeter))
    x, y, w, h = cv2.boundingRect(np.argwhere(mask.astype(np.uint8))[:, ::-1])
    fill_ratio = float(area / max(1, w * h))
    return area, perimeter, circularity, fill_ratio


def refine_with_support(mask: np.ndarray, support: np.ndarray, diameter: int) -> np.ndarray:
    r = max(5, int(round(diameter * 0.02)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    grown = cv2.dilate((mask.astype(np.uint8) * 255), kernel)
    region = cv2.bitwise_and(support, grown)
    n, labels, stats, _ = cv2.connectedComponentsWithStats((region > 0).astype(np.uint8), connectivity=8)
    touched = np.unique(labels[mask])
    refined = np.zeros_like(mask, dtype=bool)
    orig_area = max(1, int(mask.sum()))
    for lab in touched:
        if lab == 0:
            continue
        comp = labels == lab
        comp_area = int(comp.sum())
        if comp_area > 0 and comp_area <= int(orig_area * 2.5):
            refined |= comp
    if refined.sum() < int(orig_area * 0.6) or refined.sum() > int(orig_area * 2.5):
        return mask
    return refined | mask


def build_candidate(label_mask: np.ndarray, label: int, diameter: int, branch_rank: int, signal: np.ndarray, support: np.ndarray, grad_norm: np.ndarray, stage: str) -> Candidate | None:
    mask = label_mask == label
    area, perimeter, circularity, fill_ratio = mask_stats(mask)
    if area <= 0:
        return None

    min_area = max(1500, int(0.08 * math.pi * (diameter / 2.0) ** 2))
    if area < min_area:
        return None

    mask = refine_with_support(mask, support, diameter)
    area, perimeter, circularity, fill_ratio = mask_stats(mask)
    h, w = mask.shape
    img_area = float(h * w)
    huge_frac = area / img_area

    support_ratio = float((support[mask] > 0).mean()) if area else 0.0
    mean_signal = float(signal[mask].mean() / 255.0) if area else 0.0

    edge = cv2.morphologyEx((mask.astype(np.uint8) * 255), cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    edge_strength = float(grad_norm[edge].mean() / 255.0) if edge.any() else 0.0

    if huge_frac > 0.48 and support_ratio < 0.55 and mean_signal < 0.55:
        return None
    if huge_frac > 0.35 and fill_ratio < 0.16 and support_ratio < 0.65:
        return None

    stage_bonus = {
        'early_cluster': 0.12 if diameter <= 260 else 0.0,
        'cystic_early': 0.08 if 180 <= diameter <= 480 else 0.0,
        'cystic_mid': 0.08 if 200 <= diameter <= 560 else 0.0,
        'fused_large': 0.12 if diameter >= 320 else 0.0,
        'differentiated_irregular': 0.15 if diameter >= 280 else 0.0,
    }.get(stage, 0.0)

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

    return Candidate(mask=mask, score=score, area=area, diameter=diameter, branch_rank=branch_rank, support_ratio=support_ratio, mean_signal=mean_signal, edge_strength=edge_strength, circularity=circularity)


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    if inter == 0:
        return 0.0
    union = float(np.logical_or(a, b).sum())
    return inter / union if union else 0.0


def overlap_small(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    denom = float(min(a.sum(), b.sum()))
    return inter / denom if denom else 0.0


def merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    kept: list[Candidate] = []
    for cand in sorted(candidates, key=lambda c: (c.score, c.area), reverse=True):
        replaced = False
        skip = False
        for idx, prev in enumerate(kept):
            ov = overlap_small(cand.mask, prev.mask)
            j = iou(cand.mask, prev.mask)
            if ov > 0.80 or j > 0.60:
                if cand.score > prev.score * 1.08 or (cand.area > prev.area * 1.20 and cand.support_ratio >= prev.support_ratio * 0.95):
                    kept[idx] = cand
                    replaced = True
                else:
                    skip = True
                break
            if ov > 0.45 and cand.area < prev.area * 0.25:
                skip = True
                break
        if replaced or skip:
            continue
        kept.append(cand)
    return kept


def build_outputs(rgb: np.ndarray, kept: list[Candidate]) -> tuple[np.ndarray, np.ndarray]:
    h, w = rgb.shape[:2]
    label_mask = np.zeros((h, w), dtype=np.uint16)
    color_mask = np.zeros((h, w, 3), dtype=np.uint8)
    rng = np.random.default_rng(42)
    for idx, cand in enumerate(sorted(kept, key=lambda c: c.area, reverse=True), start=1):
        label_mask[cand.mask] = idx
        color = rng.integers(40, 255, size=3, dtype=np.uint8)
        color_mask[cand.mask] = color
    return label_mask, color_mask


def main() -> int:
    args = parse_args()
    src_dir = Path(args.src_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model = models.CellposeModel(gpu=True)
    batch_summary = []
    gallery_rows = []
    thumb_h = 240

    for tif in sorted(src_dir.glob('*.tif')):
        date_key = tif.name.split('_', 1)[0]
        cfg = DATE_CONFIG[date_key]
        rgb, gray = load_rgb_gray(tif)
        signal, support, grad_norm = compute_hybrid_signal(gray)

        candidates: list[Candidate] = []
        branch_summaries = []
        for branch_rank, diameter in enumerate(cfg['diameters']):
            try:
                masks, *_ = model.eval(gray, diameter=float(diameter), channels=[0, 0], normalize=True, do_3D=False)
                masks = masks.astype(np.uint16)
                branch_count = 0
                for label in range(1, int(masks.max()) + 1):
                    cand = build_candidate(masks, label, diameter, branch_rank, signal, support, grad_norm, cfg['stage'])
                    if cand is not None:
                        candidates.append(cand)
                        branch_count += 1
                branch_summaries.append({'diameter_px': diameter, 'kept_candidates_before_merge': branch_count, 'status': 'ok'})
            except Exception as exc:
                branch_summaries.append({'diameter_px': diameter, 'kept_candidates_before_merge': 0, 'status': f'failed: {type(exc).__name__}'})

        kept = merge_candidates(candidates)
        label_mask, color_mask = build_outputs(rgb, kept)
        overlay = cv2.addWeighted(rgb, 0.72, color_mask, 0.55, 0)
        edges = cv2.Canny((label_mask > 0).astype(np.uint8) * 255, 50, 150)
        overlay[edges > 0] = (255, 0, 0)

        base = tif.stem + '_multiscale'
        mask_path = out_dir / f'{base}_cellpose_mask_16bit.png'
        rgb_path = out_dir / f'{base}_cellpose_instance_rgb.png'
        overlay_path = out_dir / f'{base}_cellpose_overlay.png'
        signal_path = out_dir / f'{base}_signal.png'
        support_path = out_dir / f'{base}_support.png'
        stats_path = out_dir / f'{base}_stats.json'

        cv2.imwrite(str(mask_path), label_mask)
        cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(signal_path), signal)
        cv2.imwrite(str(support_path), support)

        stats = {
            'source_tif': str(tif),
            'stage': cfg['stage'],
            'diameters_px': cfg['diameters'],
            'mask_count': int(label_mask.max()),
            'mask_16bit': mask_path.name,
            'instance_rgb': rgb_path.name,
            'overlay': overlay_path.name,
            'signal': signal_path.name,
            'support': support_path.name,
            'branch_summaries': branch_summaries,
            'merged_candidates': [
                {
                    'area': cand.area,
                    'score': round(cand.score, 4),
                    'diameter_px': cand.diameter,
                    'support_ratio': round(cand.support_ratio, 4),
                    'mean_signal': round(cand.mean_signal, 4),
                    'edge_strength': round(cand.edge_strength, 4),
                    'circularity': round(cand.circularity, 4),
                }
                for cand in sorted(kept, key=lambda c: c.area, reverse=True)
            ],
        }
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
        batch_summary.append(stats)

        def to_thumb(img: np.ndarray) -> np.ndarray:
            scale = thumb_h / img.shape[0]
            return cv2.resize(img, (int(img.shape[1] * scale), thumb_h), interpolation=cv2.INTER_AREA)

        t1 = to_thumb(rgb)
        t2 = to_thumb(cv2.cvtColor(signal, cv2.COLOR_GRAY2RGB))
        t3 = to_thumb(overlay)
        t4 = to_thumb(color_mask)
        spacer = np.full((thumb_h, 10, 3), 255, dtype=np.uint8)
        row = np.concatenate([t1, spacer, t2, spacer, t3, spacer, t4], axis=1)
        label = f'{tif.name} | {cfg["stage"]} | d={cfg["diameters"]} | n={int(label_mask.max())}'
        canvas = np.full((thumb_h + 30, row.shape[1], 3), 255, dtype=np.uint8)
        cv2.putText(canvas, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        canvas[30:, :, :] = row
        gallery_rows.append(canvas)

    (out_dir / 'cellpose_batch_summary.json').write_text(json.dumps(batch_summary, ensure_ascii=False, indent=2), encoding='utf-8')
    if gallery_rows:
        gallery = np.full((sum(im.shape[0] for im in gallery_rows) + 10 * (len(gallery_rows) - 1), max(im.shape[1] for im in gallery_rows), 3), 255, dtype=np.uint8)
        y = 0
        for im in gallery_rows:
            gallery[y:y + im.shape[0], :im.shape[1], :] = im
            y += im.shape[0] + 10
        cv2.imwrite(str(out_dir / '10x_cellpose_multiscale_dateaware_gallery.png'), cv2.cvtColor(gallery, cv2.COLOR_RGB2BGR))

    print(out_dir)
    print(out_dir / 'cellpose_batch_summary.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
