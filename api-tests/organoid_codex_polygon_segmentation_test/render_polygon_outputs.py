#!/usr/bin/env python3
from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render polygon segmentation mask and overlay from codex JSON.")
    p.add_argument("--source-png", required=True)
    p.add_argument("--polygon-json", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--prefix", default="")
    return p.parse_args()


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def label_to_color(label: int) -> Tuple[int, int, int]:
    hue = (label * 0.61803398875) % 1.0
    sat = 0.65
    val = 0.95
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def clamp_polygon(poly: List[List[float]], w: int, h: int) -> np.ndarray:
    pts = []
    for pt in poly:
        if len(pt) < 2:
            continue
        x = int(round(float(pt[0])))
        y = int(round(float(pt[1])))
        x = min(max(x, 0), w - 1)
        y = min(max(y, 0), h - 1)
        pts.append([x, y])
    if len(pts) < 3:
        return np.zeros((0, 2), dtype=np.int32)
    return np.array(pts, dtype=np.int32)


def main() -> None:
    args = parse_args()
    source_png = Path(args.source_png).resolve()
    polygon_json = Path(args.polygon_json).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix

    rgb = load_rgb(source_png)
    h, w = rgb.shape[:2]
    obj = json.loads(polygon_json.read_text(encoding="utf-8"))

    label_mask = np.zeros((h, w), dtype=np.uint16)
    overlay = rgb.copy()
    instance_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    stats: List[Dict[str, Any]] = []

    next_id = 0
    for organoid in obj.get("organoids", []):
        pts = clamp_polygon(organoid.get("polygon_xy", []), w, h)
        if pts.shape[0] < 3:
            continue
        next_id += 1
        temp = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(temp, [pts], 255)
        label_mask[temp > 0] = next_id
        color = label_to_color(next_id)
        instance_rgb[temp > 0] = color
        fill = overlay.copy()
        fill[temp > 0] = color
        overlay = cv2.addWeighted(fill, 0.18, overlay, 0.82, 0)
        cv2.polylines(overlay, [pts], isClosed=True, color=color, thickness=2)
        ys, xs = np.where(temp > 0)
        stats.append(
            {
                "mask_id": next_id,
                "organoid_id": organoid.get("organoid_id"),
                "morphology": organoid.get("morphology"),
                "confidence_0_to_1": organoid.get("confidence_0_to_1"),
                "area_px": int(xs.size),
                "center_x_px": round(float(np.mean(xs)), 2) if xs.size else None,
                "center_y_px": round(float(np.mean(ys)), 2) if ys.size else None,
                "note": organoid.get("note", "")
            }
        )

    cv2.imwrite(str(out_dir / f"{prefix}polygon_labels_16bit.png"), label_mask)
    Image.fromarray(instance_rgb).save(out_dir / f"{prefix}polygon_instance_rgb.png")
    Image.fromarray(overlay).save(out_dir / f"{prefix}polygon_overlay.png")
    (out_dir / f"{prefix}polygon_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
