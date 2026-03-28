#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

os.environ.setdefault("TORCH_DISABLE_DYNAMO", "1")

CHECKPOINTS = {
    "sam2.1_hiera_large": {
        "url": "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt",
        "config": "configs/sam2.1/sam2.1_hiera_l.yaml",
    },
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_set = repo_root / "analysis-output/fusion-analysis-test/set_001"
    default_cache = Path.home() / ".cache/sam2"
    p = argparse.ArgumentParser(description="Run SAM2.1 large prompted segmentation on a blinded fusion-analysis set.")
    p.add_argument("set_dir", nargs="?", default=str(default_set))
    p.add_argument("--output-dir", default="")
    p.add_argument("--model-name", default="sam2.1_hiera_large", choices=sorted(CHECKPOINTS))
    p.add_argument("--device", default="cuda")
    p.add_argument("--checkpoint", default="")
    p.add_argument("--checkpoint-dir", default=str(default_cache))
    p.add_argument("--resize-max-dim", type=int, default=1536)
    p.add_argument("--min-area-px", type=int, default=220)
    p.add_argument("--candidate-iou-threshold", type=float, default=0.58)
    p.add_argument("--final-iou-threshold", type=float, default=0.65)
    p.add_argument("--fresh-area-fraction", type=float, default=0.22)
    return p.parse_args()


def resolve_output_dir(set_dir: Path, explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (set_dir.parent / f"{set_dir.name}_sam2_prompted_metadata_gpu").resolve()


def resolve_checkpoint(model_name: str, explicit: str, checkpoint_dir: Path) -> Tuple[Path, str]:
    if explicit:
        return Path(explicit).resolve(), CHECKPOINTS[model_name]["config"]
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    url = CHECKPOINTS[model_name]["url"]
    path = checkpoint_dir / Path(url).name
    if not path.exists() or path.stat().st_size < 500_000_000:
        print(json.dumps({"status": "download_checkpoint", "model_name": model_name, "checkpoint": str(path)}, ensure_ascii=False), flush=True)
        urllib.request.urlretrieve(url, path)
    return path, CHECKPOINTS[model_name]["config"]


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


def load_uid_metadata(set_dir: Path) -> Dict[str, Dict[str, Any]]:
    mapping_csv = set_dir / "internal_mapping/uid_to_source.csv"
    if not mapping_csv.exists():
        return {}
    with mapping_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
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


def component_candidates_from_mask(mask_u8: np.ndarray, min_area: int, pad: int, source_name: str) -> List[Dict[str, Any]]:
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    h, w = mask_u8.shape
    out: List[Dict[str, Any]] = []
    for idx in range(1, num):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[idx, cv2.CC_STAT_LEFT])
        y = int(stats[idx, cv2.CC_STAT_TOP])
        bw = int(stats[idx, cv2.CC_STAT_WIDTH])
        bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
        if bw < 8 or bh < 8:
            continue
        support_mask = labels == idx
        box = np.array([x, y, x + bw, y + bh], dtype=np.float32)
        cx, cy = centroids[idx]
        out.append({
            "box": expand_box(box, w, h, pad),
            "point": np.array([cx, cy], dtype=np.float32),
            "support_mask": support_mask,
            "area": area,
            "source": source_name,
        })
    return out


def derive_stage_candidates(rgb: np.ndarray, stage: str, iou_threshold: float) -> Tuple[List[Dict[str, Any]], Dict[str, np.ndarray]]:
    gray = to_gray_u8(rgb)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    bg = cv2.GaussianBlur(gray, (41, 41), 0)
    residual = cv2.subtract(bg, blur)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    inv = 255 - clahe

    if stage == "cluster":
        dark_pct = 80
        dark_min_fraction = 0.0012
        adaptive_min_fraction = 0.0008
        pad_dark, pad_adapt = 14, 12
        block_size, c_val = 45, -3
    elif stage == "differentiated_colon_like":
        dark_pct = 87
        dark_min_fraction = 0.0035
        adaptive_min_fraction = 0.0018
        pad_dark, pad_adapt = 28, 24
        block_size, c_val = 75, -8
    else:
        dark_pct = 76
        dark_min_fraction = 0.0009
        adaptive_min_fraction = 0.0006
        pad_dark, pad_adapt = 18, 16
        block_size, c_val = 61, -6

    h, w = gray.shape
    dark_min_area = int(max(80, dark_min_fraction * h * w))
    adapt_min_area = int(max(60, adaptive_min_fraction * h * w))

    dark_thresh = np.percentile(residual, dark_pct)
    dark_mask = (residual >= dark_thresh).astype(np.uint8) * 255
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    adaptive = cv2.adaptiveThreshold(inv, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    candidates = []
    candidates += component_candidates_from_mask(dark_mask, dark_min_area, pad_dark, "dark_component")
    candidates += component_candidates_from_mask(adaptive, adapt_min_area, pad_adapt, "adaptive")
    candidates = merge_candidates(candidates, iou_threshold)
    return candidates, {"gray": gray, "residual": residual, "dark_mask": dark_mask > 0}


def mask_stats(mask: np.ndarray) -> Dict[str, float]:
    area = float(mask.sum())
    if area <= 0:
        return {"area": 0.0, "perimeter": 0.0, "circularity": 0.0}
    mask_u8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    perimeter = float(sum(cv2.arcLength(cnt, True) for cnt in contours))
    circularity = 0.0
    if perimeter > 0:
        circularity = float(4.0 * math.pi * area / (perimeter * perimeter))
    return {"area": area, "perimeter": perimeter, "circularity": circularity}


def stage_limits(stage: str) -> Dict[str, float]:
    if stage == "cluster":
        return {"max_area_fraction": 0.18, "max_area_ratio": 5.0, "dark_fraction_floor": 0.24}
    if stage == "differentiated_colon_like":
        return {"max_area_fraction": 0.45, "max_area_ratio": 8.0, "dark_fraction_floor": 0.20}
    return {"max_area_fraction": 0.28, "max_area_ratio": 6.0, "dark_fraction_floor": 0.22}


def score_mask(
    mask: np.ndarray,
    score: float,
    support_mask: np.ndarray,
    image_feats: Dict[str, np.ndarray],
    stage: str,
) -> Tuple[float, Dict[str, float]]:
    s_area = float(max(1, support_mask.sum()))
    m_area = float(mask.sum())
    inter = float(np.logical_and(mask, support_mask).sum())
    union = float(np.logical_or(mask, support_mask).sum())
    support_iou = inter / max(1.0, union)
    support_recall = inter / s_area
    support_precision = inter / max(1.0, m_area)
    area_ratio = m_area / s_area
    gray = image_feats["gray"]
    dark_map = image_feats["dark_mask"]
    dark_fraction = float(dark_map[mask].mean()) if m_area > 0 else 0.0
    mean_intensity = float(gray[mask].mean()) if m_area > 0 else 255.0
    mstats = mask_stats(mask)
    circularity = mstats["circularity"]
    irregularity = max(0.0, 1.0 - min(1.0, circularity))
    area_fraction = m_area / float(mask.shape[0] * mask.shape[1])

    limits = stage_limits(stage)
    droplet_like = (
        area_fraction > limits["max_area_fraction"]
        and area_ratio > limits["max_area_ratio"]
        and circularity > 0.45
        and dark_fraction < limits["dark_fraction_floor"]
    )

    area_penalty = max(0.0, math.log(max(1.0, area_ratio)) - math.log(2.4))
    score_value = (
        2.7 * support_iou
        + 1.7 * support_recall
        + 1.9 * support_precision
        + 0.35 * float(score)
        + 0.9 * dark_fraction
        + 0.25 * irregularity
        - 0.65 * area_penalty
        - (2.2 if droplet_like else 0.0)
    )
    meta = {
        "support_iou": round(support_iou, 4),
        "support_recall": round(support_recall, 4),
        "support_precision": round(support_precision, 4),
        "area_ratio": round(area_ratio, 4),
        "dark_fraction": round(dark_fraction, 4),
        "mean_intensity": round(mean_intensity, 2),
        "circularity": round(circularity, 4),
        "irregularity": round(irregularity, 4),
        "area_fraction": round(area_fraction, 4),
        "droplet_like": float(droplet_like),
    }
    return score_value, meta


def choose_best_mask_for_candidate(
    predictor: Any,
    cand: Dict[str, Any],
    image_feats: Dict[str, np.ndarray],
    stage: str,
    min_area_px: int,
) -> Tuple[np.ndarray | None, Dict[str, Any]]:
    point = cand["point"].reshape(1, 2).astype(np.float32)
    labels = np.array([1], dtype=np.int32)
    masks, scores, _ = predictor.predict(
        point_coords=point,
        point_labels=labels,
        box=cand["box"].astype(np.float32),
        multimask_output=True,
    )
    if masks is None or len(masks) == 0:
        return None, {}
    masks = np.asarray(masks).astype(bool)
    scores = np.asarray(scores, dtype=np.float32).reshape(-1)

    best_mask = None
    best_meta: Dict[str, Any] = {}
    best_score = -1e9
    for idx, mask in enumerate(masks):
        area = int(mask.sum())
        if area < min_area_px:
            continue
        composite, meta = score_mask(mask, float(scores[idx]), cand["support_mask"], image_feats, stage)
        if composite > best_score:
            best_score = composite
            best_mask = mask
            best_meta = {
                "sam_score": float(scores[idx]),
                "composite_score": float(composite),
                **meta,
            }
    return best_mask, best_meta


def build_instance_map_from_candidates(
    predictor: Any,
    prompt_candidates: List[Dict[str, Any]],
    image_feats: Dict[str, np.ndarray],
    output_shape: Tuple[int, int],
    stage: str,
    min_area_px: int,
    fresh_area_fraction: float,
    final_iou_threshold: float,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    h, w = output_shape
    label_map = np.zeros((h, w), dtype=np.int32)
    taken = np.zeros((h, w), dtype=bool)
    next_id = 0
    chosen: List[Dict[str, Any]] = []

    for cand in prompt_candidates:
        best_mask, meta = choose_best_mask_for_candidate(predictor, cand, image_feats, stage, min_area_px)
        if best_mask is None:
            continue
        ys, xs = np.where(best_mask)
        bbox = np.array([xs.min(), ys.min(), xs.max() + 1, ys.max() + 1], dtype=np.float32)
        chosen.append({
            "mask": best_mask,
            "bbox": bbox,
            "area": int(best_mask.sum()),
            "prompt_source": cand["source"],
            **meta,
        })

    for item in sorted(chosen, key=lambda x: (x["composite_score"], x["area"]), reverse=True):
        mask = item["mask"]
        if any(box_iou(item["bbox"], prev["bbox"]) >= final_iou_threshold for prev in chosen if prev is not item and prev.get("accepted")):
            overlap_mask = np.logical_and(mask, taken)
            if overlap_mask.sum() / max(1, mask.sum()) > 0.75:
                item["accepted"] = False
                continue
        fresh = mask & (~taken)
        fresh_area = int(fresh.sum())
        if fresh_area < min_area_px:
            item["accepted"] = False
            continue
        if fresh_area < fresh_area_fraction * item["area"]:
            item["accepted"] = False
            continue
        next_id += 1
        label_map[fresh] = next_id
        taken |= fresh
        item["accepted"] = True
        item["kept_label"] = next_id
        item["fresh_area"] = fresh_area
    accepted = [x for x in chosen if x.get("accepted")]
    return label_map, accepted


def filter_final_instances(labels: np.ndarray, gray: np.ndarray, stage: str, min_area_px: int) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    out = np.zeros_like(labels, dtype=np.int32)
    stats: List[Dict[str, Any]] = []
    new_id = 0
    dark_thresh = np.percentile(gray, 35)
    for lid in [int(x) for x in np.unique(labels) if int(x) > 0]:
        mask = labels == lid
        area = int(mask.sum())
        if area < min_area_px:
            continue
        ms = mask_stats(mask)
        dark_fraction = float((gray[mask] <= dark_thresh).mean()) if area > 0 else 0.0
        area_fraction = area / float(labels.shape[0] * labels.shape[1])
        limits = stage_limits(stage)
        droplet_like = (
            area_fraction > limits["max_area_fraction"]
            and ms["circularity"] > 0.48
            and dark_fraction < limits["dark_fraction_floor"]
        )
        if droplet_like:
            continue
        ys, xs = np.where(mask)
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
            "perimeter_px": round(ms["perimeter"], 2),
            "circularity": round(ms["circularity"], 4),
            "dark_fraction": round(dark_fraction, 4),
            "area_fraction": round(area_fraction, 4),
        })
    return out, stats


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
    gallery_name = output_dir.name + "_gallery.png"
    for row in rows:
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
        draw.text((8, 8), f"{row['uid']} | original", fill=(20, 20, 20))
        draw.text((343, 8), f"prompt boxes ({row['prompt_box_count']})", fill=(20, 20, 20))
        draw.text((678, 8), f"SAM2 overlay ({row['filtered_mask_count']})", fill=(20, 20, 20))
        draw.text((1013, 8), "instance mask", fill=(20, 20, 20))
        triptychs.append(canvas)
    total_height = sum(img.height for img in triptychs) + 16 * max(0, len(triptychs) - 1)
    gallery = Image.new("RGB", (1320, total_height), "white")
    y = 0
    for img in triptychs:
        gallery.paste(img, (0, y))
        y += img.height + 16
    gallery.save(output_dir / gallery_name)


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

    checkpoint, config_name = resolve_checkpoint(args.model_name, args.checkpoint, Path(args.checkpoint_dir))

    import torch
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"

    model = build_sam2(config_name, str(checkpoint), device=device)
    predictor = SAM2ImagePredictor(model)
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
        prompt_candidates, image_feats = derive_stage_candidates(working_rgb, stage=meta["stage"], iou_threshold=args.candidate_iou_threshold)
        if not prompt_candidates:
            fallback_mask = np.ones((h, w), dtype=bool)
            prompt_candidates = [{
                "box": np.array([0, 0, w - 1, h - 1], dtype=np.float32),
                "point": np.array([w / 2.0, h / 2.0], dtype=np.float32),
                "support_mask": fallback_mask,
                "area": float(w * h),
                "source": "fallback_full_image",
            }]
        predictor.set_image(working_rgb)
        seg, accepted = build_instance_map_from_candidates(
            predictor=predictor,
            prompt_candidates=prompt_candidates,
            image_feats=image_feats,
            output_shape=(h, w),
            stage=meta["stage"],
            min_area_px=args.min_area_px,
            fresh_area_fraction=args.fresh_area_fraction,
            final_iou_threshold=args.final_iou_threshold,
        )
        if scale != 1.0:
            seg = cv2.resize(seg.astype(np.uint16), (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
        gray_full = to_gray_u8(source_rgb)
        filtered_labels, stats = filter_final_instances(seg.astype(np.int32), gray_full, meta["stage"], args.min_area_px)

        labels_png = run_dir / "sam2_labels_16bit.png"
        cv2.imwrite(str(labels_png), filtered_labels.astype(np.uint16))
        instance_rgb = render_instance_rgb(filtered_labels)
        instance_png = run_dir / "sam2_instance_rgb.png"
        Image.fromarray(instance_rgb).save(instance_png)
        overlay = render_overlay(source_rgb, filtered_labels)
        overlay_png = run_dir / "sam2_overlay.png"
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
            "model_name": args.model_name,
            "config_name": config_name,
            "day_rank": meta["day_rank"],
            "stage": meta["stage"],
            "prompt_box_count": len(prompt_candidates),
            "prompt_sources": [cand["source"] for cand in prompt_candidates],
            "boxes_working_xyxy": [cand["box"].tolist() for cand in prompt_candidates],
            "points_working_xy": [cand["point"].tolist() for cand in prompt_candidates],
            "working_scale": scale,
            "accepted_candidates": [
                {
                    "prompt_source": item["prompt_source"],
                    "area": item["area"],
                    "composite_score": round(float(item["composite_score"]), 4),
                    "support_iou": item["support_iou"],
                    "support_recall": item["support_recall"],
                    "support_precision": item["support_precision"],
                    "area_ratio": item["area_ratio"],
                    "dark_fraction": item["dark_fraction"],
                    "circularity": item["circularity"],
                    "droplet_like": bool(item["droplet_like"]),
                    "kept_label": item.get("kept_label"),
                    "fresh_area": item.get("fresh_area"),
                }
                for item in accepted
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        mask_stats_json = run_dir / "sam2_mask_stats.json"
        mask_stats_json.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = {
            "uid": uid,
            "source_tif": str(tif_path),
            "source_png": str(source_png),
            "model_name": args.model_name,
            "config_name": config_name,
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
            "uid", "source_tif", "model_name", "config_name", "checkpoint", "device", "working_scale", "day_rank", "stage",
            "prompt_box_count", "filtered_mask_count", "source_png", "prompt_boxes_png",
            "labels_png", "instance_png", "overlay_png", "mask_stats_json", "prompt_boxes_json",
        ])
        writer.writeheader()
        writer.writerows(summary_rows)
    (output_dir / "batch_manifest.json").write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    save_gallery(summary_rows, output_dir)
    gallery_name = output_dir.name + "_gallery.png"
    (output_dir / "README.md").write_text(
        "# SAM2 Prompted GPU Segmentation\n\n"
        f"- Images processed: {len(summary_rows)}\n"
        f"- Gallery: [{gallery_name}]({gallery_name})\n"
        "- Runs are under `runs/<uid>/`.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
