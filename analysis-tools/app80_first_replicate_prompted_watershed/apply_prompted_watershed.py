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


def auto_canny(img: np.ndarray) -> np.ndarray:
    med = float(np.median(img))
    low = int(max(0, 0.66 * med))
    high = int(min(255, 1.33 * med))
    if high <= low:
        high = min(255, low + 20)
    return cv2.Canny(img, low, high)


def threshold_otsu_within_mask(img: np.ndarray, roi_mask: np.ndarray) -> np.ndarray:
    vals = img[roi_mask > 0]
    if vals.size == 0:
        return np.zeros_like(img)
    thr, _ = cv2.threshold(vals.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out = np.zeros_like(img)
    out[(img >= thr) & (roi_mask > 0)] = 255
    return out


def threshold_top_fraction_within_mask(img: np.ndarray, roi_mask: np.ndarray, fg_fraction: float) -> np.ndarray:
    vals = img[roi_mask > 0]
    if vals.size == 0:
        return np.zeros_like(img)
    fg_fraction = min(0.95, max(0.01, float(fg_fraction)))
    thr = float(np.percentile(vals, (1.0 - fg_fraction) * 100.0))
    out = np.zeros_like(img)
    out[(img >= thr) & (roi_mask > 0)] = 255
    return out


def fill_binary_holes(mask_u8: np.ndarray) -> np.ndarray:
    if mask_u8.max() == 0:
        return mask_u8.copy()
    h, w = mask_u8.shape
    flood = mask_u8.copy()
    flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    return cv2.bitwise_or(mask_u8, holes)


def extract_enclosed_compartments(
    boundary_mask: np.ndarray,
    roi_mask: np.ndarray,
    min_area_px: int,
    max_area_fraction: float,
) -> np.ndarray:
    roi_u8 = (roi_mask > 0).astype(np.uint8) * 255
    boundary_u8 = (boundary_mask > 0).astype(np.uint8) * 255
    non_boundary = np.zeros_like(boundary_u8)
    non_boundary[(roi_u8 > 0) & (boundary_u8 == 0)] = 255
    boundary_band = cv2.subtract(roi_u8, cv2.erode(roi_u8, np.ones((5, 5), np.uint8), iterations=1))
    ncc, labels, stats, _ = cv2.connectedComponentsWithStats(non_boundary, connectivity=8)
    out = np.zeros_like(boundary_u8)
    roi_area = max(1.0, float((roi_u8 > 0).sum()))
    max_area_px = max_area_fraction * roi_area
    for idx in range(1, ncc):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < int(min_area_px):
            continue
        if area > max_area_px:
            continue
        comp = labels == idx
        if np.any(comp & (boundary_band > 0)):
            continue
        out[comp] = 255
    return out


def detect_primary_droplet(gray: np.ndarray, stage_label: str):
    h, w = gray.shape
    scale = min(1.0, 640.0 / float(max(h, w)))
    if scale < 1.0:
        work = cv2.resize(gray, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
    else:
        work = gray
    wh, ww = work.shape
    center = np.array([ww / 2.0, wh / 2.0], dtype=np.float32)
    grad = cv2.Laplacian(cv2.GaussianBlur(work, (5, 5), 0), cv2.CV_32F)
    grad = np.abs(grad)
    min_radius = int(min(wh, ww) * (0.18 if stage_label == "cluster" else 0.16))
    max_radius = int(min(wh, ww) * 0.48)
    best = None
    for param2 in (24, 28, 32, 36):
        circles = cv2.HoughCircles(
            work,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(20, min(wh, ww) // 4),
            param1=100,
            param2=param2,
            minRadius=min_radius,
            maxRadius=max_radius,
        )
        if circles is None:
            continue
        for x, y, r in circles[0]:
            circ_mask = np.zeros_like(work, dtype=np.uint8)
            cv2.circle(circ_mask, (int(round(x)), int(round(y))), int(round(r)), 255, 2)
            ring_strength = float(grad[circ_mask > 0].mean()) if np.any(circ_mask > 0) else 0.0
            dist_penalty = float(np.linalg.norm(np.array([x, y]) - center) / max(wh, ww))
            radius_score = float(r / max(1.0, min(wh, ww)))
            score = ring_strength + 20.0 * radius_score - 80.0 * dist_penalty
            if best is None or score > best[0]:
                best = (score, float(x), float(y), float(r))
    if best is None:
        return None
    _, x, y, r = best
    return x / scale, y / scale, r / scale


def build_circle_masks(shape: tuple[int, int], circle):
    h, w = shape
    roi_mask = np.ones((h, w), dtype=np.uint8) * 255
    shell_mask = np.zeros((h, w), dtype=np.uint8)
    if circle is None:
        return roi_mask, shell_mask
    x, y, r = circle
    center = (int(round(x)), int(round(y)))
    radius = int(round(r))
    inner_radius = max(10, int(round(radius * 0.93)))
    outer_radius = min(max(h, w), int(round(radius * 1.03)))
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(roi_mask, center, inner_radius, 255, -1)
    shell_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(shell_mask, center, outer_radius, 255, max(3, outer_radius - inner_radius))
    return roi_mask, shell_mask


def fill_enclosed_regions(
    edge_mask: np.ndarray,
    roi_mask: np.ndarray,
    forbid_mask: np.ndarray,
    min_area_px: int,
    max_area_fraction: float,
) -> np.ndarray:
    h, w = edge_mask.shape
    contours, hierarchy = cv2.findContours(edge_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(edge_mask)
    if hierarchy is None:
        return filled
    roi_area = max(1.0, float((roi_mask > 0).sum()))
    max_area_px = max_area_fraction * roi_area
    for idx, cnt in enumerate(contours):
        area = float(cv2.contourArea(cnt))
        if area < float(min_area_px):
            continue
        if area > max_area_px:
            continue
        candidate = np.zeros_like(edge_mask)
        cv2.drawContours(candidate, [cnt], -1, 255, thickness=-1)
        if np.any((candidate > 0) & (roi_mask == 0)):
            continue
        if np.any((candidate > 0) & (forbid_mask > 0)):
            continue
        ys, xs = np.where(candidate > 0)
        if xs.size == 0:
            continue
        if xs.min() <= 1 or ys.min() <= 1 or xs.max() >= (w - 2) or ys.max() >= (h - 2):
            continue
        cv2.bitwise_or(filled, candidate, dst=filled)
    return filled


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

    circle = detect_primary_droplet(clahe, str(params["stage_label"]))
    droplet_roi, droplet_shell = build_circle_masks(gray.shape, circle)

    otsu_mask = threshold_otsu_within_mask(signal, droplet_roi)
    block = ensure_odd(params["adaptive_block_size_px"], 9)
    adaptive_mask = cv2.adaptiveThreshold(
        signal,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block,
        int(params["adaptive_c_offset"]),
    )
    adaptive_mask = cv2.bitwise_and(adaptive_mask, droplet_roi)

    target_max_fraction = 0.24 if params["stage_label"] == "cluster" else (0.42 if params["stage_label"] == "cystic" else 0.62)
    strong_mask = threshold_top_fraction_within_mask(signal, droplet_roi, target_max_fraction)

    if params["threshold_mode"] == "otsu":
        binary = otsu_mask
    elif params["threshold_mode"] == "adaptive_otsu":
        binary = cv2.bitwise_and(otsu_mask, adaptive_mask)
    else:
        union_mask = cv2.bitwise_or(otsu_mask, adaptive_mask)
        inter_mask = cv2.bitwise_and(otsu_mask, adaptive_mask)
        roi_fraction = float((union_mask > 0).sum()) / max(1.0, float((droplet_roi > 0).sum()))
        inter_fraction = float((inter_mask > 0).sum()) / max(1.0, float((droplet_roi > 0).sum()))
        if roi_fraction <= target_max_fraction:
            binary = union_mask
        elif inter_fraction <= target_max_fraction and np.any(inter_mask > 0):
            binary = inter_mask
        else:
            binary = strong_mask
        binary = cv2.medianBlur(binary, 3)

    binary_fraction = float((binary > 0).sum()) / max(1.0, float((droplet_roi > 0).sum()))
    if binary_fraction > target_max_fraction * 1.15:
        binary = strong_mask

    ok = int(params["open_kernel_px"])
    ck = int(params["close_kernel_px"])
    if ok > 0:
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((ok, ok), np.uint8))
    if ck > 0:
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((ck, ck), np.uint8))
    binary = cv2.bitwise_and(binary, droplet_roi)
    binary = cv2.bitwise_and(binary, cv2.bitwise_not(droplet_shell))

    edge_base = cv2.max(auto_canny(clahe), auto_canny(signal))
    edge_base = cv2.bitwise_and(edge_base, droplet_roi)
    edge_base[droplet_shell > 0] = 0
    edge_close_k = ensure_odd(max(3, int(params["close_kernel_px"]) * 2 + 1), 3)
    edge_closed = cv2.morphologyEx(edge_base, cv2.MORPH_CLOSE, np.ones((edge_close_k, edge_close_k), np.uint8))
    edge_closed = cv2.dilate(edge_closed, np.ones((3, 3), np.uint8), iterations=1)
    edge_closed = cv2.bitwise_and(edge_closed, droplet_roi)
    edge_closed[droplet_shell > 0] = 0

    filled_regions = fill_enclosed_regions(
        edge_closed,
        roi_mask=droplet_roi,
        forbid_mask=droplet_shell,
        min_area_px=max(30, int(params["min_area_px"]) // 3),
        max_area_fraction=float(params["max_area_fraction_0_to_1"]) * 0.6,
    )
    filled_regions = fill_binary_holes(filled_regions)
    filled_regions = cv2.bitwise_and(filled_regions, droplet_roi)
    filled_regions = cv2.bitwise_and(filled_regions, cv2.bitwise_not(droplet_shell))

    dark_support = cv2.bitwise_and(cv2.bitwise_or(otsu_mask, binary), droplet_roi)
    membrane = None
    compartment_support = None

    if params["stage_label"] == "cystic":
        membrane_percentile = 25.0 if int(params["day_rank"]) >= 5 else 28.0
        membrane_thr = float(np.percentile(gray[droplet_roi > 0], membrane_percentile))
        membrane = np.zeros_like(gray, dtype=np.uint8)
        membrane[(gray <= membrane_thr) & (droplet_roi > 0)] = 255
        membrane = cv2.morphologyEx(membrane, cv2.MORPH_CLOSE, np.ones((max(7, ck + 2), max(7, ck + 2)), np.uint8))
        membrane = cv2.dilate(membrane, np.ones((5, 5), np.uint8), iterations=1)
        membrane = cv2.bitwise_or(membrane, droplet_shell)
        compartment_support = extract_enclosed_compartments(
            membrane,
            droplet_roi,
            min_area_px=max(150, int(params["min_area_px"])),
            max_area_fraction=min(0.28, float(params["max_area_fraction_0_to_1"]) * 0.55),
        )
        support = cv2.bitwise_or(compartment_support, cv2.bitwise_and(strong_mask, cv2.bitwise_not(membrane)))
    else:
        support = cv2.bitwise_or(filled_regions, dark_support)
    if ck > 0:
        support = cv2.morphologyEx(support, cv2.MORPH_CLOSE, np.ones((ck, ck), np.uint8))
    if ok > 0:
        support = cv2.morphologyEx(support, cv2.MORPH_OPEN, np.ones((ok, ok), np.uint8))
    support_fraction = float((support > 0).sum()) / max(1.0, float((droplet_roi > 0).sum()))
    if support_fraction <= target_max_fraction * 0.95:
        support = fill_binary_holes(support)
    support = cv2.bitwise_and(support, droplet_roi)
    support = cv2.bitwise_and(support, cv2.bitwise_not(droplet_shell))

    sure_bg = cv2.dilate(support, np.ones((3, 3), np.uint8), iterations=int(params["dilate_iterations"]))
    dist = cv2.distanceTransform(support, cv2.DIST_L2, 5)
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
    Image.fromarray(droplet_roi.astype(np.uint8)).save(out_dir / "droplet_roi.png")
    Image.fromarray(droplet_shell.astype(np.uint8)).save(out_dir / "droplet_shell.png")
    Image.fromarray(edge_base.astype(np.uint8)).save(out_dir / "edge_map.png")
    Image.fromarray(edge_closed.astype(np.uint8)).save(out_dir / "edge_closed.png")
    Image.fromarray(filled_regions.astype(np.uint8)).save(out_dir / "filled_regions.png")
    if membrane is not None:
        Image.fromarray(membrane.astype(np.uint8)).save(out_dir / "membrane_mask.png")
    if compartment_support is not None:
        Image.fromarray(compartment_support.astype(np.uint8)).save(out_dir / "compartment_support.png")
    Image.fromarray(otsu_mask.astype(np.uint8)).save(out_dir / "otsu_mask.png")
    Image.fromarray(adaptive_mask.astype(np.uint8)).save(out_dir / "adaptive_mask.png")
    Image.fromarray(binary.astype(np.uint8)).save(out_dir / "binary_clean.png")
    Image.fromarray(support.astype(np.uint8)).save(out_dir / "support_mask.png")
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
