#!/usr/bin/env python3
"""Postfilter a generated organoid mask by connected-component area."""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Filter generated organoid mask by area fraction.")
    p.add_argument("--source", required=True, help="Source microscopy image")
    p.add_argument("--generated-mask", required=True, help="Generated RGB mask image")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--min-area-frac", type=float, required=True, help="Minimum component area fraction to keep")
    return p.parse_args()


def label_to_color(label: int) -> tuple[int, int, int]:
    hue = (label * 0.6180339887498949) % 1.0
    sat = 0.82
    val = 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def render_overlay(source_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        color = label_to_color(lid)
        mask = (labels == lid).astype(np.uint8)
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.24, overlay, 0.76, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)
    mask_path = Path(args.generated_mask)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rgb = np.array(Image.open(source_path).convert("RGB"))
    mask_rgb = np.array(Image.open(mask_path).convert("RGB"))
    if mask_rgb.shape[:2] != source_rgb.shape[:2]:
        mask_rgb = cv2.resize(mask_rgb, (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)

    fg = (mask_rgb.max(axis=2) > 24).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    h, w = fg.shape
    total = float(h * w)

    kept_labels = np.zeros_like(labels, dtype=np.uint16)
    kept_mask_rgb = np.zeros_like(mask_rgb)
    next_label = 1
    dropped: list[dict[str, float | int]] = []
    for lid in range(1, num):
        area = int(stats[lid, cv2.CC_STAT_AREA])
        frac = area / total
        comp = labels == lid
        if frac < args.min_area_frac:
            dropped.append({"label": int(lid), "area_px": area, "area_fraction": round(frac, 6)})
            continue
        kept_labels[comp] = next_label
        kept_mask_rgb[comp] = mask_rgb[comp]
        next_label += 1

    Image.fromarray(kept_mask_rgb).save(output_dir / "filtered_generated_instance_mask.png")
    Image.fromarray(kept_mask_rgb).save(output_dir / "filtered_generated_instance_mask_flat.png")
    Image.fromarray(render_overlay(source_rgb, kept_labels)).save(output_dir / "filtered_generated_overlay.png")
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "source_path": str(source_path),
                "generated_mask_path": str(mask_path),
                "min_area_fraction": args.min_area_frac,
                "kept_count": int(next_label - 1),
                "dropped_count": int(len(dropped)),
                "dropped_components": dropped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
