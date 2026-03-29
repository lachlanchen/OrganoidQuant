#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--csv-path', required=True)
    p.add_argument('--normalize', choices=['none', 'minmax_floor'], default='none')
    p.add_argument('--floor', type=float, default=0.1)
    return p.parse_args()


def draw_text(img: np.ndarray, text: str, xy: tuple[int, int], scale: float = 0.6, color: tuple[int, int, int] = (20, 20, 20), thickness: int = 1, anchor: str = 'left') -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(text, font, scale, thickness)
    x, y = xy
    if anchor == 'center':
        x -= w // 2
    elif anchor == 'right':
        x -= w
    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def normalize_minmax_floor(values: list[float], floor: float) -> list[float]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    if vmax <= vmin:
        return [1.0 for _ in values]
    span = vmax - vmin
    return [floor + (1.0 - floor) * ((v - vmin) / span) for v in values]


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv_path).resolve()
    out_dir = csv_path.parent

    rows = []
    with csv_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'date_label': row['date_label'],
                'relative_day': int(row['relative_day']),
                'image_name': row['image_name'],
                'curvature': float(row['curvature_proxy_area_weighted_circularity']),
                'count': float(row['count']),
                'edge': float(row['edge_intensity_second_column_boundary_gradient']),
            })
    rows.sort(key=lambda r: r['relative_day'])

    if args.normalize == 'minmax_floor':
        curv_norm = normalize_minmax_floor([r['curvature'] for r in rows], args.floor)
        count_norm = normalize_minmax_floor([r['count'] for r in rows], args.floor)
        edge_norm = normalize_minmax_floor([r['edge'] for r in rows], args.floor)
        for row, c1, c2, e1 in zip(rows, curv_norm, count_norm, edge_norm):
            row['curvature_used'] = c1
            row['count_used'] = c2
            row['edge_used'] = e1
            row['edge_over_curvature_count'] = e1 / (c1 * c2)
        stem = 'edge_over_curvature_count_minmax_floor_by_day'
        title = 'Normalized Edge / (Normalized Curvature * Normalized Counts)'
        subtitle = f'App80 10uM First-Replicate Large-Recovery Segmentation | min-max with floor={args.floor:g}'
        ylabel = 'edge_norm / (curvature_norm * counts_norm)'
        csv_header = [
            'date_label', 'relative_day', 'image_name',
            'curvature_raw', 'count_raw', 'edge_raw',
            'curvature_normalized', 'count_normalized', 'edge_normalized',
            'edge_over_curvature_count_normalized'
        ]
    else:
        for row in rows:
            curvature = row['curvature']
            count = row['count']
            edge = row['edge']
            row['curvature_used'] = curvature
            row['count_used'] = count
            row['edge_used'] = edge
            row['edge_over_curvature_count'] = edge / (curvature * count) if curvature > 0 and count > 0 else 0.0
        stem = 'edge_over_curvature_count_by_day'
        title = 'Edge Intensity / (Curvature * Counts)'
        subtitle = 'App80 10uM First-Replicate Large-Recovery Segmentation'
        ylabel = 'edge / (curvature * counts)'
        csv_header = ['date_label', 'relative_day', 'image_name', 'edge_over_curvature_count']

    out_csv = out_dir / f'{stem}.csv'
    with out_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(csv_header)
        for row in rows:
            if args.normalize == 'minmax_floor':
                writer.writerow([
                    row['date_label'],
                    row['relative_day'],
                    row['image_name'],
                    f"{row['curvature']:.12f}",
                    f"{row['count']:.12f}",
                    f"{row['edge']:.12f}",
                    f"{row['curvature_used']:.12f}",
                    f"{row['count_used']:.12f}",
                    f"{row['edge_used']:.12f}",
                    f"{row['edge_over_curvature_count']:.12f}",
                ])
            else:
                writer.writerow([
                    row['date_label'],
                    row['relative_day'],
                    row['image_name'],
                    f"{row['edge_over_curvature_count']:.12f}",
                ])

    w, h = 1400, 900
    left, right, top, bottom = 120, 60, 120, 140
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    plot_w = w - left - right
    plot_h = h - top - bottom

    x_vals = [r['relative_day'] for r in rows]
    y_vals = [r['edge_over_curvature_count'] for r in rows]
    ymin = min(y_vals) if y_vals else 0.0
    ymax = max(y_vals) if y_vals else 1.0
    if ymax <= ymin:
        ymax = ymin + 1.0
    pad = 0.08 * (ymax - ymin)
    ymin -= pad
    ymax += pad

    cv2.line(img, (left, top + plot_h), (left + plot_w, top + plot_h), (60, 60, 60), 2)
    cv2.line(img, (left, top), (left, top + plot_h), (60, 60, 60), 2)

    n_grid = 5
    for i in range(n_grid + 1):
        yy = top + int(round(plot_h * i / n_grid))
        val = ymax - (ymax - ymin) * i / n_grid
        cv2.line(img, (left, yy), (left + plot_w, yy), (230, 230, 230), 1)
        draw_text(img, f'{val:.2f}', (left - 12, yy + 5), scale=0.55, anchor='right')

    pts = []
    for idx, row in enumerate(rows):
        if len(rows) == 1:
            xx = left + plot_w // 2
        else:
            xx = left + int(round(plot_w * idx / (len(rows) - 1)))
        yy = top + int(round((ymax - row['edge_over_curvature_count']) / (ymax - ymin) * plot_h))
        pts.append((xx, yy))
        cv2.line(img, (xx, top + plot_h), (xx, top + plot_h + 8), (60, 60, 60), 2)
        draw_text(img, row['date_label'], (xx, top + plot_h + 35), scale=0.55, anchor='center')

    if len(pts) >= 2:
        cv2.polylines(img, [np.array(pts, dtype=np.int32)], isClosed=False, color=(30, 30, 30), thickness=3, lineType=cv2.LINE_AA)
    for (xx, yy), row in zip(pts, rows):
        cv2.circle(img, (xx, yy), 6, (30, 30, 30), -1, lineType=cv2.LINE_AA)
        draw_text(img, f"{row['edge_over_curvature_count']:.2f}", (xx, yy - 14), scale=0.45, anchor='center')

    draw_text(img, title, (w // 2, 55), scale=1.0, thickness=2, anchor='center')
    draw_text(img, subtitle, (w // 2, 90), scale=0.65, anchor='center')
    draw_text(img, ylabel, (40, top + plot_h // 2), scale=0.6)

    out_png = out_dir / f'{stem}.png'
    cv2.imwrite(str(out_png), img)

    print(out_csv)
    print(out_png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
