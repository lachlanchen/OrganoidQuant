#!/usr/bin/env python3
"""Conservative Cellpose refinement for GRS-AI App81 masks.

The generated mask is treated as the primary instance proposal.
Cellpose only refines boundaries locally per generated region and falls back
to the generated region whenever refinement is not clearly better.
"""

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
    p = argparse.ArgumentParser(description="Refine GRS-AI masks with conservative Cellpose.")
    p.add_argument("--source", required=True, help="Source microscopy PNG")
    p.add_argument("--generated-mask", required=True, help="Generated instance mask PNG")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--gpu", action="store_true", help="Use GPU")
    return p.parse_args()


def label_to_color(label: int) -> Tuple[int, int, int]:
    hue = (label * 0.6180339887498949) % 1.0
    sat = 0.82
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


def quantize_mask(mask_rgb: np.ndarray) -> np.ndarray:
    """Reduce anti-aliased color noise while preserving flat instance regions."""
    out = mask_rgb.copy()
    fg = out.max(axis=2) > 24
    out[~fg] = 0
    # Snap colors toward coarse bins to collapse anti-aliased edge shades.
    out[fg] = ((out[fg].astype(np.uint16) + 16) // 32 * 32).clip(0, 255).astype(np.uint8)
    return out


def build_seed_labels(mask_rgb: np.ndarray, min_area: int = 300) -> Tuple[np.ndarray, np.ndarray]:
    """Use generated regions directly as seeds; avoid k-means over-segmentation."""
    q = quantize_mask(mask_rgb)
    fg = (q.max(axis=2) > 24).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)

    h, w = fg.shape
    labels = np.zeros((h, w), dtype=np.uint16)
    next_label = 1

    # Prefer connected components within each dominant color, not arbitrary intensity clusters.
    unique_colors = np.unique(q.reshape(-1, 3), axis=0)
    unique_colors = [tuple(int(v) for v in c) for c in unique_colors if any(c)]

    for color in unique_colors:
        color_mask = np.all(q == np.array(color, dtype=np.uint8), axis=2).astype(np.uint8)
        if int(color_mask.sum()) == 0:
            continue
        num, cc, stats, _ = cv2.connectedComponentsWithStats(color_mask, connectivity=8)
        for lid in range(1, num):
            area = int(stats[lid, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            x = int(stats[lid, cv2.CC_STAT_LEFT])
            y = int(stats[lid, cv2.CC_STAT_TOP])
            ww = int(stats[lid, cv2.CC_STAT_WIDTH])
            hh = int(stats[lid, cv2.CC_STAT_HEIGHT])
            touches_full_border = x <= 0 or y <= 0 or (x + ww) >= w or (y + hh) >= h
            if touches_full_border:
                continue
            comp = (cc == lid).astype(np.uint8)
            labels[comp > 0] = next_label
            next_label += 1

    support = (labels > 0).astype(np.uint8)
    return labels, support


def make_local_branches(source_rgb: np.ndarray, seed_mask: np.ndarray) -> Dict[str, np.ndarray]:
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    soft = cv2.dilate(seed_mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)), iterations=1)
    masked_clahe = clahe.copy()
    masked_clahe[soft == 0] = 0
    return {"masked_clahe": masked_clahe}


def run_local_cellpose(model: models.CellposeModel, branches: Dict[str, np.ndarray], diameters: List[int]) -> List[np.ndarray]:
    candidates: List[np.ndarray] = []
    for image in branches.values():
        for diameter in diameters:
            masks, _flows, _styles = model.eval(
                image,
                diameter=diameter,
                cellprob_threshold=-1.5,
                flow_threshold=0.4,
            )
            if masks is None:
                continue
            candidates.append(masks.astype(np.int32))
    return candidates


def conservative_refine(source_rgb: np.ndarray, seed_labels: np.ndarray, gpu: bool) -> Tuple[np.ndarray, int]:
    final = np.zeros_like(seed_labels, dtype=np.uint16)
    model = models.CellposeModel(gpu=gpu)
    candidate_passes = 0
    next_label = 1
    h, w = seed_labels.shape

    for seed_id in [int(x) for x in np.unique(seed_labels) if int(x) > 0]:
        seed_mask = seed_labels == seed_id
        ys, xs = np.where(seed_mask)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        margin = max(20, int(round(max(y1 - y0, x1 - x0) * 0.18)))
        y0 = max(0, y0 - margin)
        x0 = max(0, x0 - margin)
        y1 = min(h, y1 + margin)
        x1 = min(w, x1 + margin)

        crop_rgb = source_rgb[y0:y1, x0:x1]
        crop_seed = seed_mask[y0:y1, x0:x1]
        seed_area = float(crop_seed.sum())
        eq_diameter = max(20.0, np.sqrt(4.0 * seed_area / np.pi))
        diameters = sorted({int(max(20, min(360, round(eq_diameter * s)))) for s in (1.0, 1.15)})
        branches = make_local_branches(crop_rgb, crop_seed)
        candidates = run_local_cellpose(model, branches, diameters)
        candidate_passes += len(candidates)

        best_mask = None
        best_score = -1.0
        dilated_seed = cv2.dilate(crop_seed.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)), iterations=1) > 0

        for cand in candidates:
            for cand_id in [int(x) for x in np.unique(cand) if int(x) > 0]:
                cand_mask = cand == cand_id
                inter = float(np.logical_and(crop_seed, cand_mask).sum())
                if inter <= 0:
                    continue
                cand_area = float(cand_mask.sum())
                iou = inter / max(float(np.logical_or(crop_seed, cand_mask).sum()), 1.0)
                overlap = inter / max(seed_area, 1.0)
                size_ratio = cand_area / max(seed_area, 1.0)
                outside_soft = float(np.logical_and(cand_mask, ~dilated_seed).sum()) / max(cand_area, 1.0)
                if iou < 0.55:
                    continue
                if overlap < 0.75:
                    continue
                if size_ratio < 0.7 or size_ratio > 1.5:
                    continue
                if outside_soft > 0.12:
                    continue
                score = iou + overlap - outside_soft
                if score > best_score:
                    best_score = score
                    best_mask = cand_mask

        placed = best_mask if best_mask is not None else crop_seed
        region = final[y0:y1, x0:x1]
        region[placed] = next_label
        final[y0:y1, x0:x1] = region
        next_label += 1

    return final, candidate_passes


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
    final_labels, candidate_passes = conservative_refine(source_rgb, seed_labels, gpu=bool(args.gpu))

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
        "candidate_passes": int(candidate_passes),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
