#!/usr/bin/env python3
"""Replace one panel in a stitched mask with the same panel from another mask."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from run_app81_grsai_mask_generation import flatten_instance_mask, save_overlay


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replace one stitched mask panel from a donor mask")
    p.add_argument("--source-image", required=True, help="Original stitched source image")
    p.add_argument("--base-mask", required=True, help="Base stitched mask to preserve")
    p.add_argument("--donor-mask", required=True, help="Donor stitched mask containing the better panel")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--rows", type=int, default=3, help="Grid row count")
    p.add_argument("--cols", type=int, default=3, help="Grid column count")
    p.add_argument("--row", type=int, required=True, help="1-based panel row to replace")
    p.add_argument("--col", type=int, required=True, help="1-based panel col to replace")
    return p.parse_args()


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    source_path = Path(args.source_image)
    base_mask_path = Path(args.base_mask)
    donor_mask_path = Path(args.donor_mask)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source = np.array(Image.open(source_path).convert("RGB"))
    base = np.array(Image.open(base_mask_path).convert("RGB"))
    donor = np.array(Image.open(donor_mask_path).convert("RGB"))

    if base.shape[:2] != source.shape[:2]:
        raise RuntimeError("Base mask size does not match source image")
    if donor.shape[:2] != source.shape[:2]:
        raise RuntimeError("Donor mask size does not match source image")
    if not (1 <= args.row <= args.rows and 1 <= args.col <= args.cols):
        raise RuntimeError("Panel row/col out of range")

    h, w = source.shape[:2]
    tile_h = h // args.rows
    tile_w = w // args.cols

    row_idx = args.row - 1
    col_idx = args.col - 1
    y0 = row_idx * tile_h
    y1 = (row_idx + 1) * tile_h
    x0 = col_idx * tile_w
    x1 = (col_idx + 1) * tile_w

    merged = base.copy()
    merged[y0:y1, x0:x1] = donor[y0:y1, x0:x1]

    merged_mask_path = output_dir / "merged_instance_mask.png"
    merged_flat_mask_path = output_dir / "merged_instance_mask_flat.png"
    merged_overlay_path = output_dir / "merged_overlay.png"
    merged_flat_overlay_path = output_dir / "merged_overlay_flat.png"
    panel_crop_path = output_dir / f"merged_panel_r{args.row}c{args.col}.png"
    manifest_path = output_dir / "merge_manifest.json"

    Image.fromarray(merged).save(merged_mask_path)
    Image.fromarray(merged[y0:y1, x0:x1]).save(panel_crop_path)
    flatten_instance_mask(merged_mask_path, merged_flat_mask_path)
    save_overlay(source_path, merged_mask_path, merged_overlay_path)
    save_overlay(source_path, merged_flat_mask_path, merged_flat_overlay_path)

    write_json(
        manifest_path,
        {
            "source_image": str(source_path),
            "base_mask": str(base_mask_path),
            "donor_mask": str(donor_mask_path),
            "output_dir": str(output_dir),
            "rows": args.rows,
            "cols": args.cols,
            "replaced_panel": {"row": args.row, "col": args.col, "bbox": [x0, y0, x1, y1]},
            "merged_mask": str(merged_mask_path),
            "merged_flat_mask": str(merged_flat_mask_path),
            "merged_overlay": str(merged_overlay_path),
            "merged_flat_overlay": str(merged_flat_overlay_path),
        },
    )


if __name__ == "__main__":
    main()
