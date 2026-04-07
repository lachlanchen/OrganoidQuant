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
    overlap_dilated: float
    support_overlap: float
    boundary_strength: float
    mean_signal: float
    mean_sat: float
    border_touch: bool
    bbox_cover: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='App65 custom single-image segmentation test using soft threshold priors plus multi-branch Cellpose.')
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


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = np.zeros_like(mask, dtype=bool)
    for lab_id in range(1, n):
        if int(stats[lab_id, cv2.CC_STAT_AREA]) >= min_area:
            out |= labels == lab_id
    return out


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


def boundary_strength(mask: np.ndarray, signal: np.ndarray, grad_mag: np.ndarray) -> float:
    mask_u8 = mask.astype(np.uint8)
    outer = cv2.dilate(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))) > 0
    inner = cv2.erode(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0
    band = np.logical_and(outer, ~inner)
    if not band.any():
        band = mask
    sig = float(signal[band].mean() / 255.0) if band.any() else 0.0
    grad = float(grad_mag[band].mean() / 255.0) if band.any() else 0.0
    return 0.55 * sig + 0.45 * grad


def build_threshold_prior(rgb: np.ndarray, gray: np.ndarray, signal: np.ndarray, out_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    step = out_dir / 'step02_threshold_prior'
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    a_chan = lab[..., 1]

    blur = cv2.GaussianBlur(gray, (0, 0), 5.0)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    grad_mag = cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    signal_p72 = int(np.percentile(signal, 72))
    signal_p80 = int(np.percentile(signal, 80))
    sat_p74 = int(np.percentile(sat, 74))
    a_p74 = int(np.percentile(a_chan, 74))
    blackhat_p84 = int(np.percentile(blackhat, 84))
    grad_p60 = int(np.percentile(grad_mag, 60))
    otsu_mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1] > 0

    signal_lo = signal >= signal_p72
    signal_hi = signal >= signal_p80
    sat_hi = sat >= sat_p74
    a_hi = a_chan >= a_p74
    dark_hi = blackhat >= blackhat_p84
    grad_hi = grad_mag >= grad_p60

    union = signal_lo | sat_hi | otsu_mask | dark_hi
    strong = signal_hi | (signal_lo & (a_hi | sat_hi)) | (dark_hi & grad_hi)
    strong = remove_small_components(strong, 1500)

    dilated_seeds = cv2.dilate((strong.astype(np.uint8) * 255), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (121, 121))) > 0
    env = union & dilated_seeds
    env = cv2.morphologyEx((env.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (29, 29)))
    env = cv2.morphologyEx(env, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    env = fill_holes(env)
    env = remove_small_components(env > 0, 22000)
    env_u8 = (env.astype(np.uint8) * 255)
    core = cv2.erode(env_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35))) > 0
    if not core.any():
        core = cv2.erode(env_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))) > 0
    dilated = cv2.dilate(env_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (81, 81))) > 0

    support = ((signal_lo & grad_hi) | (dark_hi & (grad_hi | a_hi)))
    support = remove_small_components(support, 600)
    support = cv2.morphologyEx((support.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0

    save_gray(step / 'step10_signal.png', signal)
    save_gray(step / 'step11_gray.png', gray)
    save_gray(step / 'step12_saturation.png', sat)
    save_gray(step / 'step13_lab_a.png', a_chan)
    save_gray(step / 'step14_blackhat.png', blackhat)
    save_gray(step / 'step15_grad_mag.png', grad_mag)
    save_binary(step / 'step20_signal_lo.png', signal_lo)
    save_binary(step / 'step21_signal_hi.png', signal_hi)
    save_binary(step / 'step22_sat_hi.png', sat_hi)
    save_binary(step / 'step23_a_hi.png', a_hi)
    save_binary(step / 'step24_dark_hi.png', dark_hi)
    save_binary(step / 'step25_grad_hi.png', grad_hi)
    save_binary(step / 'step26_union_raw.png', union)
    save_binary(step / 'step27_strong_raw.png', strong)
    save_binary(step / 'step28_seed_dilated.png', dilated_seeds)
    save_binary(step / 'step30_hint_envelope.png', env)
    save_binary(step / 'step31_hint_core.png', core)
    save_binary(step / 'step32_hint_dilated.png', dilated)
    save_binary(step / 'step33_support_mask.png', support)

    overlay = rgb.copy()
    overlay[env] = (0.55 * overlay[env] + 0.45 * np.array([255, 190, 0])).astype(np.uint8)
    outline = cv2.Canny(env_u8, 50, 150)
    overlay[outline > 0] = (255, 0, 0)
    support_overlay = rgb.copy()
    support_overlay[support] = (0.60 * support_overlay[support] + 0.40 * np.array([0, 220, 255])).astype(np.uint8)
    save_rgb(step / 'step34_hint_overlay.png', overlay)
    save_rgb(step / 'step35_support_overlay.png', support_overlay)

    meta = {
        'thresholds': {
            'signal_p72': signal_p72,
            'signal_p80': signal_p80,
            'sat_p74': sat_p74,
            'a_p74': a_p74,
            'blackhat_p84': blackhat_p84,
            'grad_p60': grad_p60,
        },
        'note': 'Hint is a weak prior only. Final masks may extend beyond the hint envelope if image evidence is strong.',
    }
    write_json(step / 'step36_prior_summary.json', meta)
    return env, core, dilated, support, meta


def build_branch_inputs(gray: np.ndarray, signal: np.ndarray) -> list[tuple[str, np.ndarray, float]]:
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(16, 16)).apply(gray)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    dark = cv2.normalize((0.62 * signal.astype(np.float32) + 0.38 * blackhat.astype(np.float32)), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return [
        ('raw', gray, 0.08),
        ('clahe', clahe, 0.05),
        ('dark', dark, 0.04),
    ]


def run_cellpose_branches(
    model,
    rgb: np.ndarray,
    gray: np.ndarray,
    signal: np.ndarray,
    hint_env: np.ndarray,
    hint_core: np.ndarray,
    hint_dilated: np.ndarray,
    support_mask: np.ndarray,
    diameters: list[int],
    out_dir: Path,
) -> list[Candidate]:
    step_raw = out_dir / 'step03_cellpose_multibranch'
    sat = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1]
    gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    grad_mag = cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    inputs = build_branch_inputs(gray, signal)
    for idx, (name, img, _) in enumerate(inputs):
        save_gray(step_raw / f'step0{idx}_input_{name}.png', img)

    candidates: list[Candidate] = []
    branch_rows = []
    for branch_name, branch_img, branch_bonus in inputs:
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
                overlap_dilated = float(hint_dilated[mask].mean()) if area else 0.0
                support_overlap = float(support_mask[mask].mean()) if area else 0.0
                mean_signal = float(signal[mask].mean() / 255.0) if area else 0.0
                mean_sat = float(sat[mask].mean() / 255.0) if area else 0.0
                b_strength = boundary_strength(mask, signal, grad_mag)

                if border_touch and bbox_cover > 0.70 and circularity > 0.82 and fill_ratio > 0.68:
                    continue
                if overlap_env < 0.08 and overlap_dilated < 0.18 and support_overlap < 0.14 and b_strength < 0.12:
                    continue
                if area < 40000 and overlap_core < 0.03 and support_overlap < 0.20 and b_strength < 0.16:
                    continue
                if branch_name != 'raw' and area < 25000 and support_overlap < 0.28 and b_strength < 0.20:
                    continue
                if area > 1200000 and overlap_dilated < 0.22 and support_overlap < 0.18:
                    continue

                score = (
                    0.85 * overlap_env
                    + 0.35 * overlap_dilated
                    + 0.55 * support_overlap
                    + 0.55 * b_strength
                    + 0.35 * circularity
                    + 0.16 * fill_ratio
                    + 0.25 * mean_signal
                    + branch_bonus
                )
                if not border_touch:
                    score += 0.06
                if 50000 <= area <= 900000:
                    score += 0.05
                if branch_name == 'clahe' and fill_ratio < 0.45:
                    score -= 0.03
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
                    overlap_dilated=float(overlap_dilated),
                    support_overlap=float(support_overlap),
                    boundary_strength=float(b_strength),
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
                    'overlap_dilated': round(float(overlap_dilated), 6),
                    'support_overlap': round(float(support_overlap), 6),
                    'boundary_strength': round(float(b_strength), 6),
                    'mean_signal': round(float(mean_signal), 6),
                    'mean_sat': round(float(mean_sat), 6),
                    'border_touch': bool(border_touch),
                    'bbox_cover': round(float(bbox_cover), 6),
                })
            save_gray(step_raw / f'{branch_name}_diameter_{d:04d}_labels_16bit.png', branch_label)

    with (step_raw / 'candidate_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(branch_rows[0].keys()) if branch_rows else ['branch'])
        writer.writeheader()
        if branch_rows:
            writer.writerows(branch_rows)
    write_json(step_raw / 'branch_summary.json', {
        'diameters': diameters,
        'branches': [x[0] for x in inputs],
        'candidate_count': len(branch_rows),
        'note': 'Hint is used as a score prior. Candidate masks are not clipped to the hint.',
    })
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
    for rank, cand in enumerate(sorted(candidates, key=lambda c: (c.score, c.boundary_strength, c.area), reverse=True), start=1):
        action = 'keep'
        reason = 'new'
        replaced_index = None
        for idx, prev in enumerate(kept):
            ov = overlap_small(cand.mask, prev.mask)
            j = iou(cand.mask, prev.mask)
            if ov > 0.78 or j > 0.55:
                better_split = (
                    cand.circularity > prev.circularity + 0.05
                    and cand.area < prev.area * 0.92
                    and cand.boundary_strength >= prev.boundary_strength - 0.02
                )
                clearly_better = (
                    cand.score > prev.score * 1.03
                    or (cand.boundary_strength > prev.boundary_strength + 0.06 and cand.area > prev.area * 0.85)
                )
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
            'boundary_strength': round(cand.boundary_strength, 6),
            'action': action,
            'reason': reason,
            'replaced_slot': replaced_index,
        })
    return kept, trace


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

    hint_env, hint_core, hint_dilated, support_mask, hint_meta = build_threshold_prior(rgb, gray, signal, out_dir)

    model = models.CellposeModel(gpu=bool(args.gpu))
    candidates = run_cellpose_branches(model, rgb, gray, signal, hint_env, hint_core, hint_dilated, support_mask, diameters, out_dir)

    step04 = out_dir / 'step04_merge'
    step04.mkdir(parents=True, exist_ok=True)
    kept, trace = merge_candidates(candidates)
    with (step04 / 'merge_trace.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(trace[0].keys()) if trace else ['rank'])
        writer.writeheader()
        if trace:
            writer.writerows(trace)

    labels, colors, overlay = build_final_outputs(rgb, kept)
    step05 = out_dir / 'step05_final'
    save_gray(step05 / 'step50_final_mask_16bit.png', labels)
    save_rgb(step05 / 'step51_final_instance_rgb.png', colors)
    save_rgb(step05 / 'step52_final_overlay.png', overlay)
    save_gray(step05 / 'step53_final_signal.png', signal)
    save_binary(step05 / 'step54_final_hint_envelope.png', hint_env)
    save_binary(step05 / 'step55_final_hint_core.png', hint_core)
    save_binary(step05 / 'step56_final_hint_dilated.png', hint_dilated)
    save_binary(step05 / 'step57_final_support_mask.png', support_mask)

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
            'overlap_dilated': round(cand.overlap_dilated, 6),
            'support_overlap': round(cand.support_overlap, 6),
            'boundary_strength': round(cand.boundary_strength, 6),
            'mean_signal': round(cand.mean_signal, 6),
            'mean_sat': round(cand.mean_sat, 6),
            'border_touch': cand.border_touch,
            'bbox_cover': round(cand.bbox_cover, 6),
        })
    with (step05 / 'step58_final_object_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['final_label'])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    summary = {
        'source_tif': str(tif),
        'diameters_px': diameters,
        'candidate_count_before_merge': len(candidates),
        'final_count': int(labels.max()),
        'hint_note': hint_meta['note'],
        'final_objects': rows,
        'notes': {
            'goal': 'Keep v1 fast and conservative, but turn the hint into a soft prior so strong masks can extend outside it.',
            'signal_component_used': False,
            'raw_cellpose_only': False,
            'branches': ['raw', 'clahe', 'dark'],
        },
    }
    write_json(step05 / 'step59_final_summary.json', summary)
    write_json(out_dir / 'manifest.json', {
        'source_tif': str(tif),
        'output_root': str(out_dir),
        'steps': ['step01_input', 'step02_threshold_prior', 'step03_cellpose_multibranch', 'step04_merge', 'step05_final'],
        'summary': str((step05 / 'step59_final_summary.json').resolve()),
    })
    print(json.dumps({'output_root': str(out_dir), 'final_count': int(labels.max())}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
