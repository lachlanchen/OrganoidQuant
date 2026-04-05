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


ALGO_NAME = 'mask_guided_multiscale_edge_refinement'


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--source-tif', required=True)
    p.add_argument('--label-mask', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--inner-band-px', type=int, default=90)
    p.add_argument('--outer-band-px', type=int, default=70)
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
    v = float(np.median(img))
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    if upper <= lower:
        upper = min(255, lower + 16)
    return cv2.Canny(img, lower, upper)


def scharr_mag(img: np.ndarray, sigma: float) -> np.ndarray:
    if sigma > 0:
        blur = cv2.GaussianBlur(img, (0, 0), sigmaX=sigma, sigmaY=sigma)
    else:
        blur = img
    gx = cv2.Scharr(blur, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(blur, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)


def crop_box(mask: np.ndarray, pad: int, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return 0, shape[0], 0, shape[1]
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(shape[0], int(ys.max()) + pad + 1)
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(shape[1], int(xs.max()) + pad + 1)
    return y0, y1, x0, x1


def save_crop(path: Path, rgb: np.ndarray, mask: np.ndarray | None = None, edge: np.ndarray | None = None) -> None:
    out = rgb.copy()
    if mask is not None:
        mask_edge = cv2.Canny(mask.astype(np.uint8) * 255, 50, 150) > 0
        out[mask_edge] = (0, 255, 0)
    if edge is not None:
        out[edge > 0] = (255, 0, 0)
    tr.save_rgb(path, out)


def build_global_component_table(candidate_mask: np.ndarray, evidence: np.ndarray, boundary_zone: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_mask.astype(np.uint8), connectivity=8)
    kept = np.zeros_like(candidate_mask, dtype=np.uint8)
    rows: list[dict] = []
    for lab in range(1, n):
        comp = labels == lab
        area = int(stats[lab, cv2.CC_STAT_AREA])
        mean_ev = float(evidence[comp].mean()) if area else 0.0
        max_ev = float(evidence[comp].max()) if area else 0.0
        touch = bool(np.any(boundary_zone[comp]))
        keep = area >= 20 and mean_ev >= 0.18 and touch
        rows.append({
            'component_label': int(lab),
            'area_px': area,
            'mean_evidence': mean_ev,
            'max_evidence': max_ev,
            'touches_boundary_zone': touch,
            'kept': keep,
        })
        if keep:
            kept[comp] = 255
    return kept, rows


def make_contact_tile(rgb: np.ndarray, obj_mask: np.ndarray, edge_mask: np.ndarray, title: str) -> np.ndarray:
    y0, y1, x0, x1 = crop_box(obj_mask | (edge_mask > 0), 40, obj_mask.shape)
    crop = rgb[y0:y1, x0:x1].copy()
    ref = obj_mask[y0:y1, x0:x1]
    edge = edge_mask[y0:y1, x0:x1] > 0
    ref_edge = cv2.Canny(ref.astype(np.uint8) * 255, 50, 150) > 0
    crop[ref_edge] = (0, 255, 0)
    crop[edge] = (255, 0, 0)
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
    step02 = out_dir / 'step02_edge_evidence'
    step03 = out_dir / 'step03_search_band'
    step04 = out_dir / 'step04_global_edge_candidates'
    step05 = out_dir / 'step05_instance_refinement'
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
    residual_norm = detailed['residual_norm']
    clahe = detailed['clahe']

    tr.save_rgb(step01 / 'step01_source_rgb.png', rgb)
    tr.save_gray(step01 / 'step02_source_gray.png', gray)
    tr.save_labels_16bit(step01 / 'step03_current_label_mask_16bit.png', labels)
    label_rgb = tr.labels_to_rgb(labels)
    tr.save_rgb(step01 / 'step04_current_mask_overlay.png', tr.overlay_labels(rgb, labels, label_rgb))

    scharr_0 = scharr_mag(clahe, 0.0)
    scharr_12 = scharr_mag(clahe, 1.2)
    scharr_24 = scharr_mag(clahe, 2.4)
    scharr_max = np.maximum.reduce([scharr_0, scharr_12, scharr_24])
    lap_abs = np.abs(cv2.Laplacian(cv2.GaussianBlur(signal, (0, 0), 2.0), cv2.CV_32F, ksize=3))
    morph_grad = cv2.morphologyEx(signal, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    canny_clahe = auto_canny(clahe)
    canny_signal = auto_canny(signal)

    scharr_0_n = norm01(scharr_0)
    scharr_12_n = norm01(scharr_12)
    scharr_24_n = norm01(scharr_24)
    scharr_max_n = norm01(scharr_max)
    lap_n = norm01(lap_abs)
    morph_grad_n = norm01(morph_grad)
    canny_clahe_n = (canny_clahe > 0).astype(np.float32)
    canny_signal_n = (canny_signal > 0).astype(np.float32)
    residual_n = norm01(residual_norm)

    edge_evidence = (
        0.32 * scharr_max_n
        + 0.16 * lap_n
        + 0.14 * morph_grad_n
        + 0.14 * canny_clahe_n
        + 0.14 * canny_signal_n
        + 0.10 * residual_n
    )
    edge_evidence = norm01(edge_evidence)

    tr.save_gray(step02 / 'step10_clahe.png', clahe)
    tr.save_gray(step02 / 'step11_hybrid_signal.png', signal)
    tr.save_gray(step02 / 'step12_residual_norm.png', residual_norm)
    tr.save_gray(step02 / 'step13_scharr_sigma00.png', scharr_0_n)
    tr.save_gray(step02 / 'step14_scharr_sigma12.png', scharr_12_n)
    tr.save_gray(step02 / 'step15_scharr_sigma24.png', scharr_24_n)
    tr.save_gray(step02 / 'step16_scharr_max.png', scharr_max_n)
    tr.save_gray(step02 / 'step17_laplacian_abs_sigma20.png', lap_n)
    tr.save_gray(step02 / 'step18_morph_gradient_signal.png', morph_grad_n)
    tr.save_binary(step02 / 'step19_canny_clahe.png', canny_clahe)
    tr.save_binary(step02 / 'step20_canny_signal.png', canny_signal)
    tr.save_gray(step02 / 'step21_edge_evidence_raw.png', edge_evidence)
    write_json(step02 / 'edge_evidence_weights.json', {
        'algorithm': ALGO_NAME,
        'weights': {
            'scharr_max': 0.32,
            'laplacian_abs': 0.16,
            'morph_gradient_signal': 0.14,
            'canny_clahe': 0.14,
            'canny_signal': 0.14,
            'residual_norm': 0.10,
        }
    })

    union_u8 = union_mask.astype(np.uint8)
    inner_dist = cv2.distanceTransform(union_u8, cv2.DIST_L2, 5)
    outer_dist = cv2.distanceTransform((~union_mask).astype(np.uint8), cv2.DIST_L2, 5)
    search_band = ((union_mask & (inner_dist <= args.inner_band_px)) | ((~union_mask) & (outer_dist <= args.outer_band_px)))
    boundary_ref = cv2.morphologyEx(union_u8 * 255, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0
    boundary_zone = cv2.dilate(boundary_ref.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0
    evidence_in_band = edge_evidence * search_band.astype(np.float32)

    tr.save_binary(step03 / 'step22_union_mask.png', union_u8 * 255)
    tr.save_binary(step03 / 'step23_boundary_reference.png', boundary_ref)
    tr.save_gray(step03 / 'step24_inner_distance.png', inner_dist)
    tr.save_gray(step03 / 'step25_outer_distance.png', outer_dist)
    tr.save_binary(step03 / 'step26_search_band.png', search_band)
    tr.save_binary(step03 / 'step27_boundary_zone.png', boundary_zone)
    tr.save_gray(step03 / 'step28_edge_evidence_in_band.png', evidence_in_band)
    write_json(step03 / 'band_params.json', {
        'inner_band_px': args.inner_band_px,
        'outer_band_px': args.outer_band_px,
    })

    band_values = edge_evidence[search_band]
    high_thr = float(np.percentile(band_values, 88))
    low_thr = float(np.percentile(band_values, 70))
    global_seed_high = (edge_evidence >= high_thr) & search_band
    global_seed_canny = ((canny_clahe > 0) | (canny_signal > 0)) & search_band & (edge_evidence >= low_thr)
    global_raw = global_seed_high | global_seed_canny
    global_closed = cv2.morphologyEx(global_raw.astype(np.uint8) * 255, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    global_filtered, global_rows = build_global_component_table(global_closed, edge_evidence, boundary_zone)

    tr.save_binary(step04 / 'step30_global_seed_high.png', global_seed_high)
    tr.save_binary(step04 / 'step31_global_seed_canny_support.png', global_seed_canny)
    tr.save_binary(step04 / 'step32_global_candidate_raw.png', global_raw)
    tr.save_binary(step04 / 'step33_global_candidate_closed.png', global_closed)
    tr.save_binary(step04 / 'step34_global_candidate_filtered.png', global_filtered)
    tr.save_rgb(step04 / 'step35_global_candidate_overlay.png', tr.overlay_labels(rgb, global_filtered.astype(np.uint16)))
    write_csv(step04 / 'step36_global_component_table.csv', global_rows)
    write_json(step04 / 'step36_global_component_table.json', global_rows)

    final_edge = np.zeros_like(union_u8, dtype=np.uint8)
    object_rows: list[dict] = []
    object_tiles: list[np.ndarray] = []

    for label in [int(v) for v in np.unique(labels) if int(v) > 0]:
        obj_dir = step05 / f'object_{label:03d}'
        obj_dir.mkdir(parents=True, exist_ok=True)
        obj_mask = labels == label
        obj_u8 = obj_mask.astype(np.uint8)
        obj_boundary = cv2.morphologyEx(obj_u8 * 255, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0
        obj_boundary_zone = cv2.dilate(obj_boundary.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
        obj_inner = cv2.distanceTransform(obj_u8, cv2.DIST_L2, 5)
        obj_outer = cv2.distanceTransform((~obj_mask).astype(np.uint8), cv2.DIST_L2, 5)
        obj_search = ((obj_mask & (obj_inner <= args.inner_band_px)) | ((~union_mask) & (obj_outer <= args.outer_band_px)))
        local_values = edge_evidence[obj_search]
        local_high = float(np.percentile(local_values, 88)) if local_values.size else high_thr
        local_low = float(np.percentile(local_values, 70)) if local_values.size else low_thr
        seed_high = (edge_evidence >= local_high) & obj_search
        seed_canny = ((canny_clahe > 0) | (canny_signal > 0)) & obj_search & (edge_evidence >= local_low)
        raw = seed_high | seed_canny
        closed = cv2.morphologyEx(raw.astype(np.uint8) * 255, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0

        n, cc_labels, stats, _ = cv2.connectedComponentsWithStats(closed.astype(np.uint8), connectivity=8)
        kept_region = np.zeros_like(closed, dtype=np.uint8)
        boundary_inv = (~obj_boundary).astype(np.uint8)
        boundary_dist = cv2.distanceTransform(boundary_inv, cv2.DIST_L2, 5)
        kept_components = 0
        fallback_used = False
        comp_rows: list[dict] = []
        for comp_lab in range(1, n):
            comp = cc_labels == comp_lab
            area = int(stats[comp_lab, cv2.CC_STAT_AREA])
            mean_ev = float(edge_evidence[comp].mean()) if area else 0.0
            max_ev = float(edge_evidence[comp].max()) if area else 0.0
            min_boundary_dist = float(boundary_dist[comp].min()) if area else 1e9
            touches = bool(np.any(obj_boundary_zone[comp]))
            keep = area >= 12 and max_ev >= max(0.28, local_low) and (touches or min_boundary_dist <= 10.0)
            comp_rows.append({
                'component_label': int(comp_lab),
                'area_px': area,
                'mean_evidence': mean_ev,
                'max_evidence': max_ev,
                'min_boundary_distance_px': min_boundary_dist,
                'touches_object_boundary_zone': touches,
                'kept': keep,
            })
            if keep:
                kept_region[comp] = 255
                kept_components += 1

        thin_support = ((canny_clahe > 0) | (canny_signal > 0)) & (kept_region > 0)
        if int(thin_support.sum()) >= 20:
            final_obj_edge = thin_support.astype(np.uint8) * 255
        elif kept_components > 0:
            final_obj_edge = kept_region
        else:
            final_obj_edge = obj_boundary.astype(np.uint8) * 255
            fallback_used = True

        final_edge[final_obj_edge > 0] = 255

        y0, y1, x0, x1 = crop_box(obj_mask | (final_obj_edge > 0), 50, obj_mask.shape)
        crop_rgb = rgb[y0:y1, x0:x1]
        crop_signal = signal[y0:y1, x0:x1]
        crop_search = obj_search[y0:y1, x0:x1]
        crop_evidence = edge_evidence[y0:y1, x0:x1]
        crop_final = final_obj_edge[y0:y1, x0:x1]

        tr.save_rgb(obj_dir / 'step40_crop_rgb.png', crop_rgb)
        tr.save_gray(obj_dir / 'step41_crop_signal.png', crop_signal)
        tr.save_binary(obj_dir / 'step42_object_mask.png', obj_mask[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step43_object_boundary.png', obj_boundary[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step44_object_search_band.png', crop_search)
        tr.save_gray(obj_dir / 'step45_object_evidence.png', crop_evidence)
        tr.save_binary(obj_dir / 'step46_seed_high.png', seed_high[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step47_seed_canny_support.png', seed_canny[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step48_candidate_raw.png', raw[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step49_candidate_closed.png', closed[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step50_candidate_filtered.png', kept_region[y0:y1, x0:x1])
        tr.save_binary(obj_dir / 'step51_final_object_edge.png', crop_final)
        save_crop(obj_dir / 'step52_object_overlay.png', crop_rgb, obj_mask[y0:y1, x0:x1], crop_final)
        write_csv(obj_dir / 'step53_component_table.csv', comp_rows)

        edge_pixels = int((final_obj_edge > 0).sum())
        boundary_cover = float(
            np.mean(
                cv2.dilate(final_obj_edge, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))[obj_boundary] > 0
            )
        ) if obj_boundary.any() else 0.0
        row = {
            'object_label': label,
            'object_area_px': int(obj_mask.sum()),
            'local_high_threshold': local_high,
            'local_low_threshold': local_low,
            'kept_component_count': kept_components,
            'fallback_used': fallback_used,
            'final_edge_pixels': edge_pixels,
            'boundary_coverage_ratio': boundary_cover,
            'mean_final_edge_evidence': float(edge_evidence[final_obj_edge > 0].mean()) if edge_pixels else 0.0,
        }
        object_rows.append(row)
        object_tiles.append(make_contact_tile(rgb, obj_mask, final_obj_edge, f'obj {label}\nedge_px={edge_pixels}\nkeep={kept_components} fb={int(fallback_used)}'))
        write_json(obj_dir / 'step54_object_summary.json', row)

    write_csv(step05 / 'step55_object_summary_table.csv', object_rows)
    write_json(step05 / 'step55_object_summary_table.json', object_rows)
    if object_tiles:
        tr.save_contact_sheet(step05 / 'step56_object_contact_sheet.png', object_tiles, cols=3)
    tr.save_binary(step05 / 'step57_combined_edge_mask.png', final_edge)
    save_crop(step05 / 'step58_combined_edge_overlay.png', rgb, union_mask, final_edge)

    final_overlay = rgb.copy()
    mask_boundary = cv2.Canny(union_u8 * 255, 50, 150) > 0
    final_overlay[mask_boundary] = (0, 255, 0)
    final_overlay[final_edge > 0] = (255, 0, 0)
    tr.save_binary(step06 / 'step60_final_edge_mask.png', final_edge)
    tr.save_rgb(step06 / 'step61_final_edge_overlay.png', final_overlay)
    tr.save_rgb(step06 / 'step62_final_edge_only_overlay.png', np.where(final_edge[..., None] > 0, np.array([255, 255, 255], dtype=np.uint8), rgb))

    summary = {
        'algorithm': ALGO_NAME,
        'source_tif': str(source_tif),
        'label_mask': str(label_mask_path),
        'object_count': int(labels.max()),
        'global_high_threshold': high_thr,
        'global_low_threshold': low_thr,
        'final_edge_pixels_total': int((final_edge > 0).sum()),
        'objects': object_rows,
    }
    write_json(step06 / 'step63_edge_trace_summary.json', summary)
    write_json(out_dir / 'trace_manifest.json', {
        'algorithm': ALGO_NAME,
        'source_tif': str(source_tif),
        'label_mask': str(label_mask_path),
        'out_dir': str(out_dir),
        'step_dirs': [
            'step01_input',
            'step02_edge_evidence',
            'step03_search_band',
            'step04_global_edge_candidates',
            'step05_instance_refinement',
            'step06_final',
        ],
    })

    gallery = [
        cv2.resize(rgb, (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor(tr.norm_u8(edge_evidence), cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(cv2.cvtColor((search_band.astype(np.uint8) * 255), cv2.COLOR_GRAY2RGB), (480, 340), interpolation=cv2.INTER_AREA),
        cv2.resize(final_overlay, (480, 340), interpolation=cv2.INTER_AREA),
    ]
    titles = ['step01 source', 'step21 edge evidence', 'step26 search band', 'step61 final edge overlay']
    panels = []
    for title, tile in zip(titles, gallery):
        canvas = np.full((380, 480, 3), 255, dtype=np.uint8)
        cv2.putText(canvas, title, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
        canvas[40:40 + tile.shape[0], :tile.shape[1]] = tile
        panels.append(canvas)
    tr.save_rgb(out_dir / 'edge_trace_overview_gallery.png', np.concatenate([
        np.concatenate(panels[:2], axis=1),
        np.full((16, 960, 3), 255, dtype=np.uint8),
        np.concatenate(panels[2:], axis=1)
    ], axis=0))
    print(out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
