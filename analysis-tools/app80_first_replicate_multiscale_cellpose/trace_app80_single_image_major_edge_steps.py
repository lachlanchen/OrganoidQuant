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


ALGO_NAME = 'major_divider_edge_refinement'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--source-tif', required=True)
    p.add_argument('--label-mask', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--min-major-area', type=int, default=30000)
    p.add_argument('--min-major-ratio', type=float, default=0.018)
    p.add_argument('--barrier-thickness', type=int, default=11)
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


def split_stats(object_mask: np.ndarray, edge_component: np.ndarray, barrier_thickness: int) -> tuple[int, list[int], np.ndarray]:
    barrier = cv2.dilate(edge_component.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (barrier_thickness, barrier_thickness))) > 0
    space = object_mask & (~barrier)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(space.astype(np.uint8), connectivity=8)
    areas = sorted([int(stats[lab, cv2.CC_STAT_AREA]) for lab in range(1, n)], reverse=True)
    return n - 1, areas, labels.astype(np.uint16)


def keep_major_component(
    comp: np.ndarray,
    object_mask: np.ndarray,
    evidence: np.ndarray,
    interior_weight: np.ndarray,
    min_major_area: int,
    min_major_ratio: float,
    barrier_thickness: int,
) -> tuple[bool, dict, np.ndarray | None]:
    object_area = int(object_mask.sum())
    threshold_area = max(min_major_area, int(round(object_area * min_major_ratio)))
    comp_pixels = int(comp.sum())
    mean_ev = float(evidence[comp].mean()) if comp_pixels else 0.0
    mean_iw = float(interior_weight[comp].mean()) if comp_pixels else 0.0
    split_count, split_areas, split_labels = split_stats(object_mask, comp, barrier_thickness)
    large_parts = [a for a in split_areas if a >= threshold_area]
    keep = len(large_parts) >= 2 and mean_ev >= 0.18 and mean_iw >= 0.28 and comp_pixels >= 80
    info = {
        'edge_pixels': comp_pixels,
        'mean_evidence': mean_ev,
        'mean_interior_weight': mean_iw,
        'split_component_count': split_count,
        'split_areas_desc': split_areas,
        'major_area_threshold': threshold_area,
        'large_split_count': len(large_parts),
        'kept': keep,
    }
    return keep, info, split_labels if keep else None


def main() -> int:
    args = parse_args()
    source_tif = Path(args.source_tif).resolve()
    label_mask_path = Path(args.label_mask).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    step01 = out_dir / 'step01_input'
    step02 = out_dir / 'step02_major_edge_evidence'
    step03 = out_dir / 'step03_candidate_edges'
    step04 = out_dir / 'step04_major_edge_selection'
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

    bh17 = blackhat(clahe, 17)
    bh31 = blackhat(clahe, 31)
    bh51 = blackhat(clahe, 51)
    bh_max = np.maximum.reduce([bh17, bh31, bh51])
    sch20 = scharr_mag(clahe, 2.0)
    sch36 = scharr_mag(clahe, 3.6)
    sch_max = np.maximum.reduce([sch20, sch36])
    lap = np.abs(cv2.Laplacian(cv2.GaussianBlur(signal, (0, 0), 2.6), cv2.CV_32F, ksize=3))
    canny_signal = auto_canny(signal)

    bh_max_n = norm01(bh_max)
    sch_max_n = norm01(sch_max)
    lap_n = norm01(lap)
    residual_n = norm01(residual)
    canny_n = (canny_signal > 0).astype(np.float32)

    inner_dist = cv2.distanceTransform(union_mask.astype(np.uint8), cv2.DIST_L2, 5)
    interior_weight = np.clip((inner_dist - 12.0) / 85.0, 0.0, 1.0)
    interior_weight = interior_weight.astype(np.float32)

    evidence = norm01(
        0.44 * bh_max_n
        + 0.24 * sch_max_n
        + 0.12 * lap_n
        + 0.10 * residual_n
        + 0.10 * canny_n
    )
    evidence = evidence * (0.25 + 0.75 * interior_weight)
    evidence = norm01(evidence)

    tr.save_gray(step02 / 'step10_clahe.png', clahe)
    tr.save_gray(step02 / 'step11_hybrid_signal.png', signal)
    tr.save_gray(step02 / 'step12_blackhat_k17.png', bh17)
    tr.save_gray(step02 / 'step13_blackhat_k31.png', bh31)
    tr.save_gray(step02 / 'step14_blackhat_k51.png', bh51)
    tr.save_gray(step02 / 'step15_blackhat_max.png', bh_max_n)
    tr.save_gray(step02 / 'step16_scharr_sigma20.png', norm01(sch20))
    tr.save_gray(step02 / 'step17_scharr_sigma36.png', norm01(sch36))
    tr.save_gray(step02 / 'step18_scharr_max.png', sch_max_n)
    tr.save_gray(step02 / 'step19_laplacian_abs.png', lap_n)
    tr.save_gray(step02 / 'step20_residual_norm.png', residual_n)
    tr.save_binary(step02 / 'step21_canny_signal.png', canny_signal)
    tr.save_gray(step02 / 'step22_interior_weight.png', interior_weight)
    tr.save_gray(step02 / 'step23_major_edge_evidence.png', evidence)
    write_json(step02 / 'evidence_weights.json', {
        'algorithm': ALGO_NAME,
        'weights': {
            'blackhat_max': 0.44,
            'scharr_max': 0.24,
            'laplacian_abs': 0.12,
            'residual_norm': 0.10,
            'canny_signal': 0.10,
        },
    })

    vals = evidence[union_mask]
    high_thr = float(np.percentile(vals, 95))
    low_thr = float(np.percentile(vals, 86))
    seed_high = (evidence >= high_thr) & union_mask
    support_low = (evidence >= low_thr) & union_mask
    raw = seed_high | (support_low & (canny_signal > 0))
    closed = cv2.morphologyEx(raw.astype(np.uint8) * 255, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    thinned = skeletonize(closed)

    tr.save_binary(step03 / 'step24_seed_high.png', seed_high)
    tr.save_binary(step03 / 'step25_support_low.png', support_low)
    tr.save_binary(step03 / 'step26_candidate_raw.png', raw)
    tr.save_binary(step03 / 'step27_candidate_closed.png', closed)
    tr.save_binary(step03 / 'step28_candidate_skeleton.png', thinned)
    save_overlay(step03 / 'step29_candidate_overlay.png', rgb, union_mask, thinned)
    write_json(step03 / 'thresholds.json', {
        'high_threshold': high_thr,
        'low_threshold': low_thr,
        'min_major_area': args.min_major_area,
        'min_major_ratio': args.min_major_ratio,
        'barrier_thickness': args.barrier_thickness,
    })

    final_major_edge = np.zeros_like(union_mask, dtype=np.uint8)
    global_compartment_labels = np.zeros_like(labels, dtype=np.uint16)
    object_rows: list[dict] = []
    tiles: list[np.ndarray] = []
    global_comp_id = 0

    for obj_label in [int(v) for v in np.unique(labels) if int(v) > 0]:
        obj_dir = step05 / f'object_{obj_label:03d}'
        obj_dir.mkdir(parents=True, exist_ok=True)
        obj_mask = labels == obj_label
        obj_candidates = closed & obj_mask
        n, cc_labels, stats, _ = cv2.connectedComponentsWithStats(obj_candidates.astype(np.uint8), connectivity=8)
        candidate_rows: list[dict] = []
        kept_mask = np.zeros_like(obj_candidates, dtype=np.uint8)

        for lab in range(1, n):
            comp = cc_labels == lab
            comp_pixels = int(stats[lab, cv2.CC_STAT_AREA])
            mean_ev_pre = float(evidence[comp].mean()) if comp_pixels else 0.0
            mean_iw_pre = float(interior_weight[comp].mean()) if comp_pixels else 0.0
            if comp_pixels < 500 or mean_ev_pre < 0.18 or mean_iw_pre < 0.22:
                candidate_rows.append({
                    'candidate_label': int(lab),
                    'edge_pixels': comp_pixels,
                    'mean_evidence': mean_ev_pre,
                    'mean_interior_weight': mean_iw_pre,
                    'split_component_count': None,
                    'split_areas_desc': [],
                    'major_area_threshold': max(args.min_major_area, int(round(obj_mask.sum() * args.min_major_ratio))),
                    'large_split_count': 0,
                    'kept': False,
                    'reject_reason': 'prefilter_weak_or_short',
                })
                continue
            keep, info, split_labels = keep_major_component(
                comp=comp,
                object_mask=obj_mask,
                evidence=evidence,
                interior_weight=interior_weight,
                min_major_area=args.min_major_area,
                min_major_ratio=args.min_major_ratio,
                barrier_thickness=args.barrier_thickness,
            )
            info['candidate_label'] = int(lab)
            info['reject_reason'] = '' if keep else 'not_major_divider'
            candidate_rows.append(info)
            if keep:
                kept_mask[comp] = 255

        if kept_mask.any():
            kept_mask = skeletonize(kept_mask > 0)
            _, _, final_split = split_stats(obj_mask, kept_mask > 0, args.barrier_thickness)
            final_labels_local = np.zeros_like(final_split, dtype=np.uint16)
            n_final = int(final_split.max())
            keep_local_id = 0
            largest_area = 0
            for lab in range(1, n_final + 1):
                area = int(np.sum(final_split == lab))
                threshold_area = max(args.min_major_area, int(round(obj_mask.sum() * args.min_major_ratio)))
                if area < threshold_area:
                    continue
                keep_local_id += 1
                final_labels_local[final_split == lab] = keep_local_id
                largest_area = max(largest_area, area)
                global_comp_id += 1
                global_compartment_labels[final_split == lab] = global_comp_id
            compartment_count = int(final_labels_local.max())
        else:
            final_labels_local = np.zeros_like(labels, dtype=np.uint16)
            largest_area = 0
            compartment_count = 1

        final_major_edge[kept_mask > 0] = 255

        y0, y1, x0, x1 = crop_box(obj_mask | (kept_mask > 0), 50, obj_mask.shape)
        tr.save_rgb(obj_dir / 'step30_crop_rgb.png', rgb[y0:y1, x0:x1])
        tr.save_gray(obj_dir / 'step31_crop_evidence.png', evidence[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step32_object_mask.png', obj_mask[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step33_object_candidate_edges.png', obj_candidates[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step34_object_major_edges.png', kept_mask[y0:y1, x0:x1])
        tr.save_labels_16bit(obj_dir / 'step35_object_compartments_16bit.png', final_labels_local[y0:y1, x0:x1])
        save_overlay(obj_dir / 'step36_object_overlay.png', rgb[y0:y1, x0:x1], obj_mask[y0:y1, x0:x1], kept_mask[y0:y1, x0:x1], final_labels_local[y0:y1, x0:x1])
        write_csv(obj_dir / 'step37_candidate_table.csv', candidate_rows)

        row = {
            'object_label': obj_label,
            'object_area_px': int(obj_mask.sum()),
            'candidate_component_count': int(n - 1),
            'major_edge_pixels': int(kept_mask.sum()),
            'major_compartment_count': compartment_count,
            'largest_major_compartment_area_px': largest_area,
        }
        object_rows.append(row)
        tiles.append(make_tile(rgb, obj_mask, kept_mask, final_labels_local, f'obj {obj_label}\nmajor_comp={compartment_count}\nedge_px={int(kept_mask.sum())}'))
        write_json(obj_dir / 'step38_object_summary.json', row)

    write_csv(step04 / 'step40_object_summary_table.csv', object_rows)
    write_json(step04 / 'step40_object_summary_table.json', object_rows)
    if tiles:
        tr.save_contact_sheet(step04 / 'step41_object_contact_sheet.png', tiles, cols=3)

    tr.save_binary(step06 / 'step50_final_major_edge_mask.png', final_major_edge)
    tr.save_labels_16bit(step06 / 'step51_final_major_compartments_16bit.png', global_compartment_labels)
    save_overlay(step06 / 'step52_final_major_edge_overlay.png', rgb, union_mask, final_major_edge, global_compartment_labels)
    summary = {
        'algorithm': ALGO_NAME,
        'source_tif': str(source_tif),
        'label_mask': str(label_mask_path),
        'object_count': int(labels.max()),
        'final_major_edge_pixels_total': int(final_major_edge.sum()),
        'final_major_compartment_count_total': int(global_compartment_labels.max()),
        'high_threshold': high_thr,
        'low_threshold': low_thr,
        'objects': object_rows,
    }
    write_json(step06 / 'step53_major_edge_trace_summary.json', summary)
    write_json(out_dir / 'trace_manifest.json', {
        'algorithm': ALGO_NAME,
        'source_tif': str(source_tif),
        'label_mask': str(label_mask_path),
        'out_dir': str(out_dir),
        'step_dirs': [
            'step01_input',
            'step02_major_edge_evidence',
            'step03_candidate_edges',
            'step04_major_edge_selection',
            'step05_per_object',
            'step06_final',
        ],
    })

    gallery_tiles = [
        cv2.resize(rgb, (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(tr.norm_u8(evidence), cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(final_major_edge, cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(tr.overlay_labels(rgb, global_compartment_labels, tr.labels_to_rgb(global_compartment_labels)), (480, 340), interpolation=cv2.INTER_AREA),
    ]
    titles = ['step01 source', 'step23 major edge evidence', 'step50 major edge mask', 'step52 major edge overlay']
    panels = []
    for title, tile in zip(titles, gallery_tiles):
        canvas = np.full((380, 480, 3), 255, dtype=np.uint8)
        cv2.putText(canvas, title, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
        canvas[40:40 + tile.shape[0], :tile.shape[1]] = tile
        panels.append(canvas)
    tr.save_rgb(out_dir / 'major_edge_trace_overview_gallery.png', np.concatenate([
        np.concatenate(panels[:2], axis=1),
        np.full((16, 960, 3), 255, dtype=np.uint8),
        np.concatenate(panels[2:], axis=1)
    ], axis=0))
    print(out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
