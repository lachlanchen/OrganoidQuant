#!/usr/bin/env python3
from __future__ import annotations

import argparse
import colorsys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


VISUAL_PRIORS: List[Dict[str, Any]] = [
    {
        "name": "upper_fused_mass",
        "roi_frac": [0.31, 0.07, 0.71, 0.41],
        "seed_frac": [0.52, 0.25],
        "min_area_px": 30000,
        "residual_percentile": 62,
        "dark_percentile": 40,
        "grow_px": 5,
    },
    {
        "name": "left_mid_dark_cluster",
        "roi_frac": [0.16, 0.25, 0.34, 0.41],
        "seed_frac": [0.28, 0.36],
        "min_area_px": 3500,
        "residual_percentile": 70,
        "dark_percentile": 42,
        "grow_px": 3,
    },
    {
        "name": "right_upper_cluster",
        "roi_frac": [0.69, 0.24, 0.82, 0.43],
        "seed_frac": [0.75, 0.34],
        "min_area_px": 8000,
        "residual_percentile": 64,
        "dark_percentile": 42,
        "grow_px": 4,
    },
    {
        "name": "right_mid_cluster",
        "roi_frac": [0.67, 0.43, 0.82, 0.64],
        "seed_frac": [0.76, 0.55],
        "min_area_px": 9000,
        "residual_percentile": 64,
        "dark_percentile": 44,
        "grow_px": 4,
    },
    {
        "name": "lower_fused_mass",
        "roi_frac": [0.36, 0.43, 0.71, 0.85],
        "seed_frac": [0.53, 0.66],
        "min_area_px": 36000,
        "residual_percentile": 60,
        "dark_percentile": 41,
        "grow_px": 5,
    },
]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_input = repo_root / "DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"
    default_output = repo_root / "api-tests/organoid_visual_prior_cellpose_segmentation_test/output"
    p = argparse.ArgumentParser(description="Run a fast visual-prior plus Cellpose organoid segmentation test on one image.")
    p.add_argument("--input-tif", default=str(default_input))
    p.add_argument("--output-root", default=str(default_output))
    p.add_argument("--run-dir", default="")
    p.add_argument("--small-branch-manifest", default="")
    return p.parse_args()


def make_run_dir(output_root: Path, input_tif: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_parent = input_tif.parent.name.replace("/", "_")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", input_tif.stem)
    out = output_root / f"{safe_parent}_{safe_name}_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    return out


def save_png_from_tif(src_tif: Path, out_png: Path) -> None:
    with Image.open(src_tif) as im:
        im.save(out_png, format="PNG")


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def label_to_color(label: int) -> Tuple[int, int, int]:
    hue = (label * 0.61803398875) % 1.0
    sat = 0.65
    val = 0.95
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def render_instance_rgb(masks: np.ndarray) -> np.ndarray:
    out = np.zeros((masks.shape[0], masks.shape[1], 3), dtype=np.uint8)
    for lid in [int(x) for x in np.unique(masks) if int(x) > 0]:
        out[masks == lid] = label_to_color(lid)
    return out


def render_overlay(source_rgb: np.ndarray, masks: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    for lid in [int(x) for x in np.unique(masks) if int(x) > 0]:
        color = label_to_color(lid)
        mask = (masks == lid).astype(np.uint8)
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.18, overlay, 0.82, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def build_stats(masks: np.ndarray) -> List[Dict[str, Any]]:
    stats: List[Dict[str, Any]] = []
    for lid in [int(x) for x in np.unique(masks) if int(x) > 0]:
        ys, xs = np.where(masks == lid)
        area = int(xs.size)
        if area == 0:
            continue
        x0, x1 = int(np.min(xs)), int(np.max(xs) + 1)
        y0, y1 = int(np.min(ys)), int(np.max(ys) + 1)
        stats.append(
            {
                "mask_id": lid,
                "area_px": area,
                "center_x_px": round(float(np.mean(xs)), 2),
                "center_y_px": round(float(np.mean(ys)), 2),
                "bbox_x0": x0,
                "bbox_y0": y0,
                "bbox_x1": x1,
                "bbox_y1": y1,
                "equiv_radius_px": round(float(np.sqrt(area / np.pi)), 2),
            }
        )
    stats.sort(key=lambda item: item["mask_id"])
    return stats


def relabel_sequential(labels: np.ndarray) -> np.ndarray:
    out = np.zeros_like(labels, dtype=np.uint16)
    next_id = 0
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        next_id += 1
        out[labels == lid] = next_id
    return out


def load_label_png(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise FileNotFoundError(path)
    if arr.ndim != 2:
        raise ValueError(f"Expected single-channel label image: {path}")
    return arr.astype(np.uint16)


def fraction_roi_mask(shape: Tuple[int, int], roi_frac: List[float]) -> np.ndarray:
    h, w = shape
    x0 = max(0, min(w - 1, int(round(roi_frac[0] * w))))
    y0 = max(0, min(h - 1, int(round(roi_frac[1] * h))))
    x1 = max(x0 + 1, min(w, int(round(roi_frac[2] * w))))
    y1 = max(y0 + 1, min(h, int(round(roi_frac[3] * h))))
    mask = np.zeros((h, w), dtype=np.uint8)
    cx = int(round((x0 + x1) / 2.0))
    cy = int(round((y0 + y1) / 2.0))
    axes = (max(1, int(round((x1 - x0) / 2.0))), max(1, int(round((y1 - y0) / 2.0))))
    cv2.ellipse(mask, (cx, cy), axes, 0, 0, 360, 1, thickness=-1)
    mask = mask.astype(bool)
    return mask


def fraction_point(shape: Tuple[int, int], point_frac: List[float]) -> Tuple[int, int]:
    h, w = shape
    x = int(round(point_frac[0] * w))
    y = int(round(point_frac[1] * h))
    return x, y


def compute_preprocessed_maps(source_rgb: np.ndarray) -> Dict[str, np.ndarray]:
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (5, 5), 0)
    background = cv2.GaussianBlur(blur, (0, 0), 17)
    residual = np.clip(background.astype(np.float32) - blur.astype(np.float32), 0, None)
    return {"gray": gray, "clahe": clahe, "blur": blur, "residual": residual}


def circle_mask(shape: Tuple[int, int], radius_fraction: float) -> np.ndarray:
    h, w = shape
    cx = w / 2.0
    cy = h / 2.0
    r = min(h, w) * radius_fraction
    yy, xx = np.ogrid[:h, :w]
    return ((xx - cx) ** 2 + (yy - cy) ** 2) <= r ** 2


def select_best_component(binary: np.ndarray, seed_xy: Tuple[int, int], min_area_px: int, roi_mask: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    num_labels, cc_labels, stats, centroids = cv2.connectedComponentsWithStats(binary.astype(np.uint8), connectivity=8)
    seed_x, seed_y = seed_xy
    roi_boundary = roi_mask.astype(np.uint8) - cv2.erode(roi_mask.astype(np.uint8), np.ones((9, 9), np.uint8), iterations=1)
    best_mask = np.zeros_like(binary, dtype=bool)
    best_info: Dict[str, Any] = {
        "selected": False,
        "component_count": int(num_labels - 1),
    }
    best_score = None
    for src_id in range(1, num_labels):
        area = int(stats[src_id, cv2.CC_STAT_AREA])
        if area < min_area_px:
            continue
        cx, cy = centroids[src_id]
        dist = float(np.hypot(cx - seed_x, cy - seed_y))
        comp_mask = cc_labels == src_id
        boundary_touch_px = int(np.count_nonzero(comp_mask & (roi_boundary > 0)))
        score = area - 180.0 * dist - 50.0 * boundary_touch_px
        if best_score is None or score > best_score:
            best_score = score
            best_mask = comp_mask
            best_info = {
                "selected": True,
                "source_component_id": int(src_id),
                "area_px": area,
                "center_x_px": round(float(cx), 2),
                "center_y_px": round(float(cy), 2),
                "distance_to_seed_px": round(dist, 2),
                "boundary_touch_px": boundary_touch_px,
                "score": round(score, 2),
                "component_count": int(num_labels - 1),
            }
    return best_mask, best_info


def detect_visual_prior_labels(source_rgb: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any], np.ndarray]:
    maps = compute_preprocessed_maps(source_rgb)
    blur = maps["blur"]
    residual = maps["residual"]
    h, w = blur.shape
    central_circle = circle_mask((h, w), 0.42)

    labels = np.zeros((h, w), dtype=np.uint16)
    overlay = source_rgb.copy()
    next_id = 0
    region_debug: List[Dict[str, Any]] = []

    for prior in VISUAL_PRIORS:
        roi = fraction_roi_mask((h, w), prior["roi_frac"])
        seed_x, seed_y = fraction_point((h, w), prior["seed_frac"])
        roi_residual = residual[roi]
        roi_blur = blur[roi]
        residual_thr = float(np.percentile(roi_residual, prior["residual_percentile"]))
        dark_thr = float(np.percentile(roi_blur, prior["dark_percentile"]))

        candidate = (((residual >= residual_thr) | (blur <= dark_thr)) & roi & central_circle).astype(np.uint8)
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

        selected_mask, selected_info = select_best_component(candidate.astype(bool), (seed_x, seed_y), prior["min_area_px"], roi)
        if not selected_info["selected"]:
            region_debug.append(
                {
                    "name": prior["name"],
                    "selected": False,
                    "seed_x_px": seed_x,
                    "seed_y_px": seed_y,
                    "residual_threshold": round(residual_thr, 3),
                    "dark_threshold": round(dark_thr, 3),
                    "component_count": selected_info["component_count"],
                }
            )
            continue

        grown = cv2.dilate(selected_mask.astype(np.uint8), np.ones((prior["grow_px"], prior["grow_px"]), np.uint8), iterations=1)
        grown = cv2.morphologyEx(grown, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        grown = cv2.bitwise_and(grown, roi.astype(np.uint8))

        next_id += 1
        labels[grown > 0] = next_id

        color = label_to_color(next_id)
        fill = overlay.copy()
        fill[grown > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 3)
        cv2.circle(overlay, (seed_x, seed_y), 6, color, -1)

        region_debug.append(
            {
                "name": prior["name"],
                "selected": True,
                "mask_id": next_id,
                "seed_x_px": seed_x,
                "seed_y_px": seed_y,
                "residual_threshold": round(residual_thr, 3),
                "dark_threshold": round(dark_thr, 3),
                "grow_px": prior["grow_px"],
                "selection": selected_info,
            }
        )

    return labels, {"priors": region_debug}, overlay


def combine_prior_then_small(prior_labels: np.ndarray, small_labels: np.ndarray) -> np.ndarray:
    if prior_labels.shape != small_labels.shape:
        raise ValueError("Label shapes must match for combination")
    combined = np.zeros_like(prior_labels, dtype=np.uint16)
    next_id = 0
    for lid in [int(x) for x in np.unique(prior_labels) if int(x) > 0]:
        next_id += 1
        combined[prior_labels == lid] = next_id
    occupied = combined > 0
    for lid in [int(x) for x in np.unique(small_labels) if int(x) > 0]:
        mask = small_labels == lid
        area = int(np.count_nonzero(mask))
        if area == 0:
            continue
        overlap = int(np.count_nonzero(mask & occupied))
        overlap_ratio = overlap / float(area)
        ys, xs = np.where(mask)
        cx = int(round(float(np.mean(xs))))
        cy = int(round(float(np.mean(ys))))
        centroid_occupied = bool(occupied[cy, cx]) if 0 <= cy < occupied.shape[0] and 0 <= cx < occupied.shape[1] else False
        if overlap_ratio > 0.18 or centroid_occupied:
            continue
        next_id += 1
        combined[mask] = next_id
        occupied |= mask
    return combined


def write_outputs(run_dir: Path, prefix: str, source_rgb: np.ndarray, labels: np.ndarray) -> Dict[str, str]:
    labels = relabel_sequential(labels)
    label_png = run_dir / f"{prefix}_labels_16bit.png"
    rgb_png = run_dir / f"{prefix}_instance_rgb.png"
    overlay_png = run_dir / f"{prefix}_overlay.png"
    stats_json = run_dir / f"{prefix}_stats.json"
    cv2.imwrite(str(label_png), labels.astype(np.uint16))
    Image.fromarray(render_instance_rgb(labels)).save(rgb_png)
    Image.fromarray(render_overlay(source_rgb, labels)).save(overlay_png)
    write_json(stats_json, {"mask_count": len([x for x in np.unique(labels) if int(x) > 0]), "stats": build_stats(labels)})
    return {
        "label_png": str(label_png),
        "rgb_png": str(rgb_png),
        "overlay_png": str(overlay_png),
        "stats_json": str(stats_json),
    }


def render_comparison_panel(source_rgb: np.ndarray, prior_overlay: np.ndarray, small_overlay: np.ndarray, combined_overlay: np.ndarray) -> np.ndarray:
    panels = []
    for title, image in [
        ("Source", source_rgb),
        ("Visual prior", prior_overlay),
        ("Small Cellpose", small_overlay),
        ("Prior + Cellpose", combined_overlay),
    ]:
        panel = image.copy()
        cv2.putText(panel, title, (30, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3, cv2.LINE_AA)
        panels.append(panel)
    top = np.concatenate(panels[:2], axis=1)
    bottom = np.concatenate(panels[2:], axis=1)
    return np.concatenate([top, bottom], axis=0)


def main() -> int:
    args = parse_args()
    input_tif = Path(args.input_tif).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(args.run_dir).resolve() if args.run_dir else make_run_dir(output_root, input_tif)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"run_dir={run_dir}")

    source_png = run_dir / f"{input_tif.stem}.png"
    save_png_from_tif(input_tif, source_png)
    source_rgb = load_rgb(source_png)

    if not args.small_branch_manifest:
        raise RuntimeError("Expected --small-branch-manifest generated by the shell wrapper.")
    small_manifest_path = Path(args.small_branch_manifest).resolve()
    small_manifest = json.loads(small_manifest_path.read_text(encoding="utf-8"))
    small_labels = load_label_png(Path(small_manifest["filtered_label_png"]))
    small_overlay = np.array(Image.open(Path(small_manifest["overlay_png"])).convert("RGB"))

    prior_labels, prior_debug, prior_overlay = detect_visual_prior_labels(source_rgb)
    combined_labels = combine_prior_then_small(prior_labels, small_labels)

    prior_label_png = run_dir / "visual_prior_labels_16bit.png"
    prior_rgb_png = run_dir / "visual_prior_rgb.png"
    prior_overlay_png = run_dir / "visual_prior_overlay.png"
    prior_debug_json = run_dir / "visual_prior_debug.json"
    cv2.imwrite(str(prior_label_png), relabel_sequential(prior_labels).astype(np.uint16))
    Image.fromarray(render_instance_rgb(relabel_sequential(prior_labels))).save(prior_rgb_png)
    Image.fromarray(prior_overlay).save(prior_overlay_png)
    write_json(prior_debug_json, prior_debug)

    combined_outputs = write_outputs(run_dir, "visual_prior_cellpose_combined", source_rgb, combined_labels)
    comparison_panel = render_comparison_panel(
        source_rgb,
        prior_overlay,
        small_overlay,
        np.array(Image.open(combined_outputs["overlay_png"]).convert("RGB")),
    )
    comparison_png = run_dir / "comparison_panel.png"
    Image.fromarray(comparison_panel).save(comparison_png)

    summary = {
        "input_tif": str(input_tif),
        "source_png": str(source_png),
        "small_branch_manifest": str(small_manifest_path),
        "visual_prior_labels": str(prior_label_png),
        "visual_prior_rgb": str(prior_rgb_png),
        "visual_prior_overlay": str(prior_overlay_png),
        "visual_prior_debug": str(prior_debug_json),
        "combined_outputs": combined_outputs,
        "comparison_panel_png": str(comparison_png),
        "small_branch_mask_count": len([x for x in np.unique(small_labels) if int(x) > 0]),
        "visual_prior_count": len([x for x in np.unique(prior_labels) if int(x) > 0]),
        "combined_count": len([x for x in np.unique(combined_labels) if int(x) > 0]),
    }
    write_json(run_dir / "run_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
