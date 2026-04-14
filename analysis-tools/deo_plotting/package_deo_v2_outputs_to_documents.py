#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path


DOC_ROOT = Path('/home/lachlan/Documents/Zhengyu/deo_all_outputs_v2_2026-04-14')

SOURCE_DIRS = {
    'app81_figures_guided_v2': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1/figures-guided-v2'),
    'app81_figures_polished_guided_v2': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1/figures-polished-guided-v2'),
    'app65_figures_guided_v2': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_v3_direct_brightfield/figures-guided-v2'),
    'app65_figures_polished_guided_v2': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_v3_direct_brightfield/figures-polished-guided-v2'),
    'app80_figures_guided_v2': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures-guided-v2'),
    'app80_figures_polished_guided_v2': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures-polished-guided-v2'),
}

OVERLAY_SRC = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_cellpose_v5_final_selected_overlays_v1_compressed_review_v1/overlays')


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> None:
    DOC_ROOT.mkdir(parents=True, exist_ok=True)
    copied = {}
    for label, src in SOURCE_DIRS.items():
        if not src.exists():
            raise SystemExit(f'Missing source directory: {src}')
        dst = DOC_ROOT / label
        copy_tree(src, dst)
        copied[label] = str(dst)

    overlay_dst = DOC_ROOT / 'segmentation_overlays_small_flat'
    if overlay_dst.exists():
        shutil.rmtree(overlay_dst)
    overlay_dst.mkdir(parents=True, exist_ok=True)
    overlay_count = 0
    for src in sorted(OVERLAY_SRC.iterdir()):
        if src.is_file():
            shutil.copy2(src, overlay_dst / src.name)
            overlay_count += 1

    manifest = {
        'documents_root': str(DOC_ROOT),
        'copied_dirs': copied,
        'overlay_src': str(OVERLAY_SRC),
        'overlay_dst': str(overlay_dst),
        'overlay_count': overlay_count,
    }
    (DOC_ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
