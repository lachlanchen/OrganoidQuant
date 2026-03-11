#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build general image-derived priors for polygon prompt segmentation.")
    p.add_argument("--source-png", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--cellpose-overlay", default="")
    return p.parse_args()


def normalize_u8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    return np.clip((arr - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def compute_maps(rgb: np.ndarray) -> Dict[str, np.ndarray]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (5, 5), 0)
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    med = float(np.median(blur))
    edges = cv2.Canny(blur, int(max(10, 0.66 * med)), int(min(255, 1.33 * med + 20)))
    bg = cv2.GaussianBlur(blur, (0, 0), 17)
    residual = np.clip(bg.astype(np.float32) - blur.astype(np.float32), 0, None)
    return {"gray": gray, "clahe": clahe, "blur": blur, "grad": grad, "edges": edges, "residual": residual}


def top_blob_candidates(blur: np.ndarray, max_n: int = 20) -> List[Dict[str, Any]]:
    valid = blur > 5
    thr = float(np.percentile(blur[valid], 30)) if np.any(valid) else 80.0
    dark = ((blur < thr) & valid).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    num, labels, stats, cents = cv2.connectedComponentsWithStats((dark > 0).astype(np.uint8), connectivity=8)
    out: List[Dict[str, Any]] = []
    for idx in range(1, num):
        x, y, w, h, area = map(int, stats[idx])
        if area < 25:
          continue
        out.append(
            {
                "center_x_px": round(float(cents[idx][0]), 2),
                "center_y_px": round(float(cents[idx][1]), 2),
                "area_px": area,
                "bbox_x0": x,
                "bbox_y0": y,
                "bbox_x1": x + w,
                "bbox_y1": y + h,
            }
        )
    out.sort(key=lambda item: item["area_px"], reverse=True)
    return out[:max_n]


def large_mass_candidates(blur: np.ndarray, residual: np.ndarray) -> tuple[np.ndarray, List[Dict[str, Any]]]:
    h, w = blur.shape
    cx = w / 2.0
    cy = h / 2.0
    r = min(h, w) * 0.42
    yy, xx = np.ogrid[:h, :w]
    central = ((xx - cx) ** 2 + (yy - cy) ** 2) <= r ** 2

    residual_thr = float(np.percentile(residual[central], 62))
    dark_thr = float(np.percentile(blur[central], 40))
    mask = (((residual >= residual_thr) | (blur <= dark_thr)) & central).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    num, labels, stats, cents = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    regions: List[Dict[str, Any]] = []
    vis = np.zeros_like(mask)
    keep_id = 0
    for idx in range(1, num):
        x, y, bw, bh, area = map(int, stats[idx])
        if area < 2500:
            continue
        keep_id += 1
        vis[labels == idx] = keep_id
        regions.append(
            {
                "mass_id": keep_id,
                "center_x_px": round(float(cents[idx][0]), 2),
                "center_y_px": round(float(cents[idx][1]), 2),
                "area_px": area,
                "bbox_x0": x,
                "bbox_y0": y,
                "bbox_x1": x + bw,
                "bbox_y1": y + bh,
            }
        )
    regions.sort(key=lambda item: item["area_px"], reverse=True)
    return vis, regions[:12]


def render_blob_overlay(rgb: np.ndarray, blobs: List[Dict[str, Any]]) -> np.ndarray:
    vis = rgb.copy()
    for i, blob in enumerate(blobs, start=1):
        x0, y0 = int(blob["bbox_x0"]), int(blob["bbox_y0"])
        x1, y1 = int(blob["bbox_x1"]), int(blob["bbox_y1"])
        cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 255, 0), 1)
        cv2.putText(vis, str(i), (x0, max(12, y0 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 80, 80), 1, cv2.LINE_AA)
    return vis


def render_mass_overlay(rgb: np.ndarray, mass_labels: np.ndarray) -> np.ndarray:
    vis = rgb.copy()
    for lid in [int(x) for x in np.unique(mass_labels) if int(x) > 0]:
        mask = (mass_labels == lid).astype(np.uint8)
        fill = vis.copy()
        fill[mask > 0] = (255, 120, 80)
        vis = cv2.addWeighted(fill, 0.20, vis, 0.80, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contours, -1, (255, 120, 80), 2)
    return vis


def main() -> None:
    args = parse_args()
    source_png = Path(args.source_png).resolve()
    out_json = Path(args.out_json).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rgb = load_rgb(source_png)
    maps = compute_maps(rgb)
    blobs = top_blob_candidates(maps["blur"])
    mass_labels, masses = large_mass_candidates(maps["blur"], maps["residual"])

    gradient_png = out_dir / "gradient.png"
    edge_overlay_png = out_dir / "edge_overlay.png"
    blob_overlay_png = out_dir / "blob_overlay.png"
    mass_overlay_png = out_dir / "mass_overlay.png"

    Image.fromarray(normalize_u8(maps["grad"])).save(gradient_png)
    edge_overlay = rgb.copy()
    edge_overlay[maps["edges"] > 0] = (0, 255, 0)
    Image.fromarray(edge_overlay).save(edge_overlay_png)
    Image.fromarray(render_blob_overlay(rgb, blobs)).save(blob_overlay_png)
    Image.fromarray(render_mass_overlay(rgb, mass_labels)).save(mass_overlay_png)

    payload = {
        "source_png": str(source_png),
        "image_width_px": int(rgb.shape[1]),
        "image_height_px": int(rgb.shape[0]),
        "blob_candidates": blobs,
        "large_mass_candidates": masses,
        "artifacts": {
            "gradient_png": str(gradient_png),
            "edge_overlay_png": str(edge_overlay_png),
            "blob_overlay_png": str(blob_overlay_png),
            "mass_overlay_png": str(mass_overlay_png),
            "cellpose_overlay_png": args.cellpose_overlay or ""
        }
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_json), "n_blobs": len(blobs), "n_masses": len(masses)}))


if __name__ == "__main__":
    main()
