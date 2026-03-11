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


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_input = repo_root / "DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"
    default_output = repo_root / "api-tests/cellpose_organoid_segmentation_test/output"
    p = argparse.ArgumentParser(description="Run a direct Cellpose organoid segmentation test on one image.")
    p.add_argument("--input-tif", default=str(default_input))
    p.add_argument("--output-root", default=str(default_output))
    p.add_argument("--model-type", default="cyto3")
    p.add_argument("--diameter", type=float, default=32.0)
    p.add_argument("--cellprob-threshold", type=float, default=-1.5)
    p.add_argument("--flow-threshold", type=float, default=0.4)
    p.add_argument("--min-area-px", type=int, default=60)
    p.add_argument("--max-area-fraction", type=float, default=0.18)
    p.add_argument("--resize-max-dim", type=int, default=1536)
    return p.parse_args()


def make_run_dir(output_root: Path, input_tif: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_parent = input_tif.parent.name.replace("/", "_")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", input_tif.stem)
    run_dir = output_root / f"{safe_parent}_{safe_name}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def save_png_from_tif(src_tif: Path, out_png: Path) -> None:
    with Image.open(src_tif) as im:
        im.save(out_png, format="PNG")


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def preprocess_for_cellpose(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)
    rgb_enhanced = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
    return rgb_enhanced


def resize_if_needed(rgb: np.ndarray, max_dim: int) -> Tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    cur_max = max(h, w)
    if max_dim <= 0 or cur_max <= max_dim:
        return rgb, 1.0
    scale = max_dim / float(cur_max)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    resized = cv2.resize(rgb, new_size, interpolation=cv2.INTER_AREA)
    return resized, scale


def filter_masks(
    masks: np.ndarray,
    min_area_px: int,
    max_area_fraction: float,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    h, w = masks.shape
    max_area_px = int(max_area_fraction * h * w)
    kept = np.zeros_like(masks, dtype=np.int32)
    stats: List[Dict[str, Any]] = []
    new_id = 0
    labels = [int(x) for x in np.unique(masks) if int(x) > 0]
    for lid in labels:
        m = masks == lid
        area = int(np.count_nonzero(m))
        if area < min_area_px or area > max_area_px:
            continue
        ys, xs = np.where(m)
        if xs.size == 0:
            continue
        cx = float(np.mean(xs))
        cy = float(np.mean(ys))
        x0, x1 = int(np.min(xs)), int(np.max(xs) + 1)
        y0, y1 = int(np.min(ys)), int(np.max(ys) + 1)
        new_id += 1
        kept[m] = new_id
        stats.append(
            {
                "mask_id": new_id,
                "source_mask_id": lid,
                "area_px": area,
                "center_x_px": round(cx, 2),
                "center_y_px": round(cy, 2),
                "bbox_x0": x0,
                "bbox_y0": y0,
                "bbox_x1": x1,
                "bbox_y1": y1,
                "equiv_radius_px": round(float(np.sqrt(area / np.pi)), 2),
            }
        )
    return kept, stats


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


def normalize_to_u8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    out = (arr - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def save_cellpose_intermediates(run_dir: Path, flows: List[Any]) -> Dict[str, str]:
    artifacts: Dict[str, str] = {}
    if len(flows) >= 1 and isinstance(flows[0], np.ndarray):
        flow_rgb_png = run_dir / "cellpose_flow_rgb.png"
        Image.fromarray(flows[0]).save(flow_rgb_png)
        artifacts["flow_rgb_png"] = str(flow_rgb_png)

    if len(flows) >= 2 and isinstance(flows[1], np.ndarray) and flows[1].ndim == 3 and flows[1].shape[0] == 2:
        flow_y = flows[1][0]
        flow_x = flows[1][1]
        flow_mag = np.sqrt(flow_x ** 2 + flow_y ** 2)
        flow_x_png = run_dir / "cellpose_flow_x.png"
        flow_y_png = run_dir / "cellpose_flow_y.png"
        flow_mag_png = run_dir / "cellpose_flow_magnitude.png"
        cv2.imwrite(str(flow_x_png), cv2.applyColorMap(normalize_to_u8(flow_x), cv2.COLORMAP_TURBO))
        cv2.imwrite(str(flow_y_png), cv2.applyColorMap(normalize_to_u8(flow_y), cv2.COLORMAP_TURBO))
        cv2.imwrite(str(flow_mag_png), cv2.applyColorMap(normalize_to_u8(flow_mag), cv2.COLORMAP_VIRIDIS))
        artifacts["flow_x_png"] = str(flow_x_png)
        artifacts["flow_y_png"] = str(flow_y_png)
        artifacts["flow_magnitude_png"] = str(flow_mag_png)

    if len(flows) >= 3 and isinstance(flows[2], np.ndarray):
        cellprob = flows[2]
        cellprob_png = run_dir / "cellpose_cellprob_heatmap.png"
        cv2.imwrite(str(cellprob_png), cv2.applyColorMap(normalize_to_u8(cellprob), cv2.COLORMAP_INFERNO))
        artifacts["cellprob_png"] = str(cellprob_png)

    return artifacts


def main() -> int:
    args = parse_args()
    input_tif = Path(args.input_tif).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = make_run_dir(output_root, input_tif)
    print(f"run_dir={run_dir}")

    source_png = run_dir / f"{input_tif.stem}.png"
    save_png_from_tif(input_tif, source_png)
    source_rgb = load_rgb(source_png)
    working_rgb, working_scale = resize_if_needed(source_rgb, args.resize_max_dim)
    prepared_rgb = preprocess_for_cellpose(working_rgb)
    prepared_png = run_dir / "prepared_for_cellpose.png"
    Image.fromarray(prepared_rgb).save(prepared_png)

    from cellpose import models  # type: ignore

    model = models.Cellpose(model_type=args.model_type, gpu=False)
    masks_working, flows, styles, diams = model.eval(
        prepared_rgb,
        channels=[0, 0],
        diameter=args.diameter,
        cellprob_threshold=args.cellprob_threshold,
        flow_threshold=args.flow_threshold,
    )
    if working_scale != 1.0:
        masks = cv2.resize(
            masks_working.astype(np.uint16),
            (source_rgb.shape[1], source_rgb.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
    else:
        masks = masks_working

    raw_labels = [int(x) for x in np.unique(masks) if int(x) > 0]
    filtered_masks, stats = filter_masks(
        masks.astype(np.int32),
        min_area_px=args.min_area_px,
        max_area_fraction=args.max_area_fraction,
    )

    raw_label_png = run_dir / "cellpose_labels_raw_16bit.png"
    filtered_label_png = run_dir / "cellpose_labels_filtered_16bit.png"
    cv2.imwrite(str(raw_label_png), masks.astype(np.uint16))
    cv2.imwrite(str(filtered_label_png), filtered_masks.astype(np.uint16))
    intermediate_artifacts = save_cellpose_intermediates(run_dir, flows)

    instance_rgb = render_instance_rgb(filtered_masks)
    instance_rgb_png = run_dir / "cellpose_instance_rgb.png"
    Image.fromarray(instance_rgb).save(instance_rgb_png)

    overlay = render_overlay(source_rgb, filtered_masks)
    overlay_png = run_dir / "cellpose_overlay.png"
    Image.fromarray(overlay).save(overlay_png)

    summary = {
        "input_tif": str(input_tif),
        "source_png": str(source_png),
        "prepared_png": str(prepared_png),
        "preprocessing_mode": "full_image_clahe_gaussian_blur",
        "working_scale": round(working_scale, 6),
        "working_image_shape": [int(prepared_rgb.shape[1]), int(prepared_rgb.shape[0])],
        "source_image_shape": [int(source_rgb.shape[1]), int(source_rgb.shape[0])],
        "model_type": args.model_type,
        "diameter": args.diameter,
        "cellprob_threshold": args.cellprob_threshold,
        "flow_threshold": args.flow_threshold,
        "raw_mask_count": len(raw_labels),
        "filtered_mask_count": len(stats),
        "raw_label_png": str(raw_label_png),
        "filtered_label_png": str(filtered_label_png),
        "instance_rgb_png": str(instance_rgb_png),
        "overlay_png": str(overlay_png),
        "mask_stats_json": str(run_dir / "cellpose_mask_stats.json"),
        "intermediate_artifacts": intermediate_artifacts,
    }
    (run_dir / "cellpose_mask_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
