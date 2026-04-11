#!/usr/bin/env python3
"""Run direct Cellpose on the six replicate_01 stitched App81 collages.

This uses the original stitched PNGs as input, segments each 3x3 panel
independently, then stitches labels back into one combined output per collage.
"""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from cellpose import models


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run direct Cellpose on stitched App81 collages")
    p.add_argument(
        "--registry",
        default="analysis-output/app81_density_stitched_masks_v2_replicate1_nanobanana2_custom_prompts/batch_registry.json",
        help="Registry JSON containing stitched input collage paths",
    )
    p.add_argument("--output-root", required=True, help="New output root")
    p.add_argument("--gpu", action="store_true", help="Use GPU")
    p.add_argument("--rows", type=int, default=3, help="Grid rows in stitched collage")
    p.add_argument("--cols", type=int, default=3, help="Grid cols in stitched collage")
    p.add_argument(
        "--diameters",
        default="35,70,120",
        help="Comma-separated Cellpose diameters to try per panel",
    )
    p.add_argument(
        "--min-area-frac",
        type=float,
        default=0.00008,
        help="Drop components smaller than this fraction of panel area",
    )
    p.add_argument(
        "--max-area-frac",
        type=float,
        default=0.35,
        help="Drop components larger than this fraction of panel area",
    )
    return p.parse_args()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def label_to_color(label: int) -> tuple[int, int, int]:
    hue = (label * 0.6180339887498949) % 1.0
    sat = 0.82
    val = 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def render_instance_rgb(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        out[labels == lid] = label_to_color(lid)
    return out


def render_overlay(source_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        color = label_to_color(lid)
        mask = (labels == lid).astype(np.uint8)
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def load_registry(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError(f"Expected list in {path}")
    return data


def filter_labels(labels: np.ndarray, min_area: int, max_area: int) -> np.ndarray:
    out = np.zeros(labels.shape, dtype=np.uint16)
    next_label = 1
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        mask = labels == lid
        area = int(mask.sum())
        if area < min_area or area > max_area:
            continue
        out[mask] = next_label
        next_label += 1
    return out


def relabel_sequential(labels: np.ndarray, offset: int = 0) -> tuple[np.ndarray, int]:
    out = np.zeros(labels.shape, dtype=np.uint16)
    next_label = offset + 1
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        out[labels == lid] = next_label
        next_label += 1
    return out, next_label - 1


def candidate_score(labels: np.ndarray, panel_area: int) -> tuple[int, float]:
    count = int(len([x for x in np.unique(labels) if int(x) > 0]))
    fg_frac = float((labels > 0).sum()) / float(panel_area)
    return count, -abs(fg_frac - 0.06)


def panel_is_blank(panel_rgb: np.ndarray) -> bool:
    gray = cv2.cvtColor(panel_rgb, cv2.COLOR_RGB2GRAY)
    return bool(float(gray.mean()) < 2.0 and float(gray.std()) < 2.0)


def build_branches(panel_rgb: np.ndarray) -> dict[str, np.ndarray]:
    gray = cv2.cvtColor(panel_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return {"gray": gray, "clahe": clahe}


def select_panel_labels(
    model: models.CellposeModel,
    panel_rgb: np.ndarray,
    diameters: list[int],
    min_area_frac: float,
    max_area_frac: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    h, w = panel_rgb.shape[:2]
    panel_area = h * w
    min_area = max(64, int(round(panel_area * min_area_frac)))
    max_area = max(min_area + 1, int(round(panel_area * max_area_frac)))

    best_labels = np.zeros((h, w), dtype=np.uint16)
    best_meta: dict[str, Any] = {
        "selected_branch": None,
        "selected_diameter": None,
        "candidate_count": 0,
        "foreground_fraction": 0.0,
        "score": None,
        "candidates": [],
    }

    for branch_name, image in build_branches(panel_rgb).items():
        for diameter in diameters:
            masks, _flows, _styles = model.eval(
                image,
                diameter=diameter,
                channels=[0, 0],
                normalize=True,
                do_3D=False,
                flow_threshold=0.4,
                cellprob_threshold=0.0,
                min_size=min_area,
                max_size_fraction=max_area_frac,
                bsize=256,
                tile_overlap=0.1,
            )
            if masks is None:
                masks = np.zeros((h, w), dtype=np.int32)
            filtered = filter_labels(np.asarray(masks, dtype=np.int32), min_area=min_area, max_area=max_area)
            count, tie = candidate_score(filtered, panel_area)
            fg_frac = float((filtered > 0).sum()) / float(panel_area)
            meta = {
                "branch": branch_name,
                "diameter": diameter,
                "candidate_count": count,
                "foreground_fraction": fg_frac,
                "score": [count, tie],
            }
            best_meta["candidates"].append(meta)
            if best_meta["score"] is None or (count, tie) > tuple(best_meta["score"]):
                best_labels = filtered
                best_meta["selected_branch"] = branch_name
                best_meta["selected_diameter"] = diameter
                best_meta["candidate_count"] = count
                best_meta["foreground_fraction"] = fg_frac
                best_meta["score"] = [count, tie]
    return best_labels, best_meta


def segment_collage(
    image_path: Path,
    stage_dir: Path,
    model: models.CellposeModel,
    rows: int,
    cols: int,
    diameters: list[int],
    min_area_frac: float,
    max_area_frac: float,
) -> dict[str, Any]:
    source_rgb = np.array(Image.open(image_path).convert("RGB"))
    h, w = source_rgb.shape[:2]
    tile_h = h // rows
    tile_w = w // cols
    combined = np.zeros((h, w), dtype=np.uint16)
    next_offset = 0
    panel_summaries: list[dict[str, Any]] = []

    panels_dir = stage_dir / "panel_details"
    panels_dir.mkdir(parents=True, exist_ok=True)

    for row in range(rows):
        for col in range(cols):
            y0 = row * tile_h
            y1 = (row + 1) * tile_h
            x0 = col * tile_w
            x1 = (col + 1) * tile_w
            panel_rgb = source_rgb[y0:y1, x0:x1]
            panel_label = f"r{row+1}_c{col+1}"
            panel_dir = panels_dir / panel_label
            panel_dir.mkdir(parents=True, exist_ok=True)
            Image.fromarray(panel_rgb).save(panel_dir / "panel_source.png")

            blank = panel_is_blank(panel_rgb)
            summary: dict[str, Any] = {
                "panel": panel_label,
                "row": row + 1,
                "col": col + 1,
                "blank": blank,
            }

            if blank:
                summary["selected_branch"] = None
                summary["selected_diameter"] = None
                summary["candidate_count"] = 0
                panel_summaries.append(summary)
                continue

            labels, meta = select_panel_labels(model, panel_rgb, diameters, min_area_frac, max_area_frac)
            relabeled, next_offset = relabel_sequential(labels, next_offset)
            combined[y0:y1, x0:x1] = relabeled

            Image.fromarray(relabeled.astype(np.uint16)).save(panel_dir / "panel_labels_16bit.png")
            Image.fromarray(render_instance_rgb(relabeled)).save(panel_dir / "panel_instance_rgb.png")
            Image.fromarray(render_overlay(panel_rgb, relabeled)).save(panel_dir / "panel_overlay.png")

            summary.update(meta)
            panel_summaries.append(summary)

    labels_path = stage_dir / "cellpose_labels_16bit.png"
    instance_path = stage_dir / "cellpose_instance_rgb.png"
    overlay_path = stage_dir / "cellpose_overlay.png"
    source_copy_path = stage_dir / "source_stitched.png"
    summary_path = stage_dir / "cellpose_summary.json"

    Image.fromarray(source_rgb).save(source_copy_path)
    Image.fromarray(combined.astype(np.uint16)).save(labels_path)
    Image.fromarray(render_instance_rgb(combined)).save(instance_path)
    Image.fromarray(render_overlay(source_rgb, combined)).save(overlay_path)

    result = {
        "input_collage_path": str(image_path),
        "source_copy_path": str(source_copy_path),
        "labels_path": str(labels_path),
        "instance_rgb_path": str(instance_path),
        "overlay_path": str(overlay_path),
        "rows": rows,
        "cols": cols,
        "tile_width": tile_w,
        "tile_height": tile_h,
        "total_instance_count": int(len([x for x in np.unique(combined) if int(x) > 0])),
        "diameters": diameters,
        "panel_summaries": panel_summaries,
    }
    write_json(summary_path, result)
    result["summary_path"] = str(summary_path)
    return result


def main() -> None:
    args = parse_args()
    registry = load_registry(Path(args.registry))
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    diameters = [int(x.strip()) for x in args.diameters.split(",") if x.strip()]
    model = models.CellposeModel(gpu=bool(args.gpu))

    batch_results: list[dict[str, Any]] = []
    for item in registry:
        label = str(item["label"])
        image_path = Path(item["input_collage_path"])
        stage_dir = output_root / label
        stage_dir.mkdir(parents=True, exist_ok=True)
        result = segment_collage(
            image_path=image_path,
            stage_dir=stage_dir,
            model=model,
            rows=args.rows,
            cols=args.cols,
            diameters=diameters,
            min_area_frac=args.min_area_frac,
            max_area_frac=args.max_area_frac,
        )
        batch_results.append({
            "label": label,
            "status": "succeeded",
            "input_collage_path": str(image_path),
            "stage_dir": str(stage_dir),
            "summary_path": result["summary_path"],
            "total_instance_count": result["total_instance_count"],
        })

    write_json(output_root / "batch_registry.json", batch_results)
    write_json(
        output_root / "batch_summary.json",
        {
            "registry_path": str(Path(args.registry).resolve()),
            "output_root": str(output_root.resolve()),
            "rows": args.rows,
            "cols": args.cols,
            "diameters": diameters,
            "gpu": bool(args.gpu),
            "job_count": len(batch_results),
            "succeeded": len(batch_results),
        },
    )


if __name__ == "__main__":
    main()
