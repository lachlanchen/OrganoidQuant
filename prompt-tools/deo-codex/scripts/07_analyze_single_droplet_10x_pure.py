#!/usr/bin/env python3
import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def parse_path_metadata(source_tif: Path) -> Dict[str, object]:
    image_name = source_tif.stem
    date_label = source_tif.parent.name
    concentration_label = source_tif.parent.parent.name
    magnification_token = "unknown"
    sample_token = "unknown"
    m = re.search(r"(?i)(\d+x)(\d+)", image_name)
    if m:
        magnification_token = m.group(1).lower()
        sample_token = m.group(2)
    concentration_value = None
    cl = concentration_label.lower()
    if cl == "no":
        concentration_value = 0.0
    elif cl.endswith("um"):
        try:
            concentration_value = float(concentration_label[:-2])
        except Exception:
            concentration_value = None
    return {
        "concentration_label": concentration_label,
        "concentration_value_uM": concentration_value,
        "date_label": date_label,
        "magnification_token": magnification_token,
        "sample_token": sample_token,
    }


def load_gray_image(source_png: Path) -> np.ndarray:
    with Image.open(source_png) as im:
        return np.array(im.convert("L"))


def build_circle_mask(height: int, width: int, cx: float, cy: float, radius: float) -> np.ndarray:
    yy, xx = np.ogrid[:height, :width]
    return ((xx - cx) ** 2 + (yy - cy) ** 2) <= radius ** 2


def estimate_central_blob(gray: np.ndarray) -> Dict[str, float]:
    h, w = gray.shape
    blur = ndi.gaussian_filter(gray.astype(np.float32), sigma=2.5)
    valid = gray > 5
    if not np.any(valid):
        return {
            "area_px": 0.0,
            "center_x_px": w / 2.0,
            "center_y_px": h / 2.0,
            "radius_equiv_px": min(h, w) * 0.22,
            "radius_enclosing_px": min(h, w) * 0.24,
        }

    p35 = float(np.percentile(blur[valid], 35))
    dark = (blur <= p35) & valid
    dark = ndi.binary_opening(dark, structure=np.ones((3, 3), dtype=bool), iterations=1)
    dark = ndi.binary_closing(dark, structure=np.ones((5, 5), dtype=bool), iterations=1)

    labels, n = ndi.label(dark)
    image_cx = w / 2.0
    image_cy = h / 2.0
    diag = math.hypot(w, h)
    best_label = 0
    best_score = -1.0
    best_area = 0
    for i in range(1, n + 1):
        area = int(np.count_nonzero(labels == i))
        if area < 500:
            continue
        ys, xs = np.where(labels == i)
        cx = float(np.mean(xs))
        cy = float(np.mean(ys))
        dist = math.hypot(cx - image_cx, cy - image_cy)
        center_score = max(0.0, 1.0 - (dist / (0.55 * diag)))
        score = area * (0.35 + 0.65 * center_score)
        if score > best_score:
            best_label = i
            best_score = score
            best_area = area

    if best_label == 0:
        return {
            "area_px": 0.0,
            "center_x_px": image_cx,
            "center_y_px": image_cy,
            "radius_equiv_px": min(h, w) * 0.22,
            "radius_enclosing_px": min(h, w) * 0.24,
        }

    ys, xs = np.where(labels == best_label)
    cx = float(np.mean(xs))
    cy = float(np.mean(ys))
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    return {
        "area_px": float(best_area),
        "center_x_px": cx,
        "center_y_px": cy,
        "radius_equiv_px": float(math.sqrt(best_area / math.pi)),
        "radius_enclosing_px": float(np.max(d)) if d.size else float(math.sqrt(best_area / math.pi)),
    }


def circle_edge_score(grad: np.ndarray, cx: float, cy: float, r: float, n_samples: int = 96) -> Tuple[float, float]:
    if r < 5:
        return -1.0, 0.0
    h, w = grad.shape
    theta = np.linspace(0.0, 2.0 * math.pi, n_samples, endpoint=False, dtype=np.float32)
    xs = np.rint(cx + r * np.cos(theta)).astype(np.int32)
    ys = np.rint(cy + r * np.sin(theta)).astype(np.int32)
    inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    visible = float(np.mean(inside))
    if visible < 0.65 or not np.any(inside):
        return -1.0, visible
    vals = grad[ys[inside], xs[inside]]
    return float(np.mean(vals) * (0.5 + 0.5 * visible)), visible


def visible_fraction(cx: float, cy: float, r: float, width: int, height: int) -> float:
    n = 4000
    rng = np.random.default_rng(0)
    ang = rng.random(n) * 2.0 * math.pi
    rad = np.sqrt(rng.random(n)) * r
    xs = cx + rad * np.cos(ang)
    ys = cy + rad * np.sin(ang)
    return float(((xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)).mean())


def estimate_circle(gray: np.ndarray, grad: np.ndarray, blob: Dict[str, float]) -> Tuple[float, float, float, float, float]:
    h, w = gray.shape
    bx = float(blob["center_x_px"])
    by = float(blob["center_y_px"])
    re = float(blob["radius_equiv_px"])
    ren = float(blob["radius_enclosing_px"])
    min_side = min(h, w)

    start_r = max(120.0, re * 1.08)
    end_r = min(float(min_side) * 0.48, max(ren * 1.85, re * 1.55))
    if end_r <= start_r:
        end_r = max(start_r + 12.0, re * 1.4)

    shifts = (-12.0, -6.0, 0.0, 6.0, 12.0)
    radii = np.arange(start_r, end_r + 1.0, 4.0, dtype=np.float32)
    best = (bx, by, max(start_r, re * 1.2), -1.0, 0.0)
    best_score = -1.0

    for dx in shifts:
        for dy in shifts:
            cx = bx + dx
            cy = by + dy
            for r in radii:
                edge_score, visible = circle_edge_score(grad, cx, cy, float(r))
                if edge_score < 0:
                    continue
                dist_blob = math.hypot(cx - bx, cy - by)
                center_blob_score = max(0.0, 1.0 - dist_blob / max(float(r), 1.0))
                radius_floor_score = min(1.0, float(r) / max(re * 1.05, 1.0))
                total_score = (0.55 * edge_score) + (7.0 * center_blob_score) + (2.5 * visible) + (2.0 * radius_floor_score)
                if total_score > best_score:
                    best_score = total_score
                    best = (cx, cy, float(r), edge_score, visible)

    cx, cy, r, edge_score, _ = best
    vis = visible_fraction(cx, cy, r, w, h)
    return cx, cy, r, edge_score, vis


def count_dark_components(gray: np.ndarray, circle_mask: np.ndarray, min_area: int) -> Tuple[int, List[int], float]:
    inside = gray[circle_mask]
    p30 = float(np.percentile(inside, 30)) if inside.size else 0.0
    dark = (gray <= p30) & circle_mask
    dark = ndi.binary_opening(dark, structure=np.ones((3, 3), dtype=bool), iterations=1)
    dark = ndi.binary_closing(dark, structure=np.ones((5, 5), dtype=bool), iterations=1)
    labels, n = ndi.label(dark)
    areas: List[int] = []
    for i in range(1, n + 1):
        area = int(np.count_nonzero(labels == i))
        if area >= min_area:
            areas.append(area)
    dark_fraction = float(np.mean(dark[circle_mask])) if np.any(circle_mask) else 0.0
    return len(areas), sorted(areas, reverse=True), dark_fraction


def shape_class(blob_area: float, droplet_area: float, edge_score: float) -> str:
    fill = blob_area / max(droplet_area, 1.0)
    if fill < 0.25 and edge_score > 10:
        return "round"
    if fill < 0.38:
        return "slightly_irregular"
    if fill < 0.55:
        return "irregular"
    return "highly_distorted"


def main() -> None:
    p = argparse.ArgumentParser(description="Analyze a 10x image with one central droplet using PIL/NumPy/SciPy.")
    p.add_argument("--source-tif", required=True)
    p.add_argument("--source-png", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--objective-json", required=True)
    p.add_argument("--combined-json", required=True)
    args = p.parse_args()

    source_tif = Path(args.source_tif).resolve()
    source_png = Path(args.source_png).resolve()
    summary_json = Path(args.summary_json).resolve()
    objective_json = Path(args.objective_json).resolve()
    combined_json = Path(args.combined_json).resolve()

    gray = load_gray_image(source_png)
    grad_y, grad_x = np.gradient(gray.astype(np.float32))
    grad = np.sqrt(grad_x * grad_x + grad_y * grad_y)

    meta = parse_path_metadata(source_tif)
    blob = estimate_central_blob(gray)
    cx, cy, radius, edge_score, vis = estimate_circle(gray, grad, blob)
    circle_mask = build_circle_mask(gray.shape[0], gray.shape[1], cx, cy, radius)

    droplet_area = float(math.pi * radius * radius)
    droplet_circumference = float(2.0 * math.pi * radius)
    min_area = max(60, int(droplet_area * 0.0012))
    organoid_count, organoid_areas, dark_fraction = count_dark_components(gray, circle_mask, min_area=min_area)
    largest_area = int(organoid_areas[0]) if organoid_areas else 0
    mean_area = float(np.mean(organoid_areas)) if organoid_areas else 0.0
    total_area = float(sum(organoid_areas))
    largest_fraction = float(largest_area / total_area) if total_area > 0 else 0.0
    fill_fraction = float(blob["area_px"] / max(droplet_area, 1.0))
    grad_threshold = float(np.percentile(grad[circle_mask], 75)) if np.any(circle_mask) else 0.0
    edge_density = float(np.mean(grad[circle_mask] >= grad_threshold)) if np.any(circle_mask) else 0.0

    count_factor = 1.0 - min(max(organoid_count - 1, 0) / 6.0, 1.0)
    fusion_visual = 5.0 * min(
        1.0,
        0.45 * min(fill_fraction / 0.45, 1.0)
        + 0.35 * largest_fraction
        + 0.20 * count_factor,
    )
    fusion_objective = 5.0 * min(
        1.0,
        0.40 * min(dark_fraction / 0.35, 1.0)
        + 0.35 * largest_fraction
        + 0.25 * count_factor,
    )
    fusion_combined = (fusion_visual + fusion_objective) / 2.0

    if radius * 2 < min(gray.shape) * 0.32:
        size_note = "small droplet footprint for a 10x frame"
    elif radius * 2 < min(gray.shape) * 0.55:
        size_note = "medium droplet footprint for a 10x frame"
    else:
        size_note = "large droplet footprint for a 10x frame"

    if fusion_combined < 1.5:
        fusion_note = "weak fusion signal from central dark-mass morphology"
    elif fusion_combined < 3.0:
        fusion_note = "moderate fusion signal from central dark-mass morphology"
    else:
        fusion_note = "strong fusion signal from central dark-mass morphology"

    summary = {
        "source_tif": str(source_tif),
        "source_png": str(source_png),
        "concentration_label": str(meta["concentration_label"]),
        "concentration_value_uM": meta["concentration_value_uM"],
        "date_label": str(meta["date_label"]),
        "magnification_token": str(meta["magnification_token"]),
        "sample_token": str(meta["sample_token"]),
        "droplet_center_x_px": round(float(cx), 2),
        "droplet_center_y_px": round(float(cy), 2),
        "droplet_radius_px": round(float(radius), 2),
        "droplet_visible_fraction_0_to_1": round(float(vis), 4),
        "droplet_shape_class": shape_class(float(blob["area_px"]), droplet_area, edge_score),
        "droplet_boundary_confidence_0_to_1": round(float(min(1.0, max(0.2, edge_score / 18.0))), 4),
        "organoid_count_estimated_visual": int(max(1, organoid_count)),
        "fusion_score_visual_0_to_5": round(float(fusion_visual), 4),
        "size_note": size_note,
        "fusion_note": fusion_note,
        "droplet_note": "single droplet estimated from the central morphology and radial gradient profile using PIL, NumPy, and SciPy",
    }

    objective = {
        "source_png": str(source_png),
        "droplet_area_px": round(droplet_area, 2),
        "droplet_circumference_px": round(droplet_circumference, 2),
        "gray_mean_inside": round(float(np.mean(gray[circle_mask])), 4) if np.any(circle_mask) else 0.0,
        "gray_std_inside": round(float(np.std(gray[circle_mask])), 4) if np.any(circle_mask) else 0.0,
        "gradient_mean_inside": round(float(np.mean(grad[circle_mask])), 4) if np.any(circle_mask) else 0.0,
        "edge_density_inside_0_to_1": round(edge_density, 6),
        "dark_area_fraction_inside_0_to_1": round(dark_fraction, 6),
        "dark_component_count_inside": int(organoid_count),
        "dark_component_largest_area_px": int(largest_area),
        "cellpose_mask_count_inside": 0,
        "cellpose_total_area_inside_px": 0,
        "cellpose_mean_area_inside_px": 0.0,
        "cellpose_largest_area_inside_px": 0,
        "component_mean_area_inside_px": round(mean_area, 4),
        "component_total_area_inside_px": round(total_area, 2),
        "fusion_score_objective_0_to_5": round(float(fusion_objective), 4),
    }

    combined = {
        "organoid_count_visual": int(max(1, organoid_count)),
        "organoid_count_cellpose_inside": 0,
        "organoid_count_combined": int(max(1, organoid_count)),
        "fusion_score_visual_0_to_5": round(float(fusion_visual), 4),
        "fusion_score_objective_0_to_5": round(float(fusion_objective), 4),
        "fusion_score_combined_0_to_5": round(float(fusion_combined), 4),
    }

    summary_json.parent.mkdir(parents=True, exist_ok=True)
    objective_json.parent.mkdir(parents=True, exist_ok=True)
    combined_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    objective_json.write_text(json.dumps(objective, ensure_ascii=False, indent=2), encoding="utf-8")
    combined_json.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "summary_json": str(summary_json),
                "objective_json": str(objective_json),
                "combined_json": str(combined_json),
                "organoid_count_combined": combined["organoid_count_combined"],
                "fusion_score_combined_0_to_5": combined["fusion_score_combined_0_to_5"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
