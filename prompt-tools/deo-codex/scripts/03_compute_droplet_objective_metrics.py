#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image


def connected_components(binary: np.ndarray, min_size: int = 12) -> List[Dict[str, float]]:
    h, w = binary.shape
    visited = np.zeros_like(binary, dtype=bool)
    comps: List[Dict[str, float]] = []

    for y in range(h):
        for x in range(w):
            if not binary[y, x] or visited[y, x]:
                continue
            stack = [(x, y)]
            visited[y, x] = True
            pixels = []
            while stack:
                cx, cy = stack.pop()
                pixels.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < w and 0 <= ny < h and binary[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((nx, ny))

            area = len(pixels)
            if area < min_size:
                continue

            xs = np.array([p[0] for p in pixels], dtype=float)
            ys = np.array([p[1] for p in pixels], dtype=float)
            cx = float(xs.mean())
            cy = float(ys.mean())
            eq_radius = float(math.sqrt(area / math.pi))
            comps.append({
                'area_px': float(area),
                'centroid_x_px': cx,
                'centroid_y_px': cy,
                'equivalent_radius_px': eq_radius,
            })

    return comps


def compute_metrics(segment_png: Path) -> Dict:
    im = Image.open(segment_png).convert('RGBA')
    arr = np.array(im).astype(np.float32)
    alpha = arr[:, :, 3] > 0

    if not np.any(alpha):
        return {
            'segment_png': str(segment_png),
            'pixel_count_mask': 0,
            'gray_mean': 0.0,
            'gray_std': 0.0,
            'gradient_mean': 0.0,
            'gradient_p90': 0.0,
            'edge_density_p75': 0.0,
            'dark_mass_norm': 0.0,
            'dark_centroid_x_px': None,
            'dark_centroid_y_px': None,
            'dark_component_count': 0,
            'largest_dark_component_area_px': 0.0,
            'fusion_score_objective_0_to_5': 0.0,
            'organoid_candidates_objective': [],
        }

    rgb = arr[:, :, :3]
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

    gvals = gray[alpha]
    gray_mean = float(gvals.mean())
    gray_std = float(gvals.std())

    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx * gx + gy * gy)
    grad_vals = grad[alpha]
    gradient_mean = float(grad_vals.mean())
    gradient_p90 = float(np.percentile(grad_vals, 90))
    edge_thr = float(np.percentile(grad_vals, 75))
    edge_density = float((grad_vals > edge_thr).mean())

    dark_weight = np.clip(gray_mean - gray, 0, None)
    dark_vals = dark_weight[alpha]
    dark_mass_norm = float(dark_vals.sum() / max(len(dark_vals) * 255.0, 1.0))

    ys, xs = np.indices(gray.shape)
    weights = dark_weight * alpha.astype(np.float32)
    wsum = float(weights.sum())
    if wsum > 1e-6:
        dark_cx = float((weights * xs).sum() / wsum)
        dark_cy = float((weights * ys).sum() / wsum)
    else:
        dark_cx = None
        dark_cy = None

    # Objective candidate organoid map from dark-weight threshold
    thr = float(np.percentile(dark_vals, 78))
    binary = (dark_weight >= thr) & alpha
    comps = connected_components(binary, min_size=14)
    comp_count = len(comps)
    largest = max((c['area_px'] for c in comps), default=0.0)

    # Fusion objective score (heuristic): more dark mass + fewer separated dark components => higher fusion
    comp_compactness = 1.0 - min(comp_count, 20) / 20.0
    fusion_obj = 5.0 * (0.45 * dark_mass_norm + 0.35 * comp_compactness + 0.20 * edge_density)
    fusion_obj = float(max(0.0, min(5.0, fusion_obj)))

    return {
        'segment_png': str(segment_png),
        'pixel_count_mask': int(alpha.sum()),
        'gray_mean': gray_mean,
        'gray_std': gray_std,
        'gradient_mean': gradient_mean,
        'gradient_p90': gradient_p90,
        'edge_density_p75': edge_density,
        'dark_mass_norm': dark_mass_norm,
        'dark_centroid_x_px': dark_cx,
        'dark_centroid_y_px': dark_cy,
        'dark_component_count': comp_count,
        'largest_dark_component_area_px': float(largest),
        'fusion_score_objective_0_to_5': fusion_obj,
        'organoid_candidates_objective': comps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Compute objective droplet visual metrics and fusion heuristic scores.')
    parser.add_argument('--segment-manifest-json', required=True)
    parser.add_argument('--out-json', required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.segment_manifest_json).read_text(encoding='utf-8'))
    out_path = Path(args.out_json).resolve()

    rows = []
    for seg in manifest.get('segments', []):
        m = compute_metrics(Path(seg['segment_png']))
        m['droplet_id'] = int(seg['droplet_id'])
        rows.append(m)

    payload = {
        'segment_manifest_json': str(Path(args.segment_manifest_json).resolve()),
        'droplets': sorted(rows, key=lambda r: r['droplet_id']),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
