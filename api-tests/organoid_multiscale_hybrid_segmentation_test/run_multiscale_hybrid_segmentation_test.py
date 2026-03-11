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
    default_output = repo_root / "api-tests/organoid_multiscale_hybrid_segmentation_test/output"
    p = argparse.ArgumentParser(
        description="Run two organoid instance-segmentation strategies on one image: multiscale Cellpose and Cellpose plus large-mass hybrid."
    )
    p.add_argument("--input-tif", default=str(default_input))
    p.add_argument("--output-root", default=str(default_output))
    p.add_argument("--run-dir", default="")
    p.add_argument("--small-branch-manifest", default="")
    p.add_argument("--large-branch-manifest", default="")
    p.add_argument("--small-diameter", type=float, default=32.0)
    p.add_argument("--small-cellprob-threshold", type=float, default=-1.5)
    p.add_argument("--small-flow-threshold", type=float, default=0.4)
    p.add_argument("--small-min-area-px", type=int, default=60)
    p.add_argument("--small-max-area-fraction", type=float, default=0.18)
    p.add_argument("--small-resize-max-dim", type=int, default=1536)
    p.add_argument("--large-diameter", type=float, default=72.0)
    p.add_argument("--large-cellprob-threshold", type=float, default=-3.0)
    p.add_argument("--large-flow-threshold", type=float, default=0.5)
    p.add_argument("--large-min-area-px", type=int, default=1500)
    p.add_argument("--large-max-area-fraction", type=float, default=0.45)
    p.add_argument("--large-resize-max-dim", type=int, default=768)
    p.add_argument("--hybrid-large-min-area-px", type=int, default=15000)
    p.add_argument("--hybrid-central-radius-fraction", type=float, default=0.41)
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


def combine_large_then_small(large_labels: np.ndarray, small_labels: np.ndarray) -> np.ndarray:
    if large_labels.shape != small_labels.shape:
        raise ValueError("Label shapes must match for combination")
    combined = np.zeros_like(large_labels, dtype=np.uint16)
    next_id = 0

    for lid in [int(x) for x in np.unique(large_labels) if int(x) > 0]:
        next_id += 1
        combined[large_labels == lid] = next_id

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
        if overlap_ratio > 0.22 or centroid_occupied:
            continue
        next_id += 1
        combined[mask] = next_id
        occupied |= mask
    return combined


def circle_mask(shape: Tuple[int, int], radius_fraction: float) -> np.ndarray:
    h, w = shape
    cx = w / 2.0
    cy = h / 2.0
    r = min(h, w) * radius_fraction
    yy, xx = np.ogrid[:h, :w]
    return ((xx - cx) ** 2 + (yy - cy) ** 2) <= r ** 2


def detect_large_fused_regions(
    source_rgb: np.ndarray,
    *,
    central_radius_fraction: float,
    min_area_px: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (9, 9), 0)

    central = circle_mask(gray.shape, central_radius_fraction)
    thr = float(np.percentile(blur[central], 36))
    dark = np.zeros_like(gray, dtype=np.uint8)
    dark[(blur < thr) & central] = 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    num_labels, cc_labels, stats, centroids = cv2.connectedComponentsWithStats(dark, connectivity=8)
    labels = np.zeros_like(cc_labels, dtype=np.uint16)
    next_id = 0
    regions: List[Dict[str, Any]] = []

    for src_id in range(1, num_labels):
        area = int(stats[src_id, cv2.CC_STAT_AREA])
        if area < min_area_px:
            continue
        x = int(stats[src_id, cv2.CC_STAT_LEFT])
        y = int(stats[src_id, cv2.CC_STAT_TOP])
        w = int(stats[src_id, cv2.CC_STAT_WIDTH])
        h = int(stats[src_id, cv2.CC_STAT_HEIGHT])
        cx, cy = centroids[src_id]
        next_id += 1
        labels[cc_labels == src_id] = next_id
        regions.append(
            {
                "mask_id": next_id,
                "source_mask_id": int(src_id),
                "area_px": area,
                "center_x_px": round(float(cx), 2),
                "center_y_px": round(float(cy), 2),
                "bbox_x0": x,
                "bbox_y0": y,
                "bbox_x1": x + w,
                "bbox_y1": y + h,
            }
        )

    debug = {
        "threshold_percentile_value": round(thr, 3),
        "central_radius_fraction": central_radius_fraction,
        "min_area_px": min_area_px,
        "region_count": len(regions),
        "regions": regions,
    }
    return labels, debug


def render_large_detector_overlay(source_rgb: np.ndarray, large_labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    for lid in [int(x) for x in np.unique(large_labels) if int(x) > 0]:
        mask = (large_labels == lid).astype(np.uint8)
        color = label_to_color(lid)
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 3)
    return overlay


def write_method_outputs(run_dir: Path, prefix: str, source_rgb: np.ndarray, labels: np.ndarray) -> Dict[str, str]:
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


def render_comparison_panel(
    source_rgb: np.ndarray,
    multiscale_overlay: np.ndarray,
    hybrid_overlay: np.ndarray,
    large_overlay: np.ndarray,
) -> np.ndarray:
    panels = []
    for title, image in [
        ("Source", source_rgb),
        ("Multiscale Cellpose", multiscale_overlay),
        ("Hybrid Large+Cellpose", hybrid_overlay),
        ("Large-region detector", large_overlay),
    ]:
        panel = image.copy()
        cv2.putText(
            panel,
            title,
            (30, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            (255, 255, 255),
            3,
            cv2.LINE_AA,
        )
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

    if not args.small_branch_manifest or not args.large_branch_manifest:
        raise RuntimeError("Expected --small-branch-manifest and --large-branch-manifest generated by the shell wrapper.")
    small_manifest_path = Path(args.small_branch_manifest).resolve()
    large_manifest_path = Path(args.large_branch_manifest).resolve()
    small_run_dir = small_manifest_path.parent
    large_run_dir = large_manifest_path.parent
    small_manifest = json.loads(small_manifest_path.read_text(encoding="utf-8"))
    large_manifest = json.loads(large_manifest_path.read_text(encoding="utf-8"))

    small_labels = load_label_png(Path(small_manifest["filtered_label_png"]))
    large_cellpose_labels = load_label_png(Path(large_manifest["filtered_label_png"]))
    multiscale_labels = combine_large_then_small(large_cellpose_labels, small_labels)

    hybrid_large_labels, hybrid_debug = detect_large_fused_regions(
        source_rgb,
        central_radius_fraction=args.hybrid_central_radius_fraction,
        min_area_px=args.hybrid_large_min_area_px,
    )
    hybrid_labels = combine_large_then_small(hybrid_large_labels, small_labels)

    multiscale_outputs = write_method_outputs(run_dir, "multiscale_combined", source_rgb, multiscale_labels)
    hybrid_outputs = write_method_outputs(run_dir, "hybrid_combined", source_rgb, hybrid_labels)

    large_detector_overlay = render_large_detector_overlay(source_rgb, hybrid_large_labels)
    large_detector_overlay_png = run_dir / "hybrid_large_detector_overlay.png"
    large_detector_label_png = run_dir / "hybrid_large_detector_labels_16bit.png"
    large_detector_rgb_png = run_dir / "hybrid_large_detector_rgb.png"
    large_detector_json = run_dir / "hybrid_large_detector_debug.json"
    Image.fromarray(large_detector_overlay).save(large_detector_overlay_png)
    cv2.imwrite(str(large_detector_label_png), relabel_sequential(hybrid_large_labels).astype(np.uint16))
    Image.fromarray(render_instance_rgb(relabel_sequential(hybrid_large_labels))).save(large_detector_rgb_png)
    write_json(large_detector_json, hybrid_debug)

    comparison_panel = render_comparison_panel(
        source_rgb,
        np.array(Image.open(multiscale_outputs["overlay_png"]).convert("RGB")),
        np.array(Image.open(hybrid_outputs["overlay_png"]).convert("RGB")),
        large_detector_overlay,
    )
    comparison_panel_png = run_dir / "comparison_panel.png"
    Image.fromarray(comparison_panel).save(comparison_panel_png)

    summary = {
        "input_tif": str(input_tif),
        "source_png": str(source_png),
        "small_branch_run_dir": str(small_run_dir),
        "large_branch_run_dir": str(large_run_dir),
        "small_branch_manifest": str(small_run_dir / "run_manifest.json"),
        "large_branch_manifest": str(large_run_dir / "run_manifest.json"),
        "multiscale_outputs": multiscale_outputs,
        "hybrid_outputs": hybrid_outputs,
        "hybrid_large_detector_overlay": str(large_detector_overlay_png),
        "hybrid_large_detector_label_png": str(large_detector_label_png),
        "hybrid_large_detector_rgb_png": str(large_detector_rgb_png),
        "hybrid_large_detector_debug": str(large_detector_json),
        "comparison_panel_png": str(comparison_panel_png),
        "small_branch_mask_count": len([x for x in np.unique(small_labels) if int(x) > 0]),
        "large_branch_mask_count": len([x for x in np.unique(large_cellpose_labels) if int(x) > 0]),
        "hybrid_large_detector_count": len([x for x in np.unique(hybrid_large_labels) if int(x) > 0]),
        "multiscale_combined_count": len([x for x in np.unique(multiscale_labels) if int(x) > 0]),
        "hybrid_combined_count": len([x for x in np.unique(hybrid_labels) if int(x) > 0]),
    }
    write_json(run_dir / "run_manifest.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
