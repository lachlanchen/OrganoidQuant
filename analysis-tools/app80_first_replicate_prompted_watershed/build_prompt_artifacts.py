#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("source_tif")
    p.add_argument("out_dir")
    return p.parse_args()


def load_rgb(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if arr is None:
        with Image.open(path) as im:
            return np.array(im.convert("RGB").copy())
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def save_gray_png(arr: np.ndarray, path: Path) -> None:
    Image.fromarray(arr.astype(np.uint8)).save(path)


def main() -> int:
    args = parse_args()
    source_tif = Path(args.source_tif).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_png = out_dir / f"{source_tif.stem}.png"
    if not source_png.exists():
        with Image.open(source_tif) as im:
            im.save(source_png, format="PNG")

    rgb = load_rgb(source_png)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (7, 7), 0)
    bg = cv2.GaussianBlur(clahe, (41, 41), 0)
    residual = cv2.subtract(bg, blur)
    residual_norm = cv2.normalize(residual, None, 0, 255, cv2.NORM_MINMAX)
    edges = cv2.Canny(blur, 40, 120)
    edges_rgb = rgb.copy()
    edges_rgb[edges > 0] = (255, 64, 0)
    inv = 255 - clahe

    gray_png = out_dir / "gray.png"
    inv_png = out_dir / "gray_inv.png"
    residual_png = out_dir / "residual.png"
    edges_png = out_dir / "edges_overlay.png"
    save_gray_png(clahe, gray_png)
    save_gray_png(inv, inv_png)
    save_gray_png(residual_norm, residual_png)
    Image.fromarray(edges_rgb).save(edges_png)

    manifest = {
        "source_tif": str(source_tif),
        "source_png": str(source_png),
        "gray_png": str(gray_png),
        "gray_inv_png": str(inv_png),
        "residual_png": str(residual_png),
        "edges_overlay_png": str(edges_png),
        "image_width_px": int(rgb.shape[1]),
        "image_height_px": int(rgb.shape[0]),
    }
    (out_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
