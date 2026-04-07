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
    source_branch: str
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
    droplet_reject: bool


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='App81 custom single-image segmentation test using threshold hints plus Cellpose.')
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


def component_overlay(rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    out = np.zeros_like(rgb)
    rng = np.random.default_rng(123)
    for lab in range(1, int(labels.max()) + 1):
        color = rng.integers(40, 255, size=3, dtype=np.uint8)
        out[labels == lab] = color
    overlay = cv2.addWeighted(rgb, 0.72, out, 0.60, 0)
    edges = cv2.Canny((labels > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (255, 0, 0)
    return overlay


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def build_threshold_hint(rgb: np.ndarray, gray: np.ndarray, signal: np.ndarray, out_dir: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    step = out_dir / 'step02_threshold_hint'
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    a_chan = lab[..., 1]

    signal_p80 = int(np.percentile(signal, 80))
    signal_p85 = int(np.percentile(signal, 85))
    sat_p80 = int(np.percentile(sat, 80))
    a_p80 = int(np.percentile(a_chan, 80))

    signal80 = signal >= signal_p80
    signal85 = signal >= signal_p85
    sat80 = sat >= sat_p80
    a80 = a_chan >= a_p80

    union = signal80 | sat80
    strong = signal85 | (signal80 & a80)

    save_gray(step / 'step10_signal.png', signal)
    save_gray(step / 'step11_gray.png', gray)
    save_gray(step / 'step12_saturation.png', sat)
    save_gray(step / 'step13_lab_a.png', a_chan)
    save_binary(step / 'step20_signal_p80.png', signal80)
    save_binary(step / 'step21_signal_p85.png', signal85)
    save_binary(step / 'step22_sat_p80.png', sat80)
    save_binary(step / 'step23_a_p80.png', a80)
    save_binary(step / 'step24_union_raw.png', union)
    save_binary(step / 'step25_strong_raw.png', strong)

    env = (union.astype(np.uint8) * 255)
    env = cv2.morphologyEx(env, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    env = cv2.morphologyEx(env, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))

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
        keep = area >= 40000 and not (border_touch and area < 300000)
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
            'kept': keep,
        })

    kept = cv2.morphologyEx(kept, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61)))
    kept = cv2.morphologyEx(kept, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    kept = fill_holes(kept)

    core = cv2.erode(kept, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    if core.sum() == 0:
        core = cv2.erode(kept, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))

    save_binary(step / 'step30_hint_envelope.png', kept > 0)
    save_binary(step / 'step31_hint_core.png', core > 0)
    overlay = rgb.copy()
    overlay[(kept > 0)] = (0.55 * overlay[(kept > 0)] + 0.45 * np.array([255, 190, 0])).astype(np.uint8)
    outline = cv2.Canny(kept, 50, 150)
    overlay[outline > 0] = (255, 0, 0)
    save_rgb(step / 'step32_hint_overlay.png', overlay)
    write_json(step / 'step33_hint_components.json', {'components': rows, 'thresholds': {'signal_p80': signal_p80, 'signal_p85': signal_p85, 'sat_p80': sat_p80, 'a_p80': a_p80}})
    return kept > 0, core > 0, {'components': rows, 'thresholds': {'signal_p80': signal_p80, 'signal_p85': signal_p85, 'sat_p80': sat_p80, 'a_p80': a_p80}}


def run_cellpose_branches(model, rgb: np.ndarray, gray: np.ndarray, hint_env: np.ndarray, hint_core: np.ndarray, diameters: list[int], out_dir: Path) -> list[Candidate]:
    step_raw = out_dir / 'step03_cellpose_raw'
    step_masked = out_dir / 'step04_cellpose_masked'
    masked_gray = gray.copy()
    masked_gray[~hint_env] = np.median(gray).astype(gray.dtype)

    candidates: list[Candidate] = []
    for branch_name, img, step_dir, branch_bonus in [
        ('raw', gray, step_raw, 0.08),
        ('masked', masked_gray, step_masked, 0.04),
    ]:
        save_gray(step_dir / 'step00_input.png', img)
        branch_rows = []
        label_gallery = []
        for d in diameters:
            masks, *_ = model.eval(img, diameter=float(d), channels=[0, 0], normalize=True, do_3D=False)
            masks = masks.astype(np.uint16)
            branch_label = np.zeros_like(masks, dtype=np.uint16)
            kept_count = 0
            for lab_id in range(1, int(masks.max()) + 1):
                mask = masks == lab_id
                area, _, circularity, fill_ratio, border_touch, bbox_cover = mask_stats(mask)
                if area < 15000:
                    continue
                overlap_env = float(hint_env[mask].mean()) if area else 0.0
                if overlap_env < 0.55:
                    continue
                core_overlap = float(hint_core[mask].mean()) if area else 0.0
                sat = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1]
                mean_sat = float(sat[mask].mean() / 255.0) if area else 0.0
                mean_signal = float(gray[mask].mean() / 255.0) if area else 0.0
                droplet_reject = False
                if border_touch and bbox_cover > 0.70 and circularity > 0.72 and fill_ratio > 0.48:
                    droplet_reject = True
                if border_touch and overlap_env < 0.80 and area > 120000:
                    droplet_reject = True
                if droplet_reject:
                    continue
                score = 1.60 * overlap_env + 0.35 * circularity + 0.18 * fill_ratio + 0.35 * mean_signal + branch_bonus
                if not border_touch:
                    score += 0.10
                if area > 50000:
                    score += 0.05
                candidates.append(Candidate(
                    mask=mask,
                    source_branch=branch_name,
                    diameter=d,
                    score=float(score),
                    area=area,
                    circularity=float(circularity),
                    fill_ratio=float(fill_ratio),
                    overlap_env=float(overlap_env),
                    overlap_core=float(core_overlap),
                    mean_signal=float(mean_signal),
                    mean_sat=float(mean_sat),
                    border_touch=bool(border_touch),
                    bbox_cover=float(bbox_cover),
                    droplet_reject=False,
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
                    'overlap_core': round(float(core_overlap), 6),
                    'mean_signal': round(float(mean_signal), 6),
                    'mean_sat': round(float(mean_sat), 6),
                    'border_touch': bool(border_touch),
                    'bbox_cover': round(float(bbox_cover), 6),
                })
            save_gray(step_dir / f'diameter_{d:04d}_labels_16bit.png', branch_label)
            label_gallery.append((d, branch_label))
        with (step_dir / 'candidate_table.csv').open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=list(branch_rows[0].keys()) if branch_rows else ['branch', 'diameter_px'])
            writer.writeheader()
            if branch_rows:
                writer.writerows(branch_rows)
        write_json(step_dir / 'branch_summary.json', {'branch': branch_name, 'diameters': diameters, 'candidate_count': len(branch_rows)})
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
                if cand.score > prev.score * 1.03 or cand.area > prev.area * 1.08:
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
            'branch': cand.source_branch,
            'diameter_px': cand.diameter,
            'area_px': cand.area,
            'score': round(cand.score, 6),
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

    hint_env, hint_core, hint_meta = build_threshold_hint(rgb, gray, signal, out_dir)

    model = models.CellposeModel(gpu=bool(args.gpu))
    candidates = run_cellpose_branches(model, rgb, gray, hint_env, hint_core, diameters, out_dir)

    step05 = out_dir / 'step05_merge'
    step05.mkdir(parents=True, exist_ok=True)
    kept, trace = merge_candidates(candidates)
    with (step05 / 'merge_trace.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(trace[0].keys()) if trace else ['rank'])
        writer.writeheader()
        if trace:
            writer.writerows(trace)

    labels, colors, overlay = build_final_outputs(rgb, kept)
    step06 = out_dir / 'step06_final'
    save_gray(step06 / 'step60_final_mask_16bit.png', labels)
    save_rgb(step06 / 'step61_final_instance_rgb.png', colors)
    save_rgb(step06 / 'step62_final_overlay.png', overlay)
    save_gray(step06 / 'step63_final_signal.png', signal)
    save_binary(step06 / 'step64_final_hint_envelope.png', hint_env)
    save_binary(step06 / 'step65_final_hint_core.png', hint_core)

    rows = []
    for idx, cand in enumerate(sorted(kept, key=lambda c: c.area, reverse=True), start=1):
        rows.append({
            'final_label': idx,
            'branch': cand.source_branch,
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
    with (step06 / 'step66_final_object_table.csv').open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['final_label'])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    summary = {
        'source_tif': str(tif),
        'diameters_px': diameters,
        'candidate_count_before_merge': len(candidates),
        'final_count': int(labels.max()),
        'hint_component_count': int(sum(1 for x in hint_meta['components'] if x['kept'])),
        'final_objects': rows,
        'notes': {
            'goal': 'Use threshold hint envelope to gate Cellpose and suppress fragmental signal-component segmentation.',
            'droplet_avoidance': 'Reject border-dominated large circular candidates and require substantial overlap with threshold hint envelope.',
            'signal_recovery_used': False,
        },
    }
    write_json(step06 / 'step67_final_summary.json', summary)
    write_json(out_dir / 'manifest.json', {
        'source_tif': str(tif),
        'output_root': str(out_dir),
        'steps': ['step01_input', 'step02_threshold_hint', 'step03_cellpose_raw', 'step04_cellpose_masked', 'step05_merge', 'step06_final'],
        'summary': str((step06 / 'step67_final_summary.json').resolve()),
    })
    print(json.dumps({'output_root': str(out_dir), 'final_count': int(labels.max())}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
