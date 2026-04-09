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

APP80_DIR = Path("/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose")
sys.path.insert(0, str(APP80_DIR))

from cellpose import models  # noqa: E402
import run_multiscale_dateaware_cellpose as seg  # noqa: E402


@dataclass
class Candidate:
    mask: np.ndarray
    branch: str
    branch_type: str
    diameter: int
    score: float
    area: int
    circularity: float
    fill_ratio: float
    overlap_env: float
    overlap_core: float
    support_overlap: float
    boundary_strength: float
    interior_texture: float
    mean_signal: float
    border_touch: bool
    bbox_cover: float
    centroid_x: float
    centroid_y: float
    container_penalty: float = 0.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="App81 hybrid soft-prior Cellpose v3 test.")
    p.add_argument("--tif", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--diameters", default="180,260,360,520,760")
    p.add_argument("--small-diameters", default="90,120,160,220")
    p.add_argument("--large-diameters", default="920,1100")
    p.add_argument("--gpu", action="store_true", default=True)
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    keep = np.zeros_like(mask, dtype=bool)
    for lab in range(1, n):
        if int(stats[lab, cv2.CC_STAT_AREA]) >= min_area:
            keep[labels == lab] = True
    return keep


def constrained_region_grow(seed: np.ndarray, grow_mask: np.ndarray, ksize: int = 19, max_iter: int = 64) -> np.ndarray:
    cur = seed.astype(np.uint8)
    allow = grow_mask.astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    for _ in range(max_iter):
        nxt = cv2.bitwise_and(cv2.dilate(cur, kernel), allow)
        if np.array_equal(nxt, cur):
            break
        cur = nxt
    return cur > 0


def compute_local_std(gray: np.ndarray, ksize: int = 31) -> np.ndarray:
    gray_f = gray.astype(np.float32)
    mean = cv2.GaussianBlur(gray_f, (0, 0), ksize / 6.0)
    mean_sq = cv2.GaussianBlur(gray_f * gray_f, (0, 0), ksize / 6.0)
    var = np.maximum(mean_sq - mean * mean, 0.0)
    return cv2.normalize(np.sqrt(var), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def mask_stats(mask: np.ndarray) -> tuple[int, float, float, float, bool, float, float, float]:
    area = int(mask.sum())
    if area <= 0:
        return 0, 0.0, 0.0, 0.0, False, 0.0, 0.0, 0.0
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
    cx = float(xs.mean()) if len(xs) else 0.0
    cy = float(ys.mean()) if len(ys) else 0.0
    return area, perimeter, circularity, fill_ratio, border_touch, bbox_cover, cx, cy


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


def boundary_strength(mask: np.ndarray, blackhat_big: np.ndarray, blackhat_small: np.ndarray, grad_mag: np.ndarray) -> float:
    mask_u8 = mask.astype(np.uint8)
    outer = cv2.dilate(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))) > 0
    inner = cv2.erode(mask_u8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    band = np.logical_and(outer, ~inner)
    if not band.any():
        band = mask
    b_big = float(blackhat_big[band].mean() / 255.0) if band.any() else 0.0
    b_small = float(blackhat_small[band].mean() / 255.0) if band.any() else 0.0
    grad = float(grad_mag[band].mean() / 255.0) if band.any() else 0.0
    return 0.38 * b_big + 0.22 * b_small + 0.40 * grad


def build_soft_priors(
    rgb: np.ndarray, gray: np.ndarray, signal: np.ndarray, out_dir: Path
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    step = out_dir / "step02_soft_priors"
    step.mkdir(parents=True, exist_ok=True)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    a_chan = lab[..., 1]

    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(16, 16)).apply(gray)
    blackhat_big = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    blackhat_small = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))
    gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    grad_mag = cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    local_std = compute_local_std(gray)

    wall_emphasis = cv2.normalize(
        0.44 * clahe.astype(np.float32)
        + 0.24 * blackhat_big.astype(np.float32)
        + 0.18 * blackhat_small.astype(np.float32)
        + 0.14 * grad_mag.astype(np.float32),
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)
    small_wall = cv2.normalize(
        0.50 * blackhat_small.astype(np.float32)
        + 0.30 * grad_mag.astype(np.float32)
        + 0.20 * clahe.astype(np.float32),
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)

    signal78 = signal >= int(np.percentile(signal, 78))
    signal84 = signal >= int(np.percentile(signal, 84))
    sat80 = sat >= int(np.percentile(sat, 80))
    a80 = a_chan >= int(np.percentile(a_chan, 80))
    grad60 = grad_mag >= int(np.percentile(grad_mag, 60))
    blackhat_big82 = blackhat_big >= int(np.percentile(blackhat_big, 82))
    blackhat_small86 = blackhat_small >= int(np.percentile(blackhat_small, 86))
    texture68 = local_std >= int(np.percentile(local_std, 68))

    support_mask = ((grad60 & (blackhat_big82 | signal78)) | (blackhat_small86 & texture68))
    support_mask = cv2.morphologyEx((support_mask.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    support_mask = cv2.morphologyEx(support_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0

    small_seed = (blackhat_small86 & grad60) | (blackhat_small86 & signal78)
    small_seed = cv2.morphologyEx((small_seed.astype(np.uint8) * 255), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0

    seed_strong = signal84 | (blackhat_big82 & grad60) | (blackhat_small86 & grad60) | (a80 & blackhat_small86)
    seed_strong = cv2.morphologyEx((seed_strong.astype(np.uint8) * 255), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    seed_strong = remove_small_components(seed_strong, 1200)

    grow_mask = ((signal78 & (grad60 | sat80 | a80)) | support_mask | (texture68 & blackhat_big82))
    grow_mask = cv2.morphologyEx((grow_mask.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))) > 0

    hint_env = constrained_region_grow(seed_strong, grow_mask, ksize=25, max_iter=72)
    hint_env = cv2.morphologyEx((hint_env.astype(np.uint8) * 255), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))) > 0
    hint_env = fill_holes((hint_env.astype(np.uint8) * 255)) > 0
    hint_env = remove_small_components(hint_env, 2500)

    hint_core = cv2.erode((hint_env.astype(np.uint8) * 255), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))) > 0
    if hint_core.sum() == 0:
        hint_core = cv2.erode((hint_env.astype(np.uint8) * 255), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))) > 0

    support_mask = support_mask & (
        hint_env
        | constrained_region_grow(small_seed, grow_mask, ksize=11, max_iter=28)
        | (signal84 & texture68)
    )

    save_gray(step / "step10_gray.png", gray)
    save_gray(step / "step11_signal.png", signal)
    save_gray(step / "step12_clahe.png", clahe)
    save_gray(step / "step13_blackhat_big.png", blackhat_big)
    save_gray(step / "step14_blackhat_small.png", blackhat_small)
    save_gray(step / "step15_grad_mag.png", grad_mag)
    save_gray(step / "step16_local_std.png", local_std)
    save_gray(step / "step17_wall_emphasis.png", wall_emphasis)
    save_gray(step / "step18_small_wall.png", small_wall)
    save_binary(step / "step20_hint_envelope.png", hint_env > 0)
    save_binary(step / "step21_hint_core.png", hint_core > 0)
    save_binary(step / "step22_support_mask.png", support_mask)
    save_binary(step / "step23_small_seed.png", small_seed)

    overlay = rgb.copy()
    overlay[support_mask] = (0.65 * overlay[support_mask] + 0.35 * np.array([0, 220, 255])).astype(np.uint8)
    edges = cv2.Canny((hint_env > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (255, 0, 0)
    save_rgb(step / "step24_prior_overlay.png", overlay)

    meta = {
        "note": "Hybrid App81 soft-prior v3: local seed-grown hint plus large-object direct rescue.",
        "hint_fraction": round(float(hint_env.mean()), 6),
        "support_fraction": round(float(support_mask.mean()), 6),
        "seed_fraction": round(float(seed_strong.mean()), 6),
    }
    write_json(step / "step25_prior_summary.json", meta)
    return clahe, wall_emphasis, small_wall, grad_mag, blackhat_big, blackhat_small, hint_env > 0, hint_core > 0, support_mask, small_seed, meta


def branch_inputs(gray: np.ndarray, clahe: np.ndarray, wall_emphasis: np.ndarray, small_wall: np.ndarray, hint_env: np.ndarray) -> list[tuple[str, str, np.ndarray, float]]:
    masked_gray = gray.copy()
    masked_gray[~hint_env] = np.median(gray).astype(gray.dtype)
    return [
        ("guided_raw", "guided", gray, 0.08),
        ("guided_masked", "guided", masked_gray, 0.05),
        ("direct_raw", "direct", gray, 0.05),
        ("direct_clahe", "direct", clahe, 0.04),
        ("direct_wall", "direct", wall_emphasis, 0.04),
        ("large_direct_raw", "large", gray, 0.08),
        ("large_direct_wall", "large", wall_emphasis, 0.08),
        ("small_wall", "small", small_wall, 0.07),
    ]


def candidate_ok(
    branch_type: str,
    area: int,
    circularity: float,
    fill_ratio: float,
    overlap_env: float,
    support_overlap: float,
    b_strength: float,
    texture: float,
    border_touch: bool,
    bbox_cover: float,
) -> bool:
    if branch_type == "small":
        if area < 1400 or area > 55000:
            return False
        if b_strength < 0.16:
            return False
        if support_overlap < 0.015 and overlap_env < 0.015:
            return False
        if circularity < 0.12:
            return False
        if border_touch and bbox_cover > 0.30:
            return False
        return True

    if border_touch and bbox_cover > 0.72 and circularity > 0.80 and fill_ratio > 0.62 and texture < 0.22:
        return False
    if area > 280000 and circularity > 0.84 and fill_ratio > 0.72 and support_overlap < 0.045 and texture < 0.18:
        return False

    if branch_type == "guided":
        if area < 9000:
            return False
        if overlap_env < 0.15 and b_strength < 0.20:
            return False
        if area > 1200000 and b_strength < 0.17:
            return False
        return True

    if branch_type == "direct":
        if area < 10000:
            return False
        if b_strength < 0.12 and support_overlap < 0.04:
            return False
        if area < 35000 and support_overlap < 0.08 and b_strength < 0.18:
            return False
        return True

    if branch_type == "large":
        if area < 50000:
            return False
        if b_strength < 0.08 and support_overlap < 0.05:
            return False
        if overlap_env < 0.03 and support_overlap < 0.08 and texture < 0.18:
            return False
        if border_touch and bbox_cover > 0.82 and circularity > 0.82 and fill_ratio > 0.60 and texture < 0.22:
            return False
        return True

    return True


def append_threshold_large_candidates(
    candidates: list[Candidate],
    step: Path,
    signal: np.ndarray,
    grad_mag: np.ndarray,
    blackhat_big: np.ndarray,
    blackhat_small: np.ndarray,
    hint_env: np.ndarray,
    hint_core: np.ndarray,
    support_mask: np.ndarray,
    local_std: np.ndarray,
) -> None:
    rescue_mask = cv2.morphologyEx(
        (support_mask.astype(np.uint8) * 255),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (81, 81)),
    )
    rescue_mask = fill_holes(rescue_mask)
    rescue_mask = cv2.morphologyEx(
        rescue_mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    )
    labels = cv2.connectedComponents(rescue_mask.astype(np.uint8))[1].astype(np.uint16)
    save_gray(step / "threshold_large_labels_16bit.png", labels)

    for lab_id in range(1, int(labels.max()) + 1):
        mask = labels == lab_id
        area, _, circularity, fill_ratio, border_touch, bbox_cover, cx, cy = mask_stats(mask)
        if area < 50000:
            continue
        overlap_env = float(hint_env[mask].mean()) if area else 0.0
        overlap_core = float(hint_core[mask].mean()) if area else 0.0
        support_overlap = float(support_mask[mask].mean()) if area else 0.0
        b_strength = boundary_strength(mask, blackhat_big, blackhat_small, grad_mag)
        texture = float(local_std[mask].mean() / 255.0) if area else 0.0
        mean_signal = float(signal[mask].mean() / 255.0) if area else 0.0

        if b_strength < 0.08:
            continue
        if area > 180000 and texture < 0.16 and mean_signal < 0.20:
            continue
        if border_touch and bbox_cover > 0.82 and circularity > 0.82 and fill_ratio > 0.60 and texture < 0.22:
            continue

        score = (
            0.44 * b_strength
            + 0.42 * support_overlap
            + 0.24 * texture
            + 0.22 * mean_signal
            + 0.10 * circularity
            + 0.06 * fill_ratio
            + 0.16 * overlap_env
            + 0.12
        )
        if area > 120000:
            score += 0.10
        if area > 280000 and texture > 0.16:
            score += 0.06

        candidates.append(
            Candidate(
                mask=mask,
                branch="threshold_large",
                branch_type="rescue",
                diameter=0,
                score=float(score),
                area=area,
                circularity=float(circularity),
                fill_ratio=float(fill_ratio),
                overlap_env=float(overlap_env),
                overlap_core=float(overlap_core),
                support_overlap=float(support_overlap),
                boundary_strength=float(b_strength),
                interior_texture=float(texture),
                mean_signal=float(mean_signal),
                border_touch=bool(border_touch),
                bbox_cover=float(bbox_cover),
                centroid_x=float(cx),
                centroid_y=float(cy),
            )
        )


def append_crop_rescue_candidates(
    model,
    candidates: list[Candidate],
    step: Path,
    gray: np.ndarray,
    clahe: np.ndarray,
    wall_emphasis: np.ndarray,
    signal: np.ndarray,
    grad_mag: np.ndarray,
    blackhat_big: np.ndarray,
    blackhat_small: np.ndarray,
    hint_env: np.ndarray,
    hint_core: np.ndarray,
    support_mask: np.ndarray,
    local_std: np.ndarray,
) -> None:
    inv_gray = 255 - gray
    body_score = cv2.normalize(
        0.45 * inv_gray.astype(np.float32)
        + 0.25 * signal.astype(np.float32)
        + 0.20 * local_std.astype(np.float32)
        + 0.25 * blackhat_big.astype(np.float32),
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)
    save_gray(step / "crop_rescue_body_score.png", body_score)
    seed = body_score >= int(np.percentile(body_score, 94))
    seed = cv2.morphologyEx((seed.astype(np.uint8) * 255), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(seed.astype(np.uint8), connectivity=8)

    ranked = []
    for lab in range(1, n):
        area = int(stats[lab, cv2.CC_STAT_AREA])
        if area < 8000:
            continue
        x = int(stats[lab, cv2.CC_STAT_LEFT])
        y = int(stats[lab, cv2.CC_STAT_TOP])
        w = int(stats[lab, cv2.CC_STAT_WIDTH])
        h = int(stats[lab, cv2.CC_STAT_HEIGHT])
        ranked.append((area, x, y, w, h))
    ranked.sort(reverse=True)
    if not ranked:
        return

    top = ranked[:3]
    x0 = min(x for _, x, _, _, _ in top)
    y0 = min(y for _, _, y, _, _ in top)
    x1 = max(x + w for _, x, _, w, _ in top)
    y1 = max(y + h for _, _, y, _, h in top)
    bw = x1 - x0
    bh = y1 - y0
    pad_x = max(220, int(round(bw * 0.45)))
    pad_y = max(220, int(round(bh * 0.45)))
    H, W = gray.shape
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(W, x1 + pad_x)
    y1 = min(H, y1 + pad_y)
    if (x1 - x0) * (y1 - y0) > int(H * W * 0.90):
        return
    if (x1 - x0) < 500 or (y1 - y0) < 500:
        return

    crop_meta = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "seed_components": len(top)}
    write_json(step / "crop_rescue_roi.json", crop_meta)
    save_gray(step / "crop_rescue_gray.png", gray[y0:y1, x0:x1])
    save_gray(step / "crop_rescue_wall.png", wall_emphasis[y0:y1, x0:x1])

    crop_inputs = [
        ("crop_raw", gray[y0:y1, x0:x1]),
        ("crop_clahe", clahe[y0:y1, x0:x1]),
        ("crop_wall", wall_emphasis[y0:y1, x0:x1]),
    ]
    for branch_name, crop_img in crop_inputs:
        for d in [260, 360, 520, 760]:
            masks, *_ = model.eval(crop_img, diameter=float(d), channels=[0, 0], normalize=True, do_3D=False)
            masks = masks.astype(np.uint16)
            for lab_id in range(1, int(masks.max()) + 1):
                crop_mask = masks == lab_id
                if int(crop_mask.sum()) < 60000:
                    continue
                full_mask = np.zeros_like(gray, dtype=bool)
                full_mask[y0:y1, x0:x1] = crop_mask
                area, _, circularity, fill_ratio, border_touch, bbox_cover, cx, cy = mask_stats(full_mask)
                overlap_env = float(hint_env[full_mask].mean()) if area else 0.0
                overlap_core = float(hint_core[full_mask].mean()) if area else 0.0
                support_overlap = float(support_mask[full_mask].mean()) if area else 0.0
                b_strength = boundary_strength(full_mask, blackhat_big, blackhat_small, grad_mag)
                texture = float(local_std[full_mask].mean() / 255.0) if area else 0.0
                mean_signal = float(signal[full_mask].mean() / 255.0) if area else 0.0

                if b_strength < 0.08 and support_overlap < 0.06:
                    continue
                if area > 180000 and texture < 0.15 and mean_signal < 0.18:
                    continue
                if border_touch and bbox_cover > 0.88 and circularity > 0.82 and fill_ratio > 0.62 and texture < 0.22:
                    continue

                score = (
                    0.54 * b_strength
                    + 0.12 * overlap_env
                    + 0.34 * support_overlap
                    + 0.10 * circularity
                    + 0.08 * fill_ratio
                    + 0.26 * texture
                    + 0.22 * mean_signal
                    + 0.14
                )
                if area > 120000:
                    score += 0.12
                if area > 280000 and texture > 0.16:
                    score += 0.08
                if not border_touch:
                    score += 0.03

                candidates.append(
                    Candidate(
                        mask=full_mask,
                        branch=branch_name,
                        branch_type="crop",
                        diameter=d,
                        score=float(score),
                        area=area,
                        circularity=float(circularity),
                        fill_ratio=float(fill_ratio),
                        overlap_env=float(overlap_env),
                        overlap_core=float(overlap_core),
                        support_overlap=float(support_overlap),
                        boundary_strength=float(b_strength),
                        interior_texture=float(texture),
                        mean_signal=float(mean_signal),
                        border_touch=bool(border_touch),
                        bbox_cover=float(bbox_cover),
                        centroid_x=float(cx),
                        centroid_y=float(cy),
                    )
                )


def run_branches(
    model,
    rgb: np.ndarray,
    gray: np.ndarray,
    signal: np.ndarray,
    clahe: np.ndarray,
    wall_emphasis: np.ndarray,
    small_wall: np.ndarray,
    grad_mag: np.ndarray,
    blackhat_big: np.ndarray,
    blackhat_small: np.ndarray,
    hint_env: np.ndarray,
    hint_core: np.ndarray,
    support_mask: np.ndarray,
    small_seed: np.ndarray,
    diameters: list[int],
    small_diameters: list[int],
    large_diameters: list[int],
    out_dir: Path,
) -> list[Candidate]:
    step = out_dir / "step03_multibranch"
    step.mkdir(parents=True, exist_ok=True)

    inputs = branch_inputs(gray, clahe, wall_emphasis, small_wall, hint_env)
    for idx, (name, _, img, _) in enumerate(inputs):
        save_gray(step / f"step0{idx}_input_{name}.png", img)

    local_std = compute_local_std(gray)
    branch_rows = []
    candidates: list[Candidate] = []
    for branch_name, branch_type, branch_img, bonus in inputs:
        if branch_type == "small":
            branch_diams = small_diameters
        elif branch_type == "large":
            branch_diams = large_diameters
        else:
            branch_diams = diameters
        for d in branch_diams:
            masks, *_ = model.eval(branch_img, diameter=float(d), channels=[0, 0], normalize=True, do_3D=False)
            masks = masks.astype(np.uint16)
            branch_label = np.zeros_like(masks, dtype=np.uint16)
            kept_id = 0
            for lab_id in range(1, int(masks.max()) + 1):
                mask = masks == lab_id
                area, _, circularity, fill_ratio, border_touch, bbox_cover, cx, cy = mask_stats(mask)
                if area <= 0:
                    continue
                overlap_env = float(hint_env[mask].mean()) if area else 0.0
                overlap_core = float(hint_core[mask].mean()) if area else 0.0
                support_overlap = float(support_mask[mask].mean()) if area else 0.0
                b_strength = boundary_strength(mask, blackhat_big, blackhat_small, grad_mag)
                texture = float(local_std[mask].mean() / 255.0) if area else 0.0
                mean_signal = float(signal[mask].mean() / 255.0) if area else 0.0

                if branch_type == "small":
                    seed_overlap = float(small_seed[mask].mean()) if area else 0.0
                    if seed_overlap < 0.02 and b_strength < 0.20:
                        continue
                if not candidate_ok(branch_type, area, circularity, fill_ratio, overlap_env, support_overlap, b_strength, texture, border_touch, bbox_cover):
                    continue

                if branch_type == "guided":
                    score = (
                        0.62 * b_strength
                        + 0.42 * overlap_env
                        + 0.18 * overlap_core
                        + 0.22 * support_overlap
                        + 0.16 * circularity
                        + 0.10 * fill_ratio
                        + 0.16 * texture
                        + 0.16 * mean_signal
                        + bonus
                    )
                elif branch_type == "direct":
                    score = (
                        0.78 * b_strength
                        + 0.15 * overlap_env
                        + 0.28 * support_overlap
                        + 0.16 * circularity
                        + 0.10 * fill_ratio
                        + 0.20 * texture
                        + 0.18 * mean_signal
                        + bonus
                    )
                elif branch_type == "large":
                    score = (
                        0.56 * b_strength
                        + 0.06 * overlap_env
                        + 0.40 * support_overlap
                        + 0.10 * circularity
                        + 0.08 * fill_ratio
                        + 0.32 * texture
                        + 0.24 * mean_signal
                        + bonus
                    )
                else:
                    score = (
                        0.92 * b_strength
                        + 0.20 * overlap_env
                        + 0.18 * support_overlap
                        + 0.24 * circularity
                        + 0.10 * fill_ratio
                        + 0.10 * texture
                        + 0.12 * mean_signal
                        + bonus
                    )

                if not border_touch:
                    score += 0.03
                if 40000 <= area <= 900000:
                    score += 0.04
                if branch_type == "direct" and area > 180000 and b_strength > 0.20 and texture > 0.16:
                    score += 0.08
                if branch_type == "large" and area > 120000 and support_overlap > 0.10 and texture > 0.16:
                    score += 0.14
                if branch_type == "large" and area > 300000 and b_strength > 0.08:
                    score += 0.06
                if branch_type == "small" and area < 18000:
                    score += 0.05
                if area > 1300000:
                    score -= 0.10

                candidates.append(
                    Candidate(
                        mask=mask,
                        branch=branch_name,
                        branch_type=branch_type,
                        diameter=d,
                        score=float(score),
                        area=area,
                        circularity=float(circularity),
                        fill_ratio=float(fill_ratio),
                        overlap_env=float(overlap_env),
                        overlap_core=float(overlap_core),
                        support_overlap=float(support_overlap),
                        boundary_strength=float(b_strength),
                        interior_texture=float(texture),
                        mean_signal=float(mean_signal),
                        border_touch=bool(border_touch),
                        bbox_cover=float(bbox_cover),
                        centroid_x=float(cx),
                        centroid_y=float(cy),
                    )
                )
                kept_id += 1
                branch_label[mask] = kept_id
                branch_rows.append(
                    {
                        "branch": branch_name,
                        "branch_type": branch_type,
                        "diameter_px": d,
                        "candidate_label": kept_id,
                        "area_px": area,
                        "score": round(float(score), 6),
                        "circularity": round(float(circularity), 6),
                        "fill_ratio": round(float(fill_ratio), 6),
                        "overlap_env": round(float(overlap_env), 6),
                        "overlap_core": round(float(overlap_core), 6),
                        "support_overlap": round(float(support_overlap), 6),
                        "boundary_strength": round(float(b_strength), 6),
                        "interior_texture": round(float(texture), 6),
                        "mean_signal": round(float(mean_signal), 6),
                        "border_touch": bool(border_touch),
                        "bbox_cover": round(float(bbox_cover), 6),
                    }
                )
            save_gray(step / f"{branch_name}_diameter_{d:04d}_labels_16bit.png", branch_label)

    append_crop_rescue_candidates(
        model,
        candidates,
        step,
        gray,
        clahe,
        wall_emphasis,
        signal,
        grad_mag,
        blackhat_big,
        blackhat_small,
        hint_env,
        hint_core,
        support_mask,
        local_std,
    )
    append_threshold_large_candidates(
        candidates,
        step,
        signal,
        grad_mag,
        blackhat_big,
        blackhat_small,
        hint_env,
        hint_core,
        support_mask,
        local_std,
    )

    with (step / "candidate_table.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(branch_rows[0].keys()) if branch_rows else ["branch"])
        writer.writeheader()
        if branch_rows:
            writer.writerows(branch_rows)
    write_json(
        step / "branch_summary.json",
        {
            "branches": [name for name, _, _, _ in inputs],
            "diameters": diameters,
            "small_diameters": small_diameters,
            "large_diameters": large_diameters,
            "candidate_count": len(candidates),
        },
    )
    return candidates


def apply_container_penalty(candidates: list[Candidate]) -> None:
    for cand in candidates:
        if cand.area < 180000:
            continue
        if cand.circularity < 0.72 or cand.fill_ratio < 0.54:
            continue
        inside_small = 0
        for other in candidates:
            if other is cand:
                continue
            if other.area < 3500 or other.area > cand.area * 0.35:
                continue
            oy = int(round(other.centroid_y))
            ox = int(round(other.centroid_x))
            oy = min(max(oy, 0), cand.mask.shape[0] - 1)
            ox = min(max(ox, 0), cand.mask.shape[1] - 1)
            if not cand.mask[oy, ox]:
                continue
            if iou(cand.mask, other.mask) > 0.30:
                continue
            if other.boundary_strength < 0.16:
                continue
            inside_small += 1
        penalty = 0.0
        if inside_small >= 2 and cand.support_overlap < 0.12 and cand.boundary_strength < 0.26:
            penalty += 0.50
        elif inside_small >= 1 and cand.support_overlap < 0.08 and cand.boundary_strength < 0.22:
            penalty += 0.22
        cand.container_penalty = penalty
        cand.score -= penalty


def merge_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict]]:
    apply_container_penalty(candidates)
    kept: list[Candidate] = []
    trace: list[dict] = []
    ranked = sorted(candidates, key=lambda c: (c.score, c.boundary_strength, c.area), reverse=True)
    for rank, cand in enumerate(ranked, start=1):
        action = "keep"
        reason = "new"
        replaced_index = None
        for idx, prev in enumerate(kept):
            ov = overlap_small(cand.mask, prev.mask)
            j = iou(cand.mask, prev.mask)
            if ov > 0.78 or j > 0.55:
                better_split = (
                    cand.circularity > prev.circularity + 0.05
                    and cand.area < prev.area * 0.92
                    and cand.boundary_strength >= prev.boundary_strength - 0.03
                )
                large_rescue = (
                    cand.area > prev.area * 1.22
                    and cand.boundary_strength >= prev.boundary_strength - 0.02
                    and cand.score > prev.score * 0.95
                    and cand.branch_type in {"direct", "large", "rescue", "crop"}
                )
                large_override = (
                    cand.branch_type in {"large", "rescue", "crop"}
                    and prev.branch_type == "guided"
                    and cand.area > prev.area * 1.45
                    and cand.support_overlap >= prev.support_overlap * 0.75
                    and cand.boundary_strength >= prev.boundary_strength - 0.03
                    and cand.score > prev.score * 0.80
                )
                clearly_better = (
                    cand.score > prev.score * 1.03
                    or (cand.boundary_strength > prev.boundary_strength + 0.06 and cand.area > prev.area * 0.85)
                )
                if better_split or large_rescue or large_override or clearly_better:
                    action = "replace"
                    reason = f"overlap_small={ov:.3f},iou={j:.3f}"
                    kept[idx] = cand
                    replaced_index = idx + 1
                else:
                    action = "skip"
                    reason = f"overlap_small={ov:.3f},iou={j:.3f}"
                break
        if action == "keep":
            kept.append(cand)
        trace.append(
            {
                "rank": rank,
                "branch": cand.branch,
                "branch_type": cand.branch_type,
                "diameter_px": cand.diameter,
                "area_px": cand.area,
                "score": round(cand.score, 6),
                "boundary_strength": round(cand.boundary_strength, 6),
                "container_penalty": round(cand.container_penalty, 6),
                "action": action,
                "reason": reason,
                "replaced_slot": replaced_index,
            }
        )
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
    diameters = [int(x) for x in args.diameters.split(",") if x.strip()]
    small_diameters = [int(x) for x in args.small_diameters.split(",") if x.strip()]
    large_diameters = [int(x) for x in args.large_diameters.split(",") if x.strip()]

    rgb, gray = seg.load_rgb_gray(tif)
    signal, _, _ = seg.compute_hybrid_signal(gray)

    step01 = out_dir / "step01_input"
    save_rgb(step01 / "step01_source_rgb.png", rgb)
    save_gray(step01 / "step02_source_gray.png", gray)
    save_gray(step01 / "step03_signal.png", signal)

    (
        clahe,
        wall_emphasis,
        small_wall,
        grad_mag,
        blackhat_big,
        blackhat_small,
        hint_env,
        hint_core,
        support_mask,
        small_seed,
        meta,
    ) = build_soft_priors(rgb, gray, signal, out_dir)

    model = models.CellposeModel(gpu=bool(args.gpu))
    candidates = run_branches(
        model,
        rgb,
        gray,
        signal,
        clahe,
        wall_emphasis,
        small_wall,
        grad_mag,
        blackhat_big,
        blackhat_small,
        hint_env,
        hint_core,
        support_mask,
        small_seed,
        diameters,
        small_diameters,
        large_diameters,
        out_dir,
    )

    step04 = out_dir / "step04_merge"
    step04.mkdir(parents=True, exist_ok=True)
    kept, trace = merge_candidates(candidates)
    with (step04 / "merge_trace.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(trace[0].keys()) if trace else ["rank"])
        writer.writeheader()
        if trace:
            writer.writerows(trace)

    labels, colors, overlay = build_final_outputs(rgb, kept)
    step05 = out_dir / "step05_final"
    save_gray(step05 / "step50_final_mask_16bit.png", labels)
    save_rgb(step05 / "step51_final_instance_rgb.png", colors)
    save_rgb(step05 / "step52_final_overlay.png", overlay)
    save_gray(step05 / "step53_final_signal.png", signal)
    save_binary(step05 / "step54_final_hint_envelope.png", hint_env)
    save_binary(step05 / "step55_final_support_mask.png", support_mask)

    rows = []
    for idx, cand in enumerate(sorted(kept, key=lambda c: c.area, reverse=True), start=1):
        rows.append(
            {
                "final_label": idx,
                "branch": cand.branch,
                "branch_type": cand.branch_type,
                "diameter_px": cand.diameter,
                "area_px": cand.area,
                "score": round(cand.score, 6),
                "circularity": round(cand.circularity, 6),
                "fill_ratio": round(cand.fill_ratio, 6),
                "overlap_env": round(cand.overlap_env, 6),
                "overlap_core": round(cand.overlap_core, 6),
                "support_overlap": round(cand.support_overlap, 6),
                "boundary_strength": round(cand.boundary_strength, 6),
                "interior_texture": round(cand.interior_texture, 6),
                "mean_signal": round(cand.mean_signal, 6),
                "border_touch": cand.border_touch,
                "bbox_cover": round(cand.bbox_cover, 6),
                "container_penalty": round(cand.container_penalty, 6),
            }
        )
    with (step05 / "step56_final_object_table.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["final_label"])
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    summary = {
        "source_tif": str(tif),
        "diameters_px": diameters,
        "small_diameters_px": small_diameters,
        "large_diameters_px": large_diameters,
        "candidate_count_before_merge": len(candidates),
        "final_count": int(labels.max()),
        "note": meta["note"],
        "final_objects": rows,
        "notes": {
            "goal": "App81 hybrid soft-prior v3 segmentation with localized priors, explicit large-object branches, and stronger droplet suppression.",
            "branches": [
                "guided_raw",
                "guided_masked",
                "direct_raw",
                "direct_clahe",
                "direct_wall",
                "large_direct_raw",
                "large_direct_wall",
                "crop_raw",
                "crop_clahe",
                "crop_wall",
                "threshold_large",
                "small_wall",
            ],
            "hint_is_hard_gate": False,
        },
    }
    write_json(step05 / "step57_final_summary.json", summary)
    write_json(
        out_dir / "manifest.json",
        {
            "source_tif": str(tif),
            "output_root": str(out_dir),
            "steps": ["step01_input", "step02_soft_priors", "step03_multibranch", "step04_merge", "step05_final"],
            "summary": str((step05 / "step57_final_summary.json").resolve()),
        },
    )
    print(json.dumps({"output_root": str(out_dir), "final_count": int(labels.max())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
