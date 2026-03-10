#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
from PIL import Image


def build_circle_mask(width: int, height: int, cx: float, cy: float, radius: float) -> np.ndarray:
    yy, xx = np.ogrid[:height, :width]
    mask = ((xx - cx) ** 2 + (yy - cy) ** 2) <= radius ** 2
    return mask.astype(np.uint8)


def load_cellpose_stats(prior_json_path: Path) -> List[Dict]:
    prior = json.loads(prior_json_path.read_text(encoding="utf-8"))
    stats_path = prior.get("cellpose", {}).get("mask_stats_json")
    if not stats_path:
        return []
    p = Path(stats_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_gray_image(source_png: Path) -> np.ndarray:
    with Image.open(source_png) as im:
        return np.array(im.convert("L"))


def main() -> None:
    p = argparse.ArgumentParser(description="Compute simple single-droplet 10x objective metrics.")
    p.add_argument("--source-png", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--organoid-prior-json", required=True)
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    source_png = Path(args.source_png).resolve()
    summary_json = Path(args.summary_json).resolve()
    organoid_prior_json = Path(args.organoid_prior_json).resolve()
    out_json = Path(args.out_json).resolve()

    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    gray = load_gray_image(source_png)

    h, w = gray.shape[:2]
    cx = float(summary["droplet_center_x_px"])
    cy = float(summary["droplet_center_y_px"])
    radius = float(summary["droplet_radius_px"])

    circle_mask = build_circle_mask(w, h, cx, cy, radius).astype(bool)
    inside = gray[circle_mask]
    if inside.size == 0:
        raise SystemExit("Droplet circle produced empty mask.")

    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(grad_x, grad_y)
    edges = cv2.Canny(gray, 30, 90)

    p35 = float(np.percentile(inside, 35))
    dark_mask = ((gray <= p35) & circle_mask).astype(np.uint8)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(dark_mask, connectivity=8)
    dark_component_areas = [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, num_labels) if int(stats[i, cv2.CC_STAT_AREA]) >= 40]

    cellpose_stats = load_cellpose_stats(organoid_prior_json)
    inside_cellpose = []
    for item in cellpose_stats:
        mx = float(item.get("center_x_px", -1))
        my = float(item.get("center_y_px", -1))
        if (mx - cx) ** 2 + (my - cy) ** 2 <= radius ** 2:
            inside_cellpose.append(item)

    droplet_area_px = float(math.pi * radius * radius)
    droplet_circumference_px = float(2.0 * math.pi * radius)
    dark_area_fraction = float(np.mean(dark_mask[circle_mask] > 0))
    edge_density = float(np.mean(edges[circle_mask] > 0))
    gradient_mean = float(np.mean(grad[circle_mask]))

    cellpose_count_inside = len(inside_cellpose)
    cellpose_total_area_inside_px = int(sum(int(x.get("area_px", 0)) for x in inside_cellpose))
    cellpose_mean_area_inside_px = float(cellpose_total_area_inside_px / cellpose_count_inside) if cellpose_count_inside else 0.0
    cellpose_largest_area_inside_px = int(max([int(x.get("area_px", 0)) for x in inside_cellpose], default=0))
    largest_mask_fraction = float(cellpose_largest_area_inside_px / max(cellpose_total_area_inside_px, 1))
    mean_mask_fraction = float(cellpose_mean_area_inside_px / max(droplet_area_px, 1.0))

    fusion_score_objective = 5.0 * min(
        1.0,
        0.40 * min(dark_area_fraction / 0.45, 1.0)
        + 0.35 * min(largest_mask_fraction / 0.35, 1.0)
        + 0.25 * min(mean_mask_fraction / 0.02, 1.0),
    )

    payload = {
        "source_png": str(source_png),
        "summary_json": str(summary_json),
        "organoid_prior_json": str(organoid_prior_json),
        "droplet_area_px": round(droplet_area_px, 2),
        "droplet_circumference_px": round(droplet_circumference_px, 2),
        "gray_mean_inside": round(float(np.mean(inside)), 4),
        "gray_std_inside": round(float(np.std(inside)), 4),
        "gradient_mean_inside": round(gradient_mean, 4),
        "edge_density_inside_0_to_1": round(edge_density, 6),
        "dark_area_fraction_inside_0_to_1": round(dark_area_fraction, 6),
        "dark_component_count_inside": len(dark_component_areas),
        "dark_component_largest_area_px": int(max(dark_component_areas, default=0)),
        "cellpose_mask_count_inside": cellpose_count_inside,
        "cellpose_total_area_inside_px": cellpose_total_area_inside_px,
        "cellpose_mean_area_inside_px": round(cellpose_mean_area_inside_px, 4),
        "cellpose_largest_area_inside_px": cellpose_largest_area_inside_px,
        "fusion_score_objective_0_to_5": round(float(fusion_score_objective), 4),
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
