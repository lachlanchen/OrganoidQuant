#!/usr/bin/env python3
"""Simple instance separation for GRS-AI generated organoid masks.

Method:
- threshold non-black foreground from generated RGB mask
- derive stable seeds from dominant hue regions in the generated mask
- split touching support with watershed inside the mask support

This is intended to stay simple and bounded. It uses the generated mask as the
source of truth and only separates touching regions geometrically.
"""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.segmentation import watershed


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Separate GRS-AI generated masks into instances.")
    p.add_argument("--source", required=True, help="Source microscopy image")
    p.add_argument("--generated-mask", required=True, help="Generated RGB mask image")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--min-seed-area", type=int, default=120, help="Minimum seed area")
    p.add_argument("--min-final-area", type=int, default=160, help="Minimum final area")
    return p.parse_args()


def ensure_rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


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
        overlay = cv2.addWeighted(fill, 0.24, overlay, 0.76, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def build_support(mask_rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(mask_rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    fg = np.logical_and(val > 24, sat > 24).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
    fg = ndi.binary_fill_holes(fg > 0).astype(np.uint8)
    return fg


def source_feature_maps(source_rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    mean = cv2.GaussianBlur(gray, (0, 0), 11)
    sq_mean = cv2.GaussianBlur(gray * gray, (0, 0), 11)
    local_std = np.sqrt(np.maximum(sq_mean - mean * mean, 0.0))
    dark = 1.0 - gray
    return dark, local_std, grad


def remove_droplet_like_support(support: np.ndarray, source_rgb: np.ndarray) -> Tuple[np.ndarray, list[dict]]:
    h, w = support.shape
    total = float(h * w)
    dark, local_std, grad = source_feature_maps(source_rgb)
    grad_thr = float(np.quantile(grad, 0.55))
    std_thr = float(np.quantile(local_std, 0.45))
    filtered = np.zeros_like(support, dtype=np.uint8)
    dropped: list[dict] = []
    kept_any = False

    num, cc, stats, _ = cv2.connectedComponentsWithStats(support.astype(np.uint8), connectivity=8)
    for lid in range(1, num):
        mask = cc == lid
        area = int(mask.sum())
        if area == 0:
            continue
        frac = area / total
        ys, xs = np.where(mask)
        border_touch = bool((ys == 0).any() or (ys == h - 1).any() or (xs == 0).any() or (xs == w - 1).any())
        dark_mean = float(dark[mask].mean())
        std_mean = float(local_std[mask].mean())
        boundary = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
        boundary_grad = float(grad[boundary].mean()) if boundary.any() else 0.0
        droplet_like = (
            (frac > 0.10 and dark_mean < 0.34 and std_mean < std_thr and boundary_grad < grad_thr)
            or (frac > 0.22 and dark_mean < 0.40 and std_mean < max(std_thr, 0.045))
            or (border_touch and frac > 0.08 and dark_mean < 0.34 and std_mean < std_thr)
        )
        if droplet_like:
            dropped.append(
                {
                    "label": int(lid),
                    "area_fraction": round(frac, 6),
                    "touches_border": border_touch,
                    "mean_darkness": round(dark_mean, 6),
                    "mean_local_std": round(std_mean, 6),
                    "mean_boundary_grad": round(boundary_grad, 6),
                }
            )
            continue
        filtered[mask] = 1
        kept_any = True

    if not kept_any:
        return support.astype(np.uint8), dropped
    return filtered, dropped


def build_hue_seeds(mask_rgb: np.ndarray, support: np.ndarray, min_area: int) -> np.ndarray:
    hsv = cv2.cvtColor(mask_rgb, cv2.COLOR_RGB2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    val_blur = cv2.GaussianBlur(val, (5, 5), 0)
    grad_x = cv2.Sobel(val_blur, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(val_blur, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(grad_x, grad_y)
    eroded_support = cv2.erode(support.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)

    # Coarse hue bins to collapse anti-aliased shades of the same instance color.
    hue_bin = ((hue.astype(np.int32) + 7) // 15) % 12
    labels = np.zeros(hue.shape, dtype=np.uint16)
    next_label = 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    for bin_id in range(12):
        candidate = np.logical_and.reduce(
            [
                eroded_support > 0,
                sat > 60,
                val > 70,
                grad < 18,
                hue_bin == bin_id,
            ]
        ).astype(np.uint8)
        if int(candidate.sum()) == 0:
            continue
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, kernel, iterations=1)
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, kernel, iterations=1)
        eroded = cv2.erode(candidate, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
        work = eroded if int(eroded.sum()) > 0 else candidate
        num, cc, stats, _ = cv2.connectedComponentsWithStats(work, connectivity=8)
        for lid in range(1, num):
            area = int(stats[lid, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            comp = (cc == lid).astype(np.uint8)
            labels[comp > 0] = next_label
            next_label += 1

    # Fallback: if no hue seeds survive, use support connected components.
    if next_label == 1:
        num, cc, stats, _ = cv2.connectedComponentsWithStats(support.astype(np.uint8), connectivity=8)
        for lid in range(1, num):
            area = int(stats[lid, cv2.CC_STAT_AREA])
            if area < min_area:
                continue
            labels[cc == lid] = next_label
            next_label += 1

    return labels


def polish_seed_labels(seed_labels: np.ndarray, support: np.ndarray, min_area: int) -> np.ndarray:
    polished = np.zeros_like(seed_labels, dtype=np.uint16)
    next_label = 1
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    support_mask = support > 0

    for lid in [int(x) for x in np.unique(seed_labels) if int(x) > 0]:
        mask = (seed_labels == lid).astype(np.uint8)
        if int(mask.sum()) < min_area:
            continue
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
        mask = ndi.binary_fill_holes(mask > 0)
        mask = np.logical_and(mask, support_mask)
        if int(mask.sum()) < min_area:
            continue
        polished[mask] = next_label
        next_label += 1

    return polished


def separate_instances(source_rgb: np.ndarray, mask_rgb: np.ndarray, min_seed_area: int, min_final_area: int) -> Dict[str, np.ndarray]:
    support = build_support(mask_rgb)
    filtered_support, dropped = remove_droplet_like_support(support, source_rgb)
    seed_labels = build_hue_seeds(mask_rgb, filtered_support, min_seed_area)
    seed_primary = polish_seed_labels(seed_labels, filtered_support, min_final_area)
    distance = ndi.distance_transform_edt(filtered_support)
    final = watershed(-distance, markers=seed_labels.astype(np.int32), mask=filtered_support > 0).astype(np.uint16)

    cleaned = np.zeros_like(final)
    next_label = 1
    for lid in [int(x) for x in np.unique(final) if int(x) > 0]:
        mask = final == lid
        area = int(mask.sum())
        if area < min_final_area:
            continue
        cleaned[mask] = next_label
        next_label += 1

    cleaned_rgb = render_instance_rgb(cleaned)

    return {
        "support": support.astype(np.uint8),
        "filtered_support": filtered_support.astype(np.uint8),
        "seed_labels": seed_labels.astype(np.uint16),
        "seed_primary_labels": seed_primary.astype(np.uint16),
        "final_labels": cleaned.astype(np.uint16),
        "cleaned_rgb": cleaned_rgb,
        "dropped_support_components": dropped,
    }


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)
    generated_mask_path = Path(args.generated_mask)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rgb = ensure_rgb(source_path)
    mask_rgb = ensure_rgb(generated_mask_path)
    if mask_rgb.shape[:2] != source_rgb.shape[:2]:
        mask_rgb = cv2.resize(mask_rgb, (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)

    result = separate_instances(source_rgb, mask_rgb, args.min_seed_area, args.min_final_area)

    support_path = output_dir / "support_mask.png"
    filtered_support_path = output_dir / "filtered_support_mask.png"
    seed_labels_path = output_dir / "seed_labels_16bit.png"
    seed_instance_path = output_dir / "seed_instance_rgb.png"
    seed_overlay_path = output_dir / "seed_overlay.png"
    seed_primary_labels_path = output_dir / "seed_primary_labels_16bit.png"
    seed_primary_instance_path = output_dir / "seed_primary_instance_rgb.png"
    seed_primary_overlay_path = output_dir / "seed_primary_overlay.png"
    final_labels_path = output_dir / "simple_instance_labels_16bit.png"
    final_instance_path = output_dir / "simple_instance_rgb.png"
    cleaned_mask_path = output_dir / "cleaned_flat_mask.png"
    final_overlay_path = output_dir / "simple_instance_overlay.png"
    summary_path = output_dir / "simple_instance_summary.json"

    Image.fromarray((result["support"] * 255).astype(np.uint8)).save(support_path)
    Image.fromarray((result["filtered_support"] * 255).astype(np.uint8)).save(filtered_support_path)
    Image.fromarray(result["seed_labels"]).save(seed_labels_path)
    Image.fromarray(render_instance_rgb(result["seed_labels"])).save(seed_instance_path)
    Image.fromarray(render_overlay(source_rgb, result["seed_labels"])).save(seed_overlay_path)
    Image.fromarray(result["seed_primary_labels"]).save(seed_primary_labels_path)
    Image.fromarray(render_instance_rgb(result["seed_primary_labels"])).save(seed_primary_instance_path)
    Image.fromarray(render_overlay(source_rgb, result["seed_primary_labels"])).save(seed_primary_overlay_path)
    Image.fromarray(result["final_labels"]).save(final_labels_path)
    Image.fromarray(result["cleaned_rgb"]).save(cleaned_mask_path)
    Image.fromarray(result["cleaned_rgb"]).save(final_instance_path)
    Image.fromarray(render_overlay(source_rgb, result["final_labels"])).save(final_overlay_path)

    summary = {
        "source_path": str(source_path),
        "generated_mask_path": str(generated_mask_path),
        "seed_count": int(len([x for x in np.unique(result["seed_labels"]) if int(x) > 0])),
        "seed_primary_count": int(len([x for x in np.unique(result["seed_primary_labels"]) if int(x) > 0])),
        "final_count": int(len([x for x in np.unique(result["final_labels"]) if int(x) > 0])),
        "dropped_support_component_count": int(len(result["dropped_support_components"])),
        "dropped_support_components": result["dropped_support_components"],
        "min_seed_area": int(args.min_seed_area),
        "min_final_area": int(args.min_final_area),
        "method": "threshold+hue_seeds+watershed+source_droplet_filter",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
