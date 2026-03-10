#!/usr/bin/env python3
"""Build image-derived priors (gradient/edges/circle/blob/cellpose) for prompt tools."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--source-png", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--mode", choices=["droplet", "organoid"], default="droplet")
    p.add_argument("--max-circle-candidates", type=int, default=24)
    p.add_argument("--max-blob-candidates", type=int, default=48)
    p.add_argument("--cellpose-mode", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--cellpose-model", default="cyto3")
    return p.parse_args()


def infer_magnification_token(source_png: Path) -> str:
    m = re.search(r"(?:^|/)(\d+x)\d*", str(source_png), flags=re.IGNORECASE)
    return m.group(1).lower() if m else "unknown"


def normalize_u8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    lo, hi = float(np.min(arr)), float(np.max(arr))
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.uint8)
    out = (arr - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def load_bgr_image(source_png: Path) -> np.ndarray:
    with Image.open(source_png) as im:
        rgb = np.array(im.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def compute_gradient_and_edges(gray: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    grad_u8 = normalize_u8(grad)

    med = float(np.median(gray))
    lower = int(max(10, 0.66 * med))
    upper = int(min(255, 1.33 * med + 20))
    edges = cv2.Canny(gray, lower, upper)
    return grad_u8, edges


def circle_edge_support(
    edge: np.ndarray, cx: float, cy: float, radius: float, bins: int = 72
) -> Tuple[float, float]:
    h, w = edge.shape[:2]
    hits = 0
    bin_hits = 0
    total = bins
    for i in range(total):
        theta = (2.0 * math.pi * i) / total
        x = int(round(cx + radius * math.cos(theta)))
        y = int(round(cy + radius * math.sin(theta)))
        local = 0
        for dy in (-1, 0, 1):
            yy = y + dy
            if yy < 0 or yy >= h:
                continue
            for dx in (-1, 0, 1):
                xx = x + dx
                if xx < 0 or xx >= w:
                    continue
                if edge[yy, xx] > 0:
                    local = 1
                    break
            if local:
                break
        hits += local
        bin_hits += local
    edge_support = hits / float(total)

    # Completeness proxy: fraction of arc bins with boundary evidence.
    completeness = bin_hits / float(total)
    return edge_support, completeness


def dedupe_circles(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in sorted(cands, key=lambda x: x["edge_support_0_to_1"], reverse=True):
        keep = True
        for e in out:
            d = math.hypot(c["center_x_px"] - e["center_x_px"], c["center_y_px"] - e["center_y_px"])
            r_mean = 0.5 * (c["radius_px"] + e["radius_px"])
            if d < 0.30 * r_mean and abs(c["radius_px"] - e["radius_px"]) < 0.18 * r_mean:
                keep = False
                break
        if keep:
            out.append(c)
    return out


def circle_candidates(
    gray: np.ndarray, edge: np.ndarray, magnification: str, max_n: int
) -> List[Dict[str, Any]]:
    h, w = gray.shape[:2]
    min_side = min(h, w)
    blur = cv2.GaussianBlur(gray, (9, 9), 1.2)

    if magnification == "10x":
        min_r = max(35, int(min_side * 0.05))
        max_r = int(min_side * 0.20)
    else:
        min_r = max(50, int(min_side * 0.08))
        max_r = int(min_side * 0.30)

    all_cands: List[Dict[str, Any]] = []
    for p2 in (22, 26, 30, 34):
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(80, int(min_side * 0.16)),
            param1=120,
            param2=p2,
            minRadius=min_r,
            maxRadius=max_r,
        )
        if circles is None:
            continue
        for c in circles[0]:
            cx, cy, r = float(c[0]), float(c[1]), float(c[2])
            support, completeness = circle_edge_support(edge, cx, cy, r)
            all_cands.append(
                {
                    "center_x_px": round(cx, 2),
                    "center_y_px": round(cy, 2),
                    "radius_px": round(r, 2),
                    "edge_support_0_to_1": round(float(support), 4),
                    "completeness_0_to_1": round(float(completeness), 4),
                }
            )

    all_cands = dedupe_circles(all_cands)
    all_cands.sort(key=lambda x: (x["edge_support_0_to_1"], x["completeness_0_to_1"]), reverse=True)
    return all_cands[:max_n]


def blob_candidates(gray: np.ndarray, max_n: int) -> List[Dict[str, Any]]:
    mask_valid = gray > 5
    p = float(np.percentile(gray[mask_valid], 30)) if np.any(mask_valid) else 80.0
    dark = ((gray < p) & mask_valid).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))

    num, labels, stats, cent = cv2.connectedComponentsWithStats((dark > 0).astype(np.uint8), connectivity=8)
    cands: List[Dict[str, Any]] = []
    for i in range(1, num):
        x, y, bw, bh, area = map(int, stats[i])
        if area < 30:
            continue
        cx, cy = float(cent[i][0]), float(cent[i][1])
        r = math.sqrt(area / math.pi)
        patch = gray[y : y + bh, x : x + bw]
        mean_int = float(np.mean(patch)) if patch.size else 0.0
        cands.append(
            {
                "center_x_px": round(cx, 2),
                "center_y_px": round(cy, 2),
                "area_px": area,
                "radius_equiv_px": round(r, 2),
                "bbox_x0": x,
                "bbox_y0": y,
                "bbox_x1": x + bw,
                "bbox_y1": y + bh,
                "mean_intensity": round(mean_int, 2),
            }
        )
    cands.sort(key=lambda x: x["area_px"], reverse=True)
    return cands[:max_n]


def try_cellpose(
    bgr: np.ndarray, out_dir: Path, mode: str, cellpose_mode: str, model_name: str
) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "available": False,
        "attempted": False,
        "success": False,
        "model_type": model_name,
        "n_masks": 0,
        "mask_png": None,
        "mask_stats_json": None,
        "note": "",
    }
    should_run = cellpose_mode == "on" or (cellpose_mode == "auto" and mode == "organoid")
    if not should_run:
        info["note"] = "cellpose skipped by mode policy"
        return info

    try:
        from cellpose import models  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        info["note"] = f"cellpose import failed: {e}"
        return info

    info["available"] = True
    info["attempted"] = True
    try:
        model = models.Cellpose(model_type=model_name, gpu=False)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        masks, _, _, _ = model.eval(rgb, channels=[0, 0], diameter=None)
        labels = [int(x) for x in np.unique(masks) if int(x) > 0]
        info["n_masks"] = len(labels)
        mask_stats: List[Dict[str, Any]] = []
        overlay = bgr.copy()
        for lid in labels:
            m = (masks == lid).astype(np.uint8)
            cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(overlay, cnts, -1, (0, 255, 255), 1)
            ys, xs = np.where(m > 0)
            if xs.size == 0:
                continue
            mask_stats.append(
                {
                    "mask_id": lid,
                    "area_px": int(xs.size),
                    "center_x_px": round(float(np.mean(xs)), 2),
                    "center_y_px": round(float(np.mean(ys)), 2),
                    "bbox_x0": int(np.min(xs)),
                    "bbox_y0": int(np.min(ys)),
                    "bbox_x1": int(np.max(xs) + 1),
                    "bbox_y1": int(np.max(ys) + 1),
                }
            )
        mask_png = out_dir / "cellpose_overlay.png"
        mask_stats_json = out_dir / "cellpose_mask_stats.json"
        cv2.imwrite(str(mask_png), overlay)
        mask_stats_json.write_text(json.dumps(mask_stats, ensure_ascii=False, indent=2), encoding="utf-8")
        info["mask_png"] = str(mask_png)
        info["mask_stats_json"] = str(mask_stats_json)
        info["success"] = True
        info["note"] = "cellpose finished"
    except Exception as e:  # pragma: no cover - runtime optional
        info["note"] = f"cellpose execution failed: {e}"

    return info


def render_overlays(
    bgr: np.ndarray,
    grad: np.ndarray,
    edges: np.ndarray,
    circles: List[Dict[str, Any]],
    blobs: List[Dict[str, Any]],
    out_dir: Path,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gradient_png = out_dir / "gradient_magnitude.png"
    edges_png = out_dir / "edges_canny.png"
    edge_overlay_png = out_dir / "edges_overlay.png"
    circles_png = out_dir / "circle_candidates_overlay.png"
    blobs_png = out_dir / "blob_candidates_overlay.png"

    cv2.imwrite(str(gradient_png), grad)
    cv2.imwrite(str(edges_png), edges)

    edge_overlay = bgr.copy()
    edge_overlay[edges > 0] = (0, 255, 0)
    cv2.imwrite(str(edge_overlay_png), edge_overlay)

    circles_vis = bgr.copy()
    for i, c in enumerate(circles, start=1):
        cx = int(round(c["center_x_px"]))
        cy = int(round(c["center_y_px"]))
        r = int(round(c["radius_px"]))
        cv2.circle(circles_vis, (cx, cy), r, (0, 255, 255), 2)
        cv2.putText(
            circles_vis,
            str(i),
            (cx + 4, cy - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(circles_png), circles_vis)

    blobs_vis = bgr.copy()
    for i, b in enumerate(blobs, start=1):
        x0, y0 = int(b["bbox_x0"]), int(b["bbox_y0"])
        x1, y1 = int(b["bbox_x1"]), int(b["bbox_y1"])
        cv2.rectangle(blobs_vis, (x0, y0), (x1, y1), (255, 255, 0), 1)
        cv2.putText(
            blobs_vis,
            str(i),
            (x0, max(12, y0 - 2)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(blobs_png), blobs_vis)

    return {
        "gradient_png": str(gradient_png),
        "edges_png": str(edges_png),
        "edge_overlay_png": str(edge_overlay_png),
        "circle_overlay_png": str(circles_png),
        "blob_overlay_png": str(blobs_png),
    }


def main() -> None:
    args = parse_args()
    source_png = Path(args.source_png).resolve()
    out_json = Path(args.out_json).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else out_json.parent / "vision-priors"
    out_dir.mkdir(parents=True, exist_ok=True)

    bgr = load_bgr_image(source_png)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    magnification = infer_magnification_token(source_png)

    grad, edges = compute_gradient_and_edges(gray)
    circles = circle_candidates(gray, edges, magnification, args.max_circle_candidates)
    blobs = blob_candidates(gray, args.max_blob_candidates)
    artifacts = render_overlays(bgr, grad, edges, circles, blobs, out_dir)

    cellpose_info = try_cellpose(
        bgr=bgr,
        out_dir=out_dir,
        mode=args.mode,
        cellpose_mode=args.cellpose_mode,
        model_name=args.cellpose_model,
    )
    if cellpose_info.get("mask_png"):
        artifacts["cellpose_overlay_png"] = cellpose_info["mask_png"]

    valid = gray > 5
    stats = {
        "edge_density_0_to_1": round(float(np.mean(edges[valid] > 0)) if np.any(valid) else 0.0, 6),
        "gradient_mean": round(float(np.mean(grad[valid])) if np.any(valid) else 0.0, 4),
        "gradient_p90": round(float(np.percentile(grad[valid], 90)) if np.any(valid) else 0.0, 4),
    }

    payload: Dict[str, Any] = {
        "source_png": str(source_png),
        "mode": args.mode,
        "magnification_token": magnification,
        "image_width_px": int(w),
        "image_height_px": int(h),
        "stats": stats,
        "artifacts": artifacts,
        "circle_candidates": circles,
        "blob_candidates": blobs,
        "cellpose": cellpose_info,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_json), "n_circles": len(circles), "n_blobs": len(blobs)}))


if __name__ == "__main__":
    main()
