#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description='Compute enhanced tile metrics from polygon segmentation output.')
    p.add_argument('--polygon-json', required=True)
    p.add_argument('--out-json', required=True)
    p.add_argument('--source-tif', default='')
    p.add_argument('--source-png', default='')
    p.add_argument('--segmentation-manifest', default='')
    p.add_argument('--contact-radius-px', type=int, default=18)
    return p.parse_args()


def clamp_polygon(poly: List[List[float]], w: int, h: int) -> np.ndarray:
    pts: List[List[int]] = []
    for pt in poly:
        if len(pt) < 2:
            continue
        x = int(round(float(pt[0])))
        y = int(round(float(pt[1])))
        pts.append([min(max(x, 0), w - 1), min(max(y, 0), h - 1)])
    if len(pts) < 3:
        return np.zeros((0, 2), dtype=np.int32)
    return np.array(pts, dtype=np.int32)


def polygon_mask(poly: np.ndarray, w: int, h: int) -> np.ndarray:
    mask = np.zeros((h, w), dtype=np.uint8)
    if poly.shape[0] >= 3:
        cv2.fillPoly(mask, [poly], 1)
    return mask


def contour_perimeter(mask: np.ndarray) -> float:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return float(sum(cv2.arcLength(cnt, True) for cnt in contours))


def contact_fraction(masks: List[np.ndarray], radius: int) -> float:
    if len(masks) < 2:
        return 1.0 if masks else 0.0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    dilated = [cv2.dilate(m.astype(np.uint8), kernel, iterations=1) for m in masks]
    touching = 0
    total = 0
    for i in range(len(masks)):
        for j in range(i + 1, len(masks)):
            total += 1
            if np.any((dilated[i] > 0) & (dilated[j] > 0)):
                touching += 1
    return float(touching / total) if total else 0.0


def component_stats(mask: np.ndarray) -> Tuple[int, List[int]]:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    areas = [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, num_labels)]
    areas.sort(reverse=True)
    return int(num_labels - 1), areas


def score_fusion(total_area: int, n_polygons: int, n_components: int, largest_fraction: float, fused_fraction: float, contact_frac: float) -> float:
    if total_area <= 0:
        return 0.0
    if n_polygons <= 1:
        base = 0.78 + 0.18 * fused_fraction
        return round(float(max(0.0, min(5.0, 5.0 * min(1.0, base)))), 3)
    component_factor = 1.0 - min(1.0, (n_components - 1) / max(n_polygons - 1, 1))
    score = 5.0 * min(1.0, 0.38 * largest_fraction + 0.32 * fused_fraction + 0.20 * contact_frac + 0.10 * component_factor)
    return round(float(max(0.0, min(5.0, score))), 3)


def main() -> int:
    args = parse_args()
    polygon_path = Path(args.polygon_json).resolve()
    out_json = Path(args.out_json).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)

    obj = json.loads(polygon_path.read_text(encoding='utf-8'))
    w = int(obj['image_width_px'])
    h = int(obj['image_height_px'])

    organoid_rows: List[Dict[str, Any]] = []
    masks: List[np.ndarray] = []
    union_mask = np.zeros((h, w), dtype=np.uint8)
    fused_area = 0

    for organoid in obj.get('organoids', []):
        pts = clamp_polygon(organoid.get('polygon_xy', []), w, h)
        if pts.shape[0] < 3:
            continue
        mask = polygon_mask(pts, w, h)
        area_px = int(np.count_nonzero(mask))
        if area_px <= 0:
            continue
        perim_px = contour_perimeter(mask)
        ys, xs = np.where(mask > 0)
        row = {
            'organoid_id': organoid.get('organoid_id'),
            'morphology': organoid.get('morphology', 'uncertain'),
            'confidence_0_to_1': float(organoid.get('confidence_0_to_1', 0.0)),
            'area_px': area_px,
            'perimeter_px': round(perim_px, 3),
            'center_x_px': round(float(xs.mean()), 3),
            'center_y_px': round(float(ys.mean()), 3),
            'bbox_x0': int(xs.min()),
            'bbox_y0': int(ys.min()),
            'bbox_x1': int(xs.max()) + 1,
            'bbox_y1': int(ys.max()) + 1,
            'note': organoid.get('note', ''),
        }
        organoid_rows.append(row)
        masks.append(mask)
        union_mask = np.maximum(union_mask, mask)
        if row['morphology'] == 'fused_mass':
            fused_area += area_px

    total_area = int(np.count_nonzero(union_mask))
    union_perimeter = contour_perimeter(union_mask)
    n_components, comp_areas = component_stats(union_mask)
    largest_area = comp_areas[0] if comp_areas else 0
    largest_fraction = float(largest_area / total_area) if total_area > 0 else 0.0
    fused_fraction = float(fused_area / total_area) if total_area > 0 else 0.0
    touch_frac = contact_fraction(masks, args.contact_radius_px)
    fusion_0_to_5 = score_fusion(total_area, len(masks), n_components, largest_fraction, fused_fraction, touch_frac)

    payload: Dict[str, Any] = {
        'source_tif': args.source_tif or obj.get('source_tif', ''),
        'source_png': args.source_png or obj.get('source_png', ''),
        'segmentation_manifest': args.segmentation_manifest,
        'polygon_json': str(polygon_path),
        'image_width_px': w,
        'image_height_px': h,
        'organoid_count': len(masks),
        'combined_area_px': total_area,
        'combined_perimeter_px': round(union_perimeter, 3),
        'largest_component_area_px': largest_area,
        'largest_component_fraction': round(largest_fraction, 6),
        'fused_area_fraction': round(fused_fraction, 6),
        'contact_fraction': round(touch_frac, 6),
        'connected_component_count': n_components,
        'fusion_0_to_5': fusion_0_to_5,
        'fusion_note': 'Deterministic fusion score from polygon union geometry, fused-mass area share, and near-contact fraction.',
        'organoids': organoid_rows,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'out_json': str(out_json),
        'organoid_count': len(masks),
        'combined_area_px': total_area,
        'combined_perimeter_px': round(union_perimeter, 3),
        'fusion_0_to_5': fusion_0_to_5,
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
