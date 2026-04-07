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
    support_overlap: float
    boundary_strength: float
    interior_texture: float
    mean_signal: float
    border_touch: bool
    bbox_cover: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='App65 v3 direct brightfield Cellpose test.')
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


def compute_local_std(gray: np.ndarray, ksize: int = 31) -> np.ndarray:
    gray_f = gray.astype(np.float32)
    mean = cv2.GaussianBlur(gray_f, (0, 0), ksize / 6.0)
    mean_sq = cv2.GaussianBlur(gray_f * gray_f, (0, 0), ksize / 6.0)
    var = np.maximum(mean_sq - mean * mean, 0.0)
    return cv2.normalize(np.sqrt(var), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def build_direct_evidence(rgb: np.ndarray, gray: np.ndarray, signal: np.ndarray, out_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    step = out_dir / 'step02_brightfield_evidence'
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(16, 16)).apply(gray)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    grad_mag = cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    local_std = compute_local_std(gray)
    wall_emphasis = cv2.normalize(
        0.48 * clahe.astype(np.float32)
        + 0.34 * blackhat.astype(np.float32)
        + 0.18 * grad_mag.astype(np.float32),
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)

    signal_hi = signal >= int(np.percentile(signal, 76))
    blackhat_hi = blackhat >= int(np.percentile(blackhat, 82))
    grad_hi = grad_mag >= int(np.percentile(grad_mag, 58))
    texture_hi = local_std >= int(np.percentile(local_std, 68))
    support_mask = ((grad_hi & (blackhat_hi | signal_hi)) | (blackhat_hi & texture_hi))
    support_mask = cv2.morphologyEx((support_mask.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0

    save_gray(step / 'step10_gray.png', gray)
    save_gray(step / 'step11_signal.png', signal)
    save_gray(step / 'step12_clahe.png', clahe)
    save_gray(step / 'step13_blackhat.png', blackhat)
    save_gray(step / 'step14_grad_mag.png', grad_mag)
    save_gray(step / 'step15_local_std.png', local_std)
    save_gray(step / 'step16_wall_emphasis.png', wall_emphasis)
    save_binary(step / 'step20_support_mask.png', support_mask)
    support_overlay = rgb.copy()
    support_overlay[support_mask] = (0.60 * support_overlay[support_mask] + 0.40 * np.array([0, 220, 255])).astype(np.uint8)
    save_rgb(step / 'step21_support_overlay.png', support_overlay)
    write_json(step / 'step22_evidence_summary.json', {
        'note': 'This v3 path does not build or use a hint envelope. Cellpose runs directly on brightfield-derived inputs.',
    })
    return clahe, wall_emphasis, grad_mag, support_mask, {'note': 'No hint envelope used'}


def build_branch_inputs(gray: np.ndarray, clahe: np.ndarray, wall_emphasis: np.ndarray) -> list[tuple[str, np.ndarray, float]]:
    return [
        ('raw', gray, 0.08),
        ('clahe', clahe, 0.05),
        ('wall', wall_emphasis, 0.04),
    ]


def boundary_strength(mask: np.ndarray, blackhat: np.ndarray, grad_mag: np.ndarray) -> float:
    mask_u8 = mask.astype(np.uint8)
    outer = cv2.dilate(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))) > 0
    inner = cv2.erode(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0
    band = np.logical_and(outer, ~inner)
    if not band.any():
        band = mask
    wall = float(blackhat[band].mean() / 255.0) if band.any() else 0.0
    grad = float(grad_mag[band].mean() / 255.0) if band.any() else 0.0
    return 0.58 * wall + 0.42 * grad


def run_cellpose_branches(
    model,
    rgb: np.ndarray,
    gray: np.ndarray,
    signal: np.ndarray,
    clahe: np.ndarray,
    wall_emphasis: np.ndarray,
    grad_mag: np.ndarray,
    support_mask: np.ndarray,
    diameters: list[int],
    out_dir: Path,
) -> list[Candidate]:
    step = out_dir / 'step03_cellpose_multibranch'
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    texture = compute_local_std(gray)
    inputs = build_branch_inputs(gray, clahe, wall_emphasis)
    for idx, (name, img, _) in enumerate(inputs):
        save_gray(step / f'step0{idx}_input_{name}.png', img)

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
                support_overlap = float(support_mask[mask].mean()) if area else 0.0
                b_strength = boundary_strength(mask, blackhat, grad_mag)
                interior_texture = float(texture[mask].mean() / 255.0) if area else 0.0
                mean_signal = float(signal[mask].mean() / 255.0) if area else 0.0

                if border_touch and bbox_cover > 0.70 and circularity > 0.84 and fill_ratio > 0.70 and interior_texture < 0.20:
                    continue
                if b_strength < 0.10 and support_overlap < 0.08:
                    continue
                if area < 25000 and b_strength < 0.16 and support_overlap < 0.18:
                    continue
                if branch_name != 'raw' and area < 18000 and support_overlap < 0.24:
                    continue
                if area > 1200000 and b_strength < 0.16 and support_overlap < 0.16:
                    continue

                score = (
                    0.75 * b_strength
                    + 0.55 * support_overlap
                    + 0.30 * circularity
                    + 0.18 * fill_ratio
                    + 0.18 * interior_texture
                    + 0.18 * mean_signal
                    + branch_bonus
                )
                if not border_touch:
                    score += 0.05
                if 50000 <= area <= 900000:
                    score += 0.04
                if branch_name == 'wall' and fill_ratio < 0.42:
                    score -= 0.03
                if area > 1100000:
                    score -= 0.08

                candidates.append(Candidate(
                    mask=mask,
                    branch=branch_name,
                    diameter=d,
                    score=float(score),
                    area=area,
                    circularity=float(circularity),
                    fill_ratio=float(fill_ratio),
                    support_overlap=float(support_overlap),
                    boundary_strength=float(b_strength),
                    interior_texture=float(interior_texture),
                    mean_signal=float(mean_signal),
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
                    'support_overlap': round(float(support_overlap), 6),
                    'boundary_strength': round(float(b_strength), 6),
                    'interior_texture': round(float(interior_texture), 6),
                    'mean_signal': round(float(mean_signal), 6),
                    'border_touch': bool(border_touch),
                    'bbox_cover': round(float(bbox_cover), 6),
                })
            save_gray(step / f'{branch_name}_diameter_{d:04d}_labels_16bit.png', branch_label)

    with (step / 'candidate_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(branch_rows[0].keys()) if branch_rows else ['branch'])
        writer.writeheader()
        if branch_rows:
            writer.writerows(branch_rows)
    write_json(step / 'branch_summary.json', {
        'diameters': diameters,
        'branches': [x[0] for x in inputs],
        'candidate_count': len(branch_rows),
        'note': 'Direct brightfield segmentation. No hint envelope or hint clipping used.',
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

    clahe, wall_emphasis, grad_mag, support_mask, meta = build_direct_evidence(rgb, gray, signal, out_dir)

    model = models.CellposeModel(gpu=bool(args.gpu))
    candidates = run_cellpose_branches(model, rgb, gray, signal, clahe, wall_emphasis, grad_mag, support_mask, diameters, out_dir)

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
    save_binary(step05 / 'step54_final_support_mask.png', support_mask)

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
            'support_overlap': round(cand.support_overlap, 6),
            'boundary_strength': round(cand.boundary_strength, 6),
            'interior_texture': round(cand.interior_texture, 6),
            'mean_signal': round(cand.mean_signal, 6),
            'border_touch': cand.border_touch,
            'bbox_cover': round(cand.bbox_cover, 6),
        })
    with (step05 / 'step55_final_object_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['final_label'])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    summary = {
        'source_tif': str(tif),
        'diameters_px': diameters,
        'candidate_count_before_merge': len(candidates),
        'final_count': int(labels.max()),
        'note': meta['note'],
        'final_objects': rows,
        'notes': {
            'goal': 'Direct brightfield multi-branch Cellpose for App65 without hint-gated masks.',
            'signal_component_used': False,
            'branches': ['raw', 'clahe', 'wall'],
        },
    }
    write_json(step05 / 'step56_final_summary.json', summary)
    write_json(out_dir / 'manifest.json', {
        'source_tif': str(tif),
        'output_root': str(out_dir),
        'steps': ['step01_input', 'step02_brightfield_evidence', 'step03_cellpose_multibranch', 'step04_merge', 'step05_final'],
        'summary': str((step05 / 'step56_final_summary.json').resolve()),
    })
    print(json.dumps({'output_root': str(out_dir), 'final_count': int(labels.max())}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
