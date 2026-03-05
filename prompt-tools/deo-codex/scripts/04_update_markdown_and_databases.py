#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def parse_path_metadata(source_tif: Path, deo_root: Path) -> Dict[str, str]:
    rel = source_tif.relative_to(deo_root)
    parts = rel.parts

    experiment_folder = parts[0] if len(parts) > 0 else ''
    concentration_label = parts[1] if len(parts) > 1 else ''
    date_label = parts[2] if len(parts) > 2 else ''
    filename = source_tif.stem

    mag = ''
    sample = ''
    m = re.search(r'(?i)(\d+x)(\d+)', filename)
    if m:
        mag = m.group(1).lower()
        sample = m.group(2)

    concentration_value_um = ''
    if concentration_label.lower().endswith('um'):
        v = concentration_label[:-2]
        if v.isdigit():
            concentration_value_um = v
    elif concentration_label.lower() == 'no':
        concentration_value_um = '0'

    experiment_id = 'unknown'
    major_figure = 'unknown'
    part = 'single'

    if experiment_folder == 'App80 DEO':
        experiment_id = 'app80_y27632'
        major_figure = 'y27632'
    elif experiment_folder == 'App65 DEO+Alginate':
        experiment_id = 'app65_alginate'
        major_figure = 'alginate'
    elif experiment_folder == 'DEO App81 P8':
        experiment_id = 'app81_density_A'
        major_figure = 'density'
        part = 'A'
    elif experiment_folder == 'DEO test 2025.10.1':
        experiment_id = 'test2025_density_B'
        major_figure = 'density'
        part = 'B'

    return {
        'relative_path': str(rel),
        'experiment_folder': experiment_folder,
        'experiment_id': experiment_id,
        'major_figure': major_figure,
        'part': part,
        'concentration_label': concentration_label,
        'concentration_value_uM': concentration_value_um,
        'date_label': date_label,
        'magnification_token': mag,
        'sample_token': sample,
        'image_name': source_tif.stem,
    }


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


def build_markdown(
    source_tif: Path,
    source_png: Path,
    path_meta: Dict[str, str],
    ann: Dict,
    quant: Dict,
    seg_manifest: Dict,
    tif_meta: Dict,
) -> str:
    droplets_by_id = {int(d['droplet_id']): d for d in ann.get('droplets', [])}
    quant_by_id = {int(d['droplet_id']): d for d in quant.get('droplets', [])}
    seg_by_id = {int(d['droplet_id']): d for d in seg_manifest.get('segments', [])}

    lines = []
    lines.append(f"# Image Analysis - {path_meta['image_name']}")
    lines.append('')
    lines.append('## Source')
    lines.append(f"- TIFF: `{source_tif}`")
    lines.append(f"- PNG: `{source_png}`")
    lines.append('')
    lines.append('## Parsed Metadata')
    lines.append(f"- experiment_id: `{path_meta['experiment_id']}`")
    lines.append(f"- major_figure: `{path_meta['major_figure']}`")
    lines.append(f"- part: `{path_meta['part']}`")
    lines.append(f"- concentration_label: `{path_meta['concentration_label']}`")
    lines.append(f"- concentration_value_uM: `{path_meta['concentration_value_uM']}`")
    lines.append(f"- date_label: `{path_meta['date_label']}`")
    lines.append(f"- magnification_token: `{path_meta['magnification_token']}`")
    lines.append(f"- sample_token: `{path_meta['sample_token']}`")
    lines.append('')

    isummary = quant.get('image_level', {})
    lines.append('## Image-level Quantification')
    lines.append(f"- droplet_count_clear: `{isummary.get('droplet_count_clear', '')}`")
    lines.append(f"- droplet_count_including_partials: `{isummary.get('droplet_count_including_partials', '')}`")
    lines.append(f"- analyst_note: {isummary.get('analyst_note', '')}")
    lines.append('')

    lines.append('## Droplet-level Table')
    lines.append('')
    lines.append('| droplet_id | center_x | center_y | radius | partial | organoid_count_estimated | fusion_level_0_to_5 | confidence | segment_png |')
    lines.append('|---:|---:|---:|---:|:---:|---:|---:|---:|---|')
    for did in sorted(droplets_by_id.keys()):
        a = droplets_by_id[did]
        q = quant_by_id.get(did, {})
        s = seg_by_id.get(did, {})
        lines.append(
            f"| {did} | {a.get('center_x_px', '')} | {a.get('center_y_px', '')} | {a.get('radius_px', '')} | {a.get('is_partial', '')} | {q.get('organoid_count_estimated', a.get('initial_organoid_count_estimate', ''))} | {q.get('fusion_level_0_to_5', a.get('initial_fusion_level_0_to_5', ''))} | {q.get('confidence', a.get('confidence', ''))} | `{s.get('segment_png', '')}` |"
        )
    lines.append('')

    lines.append('## TIFF Metadata (partial)')
    tags = tif_meta.get('tags', {}) if isinstance(tif_meta, dict) else {}
    lines.append(f"- shape: `{tif_meta.get('shape', '')}`")
    lines.append(f"- dtype: `{tif_meta.get('dtype', '')}`")
    lines.append(f"- page_count: `{tif_meta.get('page_count', '')}`")
    lines.append(f"- has_ImageDescription: `{str('ImageDescription' in tags)}`")
    lines.append(f"- has_XResolution: `{str('XResolution' in tags)}`")
    lines.append(f"- has_YResolution: `{str('YResolution' in tags)}`")
    lines.append('')

    lines.append('## Method Notes')
    lines.append('- Droplet geometry is from vision-first prompt annotation (no threshold/cellpose used).')
    lines.append('- Segments are circular crops generated from annotated droplet circles.')
    lines.append('- Organoid-level DB rows are count-derived placeholders (no organoid segmentation in this step).')
    lines.append('')

    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Update per-image markdown and DEO databases from prompt tool outputs.')
    parser.add_argument('--source-tif', required=True)
    parser.add_argument('--source-png', required=True)
    parser.add_argument('--annotation-json', required=True)
    parser.add_argument('--quant-json', required=True)
    parser.add_argument('--segment-manifest-json', required=True)
    parser.add_argument('--tif-meta-json', default='')
    parser.add_argument('--deo-root', default='DEO')
    parser.add_argument('--markdown-root', default='DEO-MARKDOWN')
    parser.add_argument('--db-root', default='DEO-DATABASE')
    args = parser.parse_args()

    source_tif = Path(args.source_tif).resolve()
    source_png = Path(args.source_png).resolve()
    deo_root = Path(args.deo_root).resolve()
    markdown_root = Path(args.markdown_root).resolve()
    db_root = Path(args.db_root).resolve()

    ann = json.loads(Path(args.annotation_json).read_text(encoding='utf-8'))
    quant = json.loads(Path(args.quant_json).read_text(encoding='utf-8'))
    seg_manifest = json.loads(Path(args.segment_manifest_json).read_text(encoding='utf-8'))
    tif_meta = {}
    if args.tif_meta_json and Path(args.tif_meta_json).exists():
        tif_meta = json.loads(Path(args.tif_meta_json).read_text(encoding='utf-8'))

    path_meta = parse_path_metadata(source_tif, deo_root)

    rel_parent = source_tif.relative_to(deo_root).parent
    img_name = source_tif.stem
    md_dir = markdown_root / rel_parent / img_name
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f'{img_name}.md'

    md_text = build_markdown(source_tif, source_png, path_meta, ann, quant, seg_manifest, tif_meta)
    md_path.write_text(md_text, encoding='utf-8')

    now = datetime.utcnow().isoformat() + 'Z'

    image_row = {
        'source_tif': str(source_tif),
        'source_png': str(source_png),
        'relative_path': path_meta['relative_path'],
        'experiment_id': path_meta['experiment_id'],
        'major_figure': path_meta['major_figure'],
        'part': path_meta['part'],
        'concentration_label': path_meta['concentration_label'],
        'concentration_value_uM': path_meta['concentration_value_uM'],
        'date_label': path_meta['date_label'],
        'magnification_token': path_meta['magnification_token'],
        'sample_token': path_meta['sample_token'],
        'droplet_count_clear': str(quant.get('image_level', {}).get('droplet_count_clear', '')),
        'droplet_count_including_partials': str(quant.get('image_level', {}).get('droplet_count_including_partials', '')),
        'analyst_note': quant.get('image_level', {}).get('analyst_note', ''),
        'markdown_path': str(md_path),
        'updated_at_utc': now,
    }

    ann_by_id = {int(d['droplet_id']): d for d in ann.get('droplets', [])}
    quant_by_id = {int(d['droplet_id']): d for d in quant.get('droplets', [])}
    seg_by_id = {int(d['droplet_id']): d for d in seg_manifest.get('segments', [])}

    droplet_rows = []
    organoid_rows = []

    for did in sorted(ann_by_id.keys()):
        a = ann_by_id[did]
        q = quant_by_id.get(did, {})
        s = seg_by_id.get(did, {})
        organoid_count = int(q.get('organoid_count_estimated', a.get('initial_organoid_count_estimate', 0)))
        fusion = float(q.get('fusion_level_0_to_5', a.get('initial_fusion_level_0_to_5', 0)))
        conf = float(q.get('confidence', a.get('confidence', 0)))

        droplet_rows.append({
            'source_tif': str(source_tif),
            'droplet_id': str(did),
            'center_x_px': str(a.get('center_x_px', '')),
            'center_y_px': str(a.get('center_y_px', '')),
            'radius_px': str(a.get('radius_px', '')),
            'is_partial': str(a.get('is_partial', '')),
            'bbox_x0': str(s.get('bbox_x0', '')),
            'bbox_y0': str(s.get('bbox_y0', '')),
            'bbox_x1': str(s.get('bbox_x1', '')),
            'bbox_y1': str(s.get('bbox_y1', '')),
            'segment_png': str(s.get('segment_png', '')),
            'organoid_count_estimated': str(organoid_count),
            'fusion_level_0_to_5': str(fusion),
            'confidence': str(conf),
            'quant_note': q.get('quant_note', a.get('note', '')),
            'updated_at_utc': now,
        })

        for idx in range(1, organoid_count + 1):
            organoid_rows.append({
                'source_tif': str(source_tif),
                'droplet_id': str(did),
                'organoid_id_in_droplet': str(idx),
                'position_x_px': '',
                'position_y_px': '',
                'size_px': '',
                'estimation_mode': 'droplet_visual_count_placeholder',
                'updated_at_utc': now,
            })

    image_csv = db_root / 'image_database.csv'
    droplet_csv = db_root / 'droplet_database.csv'
    organoid_csv = db_root / 'organoid_database.csv'

    image_cols = list(image_row.keys())
    droplet_cols = [
        'source_tif', 'droplet_id', 'center_x_px', 'center_y_px', 'radius_px', 'is_partial',
        'bbox_x0', 'bbox_y0', 'bbox_x1', 'bbox_y1', 'segment_png',
        'organoid_count_estimated', 'fusion_level_0_to_5', 'confidence', 'quant_note', 'updated_at_utc'
    ]
    organoid_cols = [
        'source_tif', 'droplet_id', 'organoid_id_in_droplet', 'position_x_px',
        'position_y_px', 'size_px', 'estimation_mode', 'updated_at_utc'
    ]

    existing_images = [r for r in read_csv_rows(image_csv) if r.get('source_tif') != str(source_tif)]
    existing_images.append(image_row)
    write_csv_rows(image_csv, existing_images, image_cols)

    existing_droplets = [r for r in read_csv_rows(droplet_csv) if r.get('source_tif') != str(source_tif)]
    existing_droplets.extend(droplet_rows)
    write_csv_rows(droplet_csv, existing_droplets, droplet_cols)

    existing_organoids = [r for r in read_csv_rows(organoid_csv) if r.get('source_tif') != str(source_tif)]
    existing_organoids.extend(organoid_rows)
    write_csv_rows(organoid_csv, existing_organoids, organoid_cols)

    print(json.dumps({
        'markdown_path': str(md_path),
        'image_database_csv': str(image_csv),
        'droplet_database_csv': str(droplet_csv),
        'organoid_database_csv': str(organoid_csv),
        'droplet_rows_written': len(droplet_rows),
        'organoid_rows_written': len(organoid_rows),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
