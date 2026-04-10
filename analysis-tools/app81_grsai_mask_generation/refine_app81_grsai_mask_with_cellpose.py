#!/usr/bin/env python3
"""Refine GRS-AI-generated App81 masks into instance labels using Cellpose on the source image."""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image
from cellpose import models


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Refine GRS-AI masks with Cellpose.")
    p.add_argument("--source", required=True, help="Source microscopy PNG")
    p.add_argument("--generated-mask", required=True, help="Raw generated mask PNG")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--gpu", action="store_true", help="Use GPU")
    return p.parse_args()


def label_to_color(label: int) -> Tuple[int, int, int]:
    hue = (label * 0.6180339887498949) % 1.0
    sat = 0.78
    val = 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def render_instance_rgb(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        out[labels == lid] = label_to_color(lid)
    return out


def render_overlay(source_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        color = label_to_color(lid)
        mask = (labels == lid).astype(np.uint8)
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def ensure_rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def build_seed_labels(mask_rgb: np.ndarray, min_area: int = 120) -> Tuple[np.ndarray, np.ndarray]:
    hsv = cv2.cvtColor(mask_rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    fg = np.logical_and(sat > 48, val > 32).astype(np.uint8)
    if fg.sum() == 0:
        return np.zeros(fg.shape, dtype=np.uint16), fg

    num_fg, fg_cc, fg_stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    cleaned_fg = np.zeros_like(fg)
    h, w = fg.shape
    for lid in range(1, num_fg):
        area = int(fg_stats[lid, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(fg_stats[lid, cv2.CC_STAT_LEFT])
        y = int(fg_stats[lid, cv2.CC_STAT_TOP])
        ww = int(fg_stats[lid, cv2.CC_STAT_WIDTH])
        hh = int(fg_stats[lid, cv2.CC_STAT_HEIGHT])
        touches_border = x <= 0 or y <= 0 or (x + ww) >= w or (y + hh) >= h
        if touches_border:
            continue
        cleaned_fg[fg_cc == lid] = 1
    fg = cleaned_fg
    if fg.sum() == 0:
        return np.zeros(fg.shape, dtype=np.uint16), fg

    pixels = mask_rgb[fg > 0].astype(np.float32)
    k = min(6, max(3, len(pixels) // 30000 + 2))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _compactness, assignments, centers = cv2.kmeans(
        pixels,
        k,
        None,
        criteria,
        5,
        cv2.KMEANS_PP_CENTERS,
    )
    assignments = assignments.reshape(-1)

    cluster_map = np.full(fg.shape, -1, dtype=np.int32)
    cluster_map[fg > 0] = assignments

    labels = np.zeros(fg.shape, dtype=np.uint16)
    next_label = 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for cluster_id in range(k):
        cluster_mask = (cluster_map == cluster_id).astype(np.uint8)
        if cluster_mask.sum() == 0:
            continue
        cluster_mask = cv2.morphologyEx(cluster_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        cluster_mask = cv2.morphologyEx(cluster_mask, cv2.MORPH_OPEN, kernel, iterations=1)
        num, cc, stats, _ = cv2.connectedComponentsWithStats(cluster_mask, connectivity=8)
        for lid in range(1, num):
            area = int(stats[lid, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            x = int(stats[lid, cv2.CC_STAT_LEFT])
            y = int(stats[lid, cv2.CC_STAT_TOP])
            ww = int(stats[lid, cv2.CC_STAT_WIDTH])
            hh = int(stats[lid, cv2.CC_STAT_HEIGHT])
            touches_border = x <= 0 or y <= 0 or (x + ww) >= fg.shape[1] or (y + hh) >= fg.shape[0]
            if touches_border:
                continue
            labels[cc == lid] = next_label
            next_label += 1

    support = (labels > 0).astype(np.uint8)
    return labels, support


def masked_gray_branches(source_rgb: np.ndarray, support: np.ndarray) -> Dict[str, np.ndarray]:
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    dilated = cv2.dilate(support, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)), iterations=1)
    masked_gray = gray.copy()
    masked_gray[dilated == 0] = 0
    masked_clahe = clahe.copy()
    masked_clahe[dilated == 0] = 0
    return {
        "masked_gray": masked_gray,
        "masked_clahe": masked_clahe,
    }


def run_cellpose_candidates(branches: Dict[str, np.ndarray], gpu: bool) -> List[np.ndarray]:
    model = models.CellposeModel(gpu=gpu)
    diameters = [45, 90, 180, 320]
    candidates: List[np.ndarray] = []
    for branch_name, image in branches.items():
        for diameter in diameters:
            masks, _flows, _styles = model.eval(
                image,
                channels=[0, 0],
                diameter=diameter,
                cellprob_threshold=-1.5,
                flow_threshold=0.4,
            )
            if masks is None:
                continue
            candidates.append(masks.astype(np.int32))
    return candidates


def pick_refined_instances(seed_labels: np.ndarray, support: np.ndarray, candidates: List[np.ndarray]) -> np.ndarray:
    final = np.zeros(seed_labels.shape, dtype=np.uint16)
    used: set[Tuple[int, int]] = set()
    next_label = 1

    for seed_id in [int(x) for x in np.unique(seed_labels) if int(x) > 0]:
        seed_mask = seed_labels == seed_id
        seed_area = float(seed_mask.sum())
        best_mask = None
        best_score = -1.0
        for cand_idx, cand in enumerate(candidates):
            for cand_id in [int(x) for x in np.unique(cand) if int(x) > 0]:
                key = (cand_idx, cand_id)
                if key in used:
                    continue
                cand_mask = cand == cand_id
                inter = float(np.logical_and(seed_mask, cand_mask).sum())
                if inter <= 0:
                    continue
                cand_area = float(cand_mask.sum())
                overlap = inter / max(seed_area, 1.0)
                support_ratio = float(np.logical_and(cand_mask, support > 0).sum()) / max(cand_area, 1.0)
                outside_ratio = float(np.logical_and(cand_mask, support == 0).sum()) / max(cand_area, 1.0)
                size_ratio = cand_area / max(seed_area, 1.0)
                if support_ratio < 0.7 or outside_ratio > 0.2:
                    continue
                if size_ratio < 0.45 or size_ratio > 2.8:
                    continue
                score = overlap * 1.0 + support_ratio * 0.4 - outside_ratio * 0.8
                if score > best_score:
                    best_score = score
                    best_mask = (key, cand_mask)
        if best_mask is not None:
            used.add(best_mask[0])
            final[best_mask[1]] = next_label
        else:
            final[seed_mask] = next_label
        next_label += 1

    return final


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)
    mask_path = Path(args.generated_mask)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rgb = ensure_rgb(source_path)
    mask_rgb = ensure_rgb(mask_path)
    if mask_rgb.shape[:2] != source_rgb.shape[:2]:
        mask_rgb = cv2.resize(mask_rgb, (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)

    seed_labels, support = build_seed_labels(mask_rgb)
    branches = masked_gray_branches(source_rgb, support)
    candidates = run_cellpose_candidates(branches, gpu=bool(args.gpu))
    final_labels = pick_refined_instances(seed_labels, support, candidates)

    seed_labels_path = output_dir / "seed_labels_16bit.png"
    seed_instance_path = output_dir / "seed_instance_rgb.png"
    seed_overlay_path = output_dir / "seed_overlay.png"
    final_labels_path = output_dir / "cellpose_refined_labels_16bit.png"
    final_instance_path = output_dir / "cellpose_refined_instance_rgb.png"
    final_overlay_path = output_dir / "cellpose_refined_overlay.png"
    support_path = output_dir / "support_mask.png"
    summary_path = output_dir / "cellpose_refinement_summary.json"

    Image.fromarray(seed_labels.astype(np.uint16)).save(seed_labels_path)
    Image.fromarray(render_instance_rgb(seed_labels)).save(seed_instance_path)
    Image.fromarray(render_overlay(source_rgb, seed_labels)).save(seed_overlay_path)
    Image.fromarray((support * 255).astype(np.uint8)).save(support_path)
    Image.fromarray(final_labels.astype(np.uint16)).save(final_labels_path)
    Image.fromarray(render_instance_rgb(final_labels)).save(final_instance_path)
    Image.fromarray(render_overlay(source_rgb, final_labels)).save(final_overlay_path)

    summary = {
        "source_path": str(source_path),
        "generated_mask_path": str(mask_path),
        "seed_count": int(len([x for x in np.unique(seed_labels) if int(x) > 0])),
        "final_count": int(len([x for x in np.unique(final_labels) if int(x) > 0])),
        "candidate_passes": len(candidates),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
