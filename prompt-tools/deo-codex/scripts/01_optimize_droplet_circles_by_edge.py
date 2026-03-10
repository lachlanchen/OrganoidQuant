#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def circle_edge_score(grad: np.ndarray, cx: float, cy: float, r: float, min_visible: float) -> float:
    h, w = grad.shape
    if r < 5:
        return -1.0
    n = 180
    vals = []
    inside = 0
    for k in range(n):
        t = 2.0 * math.pi * k / n
        x = cx + r * math.cos(t)
        y = cy + r * math.sin(t)
        xi = int(round(x))
        yi = int(round(y))
        if 0 <= xi < w and 0 <= yi < h:
            inside += 1
            vals.append(float(grad[yi, xi]))
    visible = inside / n
    if visible < min_visible or not vals:
        return -1.0
    return float(np.mean(vals) * (0.5 + 0.5 * visible))


def optimize_circle(grad: np.ndarray, cx: float, cy: float, r: float, is_partial: bool):
    base_score = circle_edge_score(grad, cx, cy, r, min_visible=0.35 if is_partial else 0.8)

    max_shift = max(4, min(24, int(r * 0.10)))
    max_dr = max(3, min(20, int(r * 0.12)))
    step_xy = 2
    step_r = 2

    if is_partial:
        max_shift = int(max_shift * 0.6)
        max_dr = int(max_dr * 0.6)

    best = (cx, cy, r)
    best_score = base_score

    for dx in range(-max_shift, max_shift + 1, step_xy):
        for dy in range(-max_shift, max_shift + 1, step_xy):
            for dr in range(-max_dr, max_dr + 1, step_r):
                rr = max(5.0, r + dr)
                score = circle_edge_score(
                    grad,
                    cx + dx,
                    cy + dy,
                    rr,
                    min_visible=0.35 if is_partial else 0.8,
                )
                if score > best_score:
                    best_score = score
                    best = (cx + dx, cy + dy, rr)

    improved = best_score > base_score * 1.05 if base_score > 0 else best_score > base_score
    if not improved:
        return (cx, cy, r), base_score, base_score, False
    return best, base_score, best_score, True


def main() -> None:
    parser = argparse.ArgumentParser(description='Refine droplet circles by local edge-gradient optimization.')
    parser.add_argument('--annotation-json', required=True)
    parser.add_argument('--source-png', required=True)
    parser.add_argument('--out-json', required=True)
    parser.add_argument('--report-json', default='')
    args = parser.parse_args()

    ann_path = Path(args.annotation_json).resolve()
    out_path = Path(args.out_json).resolve()
    report_path = Path(args.report_json).resolve() if args.report_json else None

    ann = json.loads(ann_path.read_text(encoding='utf-8'))

    img = np.array(Image.open(Path(args.source_png).resolve()).convert('L')).astype(np.float32)
    gy, gx = np.gradient(img)
    grad = np.sqrt(gx * gx + gy * gy)

    changes = []
    droplets = ann.get('droplets', [])
    for d in droplets:
        cx = float(d.get('center_x_px', 0.0))
        cy = float(d.get('center_y_px', 0.0))
        r = float(d.get('radius_px', 1.0))
        is_partial = bool(d.get('is_partial', False))

        (nx, ny, nr), base_s, best_s, changed = optimize_circle(grad, cx, cy, r, is_partial)
        if changed:
            d['center_x_px'] = round(nx, 2)
            d['center_y_px'] = round(ny, 2)
            d['radius_px'] = round(nr, 2)
            changes.append({
                'droplet_id': int(d.get('droplet_id', 0)),
                'old': {'cx': cx, 'cy': cy, 'r': r, 'score': base_s},
                'new': {'cx': nx, 'cy': ny, 'r': nr, 'score': best_s},
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ann, ensure_ascii=False, indent=2), encoding='utf-8')

    report = {
        'source_annotation': str(ann_path),
        'output_annotation': str(out_path),
        'optimized_count': len(changes),
        'changes': changes,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
