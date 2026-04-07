#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
import sys

import cv2
import numpy as np
from scipy import ndimage as ndi

SCRIPT_DIR = Path(__file__).resolve().parent
APP80_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose')
sys.path.insert(0, str(APP80_DIR))

from cellpose import models  # noqa: E402
import run_multiscale_dateaware_cellpose as seg  # noqa: E402


@dataclass
class Candidate:
    mask: np.ndarray
    branch: str
    diameter: int
    score: float
    area: int
    circularity: float
    fill_ratio: float
    overlap_env: float
    overlap_core: float
    mean_signal: float
    mean_sat: float
    boundary_strength: float
    border_touch: bool
    bbox_cover: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='App65 custom single-image segmentation test using threshold hints plus raw Cellpose branches.')
    p.add_argument('--tif', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--diameters', default='220,320,420,520,700')
    p.add_argument('--gpu', action='store_true', default=True)
    return p.parse_args()


def save_gray(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def save_binary(path: Path, mask: np.ndarray) -> None:
    save_gray(path, (mask.astype(np.uint8) * 255))


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def fill_holes(mask255: np.ndarray) -> np.ndarray:
    work = mask255.copy()
    h, w = work.shape
    flood = work.copy()
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    return cv2.bitwise_or(work, holes)


def mask_stats(mask: np.ndarray) -> tuple[int, float, float, float, bool, float]:
    area = int(mask.sum())
    if area <= 0:
        return 0, 0.0, 0.0, 0.0, False, 0.0
    cnts, _ = cv2.findContours((mask.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = float(sum(cv2.arcLength(c, True) for c in cnts))
    circularity = float((4.0 * math.pi * area) / (perimeter * perimeter)) if perimeter > 0 else 0.0
    ys, xs = np.where(mask)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    fill_ratio = float(area / max(1, bw * bh))
    h, w = mask.shape
    border_touch = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
    bbox_cover = max(bw / w if w else 0.0, bh / h if h else 0.0)
    return area, perimeter, circularity, fill_ratio, border_touch, bbox_cover


def boundary_ring_strength(mask: np.ndarray, edge_map: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    mask_u8 = mask.astype(np.uint8) * 255
    outer = cv2.dilate(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)), iterations=1) > 0
    inner = cv2.erode(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)), iterations=1) > 0
    ring = np.logical_and(outer, ~inner)
    if ring.sum() <= 0:
        ring = outer
    return float(edge_map[ring].mean() / 255.0) if ring.any() else 0.0


def grow_within(seed_mask: np.ndarray, allow_mask: np.ndarray, kernel_size: int = 9, max_iters: int = 28) -> np.ndarray:
    region = (seed_mask.astype(np.uint8) * 255)
    allow_u8 = (allow_mask.astype(np.uint8) * 255)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    for _ in range(max_iters):
        dil = cv2.dilate(region, kernel, iterations=1)
        nxt = cv2.bitwise_and(dil, allow_u8)
        if np.array_equal(nxt, region):
            break
        region = nxt
    return region > 0


def build_threshold_hint(rgb: np.ndarray, gray: np.ndarray, signal: np.ndarray, out_dir: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    step = out_dir / 'step02_threshold_hint'
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    a_chan = lab[..., 1]

    blur9 = cv2.GaussianBlur(gray, (0, 0), 9.0)
    texture = cv2.normalize(cv2.absdiff(gray, blur9), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    gradx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grady = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.normalize(cv2.magnitude(gradx, grady), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    signal_p72 = int(np.percentile(signal, 72))
    signal_p84 = int(np.percentile(signal, 84))
    sat_p82 = int(np.percentile(sat, 82))
    a_p78 = int(np.percentile(a_chan, 78))
    texture_p78 = int(np.percentile(texture, 78))
    grad_p80 = int(np.percentile(grad, 80))

    blur = cv2.GaussianBlur(gray, (0, 0), 5.0)
    blackhat = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    blackhat_p80 = int(np.percentile(blackhat, 80))

    signal_lo = signal >= signal_p72
    signal_hi = signal >= signal_p84
    sat_hi = sat >= sat_p82
    a_hi = a_chan >= a_p78
    texture_hi = texture >= texture_p78
    grad_hi = grad >= grad_p80
    dark_wall = blackhat >= blackhat_p80

    union = (
        signal_lo & (texture_hi | grad_hi | a_hi | dark_wall)
    ) | (
        dark_wall & (texture_hi | grad_hi | signal_lo)
    ) | (
        signal_hi & (texture_hi | grad_hi | dark_wall)
    )
    strong = (
        signal_hi & (texture_hi | grad_hi | dark_wall | a_hi)
    ) | (
        dark_wall & signal_lo & (texture_hi | grad_hi)
    )

    save_gray(step / 'step10_signal.png', signal)
    save_gray(step / 'step11_gray.png', gray)
    save_gray(step / 'step12_saturation.png', sat)
    save_gray(step / 'step13_lab_a.png', a_chan)
    save_gray(step / 'step14_texture.png', texture)
    save_gray(step / 'step15_gradient.png', grad)
    save_gray(step / 'step16_blackhat.png', blackhat)
    save_binary(step / 'step20_signal_lo.png', signal_lo)
    save_binary(step / 'step21_signal_hi.png', signal_hi)
    save_binary(step / 'step22_sat_hi.png', sat_hi)
    save_binary(step / 'step23_a_hi.png', a_hi)
    save_binary(step / 'step24_texture_hi.png', texture_hi)
    save_binary(step / 'step25_grad_hi.png', grad_hi)
    save_binary(step / 'step26_dark_wall.png', dark_wall)
    save_binary(step / 'step27_union_raw.png', union)
    save_binary(step / 'step28_strong_raw.png', strong)

    union_mask = (union.astype(np.uint8) * 255)
    union_mask = cv2.morphologyEx(union_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    union_mask = cv2.morphologyEx(union_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    strong_mask = (strong.astype(np.uint8) * 255)
    strong_mask = cv2.morphologyEx(strong_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    strong_mask = cv2.morphologyEx(strong_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    strong_mask = cv2.dilate(strong_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)

    n, labels, stats, _ = cv2.connectedComponentsWithStats((strong_mask > 0).astype(np.uint8), connectivity=8)
    H, W = union_mask.shape
    kept = np.zeros_like(union_mask)
    rows = []
    for lab_id in range(1, n):
        seed_area = int(stats[lab_id, cv2.CC_STAT_AREA])
        if seed_area < 2500:
            continue
        seed_mask = labels == lab_id
        grown = grow_within(seed_mask, union_mask > 0, kernel_size=9, max_iters=32)
        grown_u8 = (grown.astype(np.uint8) * 255)
        grown_u8 = cv2.morphologyEx(grown_u8, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
        grown_u8 = cv2.morphologyEx(grown_u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        grown_u8 = fill_holes(grown_u8)
        comp_mask = grown_u8 > 0
        area = int(comp_mask.sum())
        if area < 18000:
            continue
        x = int(stats[lab_id, cv2.CC_STAT_LEFT])
        y = int(stats[lab_id, cv2.CC_STAT_TOP])
        w = int(stats[lab_id, cv2.CC_STAT_WIDTH])
        h = int(stats[lab_id, cv2.CC_STAT_HEIGHT])
        ys, xs = np.where(comp_mask)
        x = int(xs.min())
        y = int(ys.min())
        w = int(xs.max() - xs.min() + 1)
        h = int(ys.max() - ys.min() + 1)
        border_touch = bool(comp_mask[0, :].any() or comp_mask[-1, :].any() or comp_mask[:, 0].any() or comp_mask[:, -1].any())
        strong_overlap = float((strong_mask[comp_mask] > 0).mean()) if area else 0.0
        _, _, circularity, fill_ratio, _, bbox_cover = mask_stats(comp_mask)
        mean_dark = float((255 - gray[comp_mask]).mean() / 255.0) if area else 0.0
        mean_texture = float(texture[comp_mask].mean() / 255.0) if area else 0.0
        droplet_like_border = border_touch and bbox_cover > 0.78 and circularity > 0.72 and fill_ratio > 0.58 and mean_texture < 0.10
        keep = strong_overlap >= 0.05 and not droplet_like_border
        if keep:
            kept[comp_mask] = 255
        rows.append({
            'component_id': lab_id,
            'area_px': area,
            'seed_area_px': seed_area,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'border_touch': border_touch,
            'strong_overlap': round(strong_overlap, 6),
            'circularity': round(float(circularity), 6),
            'fill_ratio': round(float(fill_ratio), 6),
            'bbox_cover': round(float(bbox_cover), 6),
            'mean_dark': round(float(mean_dark), 6),
            'mean_texture': round(float(mean_texture), 6),
            'kept': keep,
        })

    kept = cv2.morphologyEx(kept, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
    kept = cv2.morphologyEx(kept, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    core = cv2.erode(kept, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    if core.sum() == 0:
        core = cv2.erode(kept, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))

    save_binary(step / 'step30_hint_envelope.png', kept > 0)
    save_binary(step / 'step31_hint_core.png', core > 0)
    overlay = rgb.copy()
    overlay[(kept > 0)] = (0.55 * overlay[(kept > 0)] + 0.45 * np.array([255, 190, 0])).astype(np.uint8)
    outline = cv2.Canny(kept, 50, 150)
    overlay[outline > 0] = (255, 0, 0)
    save_rgb(step / 'step32_hint_overlay.png', overlay)
    write_json(step / 'step33_hint_components.json', {
        'components': rows,
        'thresholds': {
            'signal_p72': signal_p72,
            'signal_p84': signal_p84,
            'sat_p82': sat_p82,
            'a_p78': a_p78,
            'texture_p78': texture_p78,
            'grad_p80': grad_p80,
            'blackhat_p80': blackhat_p80,
        },
    })
    return kept > 0, core > 0, {
        'components': rows,
        'thresholds': {
            'signal_p72': signal_p72,
            'signal_p84': signal_p84,
            'sat_p82': sat_p82,
            'a_p78': a_p78,
            'texture_p78': texture_p78,
            'grad_p80': grad_p80,
            'blackhat_p80': blackhat_p80,
        },
    }


def run_cellpose_branches(model, rgb: np.ndarray, gray: np.ndarray, hint_env: np.ndarray, hint_core: np.ndarray, diameters: list[int], out_dir: Path) -> list[Candidate]:
    step_raw = out_dir / 'step03_cellpose_raw'
    sat = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1]
    bg_value = int(np.median(gray[~hint_env])) if (~hint_env).any() else int(np.median(gray))
    gradx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grady = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.normalize(cv2.magnitude(gradx, grady), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    blackhat = cv2.morphologyEx(
        cv2.GaussianBlur(gray, (0, 0), 5.0),
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)),
    )
    edge_map = cv2.normalize(cv2.addWeighted(grad, 0.62, blackhat, 0.38, 0.0), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    masked = gray.copy()
    masked[~hint_env] = bg_value
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(16, 16)).apply(gray)
    clahe_masked = clahe.copy()
    clahe_masked[~hint_env] = bg_value
    inv_masked = 255 - gray
    inv_masked[~hint_env] = bg_value
    dark_emphasis = cv2.normalize(
        cv2.addWeighted(
            cv2.morphologyEx(cv2.GaussianBlur(gray, (0, 0), 5.0), cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))),
            1.1,
            cv2.absdiff(gray, cv2.GaussianBlur(gray, (0, 0), 9.0)),
            0.9,
            0.0,
        ),
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)
    dark_emphasis_masked = dark_emphasis.copy()
    dark_emphasis_masked[~hint_env] = 0

    branch_specs = [
        ('raw', gray, 0.00),
        ('masked', masked, 0.03),
        ('clahe_masked', clahe_masked, 0.06),
        ('inv_masked', inv_masked, 0.02),
        ('dark_emphasis_masked', dark_emphasis_masked, 0.04),
    ]

    save_gray(step_raw / 'step00_input_raw.png', gray)
    save_gray(step_raw / 'step01_input_masked.png', masked)
    save_gray(step_raw / 'step02_input_clahe_masked.png', clahe_masked)
    save_gray(step_raw / 'step03_input_inv_masked.png', inv_masked)
    save_gray(step_raw / 'step04_input_dark_emphasis_masked.png', dark_emphasis_masked)
    save_gray(step_raw / 'step05_boundary_edge_map.png', edge_map)

    candidates: list[Candidate] = []
    branch_rows = []
    for branch_name, branch_img, branch_bonus in branch_specs:
        for d in diameters:
            masks, *_ = model.eval(branch_img, diameter=float(d), channels=[0, 0], normalize=True, do_3D=False)
            masks = masks.astype(np.uint16)
            branch_label = np.zeros_like(masks, dtype=np.uint16)
            kept_count = 0
            for lab_id in range(1, int(masks.max()) + 1):
                mask = masks == lab_id
                area, _, circularity, fill_ratio, border_touch, bbox_cover = mask_stats(mask)
                if area < 12000:
                    continue
                overlap_env = float(hint_env[mask].mean()) if area else 0.0
                overlap_core = float(hint_core[mask].mean()) if area else 0.0
                if overlap_env < 0.45:
                    continue
                if area < 50000 and overlap_core < 0.08:
                    continue
                mean_signal = float(gray[mask].mean() / 255.0) if area else 0.0
                mean_sat = float(sat[mask].mean() / 255.0) if area else 0.0
                boundary_strength = boundary_ring_strength(mask, edge_map)
                if area < 28000 and boundary_strength < 0.16:
                    continue
                if area < 60000 and boundary_strength < 0.13:
                    continue
                if circularity < 0.18 and fill_ratio < 0.22 and boundary_strength < 0.15:
                    continue
                if border_touch and bbox_cover > 0.70 and circularity > 0.80 and fill_ratio > 0.65:
                    continue
                score = (
                    1.35 * overlap_env
                    + 0.52 * circularity
                    + 0.18 * fill_ratio
                    + 0.32 * mean_signal
                    + 0.42 * boundary_strength
                    + 0.16 * overlap_core
                    + branch_bonus
                )
                if not border_touch:
                    score += 0.08
                if 40000 <= area <= 900000:
                    score += 0.05
                if area > 1100000:
                    score -= 0.10
                candidates.append(Candidate(
                    mask=mask,
                    branch=branch_name,
                    diameter=d,
                    score=float(score),
                    area=area,
                    circularity=float(circularity),
                    fill_ratio=float(fill_ratio),
                    overlap_env=float(overlap_env),
                    overlap_core=float(overlap_core),
                    mean_signal=float(mean_signal),
                    mean_sat=float(mean_sat),
                    boundary_strength=float(boundary_strength),
                    border_touch=bool(border_touch),
                    bbox_cover=float(bbox_cover),
                ))
                kept_count += 1
                branch_label[mask] = kept_count
                branch_rows.append({
                    'branch': branch_name,
                    'diameter_px': d,
                    'candidate_label': kept_count,
                    'area_px': area,
                    'score': round(float(score), 6),
                    'circularity': round(float(circularity), 6),
                    'fill_ratio': round(float(fill_ratio), 6),
                    'overlap_env': round(float(overlap_env), 6),
                    'overlap_core': round(float(overlap_core), 6),
                    'mean_signal': round(float(mean_signal), 6),
                    'mean_sat': round(float(mean_sat), 6),
                    'boundary_strength': round(float(boundary_strength), 6),
                    'border_touch': bool(border_touch),
                    'bbox_cover': round(float(bbox_cover), 6),
                })
            save_gray(step_raw / f'{branch_name}_diameter_{d:04d}_labels_16bit.png', branch_label)

    with (step_raw / 'candidate_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(branch_rows[0].keys()) if branch_rows else ['diameter_px'])
        writer.writeheader()
        if branch_rows:
            writer.writerows(branch_rows)
    write_json(step_raw / 'branch_summary.json', {'diameters': diameters, 'branches': [name for name, _, _ in branch_specs], 'candidate_count': len(branch_rows)})
    return candidates


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    if inter <= 0:
        return 0.0
    union = float(np.logical_or(a, b).sum())
    return inter / union if union else 0.0


def overlap_small(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    denom = float(min(a.sum(), b.sum()))
    return inter / denom if denom else 0.0


def component_cover_ratio(component_mask: np.ndarray, kept: list[Candidate]) -> float:
    comp_area = float(component_mask.sum())
    if comp_area <= 0:
        return 0.0
    covered = np.zeros_like(component_mask, dtype=bool)
    for cand in kept:
        covered |= np.logical_and(component_mask, cand.mask)
    return float(covered.sum() / comp_area)


def merge_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict]]:
    kept: list[Candidate] = []
    trace: list[dict] = []
    for rank, cand in enumerate(sorted(candidates, key=lambda c: (c.score, c.boundary_strength, c.area), reverse=True), start=1):
        action = 'keep'
        reason = 'new'
        replaced_index: list[int] = []
        if cand.branch.endswith('rescue'):
            overlap_hits: list[tuple[int, Candidate, float, float]] = []
            for idx, prev in enumerate(kept):
                ov = overlap_small(cand.mask, prev.mask)
                j = iou(cand.mask, prev.mask)
                if ov > 0.35 or j > 0.18:
                    overlap_hits.append((idx, prev, ov, j))
            if overlap_hits:
                union_mask = np.zeros_like(cand.mask, dtype=bool)
                best_score = -1.0
                best_boundary = -1.0
                for idx, prev, _, _ in overlap_hits:
                    union_mask |= prev.mask
                    best_score = max(best_score, prev.score)
                    best_boundary = max(best_boundary, prev.boundary_strength)
                union_area = float(union_mask.sum())
                union_overlap = overlap_small(cand.mask, union_mask)
                area_ratio = float(cand.area / max(1.0, union_area))
                if union_overlap > 0.60 and 0.78 <= area_ratio <= 1.45 and cand.score >= best_score - 0.25 and cand.boundary_strength >= best_boundary - 0.08:
                    action = 'replace'
                    reason = f'rescue_union_overlap={union_overlap:.3f},area_ratio={area_ratio:.3f}'
                    for idx, *_ in reversed(overlap_hits):
                        del kept[idx]
                        replaced_index.append(idx + 1)
                    kept.append(cand)
                    trace.append({
                        'rank': rank,
                        'branch': cand.branch,
                        'diameter_px': cand.diameter,
                        'area_px': cand.area,
                        'score': round(cand.score, 6),
                        'action': action,
                        'reason': reason,
                        'replaced_slot': ','.join(str(x) for x in replaced_index) if replaced_index else None,
                    })
                    continue
        for idx, prev in enumerate(kept):
            ov = overlap_small(cand.mask, prev.mask)
            j = iou(cand.mask, prev.mask)
            if ov > 0.78 or j > 0.55:
                better_split = cand.circularity > prev.circularity + 0.05 and cand.area < prev.area * 0.92
                clearly_better = cand.score > prev.score * 1.02 or cand.area > prev.area * 1.08
                if better_split or clearly_better:
                    action = 'replace'
                    reason = f'overlap_small={ov:.3f},iou={j:.3f}'
                    kept[idx] = cand
                    replaced_index = [idx + 1]
                else:
                    action = 'skip'
                    reason = f'overlap_small={ov:.3f},iou={j:.3f}'
                break
        if action == 'keep':
            kept.append(cand)
        trace.append({
            'rank': rank,
            'branch': cand.branch,
            'diameter_px': cand.diameter,
            'area_px': cand.area,
            'score': round(cand.score, 6),
            'action': action,
            'reason': reason,
            'replaced_slot': ','.join(str(x) for x in replaced_index) if replaced_index else None,
        })
    return kept, trace


def run_texture_rescue(
    gray: np.ndarray,
    signal: np.ndarray,
    hint_env: np.ndarray,
    hint_core: np.ndarray,
    kept: list[Candidate],
    out_dir: Path,
) -> list[Candidate]:
    step = out_dir / 'step04_region_rescue'
    step.mkdir(parents=True, exist_ok=True)

    covered = np.zeros_like(hint_env, dtype=np.uint8)
    for cand in kept:
        covered[cand.mask] = 255
    covered = cv2.dilate(covered, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)), iterations=1) > 0

    blur = cv2.GaussianBlur(gray, (0, 0), 5.0)
    blackhat = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    gradx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grady = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.normalize(cv2.magnitude(gradx, grady), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    texture = cv2.normalize(cv2.absdiff(gray, cv2.GaussianBlur(gray, (0, 0), 9.0)), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    inv_gray = cv2.normalize(255 - gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    inv_norm = inv_gray.astype(np.float32) / 255.0
    texture_norm = texture.astype(np.float32) / 255.0
    blackhat_norm = blackhat.astype(np.float32) / 255.0
    grad_norm = grad.astype(np.float32) / 255.0
    confidence = (
        0.38 * inv_norm
        + 0.24 * blackhat_norm
        + 0.22 * texture_norm
        + 0.16 * grad_norm
    )
    edge_map = cv2.normalize(cv2.addWeighted(grad, 0.62, blackhat, 0.38, 0.0), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    texture_hi = texture >= np.percentile(texture, 80)
    blackhat_hi = blackhat >= np.percentile(blackhat, 82)
    grad_hi = grad >= np.percentile(grad, 82)
    dark_hi = inv_gray >= np.percentile(inv_gray, 72)

    support = hint_env & dark_hi & (texture_hi | blackhat_hi | grad_hi) & (~covered)
    support = cv2.morphologyEx((support.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))
    support = cv2.morphologyEx(support, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    support = fill_holes(support)

    save_gray(step / 'step40_texture.png', texture)
    save_gray(step / 'step41_blackhat.png', blackhat)
    save_gray(step / 'step42_inverted_gray.png', inv_gray)
    save_binary(step / 'step43_support_mask.png', support > 0)
    save_gray(step / 'step44_confidence.png', np.clip(confidence * 255.0, 0, 255).astype(np.uint8))

    hint_n, hint_labels, hint_stats, _ = cv2.connectedComponentsWithStats(hint_env.astype(np.uint8), connectivity=8)
    candidates: list[Candidate] = []
    rows = []
    rescue_labels = np.zeros_like(hint_labels, dtype=np.uint16)
    kept_count = 0
    component_rows = []
    for comp_id in range(1, hint_n):
        component_mask = hint_labels == comp_id
        comp_area = int(hint_stats[comp_id, cv2.CC_STAT_AREA])
        if comp_area < 30000:
            continue
        coverage = component_cover_ratio(component_mask, kept)
        unresolved = component_mask & (~covered)
        unresolved_area = int(unresolved.sum())
        if coverage >= 0.72 or unresolved_area < 15000:
            component_rows.append({
                'component_id': comp_id,
                'component_area_px': comp_area,
                'cellpose_coverage': round(float(coverage), 6),
                'unresolved_area_px': unresolved_area,
                'rescue_triggered': False,
            })
            continue

        comp_conf = confidence[component_mask]
        hi_thr = max(float(np.percentile(comp_conf, 72)), 0.40)
        lo_thr = max(float(np.percentile(comp_conf, 56)), 0.28)
        seed = unresolved & (confidence >= hi_thr)
        grow = unresolved & (confidence >= lo_thr)
        seed_u8 = (seed.astype(np.uint8) * 255)
        grow_u8 = (grow.astype(np.uint8) * 255)
        seed_u8 = cv2.morphologyEx(seed_u8, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
        seed_u8 = cv2.morphologyEx(seed_u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        region = seed_u8.copy()
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        for _ in range(24):
            dil = cv2.dilate(region, kernel, iterations=1)
            grown = cv2.bitwise_and(dil, grow_u8)
            if np.array_equal(grown, region):
                break
            region = grown
        region = cv2.morphologyEx(region, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        region = fill_holes(region)
        save_binary(step / f'component_{comp_id:02d}_seed.png', seed)
        save_binary(step / f'component_{comp_id:02d}_grow.png', grow)
        save_binary(step / f'component_{comp_id:02d}_region.png', region > 0)

        n, labels, stats, _ = cv2.connectedComponentsWithStats((region > 0).astype(np.uint8), connectivity=8)
        component_triggered = False
        for label_id in range(1, n):
            mask = labels == label_id
            if np.logical_and(mask, component_mask).sum() <= 0:
                continue
            mask &= component_mask
            area, _, circularity, fill_ratio, border_touch, bbox_cover = mask_stats(mask)
            min_area = max(22000, int(0.08 * comp_area))
            if area < min_area:
                continue
            overlap_env = float(hint_env[mask].mean()) if area else 0.0
            overlap_core = float(hint_core[mask].mean()) if area else 0.0
            mean_signal = float(gray[mask].mean() / 255.0) if area else 0.0
            mean_grad = float(grad[mask].mean() / 255.0) if area else 0.0
            mean_texture = float(texture[mask].mean() / 255.0) if area else 0.0
            mean_blackhat = float(blackhat[mask].mean() / 255.0) if area else 0.0
            mean_dark = float(inv_gray[mask].mean() / 255.0) if area else 0.0
            boundary_strength = boundary_ring_strength(mask, edge_map)
            droplet_like_border = (
                border_touch
                and bbox_cover > 0.78
                and circularity > 0.72
                and fill_ratio > 0.58
                and mean_texture < 0.10
                and mean_blackhat < 0.06
            )
            if droplet_like_border:
                continue
            if area > int(0.78 * comp_area):
                continue
            if mean_texture < 0.10 and mean_blackhat < 0.08 and mean_dark < 0.22:
                continue
            score = (
                1.18 * overlap_env
                + 0.16 * fill_ratio
                + 0.26 * mean_dark
                + 0.22 * mean_texture
                + 0.20 * mean_blackhat
                + 0.10 * mean_grad
                + 0.08 * overlap_core
                + 0.12 * boundary_strength
            )
            cand = Candidate(
                mask=mask,
                branch='component_rescue',
                diameter=0,
                score=float(score),
                area=area,
                circularity=float(circularity),
                fill_ratio=float(fill_ratio),
                overlap_env=float(overlap_env),
                overlap_core=float(overlap_core),
                mean_signal=float(mean_signal),
                mean_sat=0.0,
                boundary_strength=float(boundary_strength),
                border_touch=bool(border_touch),
                bbox_cover=float(bbox_cover),
            )
            candidates.append(cand)
            kept_count += 1
            rescue_labels[mask] = kept_count
            component_triggered = True
            rows.append({
                'candidate_label': kept_count,
                'component_id': comp_id,
                'area_px': area,
                'score': round(float(score), 6),
                'circularity': round(float(circularity), 6),
                'fill_ratio': round(float(fill_ratio), 6),
                'overlap_env': round(float(overlap_env), 6),
                'overlap_core': round(float(overlap_core), 6),
                'mean_signal': round(float(mean_signal), 6),
                'mean_grad': round(float(mean_grad), 6),
                'mean_texture': round(float(mean_texture), 6),
                'mean_blackhat': round(float(mean_blackhat), 6),
                'mean_dark': round(float(mean_dark), 6),
                'boundary_strength': round(float(boundary_strength), 6),
                'border_touch': bool(border_touch),
                'bbox_cover': round(float(bbox_cover), 6),
            })
        component_rows.append({
            'component_id': comp_id,
            'component_area_px': comp_area,
            'cellpose_coverage': round(float(coverage), 6),
            'unresolved_area_px': unresolved_area,
            'rescue_triggered': component_triggered,
            'hi_threshold': round(hi_thr, 6),
            'lo_threshold': round(lo_thr, 6),
        })

    save_gray(step / 'step45_region_labels_16bit.png', rescue_labels)
    if rows:
        with (step / 'candidate_table.csv').open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    if component_rows:
        with (step / 'component_summary.csv').open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(component_rows[0].keys()))
            writer.writeheader()
            writer.writerows(component_rows)
    write_json(step / 'step49_rescue_summary.json', {
        'support_px': int((support > 0).sum()),
        'candidate_count': len(rows),
        'component_count': len(component_rows),
    })
    return candidates


def build_final_outputs(rgb: np.ndarray, kept: list[Candidate]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = rgb.shape[:2]
    labels = np.zeros((h, w), dtype=np.uint16)
    colors = np.zeros((h, w, 3), dtype=np.uint8)
    rng = np.random.default_rng(42)
    for idx, cand in enumerate(sorted(kept, key=lambda c: c.area, reverse=True), start=1):
        labels[cand.mask] = idx
        colors[cand.mask] = rng.integers(40, 255, size=3, dtype=np.uint8)
    overlay = cv2.addWeighted(rgb, 0.72, colors, 0.60, 0)
    edges = cv2.Canny((labels > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (255, 0, 0)
    return labels, colors, overlay


def main() -> int:
    args = parse_args()
    tif = Path(args.tif).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    diameters = [int(x) for x in args.diameters.split(',') if x.strip()]

    rgb, gray = seg.load_rgb_gray(tif)
    signal, _, _ = seg.compute_hybrid_signal(gray)

    step01 = out_dir / 'step01_input'
    save_rgb(step01 / 'step01_source_rgb.png', rgb)
    save_gray(step01 / 'step02_source_gray.png', gray)

    hint_env, hint_core, hint_meta = build_threshold_hint(rgb, gray, signal, out_dir)

    model = models.CellposeModel(gpu=bool(args.gpu))
    candidates = run_cellpose_branches(model, rgb, gray, hint_env, hint_core, diameters, out_dir)

    initial_kept, _ = merge_candidates(candidates)
    rescue_candidates = run_texture_rescue(gray, signal, hint_env, hint_core, initial_kept, out_dir)

    step05 = out_dir / 'step05_merge'
    step05.mkdir(parents=True, exist_ok=True)
    kept, trace = merge_candidates(candidates + rescue_candidates)
    with (step05 / 'merge_trace.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(trace[0].keys()) if trace else ['rank'])
        writer.writeheader()
        if trace:
            writer.writerows(trace)

    labels, colors, overlay = build_final_outputs(rgb, kept)
    step06 = out_dir / 'step06_final'
    save_gray(step06 / 'step50_final_mask_16bit.png', labels)
    save_rgb(step06 / 'step51_final_instance_rgb.png', colors)
    save_rgb(step06 / 'step52_final_overlay.png', overlay)
    save_gray(step06 / 'step53_final_signal.png', signal)
    save_binary(step06 / 'step54_final_hint_envelope.png', hint_env)
    save_binary(step06 / 'step55_final_hint_core.png', hint_core)

    rows = []
    for idx, cand in enumerate(sorted(kept, key=lambda c: c.area, reverse=True), start=1):
        rows.append({
            'final_label': idx,
            'branch': cand.branch,
            'diameter_px': cand.diameter,
            'area_px': cand.area,
            'score': round(cand.score, 6),
            'circularity': round(cand.circularity, 6),
            'fill_ratio': round(cand.fill_ratio, 6),
            'overlap_env': round(cand.overlap_env, 6),
            'overlap_core': round(cand.overlap_core, 6),
            'mean_signal': round(cand.mean_signal, 6),
            'mean_sat': round(cand.mean_sat, 6),
            'boundary_strength': round(cand.boundary_strength, 6),
            'border_touch': cand.border_touch,
            'bbox_cover': round(cand.bbox_cover, 6),
        })
    with (step06 / 'step56_final_object_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['final_label'])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    summary = {
        'source_tif': str(tif),
        'diameters_px': diameters,
        'candidate_count_before_merge': len(candidates),
        'texture_rescue_candidate_count': len(rescue_candidates),
        'final_count': int(labels.max()),
        'hint_component_count': int(sum(1 for x in hint_meta['components'] if x['kept'])),
        'final_objects': rows,
        'notes': {
            'goal': 'Use App65-specific threshold hints with multi-branch Cellpose plus texture-based irregular-mass rescue while avoiding the old signal_component blob recovery.',
            'signal_component_used': False,
            'texture_rescue_used': len(rescue_candidates) > 0,
        },
    }
    write_json(step06 / 'step57_final_summary.json', summary)
    write_json(out_dir / 'manifest.json', {
        'source_tif': str(tif),
        'output_root': str(out_dir),
        'steps': ['step01_input', 'step02_threshold_hint', 'step03_cellpose_raw', 'step04_region_rescue', 'step05_merge', 'step06_final'],
        'summary': str((step06 / 'step57_final_summary.json').resolve()),
    })
    print(json.dumps({'output_root': str(out_dir), 'final_count': int(labels.max())}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
