#!/usr/bin/env python3
from __future__ import annotations

import csv
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

METRIC_CSVS = {
    'app81': {
        'csv': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1/profiling/quantification/per_image_metrics.csv'),
        'group_field': 'condition',
    },
    'app65': {
        'csv': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_v3_direct_brightfield/profiling/quantification/per_image_metrics.csv'),
        'group_field': 'condition',
    },
    'app80': {
        'csv': Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv'),
        'group_field': 'concentration',
    },
}

APP81_ARCHIVED_EXPORTS = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_cellpose_v5_final_single_exports_v2')


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def copy_full_overlays() -> dict[str, object]:
    root = DOC_ROOT / 'segmentation_overlays_full_by_dataset'
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    copied_counts: dict[str, int] = {}
    for dataset, spec in METRIC_CSVS.items():
        csv_path = spec['csv']
        group_field = spec['group_field']
        dataset_root = root / dataset
        dataset_root.mkdir(parents=True, exist_ok=True)
        count = 0
        with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                overlay = row.get('overlay_path', '').strip()
                if not overlay:
                    continue
                src = Path(overlay)
                if not src.exists():
                    continue
                group = row.get(group_field, 'unknown').strip() or 'unknown'
                date_key = row.get('date_key', 'unknown_date').strip() or 'unknown_date'
                dst_dir = dataset_root / group / date_key
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst_dir / src.name)
                count += 1
        copied_counts[dataset] = count

    # App81 final overlays are preserved in the archived stitched single-export tree.
    # Flatten the last "from_*" folder into the filename to avoid one extra nesting level.
    app81_root = root / 'app81'
    if app81_root.exists():
        shutil.rmtree(app81_root)
    app81_root.mkdir(parents=True, exist_ok=True)
    app81_count = 0
    if APP81_ARCHIVED_EXPORTS.exists():
        for src in APP81_ARCHIVED_EXPORTS.glob('*/*/from_*/overlay.png'):
            date_dir = src.parents[2].name
            image_dir = src.parents[1].name
            from_dir = src.parents[0].name
            dst_dir = app81_root / date_dir / image_dir
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst_name = f'{from_dir}_overlay.png'
            shutil.copy2(src, dst_dir / dst_name)
            app81_count += 1
    copied_counts['app81'] = app81_count
    return {
        'root': str(root),
        'counts': copied_counts,
    }


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

    full_overlay_info = copy_full_overlays()

    manifest = {
        'documents_root': str(DOC_ROOT),
        'copied_dirs': copied,
        'overlay_src': str(OVERLAY_SRC),
        'overlay_dst': str(overlay_dst),
        'overlay_count': overlay_count,
        'full_overlays': full_overlay_info,
    }
    (DOC_ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
