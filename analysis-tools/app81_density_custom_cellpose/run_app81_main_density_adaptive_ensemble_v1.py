#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
import traceback

import cv2
import numpy as np

BASE_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_density_multiscale_cellpose')
APP80_DIR = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose')
for path in (BASE_DIR, APP80_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_app81_main_density_large_recovery as app81_base  # noqa: E402
import run_multiscale_dateaware_cellpose as seg  # noqa: E402

CONDITION_ORDER = app81_base.CONDITION_ORDER
resolve_conditions = app81_base.resolve_conditions
discover_images = app81_base.discover_images
aggregate_segmentation_metrics = app81_base.aggregate_segmentation_metrics
write_per_image_csv = app81_base.write_per_image_csv
write_daily_summary = app81_base.write_daily_summary
stage_and_diameters = app81_base.stage_and_diameters
natural_key = app81_base.natural_key


# Threshold / watershed is primary. Cellpose is used only as a global secondary source and local refiner.

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--src-root', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--conditions', default=','.join(CONDITION_ORDER))
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--checkpoint-every', type=int, default=10)
    p.add_argument('--max-errors', type=int, default=50)
    p.add_argument('--limit', type=int)
    return p.parse_args()


def save_gray(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def save_binary(path: Path, mask: np.ndarray) -> None:
    save_gray(path, (mask.astype(np.uint8) * 255))


def local_std(gray: np.ndarray, sigma: float = 5.0) -> np.ndarray:
    g = gray.astype(np.float32)
    mean = cv2.GaussianBlur(g, (0, 0), sigma)
    mean_sq = cv2.GaussianBlur(g * g, (0, 0), sigma)
    var = np.maximum(mean_sq - mean * mean, 0.0)
    out = np.sqrt(var)
    return cv2.normalize(out, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def norm_combo(*parts: tuple[np.ndarray, float]) -> np.ndarray:
    acc = None
    for arr, wt in parts:
        arrf = arr.astype(np.float32)
        acc = arrf * wt if acc is None else acc + arrf * wt
    return cv2.normalize(acc, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def fill_holes(mask: np.ndarray) -> np.ndarray:
    return seg.fill_holes((mask.astype(np.uint8) * 255)) > 0


def remove_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(mask, dtype=bool)
    for lab in range(1, n):
        if int(stats[lab, cv2.CC_STAT_AREA]) >= min_area:
            keep[labels == lab] = True
    return keep


def build_maps(gray: np.ndarray) -> dict[str, np.ndarray]:
    clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(12, 12)).apply(gray)
    inv = 255 - clahe
    bh_small = cv2.morphologyEx(clahe, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
    bh_big = cv2.morphologyEx(clahe, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    gx = cv2.Scharr(clahe, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(clahe, cv2.CV_32F, 0, 1)
    grad = cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    lap = cv2.Laplacian(clahe, cv2.CV_32F, ksize=3)
    lap = cv2.normalize(np.abs(lap), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    tex = local_std(clahe)
    rim = norm_combo((bh_small, 0.40), (grad, 0.32), (lap, 0.10), (tex, 0.18))
    body = norm_combo((inv, 0.36), (bh_big, 0.24), (tex, 0.24), (grad, 0.16))
    return {
        'clahe': clahe,
        'inv': inv,
        'bh_small': bh_small,
        'bh_big': bh_big,
        'grad': grad,
        'lap': lap,
        'tex': tex,
        'rim': rim,
        'body': body,
    }


def build_threshold_masks(signal: np.ndarray, support: np.ndarray, maps: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    rim = maps['rim']
    body = maps['body']

    rim_thr = int(np.percentile(rim, 86))
    body_seed_thr = int(np.percentile(body, 90))
    body_support_thr = int(np.percentile(body, 76))

    rim_bin = rim >= rim_thr
    rim_bin = cv2.morphologyEx((rim_bin.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    rim_bin = cv2.morphologyEx((rim_bin.astype(np.uint8) * 255), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0

    body_seed = body >= body_seed_thr
    body_seed = cv2.morphologyEx((body_seed.astype(np.uint8) * 255), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0

    body_support = body >= body_support_thr
    body_support = cv2.morphologyEx((body_support.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))) > 0
    body_support = body_support | (support > 0)

    grown = (body_seed.astype(np.uint8) * 255)
    allow = body_support.astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    for _ in range(32):
        nxt = cv2.bitwise_and(cv2.dilate(grown, kernel), allow)
        if np.array_equal(nxt, grown):
            break
        grown = nxt
    mass_mask = fill_holes(grown > 0)
    mass_mask = cv2.morphologyEx((mass_mask.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))) > 0

    cyst_mask = fill_holes(rim_bin)
    cyst_mask = cv2.morphologyEx((cyst_mask.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0

    union = remove_small(mass_mask | cyst_mask, 900)
    return {
        'rim_bin': rim_bin,
        'body_seed': body_seed,
        'body_support': body_support,
        'mass_mask': mass_mask,
        'cyst_mask': cyst_mask,
        'union': union,
    }


def boundary_strength(mask: np.ndarray, rim_score: np.ndarray) -> float:
    mask_u8 = mask.astype(np.uint8)
    outer = cv2.dilate(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))) > 0
    inner = cv2.erode(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    band = np.logical_and(outer, ~inner)
    if not band.any():
        band = mask
    return float(rim_score[band].mean() / 255.0) if band.any() else 0.0


def body_fraction(mask: np.ndarray, body_support: np.ndarray) -> float:
    return float(body_support[mask].mean()) if mask.any() else 0.0


def bbox_cover(mask: np.ndarray) -> float:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return 0.0
    h, w = mask.shape
    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    return max(bw / w if w else 0.0, bh / h if h else 0.0)


def split_component(mask: np.ndarray, clahe: np.ndarray, body_seed: np.ndarray) -> list[np.ndarray]:
    area = int(mask.sum())
    if area <= 0:
        return []
    if area > 220000:
        return [mask]

    ys, xs = np.where(mask)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    pad = 12
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(mask.shape[1], x1 + pad)
    y1 = min(mask.shape[0], y1 + pad)
    crop_mask = mask[y0:y1, x0:x1]
    crop_seed = body_seed[y0:y1, x0:x1] & crop_mask
    dist = cv2.distanceTransform(crop_mask.astype(np.uint8), cv2.DIST_L2, 5)
    if float(dist.max()) <= 0.0:
        return [mask]

    sure_fg = dist > float(dist.max()) * 0.42
    sure_fg |= crop_seed
    sure_fg = cv2.morphologyEx((sure_fg.astype(np.uint8) * 255), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    n, markers = cv2.connectedComponents(sure_fg.astype(np.uint8), connectivity=8)
    if n <= 2:
        return [mask]

    markers = markers.astype(np.int32) + 1
    markers[~crop_mask] = 0
    ws = cv2.watershed(cv2.cvtColor(clahe[y0:y1, x0:x1], cv2.COLOR_GRAY2RGB), markers)
    out = []
    for lab in range(2, int(ws.max()) + 1):
        sub = ws == lab
        if int(sub.sum()) < 900:
            continue
        full = np.zeros_like(mask, dtype=bool)
        full[y0:y1, x0:x1] = sub
        out.append(full)
    return out if out else [mask]


def threshold_candidate(mask: np.ndarray, stage: str, signal: np.ndarray, support: np.ndarray, maps: dict[str, np.ndarray], body_support: np.ndarray, source: str) -> seg.Candidate | None:
    area, _, circularity, fill_ratio = seg.mask_stats(mask)
    if area < 900:
        return None
    h, w = mask.shape
    frac = area / float(h * w)
    b_strength = boundary_strength(mask, maps['rim'])
    supp_ratio = float((support[mask] > 0).mean()) if area else 0.0
    body_frac = body_fraction(mask, body_support)
    mean_signal = float(maps['body'][mask].mean() / 255.0) if area else 0.0
    cover = bbox_cover(mask)
    border_touch = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())

    if b_strength < 0.10:
        return None
    if area < 3000 and (circularity < 0.18 or fill_ratio < 0.14):
        return None
    if area < 8000 and body_frac < 0.03 and b_strength < 0.18:
        return None

    if area > 120000 and circularity > 0.74 and fill_ratio > 0.52 and body_frac < 0.10:
        return None
    if frac > 0.45 and circularity > 0.78 and body_frac < 0.12:
        return None
    if border_touch and frac > 0.18 and body_frac < 0.15:
        return None
    if cover > 0.88 and body_frac < 0.10:
        return None
    if area > 140000 and body_frac < 0.16 and mean_signal < 0.30:
        return None

    stage_bonus = {
        'early_cluster': 0.04,
        'cystic_early': 0.08,
        'cystic_mid': 0.08,
        'fused_large': 0.12,
        'differentiated_irregular': 0.10,
    }.get(stage, 0.0)
    score = 1.55 * b_strength + 0.95 * supp_ratio + 0.70 * body_frac + 0.35 * mean_signal + 0.22 * fill_ratio + stage_bonus
    if 4000 <= area <= 220000:
        score += 0.04
    if source == 'mass':
        score += 0.06
    if area > 200000 and body_frac > 0.20:
        score += 0.08
    pseudo_d = max(24, int(round(math.sqrt((4.0 * area) / math.pi))))
    return seg.Candidate(mask=mask, score=float(score), area=area, diameter=pseudo_d, branch_rank=0, support_ratio=float(supp_ratio), mean_signal=float(mean_signal), edge_strength=float(b_strength), circularity=float(circularity), source=f'threshold_{source}')


def global_cellpose_candidates(model, gray: np.ndarray, signal: np.ndarray, support: np.ndarray, grad_norm: np.ndarray, stage: str, diameters: list[int], maps: dict[str, np.ndarray], body_support: np.ndarray, out_dir: Path) -> list[seg.Candidate]:
    step = out_dir / 'step05_cellpose_global'
    step.mkdir(parents=True, exist_ok=True)
    cands: list[seg.Candidate] = []
    for branch_rank, diameter in enumerate(diameters):
        masks, *_ = model.eval(gray, diameter=float(diameter), channels=[0, 0], normalize=True, do_3D=False)
        masks = masks.astype(np.uint16)
        preview = np.zeros_like(masks, dtype=np.uint16)
        kept_id = 0
        for label in range(1, int(masks.max()) + 1):
            cand = seg.build_candidate(masks, label, diameter, branch_rank, signal, support, grad_norm, stage)
            if cand is None:
                continue
            mask = cand.mask
            area = cand.area
            frac = area / float(mask.shape[0] * mask.shape[1])
            body_frac = body_fraction(mask, body_support)
            cover = bbox_cover(mask)
            border_touch = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
            if area > 120000 and cand.circularity > 0.74 and body_frac < 0.10:
                continue
            if frac > 0.45 and cand.circularity > 0.78 and body_frac < 0.12:
                continue
            if border_touch and frac > 0.18 and body_frac < 0.15:
                continue
            if cover > 0.88 and body_frac < 0.10:
                continue
            cand.source = f'cellpose_global_d{diameter}'
            cand.score += 0.02
            cands.append(cand)
            kept_id += 1
            preview[mask] = kept_id
        save_gray(step / f'diameter_{diameter:04d}_labels_16bit.png', preview)
    return cands


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    if inter == 0:
        return 0.0
    union = float(np.logical_or(a, b).sum())
    return inter / union if union else 0.0


def local_refine_thresholds(model, gray: np.ndarray, signal: np.ndarray, support: np.ndarray, grad_norm: np.ndarray, maps: dict[str, np.ndarray], threshold_cands: list[seg.Candidate], out_dir: Path) -> list[seg.Candidate]:
    step = out_dir / 'step06_cellpose_local_refine'
    step.mkdir(parents=True, exist_ok=True)
    refined: list[seg.Candidate] = []
    threshold_cands = sorted(threshold_cands, key=lambda c: c.area, reverse=True)[:4]
    for idx, base_cand in enumerate(threshold_cands, start=1):
        if base_cand.area < 6000:
            continue
        ys, xs = np.where(base_cand.mask)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        pad_x = max(25, int(round((x1 - x0) * 0.18)))
        pad_y = max(25, int(round((y1 - y0) * 0.18)))
        x0 = max(0, x0 - pad_x)
        y0 = max(0, y0 - pad_y)
        x1 = min(gray.shape[1], x1 + pad_x)
        y1 = min(gray.shape[0], y1 + pad_y)
        crop = gray[y0:y1, x0:x1]
        save_gray(step / f'crop_{idx:02d}_gray.png', crop)
        d = max(40, min(700, base_cand.diameter))
        masks, *_ = model.eval(crop, diameter=float(d), channels=[0, 0], normalize=True, do_3D=False)
        masks = masks.astype(np.uint16)
        best = None
        best_score = -1.0
        preview = np.zeros_like(masks, dtype=np.uint16)
        kept_id = 0
        for label in range(1, int(masks.max()) + 1):
            crop_mask = masks == label
            full = np.zeros_like(gray, dtype=bool)
            full[y0:y1, x0:x1] = crop_mask
            ov = iou(full, base_cand.mask)
            if ov < 0.25:
                continue
            cand = seg.build_candidate_from_mask(full, d, idx, signal, support, grad_norm, 'cystic_mid', source=f'cellpose_refine_d{d}')
            if cand is None:
                continue
            score = cand.score + 0.45 * ov
            if score > best_score:
                best = cand
                best_score = score
            kept_id += 1
            preview[crop_mask] = kept_id
        save_gray(step / f'crop_{idx:02d}_labels_16bit.png', preview)
        if best is not None:
            best.source = f'cellpose_refine_d{d}'
            best.score += 0.05
            refined.append(best)
    return refined


def summarize_branches(candidates: list[seg.Candidate]) -> list[dict]:
    grouped: dict[str, list[seg.Candidate]] = {}
    for cand in candidates:
        grouped.setdefault(str(cand.source), []).append(cand)
    rows = []
    for branch, subset in sorted(grouped.items()):
        rows.append({
            'branch': branch,
            'candidate_count_before_merge': len(subset),
            'mean_score': round(float(np.mean([c.score for c in subset])), 6),
            'mean_area': round(float(np.mean([c.area for c in subset])), 2),
            'mean_support_ratio': round(float(np.mean([c.support_ratio for c in subset])), 6),
        })
    return rows


def build_outputs(rgb: np.ndarray, kept: list[seg.Candidate]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    label_mask, color_mask = seg.build_outputs(rgb, kept)
    overlay = cv2.addWeighted(rgb, 0.72, color_mask, 0.55, 0)
    edges = cv2.Canny((label_mask > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (255, 0, 0)
    return label_mask, color_mask, overlay


def metric_sort_key(row: dict) -> tuple[int, int, tuple[int, str]]:
    return (CONDITION_ORDER.index(row['condition']), int(row['relative_day']), natural_key(Path(row['image_name'])))


def normalize_metrics(metrics: list[dict]) -> None:
    if not metrics:
        return
    count_norm = app81_base.base.minmax_floor([float(row['count']) for row in metrics], 0.1)
    curvature_norm = app81_base.base.minmax_floor([float(row['curvature']) for row in metrics], 0.1)
    edge_norm = app81_base.base.minmax_floor([float(row['edge_intensity']) for row in metrics], 0.1)
    for row, cn, kn, en in zip(metrics, count_norm, curvature_norm, edge_norm):
        row['count_norm'] = cn
        row['curvature_norm'] = kn
        row['edge_norm'] = en
        row['normalized_edge_over_count_curvature'] = en / (cn * kn)


def write_checkpoint(metrics: list[dict], per_image_csv: Path, daily_csv: Path, manifest_path: Path, manifest: dict, failures: list[dict]) -> None:
    metrics.sort(key=metric_sort_key)
    normalize_metrics(metrics)
    write_per_image_csv(metrics, per_image_csv)
    write_daily_summary(metrics, daily_csv)
    manifest['n_images'] = len(metrics)
    manifest['failure_count'] = len(failures)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def append_failure_row(path: Path, row: dict) -> None:
    exists = path.exists()
    with path.open('a', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['condition', 'date_key', 'date_label', 'relative_day', 'image_name', 'source_tif', 'error_type', 'error_message'])
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def process_one(model, tif: Path, out_dir: Path, relative_day: int, condition: str, overwrite: bool) -> dict:
    date_key = tif.parent.name
    cfg = stage_and_diameters(condition, relative_day)
    stem = f'{date_key}_{tif.stem}'
    mask_path = out_dir / f'{stem}_mask_16bit.png'
    rgb_path = out_dir / f'{stem}_instance_rgb.png'
    overlay_path = out_dir / f'{stem}_overlay.png'
    signal_path = out_dir / f'{stem}_signal.png'
    stats_path = out_dir / f'{stem}_segmentation_stats.json'
    metric_path = out_dir / f'{stem}_metrics.json'

    if not overwrite:
        required = [metric_path, stats_path, mask_path, signal_path, rgb_path, overlay_path]
        existing_ok = all(p.exists() and p.stat().st_size > 0 for p in required)
        if existing_ok:
            try:
                return json.loads(metric_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass

    rgb, gray = seg.load_rgb_gray(tif)
    signal, support, grad_norm = seg.compute_hybrid_signal(gray)
    maps = build_maps(gray)
    masks = build_threshold_masks(signal, support, maps)

    tmp_dir = out_dir / f'{stem}_adaptive_ensemble_tmp'
    step01 = tmp_dir / 'step01_input'
    step02 = tmp_dir / 'step02_maps'
    step03 = tmp_dir / 'step03_thresholds'
    step04 = tmp_dir / 'step04_threshold_watershed'
    step07 = tmp_dir / 'step07_final'
    for d in (step01, step02, step03, step04, step07):
        d.mkdir(parents=True, exist_ok=True)
    save_rgb(step01 / 'step01_source_rgb.png', rgb)
    save_gray(step01 / 'step02_source_gray.png', gray)
    save_gray(step01 / 'step03_signal.png', signal)
    save_gray(step01 / 'step04_support.png', support)
    for name in ['clahe', 'inv', 'bh_small', 'bh_big', 'grad', 'lap', 'tex', 'rim', 'body']:
        save_gray(step02 / f'{name}.png', maps[name])
    for name in ['rim_bin', 'body_seed', 'body_support', 'mass_mask', 'cyst_mask', 'union']:
        save_binary(step03 / f'{name}.png', masks[name])

    # Threshold + watershed proposals.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(masks['union'].astype(np.uint8), connectivity=8)
    ws_labels = np.zeros_like(labels, dtype=np.uint16)
    threshold_cands: list[seg.Candidate] = []
    next_lab = 1
    for lab in range(1, n):
        comp = labels == lab
        if int(stats[lab, cv2.CC_STAT_AREA]) < 900:
            continue
        source_kind = 'mass' if masks['mass_mask'][comp].mean() >= masks['cyst_mask'][comp].mean() else 'cyst'
        pieces = split_component(comp, maps['clahe'], masks['body_seed'])
        for piece in pieces:
            cand = threshold_candidate(piece, cfg['stage'], signal, support, maps, masks['body_support'], source_kind)
            if cand is None:
                continue
            threshold_cands.append(cand)
            ws_labels[piece] = next_lab
            next_lab += 1
    save_gray(step04 / 'watershed_labels_16bit.png', ws_labels)

    # Limited global Cellpose branches, stage-aware.
    global_diams = cfg['diameters'][:2] if len(cfg['diameters']) >= 2 else cfg['diameters']
    cellpose_global = global_cellpose_candidates(model, gray, signal, support, grad_norm, cfg['stage'], global_diams, maps, masks['body_support'], tmp_dir)

    # Local Cellpose refinement on the largest threshold objects.
    cellpose_local = local_refine_thresholds(model, gray, signal, support, grad_norm, maps, threshold_cands, tmp_dir)

    all_cands = threshold_cands + cellpose_global + cellpose_local
    kept = seg.merge_candidates(all_cands)
    label_mask, color_mask, overlay = build_outputs(rgb, kept)
    save_gray(step07 / 'step70_final_mask_16bit.png', label_mask)
    save_rgb(step07 / 'step71_final_instance_rgb.png', color_mask)
    save_rgb(step07 / 'step72_final_overlay.png', overlay)

    cv2.imwrite(str(mask_path), label_mask)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(signal_path), signal)

    shape_metrics = aggregate_segmentation_metrics(label_mask, signal)
    seg_stats = {
        'source_tif': str(tif),
        'condition': condition,
        'relative_day': relative_day,
        'stage': cfg['stage'],
        'pipeline': 'app81_adaptive_ensemble_v1',
        'mask_count': int(label_mask.max()),
        'tmp_dir': str(tmp_dir),
        'threshold_candidate_count': len(threshold_cands),
        'cellpose_global_candidate_count': len(cellpose_global),
        'cellpose_local_candidate_count': len(cellpose_local),
        'branch_summaries': summarize_branches(all_cands),
        'merged_candidates': [
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
        'notes': {
            'goal': 'Per-image adaptive ensemble: threshold + watershed proposals, then limited global and local Cellpose refinement.',
            'codex_prompt_segmentation': False,
        },
    }
    stats_path.write_text(json.dumps(seg_stats, ensure_ascii=False, indent=2), encoding='utf-8')

    metric = {
        'condition': condition,
        'date_key': date_key,
        'image_name': tif.name,
        'source_tif': str(tif),
        'stage': 'adaptive_ensemble_v1',
        'count': shape_metrics['count'],
        'curvature': shape_metrics['curvature'],
        'roundness': shape_metrics['roundness'],
        'roundness_deviation_norm': shape_metrics['roundness_deviation_norm'],
        'roundness_deviation_px_total': shape_metrics['roundness_deviation_px_total'],
        'edge_intensity': shape_metrics['edge_intensity'],
        'total_area_px': shape_metrics['total_area_px'],
        'average_perimeter_px': shape_metrics['average_perimeter_px'],
        'mask_path': str(mask_path),
        'instance_rgb_path': str(rgb_path),
        'overlay_path': str(overlay_path),
        'signal_path': str(signal_path),
        'stats_path': str(stats_path),
    }
    metric_path.write_text(json.dumps(metric, ensure_ascii=False, indent=2), encoding='utf-8')
    return metric


def main() -> int:
    args = parse_args()
    src_root = Path(args.src_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / 'runs'
    db_dir = out_dir / 'profiling' / 'quantification'
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    cv2.setNumThreads(1)
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
    os.environ.setdefault('MKL_NUM_THREADS', '1')
    os.environ.setdefault('NUMEXPR_NUM_THREADS', '1')
    os.environ.setdefault('VECLIB_MAXIMUM_THREADS', '1')
    os.environ.setdefault('TBB_NUM_THREADS', '1')

    conditions = resolve_conditions(args.conditions)
    images, skipped = discover_images(src_root, conditions)
    if args.limit:
        images = images[:args.limit]
    if not images:
        raise SystemExit(f'No main-phase labeled 10x TIFFs found under {src_root} for {conditions}')

    day0 = min(dt for _, _, _, dt, _ in images)
    model = seg.models.CellposeModel(gpu=True)
    metrics: list[dict] = []
    failures: list[dict] = []
    total = len(images)

    per_image_csv = db_dir / 'per_image_metrics.csv'
    daily_csv = db_dir / 'daily_summary.csv'
    failure_csv = db_dir / 'failed_images.csv'
    failure_log = db_dir / 'failed_images_tracebacks.log'
    manifest_path = out_dir / 'run_manifest.json'
    manifest = {
        'src_root': str(src_root),
        'out_dir': str(out_dir),
        'conditions': conditions,
        'phase': 'main_only',
        'magnification': '10x_only',
        'pipeline': 'app81_adaptive_ensemble_v1',
        'n_images': 0,
        'expected_images': total,
        'skipped': skipped,
        'per_image_csv': str(per_image_csv),
        'daily_summary_csv': str(daily_csv),
        'failure_csv': str(failure_csv),
        'limit': args.limit,
    }

    for idx, (condition, date_key, date_label, dt, tif) in enumerate(images, start=1):
        per_date_out = runs_dir / condition / date_key
        per_date_out.mkdir(parents=True, exist_ok=True)
        relative_day = (dt - day0).days
        try:
            metric = process_one(model, tif, per_date_out, relative_day, condition, args.overwrite)
            metric['condition'] = condition
            metric['date_label'] = date_label
            metric['relative_day'] = relative_day
            metrics.append(metric)
            print(f'[{idx}/{total}] {condition} {date_key} {tif.name} -> count={metric["count"]}', flush=True)
            if len(metrics) % args.checkpoint_every == 0 or idx == total:
                write_checkpoint(metrics, per_image_csv, daily_csv, manifest_path, manifest, failures)
        except Exception as exc:
            failure = {
                'condition': condition,
                'date_key': date_key,
                'date_label': date_label,
                'relative_day': relative_day,
                'image_name': tif.name,
                'source_tif': str(tif),
                'error_type': type(exc).__name__,
                'error_message': str(exc),
            }
            failures.append(failure)
            append_failure_row(failure_csv, failure)
            with failure_log.open('a', encoding='utf-8') as fh:
                fh.write(f'[{idx}/{total}] {condition} {date_key} {tif.name}\n')
                fh.write(traceback.format_exc())
                fh.write('\n')
            print(f'[{idx}/{total}] ERROR {condition} {date_key} {tif.name}: {type(exc).__name__}: {exc}', flush=True)
            if len(failures) >= args.max_errors:
                raise RuntimeError(f'Too many image failures: {len(failures)}') from exc

    write_checkpoint(metrics, per_image_csv, daily_csv, manifest_path, manifest, failures)
    print(per_image_csv)
    print(daily_csv)
    print(manifest_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
