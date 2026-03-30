#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import run_multiscale_dateaware_cellpose as seg  # noqa: E402
import run_app80_10uM_all_replicates_large_recovery as batch  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--runs-root', required=True)
    return p.parse_args()


def source_tif_for_mask(mask_path: Path) -> Path:
    stem = mask_path.name.removesuffix('_mask_16bit.png')
    metric_path = mask_path.with_name(f'{stem}_metrics.json')
    stats_path = mask_path.with_name(f'{stem}_segmentation_stats.json')
    for meta in (metric_path, stats_path):
        if meta.exists():
            data = json.loads(meta.read_text(encoding='utf-8'))
            src = data.get('source_tif')
            if src:
                return Path(src)
    raise RuntimeError(f'No source_tif metadata found for {mask_path}')


def main() -> int:
    args = parse_args()
    runs_root = Path(args.runs_root).resolve()
    mask_paths = sorted(runs_root.rglob('*_mask_16bit.png'))
    if not mask_paths:
        raise SystemExit(f'No *_mask_16bit.png found under {runs_root}')

    done = 0
    for mask_path in mask_paths:
        stem = mask_path.name.removesuffix('_mask_16bit.png')
        rgb_path = mask_path.with_name(f'{stem}_instance_rgb.png')
        overlay_path = mask_path.with_name(f'{stem}_overlay.png')
        if rgb_path.exists() and overlay_path.exists():
            continue

        source_tif = source_tif_for_mask(mask_path)
        source_rgb, _ = seg.load_rgb_gray(source_tif)
        label_mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        if label_mask is None:
            raise RuntimeError(f'Failed to read {mask_path}')
        color_mask = batch.render_instance_rgb(label_mask)
        overlay = batch.render_overlay(source_rgb, label_mask, color_mask)
        cv2.imwrite(str(rgb_path), cv2.cvtColor(color_mask, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        done += 1
        print(f'backfilled {rgb_path.name}')

    print(f'created {done} render pairs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
