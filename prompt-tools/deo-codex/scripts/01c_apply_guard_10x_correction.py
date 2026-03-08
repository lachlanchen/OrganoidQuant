#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict

from PIL import Image


def infer_position_label(cx: float, cy: float, w: int, h: int) -> str:
    if cx < 0:
        return 'edge-left'
    if cx > w:
        return 'edge-right'
    if cy < 0:
        return 'edge-top'
    if cy > h:
        return 'edge-bottom'

    x_bin = 0 if cx < w / 3 else 1 if cx < 2 * w / 3 else 2
    y_bin = 0 if cy < h / 3 else 1 if cy < 2 * h / 3 else 2
    labels = {
        (0, 0): 'top-left',
        (1, 0): 'top-center',
        (2, 0): 'top-right',
        (0, 1): 'mid-left',
        (1, 1): 'center',
        (2, 1): 'mid-right',
        (0, 2): 'bottom-left',
        (1, 2): 'bottom-center',
        (2, 2): 'bottom-right',
    }
    return labels[(x_bin, y_bin)]


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def main() -> None:
    p = argparse.ArgumentParser(description='Apply guard-recommended single-center droplet correction for 10x.')
    p.add_argument('--annotation-json', required=True)
    p.add_argument('--guard-json', required=True)
    p.add_argument('--source-png', required=True)
    p.add_argument('--out-json', required=True)
    args = p.parse_args()

    ann_path = Path(args.annotation_json).resolve()
    guard_path = Path(args.guard_json).resolve()
    src_png = Path(args.source_png).resolve()
    out_path = Path(args.out_json).resolve()

    ann: Dict = json.loads(ann_path.read_text(encoding='utf-8'))
    guard: Dict = json.loads(guard_path.read_text(encoding='utf-8'))

    action = str(guard.get('action', 'accept'))
    rec = guard.get('primary_droplet_recommended')
    if action != 'retry_with_single_center' or not isinstance(rec, dict):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(ann, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'applied': False, 'reason': 'guard_action_not_retry_or_no_recommendation'}))
        return

    with Image.open(src_png) as im:
        w, h = im.size

    cx = float(rec.get('center_x_px', w / 2))
    cy = float(rec.get('center_y_px', h / 2))
    r = float(rec.get('radius_px', min(w, h) * 0.15))

    cx = clamp(cx, 0.0, float(w - 1))
    cy = clamp(cy, 0.0, float(h - 1))
    r = max(2.0, min(r, 0.49 * min(w, h)))

    is_partial = bool(rec.get('is_partial', False))
    completeness = bool(rec.get('completeness', not is_partial))
    confidence = clamp(float(rec.get('confidence', 0.7)), 0.0, 1.0)

    fallback_organoid = 0
    fallback_fusion = 0.0
    if ann.get('droplets'):
        d0 = ann['droplets'][0]
        fallback_organoid = int(d0.get('initial_organoid_count_estimate', 0) or 0)
        fallback_fusion = float(d0.get('initial_fusion_level_0_to_5', 0.0) or 0.0)

    droplet = {
        'droplet_id': 1,
        'center_x_px': cx,
        'center_y_px': cy,
        'radius_px': r,
        'is_partial': is_partial,
        'completeness': completeness,
        'position_label': infer_position_label(cx, cy, w, h),
        'confidence': confidence,
        'initial_organoid_count_estimate': fallback_organoid,
        'initial_fusion_level_0_to_5': fallback_fusion,
        'note': f"guard_10x_single_center_applied: {str(rec.get('note', ''))}",
    }

    ann['droplets'] = [droplet]
    ann.setdefault('image_summary', {})
    ann['image_summary']['droplet_count_clear'] = 1 if not is_partial else 0
    ann['image_summary']['droplet_count_including_partials'] = 1
    ann['image_summary']['note'] = str(guard.get('guard_note', ''))
    ann['guard_10x_applied'] = True

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ann, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({'applied': True, 'center_x_px': cx, 'center_y_px': cy, 'radius_px': r}, ensure_ascii=False))


if __name__ == '__main__':
    main()
