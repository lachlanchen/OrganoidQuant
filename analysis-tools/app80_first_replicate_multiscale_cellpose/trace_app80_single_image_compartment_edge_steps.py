#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

import run_multiscale_dateaware_cellpose as seg
import trace_app80_single_image_steps as tr


ALGO_NAME = 'multiscale_dark_wall_compartment_edges'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--source-tif', required=True)
    p.add_argument('--label-mask', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--halo-px', type=int, default=30)
    p.add_argument('--min-compartment-area', type=int, default=2000)
    return p.parse_args()


def write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def norm01(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(arr.shape, dtype=np.float32)
    return np.clip((arr - lo) / (hi - lo), 0.0, 1.0)


def auto_canny(img: np.ndarray, sigma: float = 0.33) -> np.ndarray:
    med = float(np.median(img))
    low = int(max(0, (1.0 - sigma) * med))
    high = int(min(255, (1.0 + sigma) * med))
    if high <= low:
        high = min(255, low + 16)
    return cv2.Canny(img, low, high)


def scharr_mag(img: np.ndarray, sigma: float) -> np.ndarray:
    if sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), sigmaX=sigma, sigmaY=sigma)
    gx = cv2.Scharr(img, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(img, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


def blackhat(img: np.ndarray, k: int) -> np.ndarray:
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.morphologyEx(img, cv2.MORPH_BLACKHAT, ker)


def skeletonize(binary: np.ndarray) -> np.ndarray:
    img = (binary > 0).astype(np.uint8) * 255
    skel = np.zeros_like(img)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while True:
        opened = cv2.morphologyEx(img, cv2.MORPH_OPEN, element)
        temp = cv2.subtract(img, opened)
        eroded = cv2.erode(img, element)
        skel = cv2.bitwise_or(skel, temp)
        img = eroded
        if cv2.countNonZero(img) == 0:
            break
    return skel


def crop_box(mask: np.ndarray, pad: int, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return 0, shape[0], 0, shape[1]
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(shape[0], int(ys.max()) + pad + 1)
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(shape[1], int(xs.max()) + pad + 1)
    return y0, y1, x0, x1


def filter_components(mask: np.ndarray, high_seed: np.ndarray, canny_support: np.ndarray, min_area: int) -> tuple[np.ndarray, list[dict]]:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    kept = np.zeros_like(mask, dtype=np.uint8)
    rows: list[dict] = []
    for lab in range(1, n):
        comp = labels == lab
        area = int(stats[lab, cv2.CC_STAT_AREA])
        touch_high = bool(np.any(high_seed[comp]))
        touch_canny = bool(np.any(canny_support[comp]))
        keep = area >= min_area and (touch_high or touch_canny)
        rows.append({
            'component_label': int(lab),
            'area_px': area,
            'touches_high_seed': touch_high,
            'touches_canny_support': touch_canny,
            'kept': keep,
        })
        if keep:
            kept[comp] = 255
    return kept, rows


def save_overlay(path: Path, rgb: np.ndarray, object_mask: np.ndarray | None = None, edge_mask: np.ndarray | None = None, comp_labels: np.ndarray | None = None) -> None:
    out = rgb.copy()
    if comp_labels is not None:
        colors = tr.labels_to_rgb(comp_labels.astype(np.uint16))
        out = cv2.addWeighted(out, 0.72, colors, 0.45, 0)
    if object_mask is not None:
        obj_edge = cv2.Canny(object_mask.astype(np.uint8) * 255, 50, 150) > 0
        out[obj_edge] = (0, 255, 0)
    if edge_mask is not None:
        out[edge_mask > 0] = (255, 0, 0)
    tr.save_rgb(path, out)


def make_tile(rgb: np.ndarray, obj_mask: np.ndarray, edge_mask: np.ndarray, comp_labels: np.ndarray, title: str) -> np.ndarray:
    y0, y1, x0, x1 = crop_box(obj_mask | (edge_mask > 0), 40, obj_mask.shape)
    crop = rgb[y0:y1, x0:x1].copy()
    colors = tr.labels_to_rgb(comp_labels[y0:y1, x0:x1].astype(np.uint16))
    crop = cv2.addWeighted(crop, 0.72, colors, 0.45, 0)
    obj_edge = cv2.Canny(obj_mask[y0:y1, x0:x1].astype(np.uint8) * 255, 50, 150) > 0
    crop[obj_edge] = (0, 255, 0)
    crop[edge_mask[y0:y1, x0:x1] > 0] = (255, 0, 0)
    scale = min(220 / crop.shape[0], 220 / crop.shape[1])
    resized = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((255, 240, 3), 255, dtype=np.uint8)
    yoff = 30 + (220 - resized.shape[0]) // 2
    xoff = (240 - resized.shape[1]) // 2
    canvas[yoff:yoff + resized.shape[0], xoff:xoff + resized.shape[1]] = resized
    for i, line in enumerate(title.split('\n')):
        cv2.putText(canvas, line[:34], (8, 18 + i * 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    return canvas


def main() -> int:
    args = parse_args()
    source_tif = Path(args.source_tif).resolve()
    label_mask_path = Path(args.label_mask).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    step01 = out_dir / 'step01_input'
    step02 = out_dir / 'step02_dark_wall_evidence'
    step03 = out_dir / 'step03_hysteresis_linking'
    step04 = out_dir / 'step04_compartment_split'
    step05 = out_dir / 'step05_per_object'
    step06 = out_dir / 'step06_final'
    for p in (step01, step02, step03, step04, step05, step06):
        p.mkdir(parents=True, exist_ok=True)

    rgb, gray = seg.load_rgb_gray(source_tif)
    labels = cv2.imread(str(label_mask_path), cv2.IMREAD_UNCHANGED)
    if labels is None:
        raise RuntimeError(f'Failed to read label mask: {label_mask_path}')
    labels = labels.astype(np.uint16)
    union_mask = labels > 0
    if not union_mask.any():
        raise RuntimeError('Label mask is empty')

    detailed = tr.compute_hybrid_signal_detailed(gray)
    signal = detailed['signal']
    clahe = detailed['clahe']
    residual = detailed['residual_norm']

    tr.save_rgb(step01 / 'step01_source_rgb.png', rgb)
    tr.save_gray(step01 / 'step02_source_gray.png', gray)
    tr.save_labels_16bit(step01 / 'step03_label_mask_16bit.png', labels)
    save_overlay(step01 / 'step04_label_overlay.png', rgb, union_mask)

    bh9 = blackhat(clahe, 9)
    bh17 = blackhat(clahe, 17)
    bh31 = blackhat(clahe, 31)
    bh_max = np.maximum.reduce([bh9, bh17, bh31])
    sch0 = scharr_mag(clahe, 0.0)
    sch12 = scharr_mag(clahe, 1.2)
    sch24 = scharr_mag(clahe, 2.4)
    sch_max = np.maximum.reduce([sch0, sch12, sch24])
    lap = np.abs(cv2.Laplacian(cv2.GaussianBlur(signal, (0, 0), 1.8), cv2.CV_32F, ksize=3))
    canny_clahe = auto_canny(clahe)
    canny_signal = auto_canny(signal)

    bh_max_n = norm01(bh_max)
    sch_max_n = norm01(sch_max)
    lap_n = norm01(lap)
    residual_n = norm01(residual)
    canny_union = ((canny_clahe > 0) | (canny_signal > 0)).astype(np.float32)

    evidence = norm01(
        0.36 * bh_max_n
        + 0.24 * sch_max_n
        + 0.14 * lap_n
        + 0.14 * residual_n
        + 0.12 * canny_union
    )

    search = cv2.dilate(union_mask.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * args.halo_px + 1, 2 * args.halo_px + 1))) > 0
    evidence_search = evidence * search.astype(np.float32)

    tr.save_gray(step02 / 'step10_clahe.png', clahe)
    tr.save_gray(step02 / 'step11_hybrid_signal.png', signal)
    tr.save_gray(step02 / 'step12_blackhat_k09.png', bh9)
    tr.save_gray(step02 / 'step13_blackhat_k17.png', bh17)
    tr.save_gray(step02 / 'step14_blackhat_k31.png', bh31)
    tr.save_gray(step02 / 'step15_blackhat_max.png', bh_max_n)
    tr.save_gray(step02 / 'step16_scharr_max.png', sch_max_n)
    tr.save_gray(step02 / 'step17_laplacian_abs.png', lap_n)
    tr.save_gray(step02 / 'step18_residual_norm.png', residual_n)
    tr.save_binary(step02 / 'step19_canny_clahe.png', canny_clahe)
    tr.save_binary(step02 / 'step20_canny_signal.png', canny_signal)
    tr.save_gray(step02 / 'step21_compartment_evidence.png', evidence)
    write_json(step02 / 'evidence_weights.json', {
        'algorithm': ALGO_NAME,
        'weights': {
            'blackhat_max': 0.36,
            'scharr_max': 0.24,
            'laplacian_abs': 0.14,
            'residual_norm': 0.14,
            'canny_union': 0.12,
        },
    })

    vals = evidence[search]
    high_thr = float(np.percentile(vals, 90))
    low_thr = float(np.percentile(vals, 72))
    seed_high = (evidence >= high_thr) & search
    support_low = (evidence >= low_thr) & search
    canny_support = ((canny_clahe > 0) | (canny_signal > 0)) & search
    raw_link = support_low | canny_support
    closed = cv2.morphologyEx(raw_link.astype(np.uint8) * 255, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    filtered, cc_rows = filter_components(closed, seed_high, canny_support, min_area=12)
    skel = skeletonize(filtered)
    final_edge = cv2.bitwise_or(skel, (canny_support & (filtered > 0)).astype(np.uint8) * 255)

    tr.save_binary(step03 / 'step22_search_region.png', search)
    tr.save_gray(step03 / 'step23_evidence_in_search.png', evidence_search)
    tr.save_binary(step03 / 'step24_seed_high.png', seed_high)
    tr.save_binary(step03 / 'step25_support_low.png', support_low)
    tr.save_binary(step03 / 'step26_canny_support.png', canny_support)
    tr.save_binary(step03 / 'step27_raw_link.png', raw_link)
    tr.save_binary(step03 / 'step28_after_close.png', closed)
    tr.save_binary(step03 / 'step29_filtered_components.png', filtered)
    tr.save_binary(step03 / 'step30_skeletonized.png', skel)
    tr.save_binary(step03 / 'step31_final_edge_map.png', final_edge)
    save_overlay(step03 / 'step32_edge_overlay.png', rgb, union_mask, final_edge)
    write_csv(step03 / 'step33_component_table.csv', cc_rows)
    write_json(step03 / 'step33_component_table.json', cc_rows)
    write_json(step03 / 'thresholds.json', {
        'high_threshold': high_thr,
        'low_threshold': low_thr,
        'halo_px': args.halo_px,
    })

    barrier = cv2.dilate(final_edge, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    compartment_space = union_mask & (~barrier)
    n_all, labels_all, stats_all, _ = cv2.connectedComponentsWithStats(compartment_space.astype(np.uint8), connectivity=8)
    compartment_labels = np.zeros_like(labels_all, dtype=np.uint16)
    comp_rows: list[dict] = []
    keep_id = 0
    for lab in range(1, n_all):
        area = int(stats_all[lab, cv2.CC_STAT_AREA])
        if area < args.min_compartment_area:
            continue
        keep_id += 1
        compartment_labels[labels_all == lab] = keep_id
        ys, xs = np.where(labels_all == lab)
        comp_rows.append({
            'compartment_label': keep_id,
            'area_px': area,
            'centroid_x_px': float(xs.mean()) if xs.size else None,
            'centroid_y_px': float(ys.mean()) if ys.size else None,
        })

    tr.save_binary(step04 / 'step40_barrier_from_edges.png', barrier)
    tr.save_binary(step04 / 'step41_compartment_space.png', compartment_space)
    tr.save_labels_16bit(step04 / 'step42_compartment_labels_16bit.png', compartment_labels)
    save_overlay(step04 / 'step43_compartment_overlay.png', rgb, union_mask, final_edge, compartment_labels)
    write_csv(step04 / 'step44_compartment_table.csv', comp_rows)
    write_json(step04 / 'step44_compartment_table.json', comp_rows)

    object_rows: list[dict] = []
    tiles: list[np.ndarray] = []
    for obj_label in [int(v) for v in np.unique(labels) if int(v) > 0]:
        obj_dir = step05 / f'object_{obj_label:03d}'
        obj_dir.mkdir(parents=True, exist_ok=True)
        obj_mask = labels == obj_label
        obj_edges = (final_edge > 0) & obj_mask
        obj_barrier = cv2.dilate(obj_edges.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
        obj_space = obj_mask & (~obj_barrier)
        n_obj, obj_cc, obj_stats, _ = cv2.connectedComponentsWithStats(obj_space.astype(np.uint8), connectivity=8)
        obj_comp_labels = np.zeros_like(obj_cc, dtype=np.uint16)
        obj_keep = 0
        obj_comp_rows: list[dict] = []
        for lab in range(1, n_obj):
            area = int(obj_stats[lab, cv2.CC_STAT_AREA])
            if area < args.min_compartment_area:
                continue
            obj_keep += 1
            obj_comp_labels[obj_cc == lab] = obj_keep
            obj_comp_rows.append({'compartment_label': obj_keep, 'area_px': area})

        y0, y1, x0, x1 = crop_box(obj_mask | obj_edges, 50, obj_mask.shape)
        tr.save_rgb(obj_dir / 'step50_crop_rgb.png', rgb[y0:y1, x0:x1])
        tr.save_gray(obj_dir / 'step51_crop_evidence.png', evidence[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step52_object_mask.png', obj_mask[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step53_object_edge.png', obj_edges[y0:y1, x0:x1])
        tr.save_labels_16bit(obj_dir / 'step54_object_compartments_16bit.png', obj_comp_labels[y0:y1, x0:x1])
        save_overlay(obj_dir / 'step55_object_overlay.png', rgb[y0:y1, x0:x1], obj_mask[y0:y1, x0:x1], obj_edges[y0:y1, x0:x1], obj_comp_labels[y0:y1, x0:x1])
        write_csv(obj_dir / 'step56_object_compartment_table.csv', obj_comp_rows)

        row = {
            'object_label': obj_label,
            'object_area_px': int(obj_mask.sum()),
            'edge_pixels_inside_object': int(obj_edges.sum()),
            'compartment_count': obj_keep,
            'largest_compartment_area_px': max((r['area_px'] for r in obj_comp_rows), default=0),
        }
        object_rows.append(row)
        tiles.append(make_tile(rgb, obj_mask, obj_edges.astype(np.uint8) * 255, obj_comp_labels, f'obj {obj_label}\ncomp={obj_keep}\nedge_px={int(obj_edges.sum())}'))
        write_json(obj_dir / 'step57_object_summary.json', row)

    write_csv(step05 / 'step58_object_summary_table.csv', object_rows)
    write_json(step05 / 'step58_object_summary_table.json', object_rows)
    if tiles:
        tr.save_contact_sheet(step05 / 'step59_object_contact_sheet.png', tiles, cols=3)

    save_overlay(step06 / 'step60_final_edge_overlay.png', rgb, union_mask, final_edge)
    tr.save_binary(step06 / 'step61_final_edge_mask.png', final_edge)
    tr.save_labels_16bit(step06 / 'step62_final_compartment_labels_16bit.png', compartment_labels)
    save_overlay(step06 / 'step63_final_compartment_overlay.png', rgb, union_mask, final_edge, compartment_labels)
    summary = {
        'algorithm': ALGO_NAME,
        'source_tif': str(source_tif),
        'label_mask': str(label_mask_path),
        'object_count': int(labels.max()),
        'compartment_count_total': int(compartment_labels.max()),
        'final_edge_pixels_total': int((final_edge > 0).sum()),
        'high_threshold': high_thr,
        'low_threshold': low_thr,
        'objects': object_rows,
    }
    write_json(step06 / 'step64_compartment_trace_summary.json', summary)
    write_json(out_dir / 'trace_manifest.json', {
        'algorithm': ALGO_NAME,
        'source_tif': str(source_tif),
        'label_mask': str(label_mask_path),
        'out_dir': str(out_dir),
        'step_dirs': [
            'step01_input',
            'step02_dark_wall_evidence',
            'step03_hysteresis_linking',
            'step04_compartment_split',
            'step05_per_object',
            'step06_final',
        ],
    })

    gallery_tiles = [
        cv2.resize(rgb, (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(tr.norm_u8(evidence), cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(final_edge, cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(tr.overlay_labels(rgb, compartment_labels, tr.labels_to_rgb(compartment_labels)), (480, 340), interpolation=cv2.INTER_AREA),
    ]
    titles = ['step01 source', 'step21 compartment evidence', 'step61 final edge mask', 'step63 compartment overlay']
    panels = []
    for title, tile in zip(titles, gallery_tiles):
        canvas = np.full((380, 480, 3), 255, dtype=np.uint8)
        cv2.putText(canvas, title, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
        canvas[40:40 + tile.shape[0], :tile.shape[1]] = tile
        panels.append(canvas)
    tr.save_rgb(out_dir / 'compartment_trace_overview_gallery.png', np.concatenate([
        np.concatenate(panels[:2], axis=1),
        np.full((16, 960, 3), 255, dtype=np.uint8),
        np.concatenate(panels[2:], axis=1)
    ], axis=0))
    print(out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
