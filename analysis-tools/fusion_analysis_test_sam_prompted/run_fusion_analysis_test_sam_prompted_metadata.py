#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

os.environ.setdefault("TORCH_DISABLE_DYNAMO", "1")

CHECKPOINT_URLS = {
    "vit_h": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth",
    "vit_l": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth",
    "vit_b": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_set = repo_root / "analysis-output/fusion-analysis-test/set_001"
    default_cache = Path.home() / ".cache/segment-anything"
    p = argparse.ArgumentParser(description="Run prompted SAM segmentation on a blinded fusion-analysis set.")
    p.add_argument("set_dir", nargs="?", default=str(default_set))
    p.add_argument("--output-dir", default="")
    p.add_argument("--model-type", default="vit_h", choices=["vit_h", "vit_l", "vit_b"])
    p.add_argument("--device", default="cuda")
    p.add_argument("--checkpoint", default="")
    p.add_argument("--checkpoint-dir", default=str(default_cache))
    p.add_argument("--resize-max-dim", type=int, default=1536)
    p.add_argument("--min-area-px", type=int, default=180)
    p.add_argument("--large-box-min-area-fraction", type=float, default=0.008)
    p.add_argument("--box-expand-px", type=int, default=24)
    p.add_argument("--iou-merge-threshold", type=float, default=0.65)
    p.add_argument("--fresh-area-fraction", type=float, default=0.25)
    return p.parse_args()


def resolve_output_dir(set_dir: Path, explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (set_dir.parent / f"{set_dir.name}_sam_prompted_metadata_gpu").resolve()


def resolve_checkpoint(model_type: str, explicit: str, checkpoint_dir: Path) -> Path:
    if explicit:
        return Path(explicit).resolve()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    name = Path(CHECKPOINT_URLS[model_type]).name
    path = checkpoint_dir / name
    if path.exists() and path.stat().st_size > 100_000_000:
        return path
    print(json.dumps({"status": "download_checkpoint", "model_type": model_type, "checkpoint": str(path)}, ensure_ascii=False))
    urllib.request.urlretrieve(CHECKPOINT_URLS[model_type], path)
    return path


def load_rgb(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if arr is None:
        with Image.open(path) as im:
            return np.array(im.convert("RGB").copy())
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def resize_if_needed(rgb: np.ndarray, max_dim: int) -> Tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    cur_max = max(h, w)
    if max_dim <= 0 or cur_max <= max_dim:
        return rgb, 1.0
    scale = max_dim / float(cur_max)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    resized = cv2.resize(rgb, new_size, interpolation=cv2.INTER_AREA)
    return resized, scale


def to_gray_u8(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def box_iou(a: np.ndarray, b: np.ndarray) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1.0, float((ax1 - ax0) * (ay1 - ay0)))
    area_b = max(1.0, float((bx1 - bx0) * (by1 - by0)))
    return inter / (area_a + area_b - inter)


def expand_box(box: np.ndarray, w: int, h: int, pad: int) -> np.ndarray:
    x0, y0, x1, y1 = box.astype(int)
    return np.array([
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(w - 1, x1 + pad),
        min(h - 1, y1 + pad),
    ], dtype=np.float32)


def merge_boxes(boxes: List[np.ndarray], iou_threshold: float) -> List[np.ndarray]:
    kept: List[np.ndarray] = []
    for box in sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if any(box_iou(box, prev) >= iou_threshold for prev in kept):
            continue
        kept.append(box)
    return kept


def load_uid_metadata(set_dir: Path) -> Dict[str, Dict[str, Any]]:
    mapping_csv = set_dir / "internal_mapping/uid_to_source.csv"
    if not mapping_csv.exists():
        return {}
    rows: List[Dict[str, str]] = []
    with mapping_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    ordered_folders = sorted({row["source_folder"] for row in rows})
    folder_to_rank = {folder: idx + 1 for idx, folder in enumerate(ordered_folders)}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        rank = folder_to_rank[row["source_folder"]]
        if rank == 1:
            stage = "cluster"
        elif rank == len(ordered_folders):
            stage = "differentiated_colon_like"
        else:
            stage = "cystic"
        out[row["uid"]] = {
            "source_path": row["source_path"],
            "source_folder": row["source_folder"],
            "day_rank": rank,
            "stage": stage,
        }
    return out


def merge_candidates(candidates: List[Dict[str, Any]], iou_threshold: float) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for cand in sorted(candidates, key=lambda c: c["area"], reverse=True):
        if any(box_iou(cand["box"], prev["box"]) >= iou_threshold for prev in kept):
            continue
        kept.append(cand)
    return kept


def derive_dark_component_candidates(rgb: np.ndarray, min_area_fraction: float, pad: int, percentile: float) -> List[Dict[str, Any]]:
    gray = to_gray_u8(rgb)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    bg = cv2.GaussianBlur(gray, (41, 41), 0)
    residual = cv2.subtract(bg, blur)
    thresh = np.percentile(residual, percentile)
    mask = residual >= thresh
    mask = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    h, w = gray.shape
    min_area = int(min_area_fraction * h * w)
    candidates: List[Dict[str, Any]] = []
    for idx in range(1, num):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[idx, cv2.CC_STAT_LEFT])
        y = int(stats[idx, cv2.CC_STAT_TOP])
        bw = int(stats[idx, cv2.CC_STAT_WIDTH])
        bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
        box = np.array([x, y, x + bw, y + bh], dtype=np.float32)
        cx, cy = centroids[idx]
        candidates.append({
            "box": expand_box(box, w, h, pad),
            "point": np.array([cx, cy], dtype=np.float32),
            "area": area,
            "source": "dark_component",
        })
    return candidates


def derive_adaptive_candidates(rgb: np.ndarray, min_area_fraction: float, pad: int) -> List[Dict[str, Any]]:
    gray = to_gray_u8(rgb)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    inv = 255 - clahe
    mask = cv2.adaptiveThreshold(inv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 61, -6)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    h, w = gray.shape
    min_area = int(min_area_fraction * h * w)
    candidates: List[Dict[str, Any]] = []
    for idx in range(1, num):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[idx, cv2.CC_STAT_LEFT])
        y = int(stats[idx, cv2.CC_STAT_TOP])
        bw = int(stats[idx, cv2.CC_STAT_WIDTH])
        bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
        if bw < 12 or bh < 12:
            continue
        box = np.array([x, y, x + bw, y + bh], dtype=np.float32)
        cx, cy = centroids[idx]
        candidates.append({
            "box": expand_box(box, w, h, pad),
            "point": np.array([cx, cy], dtype=np.float32),
            "area": area,
            "source": "adaptive",
        })
    return candidates


def derive_stage_candidates(rgb: np.ndarray, stage: str, day_rank: int, iou_threshold: float) -> List[Dict[str, Any]]:
    if stage == "cluster":
        candidates = (
            derive_dark_component_candidates(rgb, min_area_fraction=0.0015, pad=16, percentile=80) +
            derive_adaptive_candidates(rgb, min_area_fraction=0.0007, pad=14)
        )
    elif stage == "differentiated_colon_like":
        candidates = (
            derive_dark_component_candidates(rgb, min_area_fraction=0.004, pad=34, percentile=86) +
            derive_adaptive_candidates(rgb, min_area_fraction=0.002, pad=28)
        )
    else:
        candidates = (
            derive_dark_component_candidates(rgb, min_area_fraction=0.001, pad=22, percentile=76) +
            derive_adaptive_candidates(rgb, min_area_fraction=0.0006, pad=18)
        )
    return merge_candidates(candidates, iou_threshold)


def filter_instance_map(seg: np.ndarray, min_area_px: int) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    labels = [int(x) for x in np.unique(seg) if int(x) > 0]
    out = np.zeros_like(seg, dtype=np.int32)
    stats: List[Dict[str, Any]] = []
    new_id = 0
    for lid in labels:
        mask = seg == lid
        area = int(mask.sum())
        if area < min_area_px:
            continue
        ys, xs = np.where(mask)
        if xs.size == 0:
            continue
        new_id += 1
        out[mask] = new_id
        stats.append({
            "mask_id": new_id,
            "area_px": area,
            "center_x_px": round(float(xs.mean()), 2),
            "center_y_px": round(float(ys.mean()), 2),
            "bbox_x0": int(xs.min()),
            "bbox_y0": int(ys.min()),
            "bbox_x1": int(xs.max() + 1),
            "bbox_y1": int(ys.max() + 1),
        })
    return out, stats


def build_instance_map_from_candidates(
    predictor: Any,
    prompt_candidates: List[Dict[str, Any]],
    output_shape: Tuple[int, int],
    min_area_px: int,
    fresh_area_fraction: float,
) -> np.ndarray:
    h, w = output_shape
    label_map = np.zeros((h, w), dtype=np.int32)
    taken = np.zeros((h, w), dtype=bool)
    next_id = 0

    scored_masks: List[Tuple[float, float, np.ndarray]] = []
    for cand in prompt_candidates:
        box = cand["box"]
        point = cand["point"].reshape(1, 2).astype(np.float32)
        labels = np.array([1], dtype=np.int32)
        masks, scores, _ = predictor.predict(
            point_coords=point,
            point_labels=labels,
            box=box.astype(np.float32),
            multimask_output=True,
        )
        if masks is None or len(masks) == 0:
            continue
        masks = np.asarray(masks)
        scores = np.asarray(scores, dtype=np.float32).reshape(-1)
        areas = masks.reshape(masks.shape[0], -1).sum(axis=1).astype(np.float32)
        best_idx = int(np.argmax(scores + 1e-5 * areas))
        best_mask = masks[best_idx].astype(bool)
        area = int(best_mask.sum())
        if area < min_area_px:
            continue
        scored_masks.append((float(scores[best_idx]), float(area), best_mask))

    for score, area, mask in sorted(scored_masks, key=lambda x: (x[0], x[1]), reverse=True):
        fresh = mask & (~taken)
        fresh_area = int(fresh.sum())
        if fresh_area < min_area_px:
            continue
        if fresh_area < fresh_area_fraction * area:
            continue
        next_id += 1
        label_map[fresh] = next_id
        taken |= fresh

    return label_map


def render_instance_rgb(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    hsv = np.zeros((1, 1, 3), dtype=np.uint8)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        hue = int(((lid * 0.61803398875) % 1.0) * 179)
        hsv[0, 0] = (hue, 180, 240)
        color = tuple(int(c) for c in cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0])
        out[labels == lid] = color
    return out


def render_overlay(source_rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    overlay = source_rgb.copy()
    palette = render_instance_rgb(labels)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        mask = (labels == lid).astype(np.uint8)
        colors = palette[mask > 0]
        if colors.size == 0:
            continue
        color = tuple(int(c) for c in colors[0])
        fill = overlay.copy()
        fill[mask > 0] = color
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color, 2)
    return overlay


def render_boxes(rgb: np.ndarray, boxes: List[np.ndarray]) -> np.ndarray:
    img = Image.fromarray(rgb.copy())
    draw = ImageDraw.Draw(img)
    for idx, box in enumerate(boxes, start=1):
        x0, y0, x1, y1 = map(int, box.tolist())
        draw.rectangle([x0, y0, x1, y1], outline=(255, 80, 0), width=3)
        draw.text((x0 + 4, y0 + 4), str(idx), fill=(255, 80, 0))
    return np.array(img)


def save_gallery(rows: List[dict], output_dir: Path) -> None:
    triptychs: List[Image.Image] = []
    for row in rows:
        uid = row["uid"]
        original = Image.open(Path(row["source_png"])).convert("RGB").resize((320, 240))
        prompt_overlay = Image.open(Path(row["prompt_boxes_png"])).convert("RGB").resize((320, 240))
        seg_overlay = Image.open(Path(row["overlay_png"])).convert("RGB").resize((320, 240))
        instance = Image.open(Path(row["instance_png"])).convert("RGB").resize((320, 240))
        canvas = Image.new("RGB", (1320, 280), "white")
        draw = ImageDraw.Draw(canvas)
        canvas.paste(original, (0, 36))
        canvas.paste(prompt_overlay, (335, 36))
        canvas.paste(seg_overlay, (670, 36))
        canvas.paste(instance, (1005, 36))
        draw.text((8, 8), f"{uid} | original", fill=(20, 20, 20))
        draw.text((343, 8), f"prompt boxes ({row['prompt_box_count']})", fill=(20, 20, 20))
        draw.text((678, 8), f"SAM overlay ({row['filtered_mask_count']})", fill=(20, 20, 20))
        draw.text((1013, 8), "instance mask", fill=(20, 20, 20))
        triptychs.append(canvas)
    total_height = sum(img.height for img in triptychs) + 16 * max(0, len(triptychs) - 1)
    gallery = Image.new("RGB", (1320, total_height), "white")
    y = 0
    for img in triptychs:
        gallery.paste(img, (0, y))
        y += img.height + 16
    gallery.save(output_dir / "set_001_sam_prompted_metadata_gpu_gallery.png")


def main() -> int:
    args = parse_args()
    set_dir = Path(args.set_dir).resolve()
    blinded_dir = set_dir / "blinded_images"
    output_dir = resolve_output_dir(set_dir, args.output_dir)
    runs_dir = output_dir / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    uid_metadata = load_uid_metadata(set_dir)

    input_files = sorted(blinded_dir.glob("*.tif"))
    if not input_files:
        raise SystemExit(f"No TIFF files found in {blinded_dir}")

    checkpoint = resolve_checkpoint(args.model_type, args.checkpoint, Path(args.checkpoint_dir))

    import torch
    from segment_anything import SamPredictor, sam_model_registry

    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"
    sam = sam_model_registry[args.model_type](checkpoint=str(checkpoint))
    sam.to(device=device)
    predictor = SamPredictor(sam)
    summary_rows: List[dict] = []

    for tif_path in input_files:
        uid = tif_path.stem
        run_dir = runs_dir / uid
        run_dir.mkdir(parents=True, exist_ok=True)

        existing_manifest = run_dir / "run_manifest.json"
        if existing_manifest.exists():
            manifest = json.loads(existing_manifest.read_text(encoding="utf-8"))
            summary_rows.append(manifest)
            print(json.dumps({"uid": uid, "status": "skip_existing", "filtered_mask_count": manifest.get("filtered_mask_count", 0)}, ensure_ascii=False), flush=True)
            continue

        source_png = run_dir / f"{uid}.png"
        if not source_png.exists():
            with Image.open(tif_path) as im:
                im.save(source_png, format="PNG")

        source_rgb = load_rgb(source_png)
        working_rgb, scale = resize_if_needed(source_rgb, args.resize_max_dim)
        h, w = working_rgb.shape[:2]

        meta = uid_metadata.get(uid, {"day_rank": 0, "stage": "unknown", "source_path": str(tif_path), "source_folder": str(tif_path.parent)})
        prompt_candidates = derive_stage_candidates(
            working_rgb,
            stage=meta["stage"],
            day_rank=int(meta["day_rank"]),
            iou_threshold=args.iou_merge_threshold,
        )
        if not prompt_candidates:
            prompt_candidates = [{
                "box": np.array([0, 0, w - 1, h - 1], dtype=np.float32),
                "point": np.array([w / 2.0, h / 2.0], dtype=np.float32),
                "area": float(w * h),
                "source": "fallback_full_image",
            }]

        predictor.set_image(working_rgb)
        seg = build_instance_map_from_candidates(
            predictor=predictor,
            prompt_candidates=prompt_candidates,
            output_shape=(h, w),
            min_area_px=args.min_area_px,
            fresh_area_fraction=args.fresh_area_fraction,
        )
        if scale != 1.0:
            seg = cv2.resize(seg.astype(np.uint16), (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
        filtered_labels, stats = filter_instance_map(seg.astype(np.int32), args.min_area_px)

        labels_png = run_dir / "sam_labels_16bit.png"
        cv2.imwrite(str(labels_png), filtered_labels.astype(np.uint16))
        instance_rgb = render_instance_rgb(filtered_labels)
        instance_png = run_dir / "sam_instance_rgb.png"
        Image.fromarray(instance_rgb).save(instance_png)
        overlay = render_overlay(source_rgb, filtered_labels)
        overlay_png = run_dir / "sam_overlay.png"
        Image.fromarray(overlay).save(overlay_png)
        prompt_overlay = render_boxes(working_rgb, [cand["box"] for cand in prompt_candidates])
        if scale != 1.0:
            prompt_overlay = cv2.resize(prompt_overlay, (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
        prompt_overlay_png = run_dir / "prompt_boxes_overlay.png"
        Image.fromarray(prompt_overlay).save(prompt_overlay_png)

        prompt_boxes_json = run_dir / "prompt_boxes.json"
        prompt_boxes_json.write_text(json.dumps({
            "uid": uid,
            "source_tif": str(tif_path),
            "source_path_unblinded": meta["source_path"],
            "source_folder_unblinded": meta["source_folder"],
            "checkpoint": str(checkpoint),
            "model_type": args.model_type,
            "day_rank": meta["day_rank"],
            "stage": meta["stage"],
            "prompt_box_count": len(prompt_candidates),
            "prompt_sources": [cand["source"] for cand in prompt_candidates],
            "boxes_working_xyxy": [cand["box"].tolist() for cand in prompt_candidates],
            "points_working_xy": [cand["point"].tolist() for cand in prompt_candidates],
            "working_scale": scale,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        mask_stats_json = run_dir / "sam_mask_stats.json"
        mask_stats_json.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = {
            "uid": uid,
            "source_tif": str(tif_path),
            "source_png": str(source_png),
            "model_type": args.model_type,
            "checkpoint": str(checkpoint),
            "device": device,
            "working_scale": scale,
            "day_rank": meta["day_rank"],
            "stage": meta["stage"],
            "prompt_box_count": len(prompt_candidates),
            "filtered_mask_count": len(stats),
            "prompt_boxes_png": str(prompt_overlay_png),
            "labels_png": str(labels_png),
            "instance_png": str(instance_png),
            "overlay_png": str(overlay_png),
            "mask_stats_json": str(mask_stats_json),
            "prompt_boxes_json": str(prompt_boxes_json),
        }
        (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        summary_rows.append(manifest)
        print(json.dumps({"uid": uid, "day_rank": meta["day_rank"], "stage": meta["stage"], "prompt_box_count": len(prompt_candidates), "filtered_mask_count": len(stats)}, ensure_ascii=False), flush=True)

    with (output_dir / "batch_manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "uid", "source_tif", "model_type", "checkpoint", "device", "working_scale", "day_rank", "stage",
            "prompt_box_count", "filtered_mask_count", "source_png", "prompt_boxes_png",
            "labels_png", "instance_png", "overlay_png", "mask_stats_json", "prompt_boxes_json",
        ])
        writer.writeheader()
        writer.writerows(summary_rows)
    (output_dir / "batch_manifest.json").write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    save_gallery(summary_rows, output_dir)
    (output_dir / "README.md").write_text(
        "# SAM Prompted GPU Segmentation\n\n"
        f"- Images processed: {len(summary_rows)}\n"
        f"- Gallery: [set_001_sam_prompted_metadata_gpu_gallery.png](set_001_sam_prompted_metadata_gpu_gallery.png)\n"
        "- Runs are under `runs/<uid>/`.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
