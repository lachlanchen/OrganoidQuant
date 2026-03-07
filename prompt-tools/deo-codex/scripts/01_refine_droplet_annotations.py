#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple
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


def circle_intersection_area(c1: Tuple[float, float, float], c2: Tuple[float, float, float]) -> float:
    x1, y1, r1 = c1
    x2, y2, r2 = c2
    d = math.hypot(x1 - x2, y1 - y2)

    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2

    a1 = math.acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    a2 = math.acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    return r1 * r1 * a1 + r2 * r2 * a2 - 0.5 * math.sqrt(
        (-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2)
    )


def approx_visible_fraction(cx: float, cy: float, r: float, w: int, h: int) -> float:
    r = max(r, 1.0)
    step = max(int(r / 10), 8)
    x0 = int(cx - r)
    x1 = int(cx + r)
    y0 = int(cy - r)
    y1 = int(cy + r)

    inside = 0
    visible = 0
    rr = r * r
    for y in range(y0, y1 + 1, step):
        for x in range(x0, x1 + 1, step):
            if (x - cx) ** 2 + (y - cy) ** 2 <= rr:
                inside += 1
                if 0 <= x < w and 0 <= y < h:
                    visible += 1
    if inside == 0:
        return 0.0
    return visible / inside


def pick_better(a: Dict, b: Dict, w: int, h: int) -> Tuple[Dict, Dict]:
    def score(d: Dict) -> float:
        conf = float(d.get('confidence', 0.0))
        cx = float(d.get('center_x_px', 0.0))
        cy = float(d.get('center_y_px', 0.0))
        r = float(d.get('radius_px', 1.0))
        vis = approx_visible_fraction(cx, cy, r, w, h)
        return conf * 0.6 + vis * 0.4

    sa = score(a)
    sb = score(b)
    return (a, b) if sa >= sb else (b, a)


def dedupe_partial_droplets(droplets: List[Dict], w: int, h: int) -> Tuple[List[Dict], List[Dict]]:
    removed = []
    keep = [True] * len(droplets)

    for i in range(len(droplets)):
        if not keep[i]:
            continue
        di = droplets[i]
        if not bool(di.get('is_partial', False)):
            continue
        c1 = (float(di['center_x_px']), float(di['center_y_px']), float(di['radius_px']))
        a1 = math.pi * c1[2] * c1[2]

        for j in range(i + 1, len(droplets)):
            if not keep[j]:
                continue
            dj = droplets[j]
            if not bool(dj.get('is_partial', False)):
                continue

            c2 = (float(dj['center_x_px']), float(dj['center_y_px']), float(dj['radius_px']))
            a2 = math.pi * c2[2] * c2[2]
            inter = circle_intersection_area(c1, c2)
            ratio_small = inter / max(min(a1, a2), 1.0)

            # Treat highly-overlapped partial circles as duplicates.
            if ratio_small >= 0.82:
                better, worse = pick_better(di, dj, w, h)
                if worse is di:
                    keep[i] = False
                    removed.append({
                        'removed_droplet_id_original': int(di.get('droplet_id', i + 1)),
                        'kept_droplet_id_original': int(dj.get('droplet_id', j + 1)),
                        'reason': f'partial_overlap_ratio_small={ratio_small:.3f}',
                    })
                    break
                else:
                    keep[j] = False
                    removed.append({
                        'removed_droplet_id_original': int(dj.get('droplet_id', j + 1)),
                        'kept_droplet_id_original': int(di.get('droplet_id', i + 1)),
                        'reason': f'partial_overlap_ratio_small={ratio_small:.3f}',
                    })

    out = [d for d, k in zip(droplets, keep) if k]
    return out, removed


def main() -> None:
    parser = argparse.ArgumentParser(description='Refine prompt-annotated droplet circles: normalize + dedupe partial overlaps.')
    parser.add_argument('--annotation-json', required=True)
    parser.add_argument('--source-png', required=True)
    parser.add_argument('--out-json', required=True)
    parser.add_argument('--report-json', required=False, default='')
    parser.add_argument('--min-partial-visibility', type=float, default=0.5)
    args = parser.parse_args()

    ann_path = Path(args.annotation_json).resolve()
    out_path = Path(args.out_json).resolve()
    report_path = Path(args.report_json).resolve() if args.report_json else None

    ann = json.loads(ann_path.read_text(encoding='utf-8'))

    with Image.open(Path(args.source_png).resolve()) as im:
        w, h = im.size

    droplets = ann.get('droplets', [])

    normalized = []
    for idx, d in enumerate(droplets, start=1):
        cx = float(d.get('center_x_px', 0.0))
        cy = float(d.get('center_y_px', 0.0))
        r = max(float(d.get('radius_px', 1.0)), 1.0)
        is_partial = bool(d.get('is_partial', False))
        completeness = bool(d.get('completeness', not is_partial))
        confidence = max(0.0, min(1.0, float(d.get('confidence', 0.0))))
        position_label = d.get('position_label') or infer_position_label(cx, cy, w, h)

        row = dict(d)
        row['droplet_id'] = int(d.get('droplet_id', idx))
        row['center_x_px'] = cx
        row['center_y_px'] = cy
        row['radius_px'] = r
        row['is_partial'] = is_partial
        row['completeness'] = completeness
        row['position_label'] = position_label
        row['confidence'] = confidence
        normalized.append(row)

    # Detect and fix common coordinate-frame mismatch:
    # model may output coordinates in a downscaled preview frame (typically 1080x768)
    # while segmentation expects full-resolution pixels (e.g., 2880x2048).
    scaled_from_preview = False
    if normalized:
        max_extent_x = max(abs(float(d['center_x_px'])) + float(d['radius_px']) for d in normalized)
        max_extent_y = max(abs(float(d['center_y_px'])) + float(d['radius_px']) for d in normalized)
        median_r = sorted(float(d['radius_px']) for d in normalized)[len(normalized) // 2]

        if w >= 1800 and h >= 1200 and max_extent_x <= 1300 and max_extent_y <= 1000 and median_r < min(w, h) * 0.12:
            sx = w / 1080.0
            sy = h / 768.0
            sr = (sx + sy) / 2.0
            for d in normalized:
                d['center_x_px'] = float(d['center_x_px']) * sx
                d['center_y_px'] = float(d['center_y_px']) * sy
                d['radius_px'] = float(d['radius_px']) * sr
                d['position_label'] = infer_position_label(float(d['center_x_px']), float(d['center_y_px']), w, h)
            scaled_from_preview = True

    deduped, removed = dedupe_partial_droplets(normalized, w, h)

    min_partial_visibility = max(0.0, min(1.0, float(args.min_partial_visibility)))
    removed_small_partials = []
    filtered = []
    for d in deduped:
        cx = float(d['center_x_px'])
        cy = float(d['center_y_px'])
        r = float(d['radius_px'])
        vis = approx_visible_fraction(cx, cy, r, w, h)
        d['visible_fraction_0_to_1'] = round(float(vis), 4)
        is_partial = bool(d.get('is_partial', False))
        if is_partial and vis < min_partial_visibility:
            removed_small_partials.append({
                'removed_droplet_id_original': int(d.get('droplet_id', 0)),
                'visible_fraction_0_to_1': round(float(vis), 4),
                'threshold_0_to_1': min_partial_visibility,
                'reason': 'partial_visibility_below_threshold',
            })
            continue
        filtered.append(d)
    deduped = filtered

    deduped.sort(key=lambda x: int(x['droplet_id']))
    for i, d in enumerate(deduped, start=1):
        d['droplet_id'] = i

    clear = sum(1 for d in deduped if not bool(d.get('is_partial', False)))
    incl = len(deduped)

    ann['droplets'] = deduped
    ann.setdefault('image_summary', {})
    ann['image_summary']['droplet_count_clear'] = clear
    ann['image_summary']['droplet_count_including_partials'] = incl

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ann, ensure_ascii=False, indent=2), encoding='utf-8')

    report = {
        'source_annotation': str(ann_path),
        'output_annotation': str(out_path),
        'image_width': w,
        'image_height': h,
        'input_droplet_count': len(droplets),
        'output_droplet_count': len(deduped),
        'removed_duplicates': removed,
        'removed_small_partials': removed_small_partials,
        'min_partial_visibility_threshold_0_to_1': min_partial_visibility,
        'scaled_from_preview_frame': scaled_from_preview,
    }

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
