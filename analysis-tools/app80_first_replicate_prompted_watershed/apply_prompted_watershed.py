#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("source_tif")
    p.add_argument("params_json")
    p.add_argument("output_dir")
    return p.parse_args()


def ensure_odd(v: int, minimum: int = 1) -> int:
    v = max(minimum, int(v))
    return v if v % 2 == 1 else v + 1


def load_rgb(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if arr is None:
        with Image.open(path) as im:
            return np.array(im.convert("RGB").copy())
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def mask_geometry(mask: np.ndarray):
    area = float(mask.sum())
    if area <= 0:
        return 0.0, 0.0
    mask_u8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = float(sum(cv2.arcLength(cnt, True) for cnt in contours))
    circularity = 0.0
    if perimeter > 0:
        circularity = float(4.0 * math.pi * area / (perimeter * perimeter))
    return perimeter, circularity


def render_instance_rgb(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    hsv = np.zeros((1, 1, 3), dtype=np.uint8)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        hue = int(((lid * 0.61803398875) % 1.0) * 179)
        hsv[0, 0] = (hue, 180, 240)
        color = tuple(int(c) for c in cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0])
        out[labels == lid] = color
    return out


def render_overlay(source_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    palette = render_instance_rgb(labels)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        mask = (labels == lid).astype(np.uint8)
        colors = palette[mask > 0]
        if colors.size == 0:
            continue
        color = tuple(int(c) for c in colors[0])
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def main() -> int:
    args = parse_args()
    source_tif = Path(args.source_tif).resolve()
    params = json.loads(Path(args.params_json).read_text(encoding="utf-8"))
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    source_png = out_dir / f"{source_tif.stem}.png"
    if not source_png.exists():
        with Image.open(source_tif) as im:
            im.save(source_png, format="PNG")

    rgb = load_rgb(source_png)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=float(params["clahe_clip_limit"]), tileGridSize=(8, 8)).apply(gray)

    fgk = ensure_odd(params["foreground_blur_kernel_px"], 1)
    bgk = ensure_odd(params["background_blur_kernel_px"], 9)
    blur = cv2.GaussianBlur(clahe, (fgk, fgk), 0)
    bg = cv2.GaussianBlur(clahe, (bgk, bgk), 0)
    residual = cv2.subtract(bg, blur)
    inv = 255 - blur
    residual_norm = cv2.normalize(residual, None, 0, 255, cv2.NORM_MINMAX)
    inv_norm = cv2.normalize(inv, None, 0, 255, cv2.NORM_MINMAX)

    if params["signal_mode"] == "gray_inv":
        signal = inv_norm
    elif params["signal_mode"] == "residual":
        signal = residual_norm
    else:
        signal = cv2.addWeighted(inv_norm, 0.45, residual_norm, 0.55, 0)

    _, otsu_mask = cv2.threshold(signal, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    block = ensure_odd(params["adaptive_block_size_px"], 9)
    adaptive_mask = cv2.adaptiveThreshold(
        signal,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block,
        int(params["adaptive_c_offset"]),
    )

    if params["threshold_mode"] == "otsu":
        binary = otsu_mask
    elif params["threshold_mode"] == "adaptive_otsu":
        binary = cv2.bitwise_or(otsu_mask, adaptive_mask)
    else:
        binary = cv2.bitwise_or(otsu_mask, adaptive_mask)
        binary = cv2.medianBlur(binary, 3)

    ok = int(params["open_kernel_px"])
    ck = int(params["close_kernel_px"])
    if ok > 0:
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((ok, ok), np.uint8))
    if ck > 0:
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((ck, ck), np.uint8))

    sure_bg = cv2.dilate(binary, np.ones((3, 3), np.uint8), iterations=int(params["dilate_iterations"]))
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, sure_fg = cv2.threshold(
        dist,
        float(params["distance_threshold_fraction_0_to_1"]) * float(dist.max() if dist.size else 1.0),
        255,
        0,
    )
    sure_fg = sure_fg.astype(np.uint8)

    ncc, cc_labels, cc_stats, _ = cv2.connectedComponentsWithStats(sure_fg, connectivity=8)
    cleaned_fg = np.zeros_like(sure_fg)
    for idx in range(1, ncc):
        area = int(cc_stats[idx, cv2.CC_STAT_AREA])
        if area >= int(params["min_seed_area_px"]):
            cleaned_fg[cc_labels == idx] = 255
    sure_fg = cleaned_fg

    unknown = cv2.subtract(sure_bg, sure_fg)
    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1
    markers[unknown == 255] = 0
    ws_rgb = cv2.cvtColor(blur, cv2.COLOR_GRAY2RGB)
    markers = cv2.watershed(ws_rgb, markers.astype(np.int32))

    raw_labels = np.zeros_like(markers, dtype=np.int32)
    current = 0
    mask_stats = []
    dark_thresh = np.percentile(gray, 35)
    max_area_fraction = float(params["max_area_fraction_0_to_1"])
    circ_min = float(params["droplet_reject_circularity_min_0_to_1"])
    dark_frac_max = float(params["droplet_reject_dark_fraction_max_0_to_1"])
    h, w = gray.shape

    for lid in sorted(int(x) for x in np.unique(markers) if int(x) > 1):
        mask = markers == lid
        area = int(mask.sum())
        if area < int(params["min_area_px"]):
            continue
        area_fraction = area / float(h * w)
        perimeter, circularity = mask_geometry(mask)
        dark_fraction = float((gray[mask] <= dark_thresh).mean()) if area > 0 else 0.0
        droplet_like = area_fraction > max_area_fraction and circularity > circ_min and dark_fraction < dark_frac_max
        if droplet_like:
            continue
        ys, xs = np.where(mask)
        if xs.size == 0:
            continue
        current += 1
        raw_labels[mask] = current
        mask_stats.append(
            {
                "mask_id": current,
                "area_px": area,
                "center_x_px": round(float(xs.mean()), 2),
                "center_y_px": round(float(ys.mean()), 2),
                "bbox_x0": int(xs.min()),
                "bbox_y0": int(ys.min()),
                "bbox_x1": int(xs.max() + 1),
                "bbox_y1": int(ys.max() + 1),
                "perimeter_px": round(perimeter, 2),
                "circularity": round(circularity, 4),
                "dark_fraction": round(dark_fraction, 4),
                "area_fraction": round(area_fraction, 4),
            }
        )

    Image.fromarray(signal.astype(np.uint8)).save(out_dir / "signal.png")
    Image.fromarray(otsu_mask.astype(np.uint8)).save(out_dir / "otsu_mask.png")
    Image.fromarray(adaptive_mask.astype(np.uint8)).save(out_dir / "adaptive_mask.png")
    Image.fromarray(binary.astype(np.uint8)).save(out_dir / "binary_clean.png")
    Image.fromarray(dist_norm).save(out_dir / "distance_transform.png")
    Image.fromarray(sure_fg.astype(np.uint8)).save(out_dir / "sure_fg.png")
    Image.fromarray((unknown > 0).astype(np.uint8) * 255).save(out_dir / "unknown_region.png")
    labels_png = out_dir / "watershed_labels_16bit.png"
    cv2.imwrite(str(labels_png), raw_labels.astype(np.uint16))
    instance_png = out_dir / "watershed_instance_rgb.png"
    Image.fromarray(render_instance_rgb(raw_labels)).save(instance_png)
    overlay_png = out_dir / "watershed_overlay.png"
    Image.fromarray(render_overlay(rgb, raw_labels)).save(overlay_png)
    (out_dir / "watershed_mask_stats.json").write_text(json.dumps(mask_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
