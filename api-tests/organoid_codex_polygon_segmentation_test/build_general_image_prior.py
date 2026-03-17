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
    p.add_argument("--cellpose-small-manifest", default="")
    p.add_argument("--cellpose-large-manifest", default="")
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


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cellpose_branch(manifest_path: str) -> Dict[str, Any]:
    if not manifest_path:
        return {}
    path = Path(manifest_path).resolve()
    if not path.is_file():
        return {}

    manifest = load_json(path)
    stats_path = Path(manifest.get("mask_stats_json", "")).resolve() if manifest.get("mask_stats_json") else None
    labels_path = Path(manifest.get("filtered_label_png", "")).resolve() if manifest.get("filtered_label_png") else None

    stats: List[Dict[str, Any]] = []
    if stats_path and stats_path.is_file():
        stats = load_json(stats_path)
        stats.sort(key=lambda item: int(item.get("area_px", 0)), reverse=True)

    labels = None
    if labels_path and labels_path.is_file():
        labels = cv2.imread(str(labels_path), cv2.IMREAD_UNCHANGED)
        if labels is not None and labels.ndim == 3:
            labels = labels[:, :, 0]

    return {
        "manifest_path": str(path),
        "overlay_png": manifest.get("overlay_png", ""),
        "filtered_label_png": manifest.get("filtered_label_png", ""),
        "filtered_mask_count": int(manifest.get("filtered_mask_count", 0)),
        "stats_top": stats[:16],
        "labels": labels,
    }


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


def render_branch_contours(vis: np.ndarray, labels: np.ndarray | None, color: tuple[int, int, int], thickness: int) -> None:
    if labels is None:
        return
    ids = [int(x) for x in np.unique(labels) if int(x) > 0]
    for lid in ids:
        mask = (labels == lid).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cv2.drawContours(vis, contours, -1, color, thickness)


def render_combined_prior_overlay(
    rgb: np.ndarray,
    edges: np.ndarray,
    blobs: List[Dict[str, Any]],
    mass_labels: np.ndarray,
    small_branch: Dict[str, Any],
    large_branch: Dict[str, Any],
) -> np.ndarray:
    vis = rgb.copy()

    # Sparse edges help the refine pass tighten boundaries without overwhelming the image.
    vis[edges > 0] = (40, 220, 90)

    for blob in blobs[:12]:
        x0, y0 = int(blob["bbox_x0"]), int(blob["bbox_y0"])
        x1, y1 = int(blob["bbox_x1"]), int(blob["bbox_y1"])
        cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 240, 90), 1)

    for lid in [int(x) for x in np.unique(mass_labels) if int(x) > 0]:
        mask = (mass_labels == lid).astype(np.uint8)
        fill = vis.copy()
        fill[mask > 0] = (255, 125, 80)
        vis = cv2.addWeighted(fill, 0.12, vis, 0.88, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cv2.drawContours(vis, contours, -1, (255, 125, 80), 2)

    render_branch_contours(vis, small_branch.get("labels"), (70, 210, 255), 1)
    render_branch_contours(vis, large_branch.get("labels"), (255, 80, 220), 2)
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
    small_branch = load_cellpose_branch(args.cellpose_small_manifest)
    large_branch = load_cellpose_branch(args.cellpose_large_manifest)

    gradient_png = out_dir / "gradient.png"
    edge_overlay_png = out_dir / "edge_overlay.png"
    blob_overlay_png = out_dir / "blob_overlay.png"
    mass_overlay_png = out_dir / "mass_overlay.png"
    combined_prior_overlay_png = out_dir / "combined_prior_overlay.png"

    Image.fromarray(normalize_u8(maps["grad"])).save(str(gradient_png))
    edge_overlay = rgb.copy()
    edge_overlay[maps["edges"] > 0] = (0, 255, 0)
    Image.fromarray(edge_overlay).save(str(edge_overlay_png))
    Image.fromarray(render_blob_overlay(rgb, blobs)).save(str(blob_overlay_png))
    Image.fromarray(render_mass_overlay(rgb, mass_labels)).save(str(mass_overlay_png))
    Image.fromarray(
        render_combined_prior_overlay(
            rgb,
            maps["edges"],
            blobs,
            mass_labels,
            small_branch,
            large_branch,
        )
    ).save(str(combined_prior_overlay_png))

    payload = {
        "source_png": str(source_png),
        "image_width_px": int(rgb.shape[1]),
        "image_height_px": int(rgb.shape[0]),
        "blob_candidates": blobs,
        "large_mass_candidates": masses,
        "cellpose_small": {
            "filtered_mask_count": int(small_branch.get("filtered_mask_count", 0)),
            "stats_top": small_branch.get("stats_top", []),
        },
        "cellpose_large": {
            "filtered_mask_count": int(large_branch.get("filtered_mask_count", 0)),
            "stats_top": large_branch.get("stats_top", []),
        },
        "artifacts": {
            "gradient_png": str(gradient_png),
            "edge_overlay_png": str(edge_overlay_png),
            "blob_overlay_png": str(blob_overlay_png),
            "mass_overlay_png": str(mass_overlay_png),
            "combined_prior_overlay_png": str(combined_prior_overlay_png),
            "cellpose_small_overlay_png": small_branch.get("overlay_png", ""),
            "cellpose_large_overlay_png": large_branch.get("overlay_png", ""),
        }
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_json), "n_blobs": len(blobs), "n_masses": len(masses)}))


if __name__ == "__main__":
    main()
