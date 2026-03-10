#!/usr/bin/env python3
import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np


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


def circle_edge_score(grad: np.ndarray, cx: float, cy: float, r: float, min_visible: float = 0.65) -> float:
    if r < 5:
        return -1.0
    h, w = grad.shape
    vals = []
    total = 180
    inside = 0
    for k in range(total):
        theta = (2.0 * math.pi * k) / total
        x = int(round(cx + r * math.cos(theta)))
        y = int(round(cy + r * math.sin(theta)))
        if 0 <= x < w and 0 <= y < h:
            inside += 1
            vals.append(float(grad[y, x]))
    visible = inside / float(total)
    if visible < min_visible or not vals:
        return -1.0
    return float(np.mean(vals) * (0.5 + 0.5 * visible))


def optimize_circle(grad: np.ndarray, cx: float, cy: float, r: float) -> Tuple[float, float, float, float]:
    best_score = circle_edge_score(grad, cx, cy, r)
    best = (cx, cy, r)
    max_shift = max(4, min(32, int(r * 0.08)))
    max_dr = max(4, min(32, int(r * 0.10)))
    for dx in range(-max_shift, max_shift + 1, 2):
        for dy in range(-max_shift, max_shift + 1, 2):
            for dr in range(-max_dr, max_dr + 1, 2):
                rr = max(5.0, r + dr)
                score = circle_edge_score(grad, cx + dx, cy + dy, rr)
                if score > best_score:
                    best_score = score
                    best = (cx + dx, cy + dy, rr)
    return best[0], best[1], best[2], best_score


def visible_fraction(cx: float, cy: float, r: float, width: int, height: int) -> float:
    n = 20000
    rng = np.random.default_rng(0)
    ang = rng.random(n) * 2.0 * math.pi
    rad = np.sqrt(rng.random(n)) * r
    xs = cx + rad * np.cos(ang)
    ys = cy + rad * np.sin(ang)
    inside = ((xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)).mean()
    return float(inside)


def largest_central_blob(gray: np.ndarray) -> Dict[str, float]:
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    _, inv = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    inv = cv2.morphologyEx(inv, cv2.MORPH_OPEN, np.ones((5, 5), dtype=np.uint8))
    inv = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8))
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(inv, connectivity=8)
    image_cx = w / 2.0
    image_cy = h / 2.0
    diag = math.hypot(w, h)
    best = None
    best_score = -1.0
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 500:
            continue
        cx, cy = float(centroids[i][0]), float(centroids[i][1])
        dist = math.hypot(cx - image_cx, cy - image_cy)
        center_score = max(0.0, 1.0 - (dist / (0.55 * diag)))
        score = area * (0.35 + 0.65 * center_score)
        if score > best_score:
            best_score = score
            best = {
                "label_id": i,
                "area_px": area,
                "center_x_px": cx,
                "center_y_px": cy,
                "bbox_x0": int(stats[i, cv2.CC_STAT_LEFT]),
                "bbox_y0": int(stats[i, cv2.CC_STAT_TOP]),
                "bbox_w": int(stats[i, cv2.CC_STAT_WIDTH]),
                "bbox_h": int(stats[i, cv2.CC_STAT_HEIGHT]),
            }
    if best is None:
        return {
            "area_px": 0,
            "center_x_px": image_cx,
            "center_y_px": image_cy,
            "radius_equiv_px": min(h, w) * 0.22,
            "radius_enclosing_px": min(h, w) * 0.24,
        }

    comp = (labels == int(best["label_id"])).astype(np.uint8)
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(contours, key=cv2.contourArea)
    (_, _), r_enclosing = cv2.minEnclosingCircle(cnt)
    r_equiv = math.sqrt(float(best["area_px"]) / math.pi)
    best["radius_equiv_px"] = float(r_equiv)
    best["radius_enclosing_px"] = float(r_enclosing)
    return best


def collect_circle_candidates(gray: np.ndarray, prior_json: Dict, blob: Dict[str, float]) -> List[Tuple[float, float, float]]:
    h, w = gray.shape
    min_side = min(h, w)
    blur = cv2.GaussianBlur(gray, (9, 9), 1.2)
    out: List[Tuple[float, float, float]] = []

    for item in prior_json.get("circle_candidates", []):
        out.append((float(item["center_x_px"]), float(item["center_y_px"]), float(item["radius_px"])))

    for p2 in (18, 22, 26, 30):
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(100, int(min_side * 0.15)),
            param1=110,
            param2=p2,
            minRadius=max(180, int(min_side * 0.12)),
            maxRadius=int(min_side * 0.48),
        )
        if circles is None:
            continue
        for c in circles[0]:
            out.append((float(c[0]), float(c[1]), float(c[2])))

    bx = float(blob["center_x_px"])
    by = float(blob["center_y_px"])
    re = float(blob["radius_equiv_px"])
    ren = float(blob["radius_enclosing_px"])
    for scale in (1.12, 1.20, 1.28, 1.36):
        out.append((bx, by, re * scale))
    out.append((bx, by, max(ren, re * 1.12)))

    deduped: List[Tuple[float, float, float]] = []
    for cx, cy, r in out:
        keep = True
        for ex, ey, er in deduped:
            if math.hypot(cx - ex, cy - ey) < 0.18 * max(r, er) and abs(r - er) < 0.12 * max(r, er):
                keep = False
                break
        if keep:
            deduped.append((cx, cy, r))
    return deduped


def estimate_shape_class(blob_area: float, droplet_area: float, edge_score: float) -> str:
    fill = blob_area / max(droplet_area, 1.0)
    if fill < 0.25 and edge_score > 12:
        return "round"
    if fill < 0.38:
        return "slightly_irregular"
    if fill < 0.55:
        return "irregular"
    return "highly_distorted"


def main() -> None:
    p = argparse.ArgumentParser(description="Detect one single droplet in a 10x image using direct measurements.")
    p.add_argument("--source-tif", required=True)
    p.add_argument("--source-png", required=True)
    p.add_argument("--droplet-prior-json", required=True)
    p.add_argument("--organoid-prior-json", required=True)
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    source_tif = Path(args.source_tif).resolve()
    source_png = Path(args.source_png).resolve()
    droplet_prior_json = Path(args.droplet_prior_json).resolve()
    organoid_prior_json = Path(args.organoid_prior_json).resolve()
    out_json = Path(args.out_json).resolve()

    gray = cv2.imread(str(source_png), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise SystemExit(f"Failed to read image: {source_png}")
    h, w = gray.shape[:2]
    gy, gx = np.gradient(gray.astype(np.float32))
    grad = np.sqrt(gx * gx + gy * gy)

    prior = json.loads(droplet_prior_json.read_text(encoding="utf-8"))
    organoid_prior = json.loads(organoid_prior_json.read_text(encoding="utf-8"))
    meta = parse_path_metadata(source_tif)
    blob = largest_central_blob(gray)

    candidates = collect_circle_candidates(gray, prior, blob)
    image_cx = w / 2.0
    image_cy = h / 2.0
    best = None
    best_score = -1.0
    for cx, cy, r in candidates:
        nx, ny, nr, edge_score = optimize_circle(grad, cx, cy, r)
        if nr < 80:
            continue
        dist_blob = math.hypot(nx - float(blob["center_x_px"]), ny - float(blob["center_y_px"]))
        dist_image = math.hypot(nx - image_cx, ny - image_cy)
        center_blob_score = max(0.0, 1.0 - dist_blob / max(nr, 1.0))
        center_image_score = max(0.0, 1.0 - dist_image / (0.8 * max(nr, 1.0)))
        radius_floor_score = min(1.0, nr / max(float(blob["radius_equiv_px"]) * 1.1, 1.0))
        visible = visible_fraction(nx, ny, nr, w, h)
        total_score = (
            (0.50 * max(edge_score, 0.0))
            + (8.0 * center_blob_score)
            + (4.0 * center_image_score)
            + (3.0 * visible)
            + (2.0 * radius_floor_score)
        )
        if total_score > best_score:
            best_score = total_score
            best = (nx, ny, nr, edge_score, visible)

    if best is None:
        raise SystemExit("Failed to estimate a single droplet circle.")

    cx, cy, radius, edge_score, vis = best
    cellpose_n = int(organoid_prior.get("cellpose", {}).get("n_masks", 0) or 0)
    organoid_count_est = max(1, int(round(0.75 * cellpose_n)))
    droplet_area = math.pi * radius * radius
    blob_area = float(blob["area_px"])
    fusion_proxy = 5.0 * min(1.0, 0.55 * min(blob_area / max(droplet_area * 0.55, 1.0), 1.0) + 0.45 * min(float(blob["radius_equiv_px"]) / max(radius * 0.72, 1.0), 1.0))
    fusion_proxy = round(float(fusion_proxy), 4)
    shape_class = estimate_shape_class(blob_area, droplet_area, edge_score)

    if radius * 2 < min(h, w) * 0.32:
        size_note = "small droplet footprint for a 10x frame"
    elif radius * 2 < min(h, w) * 0.55:
        size_note = "medium droplet footprint for a 10x frame"
    else:
        size_note = "large droplet footprint for a 10x frame"

    if fusion_proxy < 1.5:
        fusion_note = "weak fusion signal from direct dark-mass geometry"
    elif fusion_proxy < 3.0:
        fusion_note = "moderate fusion signal from direct dark-mass geometry"
    else:
        fusion_note = "strong fusion signal from direct dark-mass geometry"

    payload = {
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
        "droplet_shape_class": shape_class,
        "droplet_boundary_confidence_0_to_1": round(float(min(1.0, max(0.2, edge_score / 20.0))), 4),
        "organoid_count_estimated_visual": int(organoid_count_est),
        "fusion_score_visual_0_to_5": fusion_proxy,
        "size_note": size_note,
        "fusion_note": fusion_note,
        "droplet_note": "single droplet estimated from central dark-mass geometry, Hough circle candidates, and local edge refinement",
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
