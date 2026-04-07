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

    union = (signal_lo & (texture_hi | grad_hi | a_hi)) | (texture_hi & grad_hi) | (dark_wall & texture_hi) | sat_hi
    strong = signal_hi | (texture_hi & grad_hi) | (dark_wall & (signal_lo | a_hi))

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

    env = (union.astype(np.uint8) * 255)
    env = cv2.morphologyEx(env, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    env = cv2.dilate(env, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)), iterations=1)
    env = cv2.morphologyEx(env, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    env = fill_holes(env)

    strong_mask = (strong.astype(np.uint8) * 255)
    strong_mask = cv2.dilate(strong_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)), iterations=1)

    n, labels, stats, _ = cv2.connectedComponentsWithStats((env > 0).astype(np.uint8), connectivity=8)
    H, W = env.shape
    kept = np.zeros_like(env)
    rows = []
    for lab_id in range(1, n):
        area = int(stats[lab_id, cv2.CC_STAT_AREA])
        x = int(stats[lab_id, cv2.CC_STAT_LEFT])
        y = int(stats[lab_id, cv2.CC_STAT_TOP])
        w = int(stats[lab_id, cv2.CC_STAT_WIDTH])
        h = int(stats[lab_id, cv2.CC_STAT_HEIGHT])
        border_touch = (x == 0 or y == 0 or x + w >= W or y + h >= H)
        comp_mask = labels == lab_id
        strong_overlap = float((strong_mask[comp_mask] > 0).mean()) if area else 0.0
        keep = area >= 18000 and strong_overlap >= 0.04 and not (border_touch and area < 90000)
        if keep:
            kept[labels == lab_id] = 255
        rows.append({
            'component_id': lab_id,
            'area_px': area,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'border_touch': border_touch,
            'strong_overlap': round(strong_overlap, 6),
            'kept': keep,
        })

    kept = cv2.morphologyEx(kept, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    kept = cv2.morphologyEx(kept, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    kept = fill_holes(kept)
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
                if border_touch and bbox_cover > 0.70 and circularity > 0.80 and fill_ratio > 0.65:
                    continue
                score = (
                    1.35 * overlap_env
                    + 0.52 * circularity
                    + 0.18 * fill_ratio
                    + 0.32 * mean_signal
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


def merge_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict]]:
    kept: list[Candidate] = []
    trace: list[dict] = []
    for rank, cand in enumerate(sorted(candidates, key=lambda c: (c.score, c.area), reverse=True), start=1):
        action = 'keep'
        reason = 'new'
        replaced_index = None
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
                    replaced_index = idx + 1
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
            'replaced_slot': replaced_index,
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

    n, labels, stats, _ = cv2.connectedComponentsWithStats((support > 0).astype(np.uint8), connectivity=8)
    candidates: list[Candidate] = []
    rows = []
    rescue_labels = np.zeros_like(labels, dtype=np.uint16)
    kept_count = 0
    for label_id in range(1, n):
        mask = labels == label_id
        area, _, circularity, fill_ratio, border_touch, bbox_cover = mask_stats(mask)
        if area < 30000:
            continue
        if border_touch and bbox_cover > 0.75:
            continue
        if area > int(0.35 * hint_env.sum()):
            continue
        overlap_env = float(hint_env[mask].mean()) if area else 0.0
        overlap_core = float(hint_core[mask].mean()) if area else 0.0
        mean_signal = float(gray[mask].mean() / 255.0) if area else 0.0
        mean_grad = float(grad[mask].mean() / 255.0) if area else 0.0
        mean_texture = float(texture[mask].mean() / 255.0) if area else 0.0
        mean_blackhat = float(blackhat[mask].mean() / 255.0) if area else 0.0
        mean_dark = float(inv_gray[mask].mean() / 255.0) if area else 0.0
        if mean_texture < 0.12 and mean_blackhat < 0.08:
            continue
        score = 1.10 * overlap_env + 0.20 * fill_ratio + 0.25 * mean_dark + 0.24 * mean_texture + 0.18 * mean_blackhat + 0.12 * mean_grad + 0.08 * overlap_core
        cand = Candidate(
            mask=mask,
            branch='texture_rescue',
            diameter=0,
            score=float(score),
            area=area,
            circularity=float(circularity),
            fill_ratio=float(fill_ratio),
            overlap_env=float(overlap_env),
            overlap_core=float(overlap_core),
            mean_signal=float(mean_signal),
            mean_sat=0.0,
            border_touch=bool(border_touch),
            bbox_cover=float(bbox_cover),
        )
        candidates.append(cand)
        kept_count += 1
        rescue_labels[mask] = kept_count
        rows.append({
            'candidate_label': kept_count,
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
            'border_touch': bool(border_touch),
            'bbox_cover': round(float(bbox_cover), 6),
        })

    save_gray(step / 'step44_region_labels_16bit.png', rescue_labels)
    if rows:
        with (step / 'candidate_table.csv').open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    write_json(step / 'step49_rescue_summary.json', {'support_px': int((support > 0).sum()), 'candidate_count': len(rows)})
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
