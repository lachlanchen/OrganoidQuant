#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


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


def load_objective_metrics(path: Optional[Path]) -> Dict[int, Dict]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    out = {}
    for d in payload.get('droplets', []):
        out[int(d['droplet_id'])] = d
    return out


def load_organoid_outputs(organoid_dir: Optional[Path]) -> Dict[int, Dict]:
    if not organoid_dir or not organoid_dir.exists():
        return {}
    out: Dict[int, Dict] = {}
    for p in sorted(organoid_dir.glob('droplet_*_organoids.json')):
        try:
            obj = json.loads(p.read_text(encoding='utf-8'))
            out[int(obj['droplet_id'])] = obj
        except Exception:
            continue
    return out


def combine_fusion(prompt_val: Optional[float], objective_val: Optional[float]) -> Optional[float]:
    if prompt_val is None and objective_val is None:
        return None
    if prompt_val is None:
        return objective_val
    if objective_val is None:
        return prompt_val
    return round(0.6 * prompt_val + 0.4 * objective_val, 4)


def build_markdown(
    source_tif: Path,
    source_png: Path,
    path_meta: Dict[str, str],
    ann: Dict,
    quant: Dict,
    seg_manifest: Dict,
    tif_meta: Dict,
    obj_by_id: Dict[int, Dict],
    org_by_id: Dict[int, Dict],
    refine_report: Optional[Dict],
    edgeopt_report: Optional[Dict],
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
    for k in ['experiment_id', 'major_figure', 'part', 'concentration_label', 'concentration_value_uM', 'date_label', 'magnification_token', 'sample_token']:
        lines.append(f"- {k}: `{path_meta[k]}`")
    lines.append('')

    isummary = quant.get('image_level', {})
    lines.append('## Image-level Quantification')
    lines.append(f"- droplet_count_clear: `{isummary.get('droplet_count_clear', '')}`")
    lines.append(f"- droplet_count_including_partials: `{isummary.get('droplet_count_including_partials', '')}`")
    lines.append(f"- analyst_note: {isummary.get('analyst_note', '')}")
    lines.append('')

    if refine_report:
        lines.append('## Annotation Refinement')
        lines.append(f"- input_droplet_count: `{refine_report.get('input_droplet_count', '')}`")
        lines.append(f"- output_droplet_count: `{refine_report.get('output_droplet_count', '')}`")
        lines.append(f"- removed_duplicates: `{len(refine_report.get('removed_duplicates', []))}`")
        if edgeopt_report:
            lines.append(f"- edge_optimized_circles: `{edgeopt_report.get('optimized_count', 0)}`")
        lines.append('')

    lines.append('## Droplet-level Table')
    lines.append('')
    lines.append('| droplet_id | completeness | position | center_x | center_y | radius | prompt_organoid_count | fusion_prompt | fusion_objective | fusion_combined | confidence | segment_png |')
    lines.append('|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|')

    for did in sorted(droplets_by_id.keys()):
        a = droplets_by_id[did]
        q = quant_by_id.get(did, {})
        s = seg_by_id.get(did, {})
        o = obj_by_id.get(did, {})

        prompt_f = q.get('fusion_level_0_to_5', a.get('initial_fusion_level_0_to_5'))
        prompt_f = float(prompt_f) if prompt_f is not None else None
        obj_f = o.get('fusion_score_objective_0_to_5')
        obj_f = float(obj_f) if obj_f is not None else None
        comb_f = combine_fusion(prompt_f, obj_f)

        lines.append(
            f"| {did} | {bool(a.get('completeness', not a.get('is_partial', False)))} | {a.get('position_label', '')} | {a.get('center_x_px', '')} | {a.get('center_y_px', '')} | {a.get('radius_px', '')} | {q.get('organoid_count_estimated', a.get('initial_organoid_count_estimate', ''))} | {'' if prompt_f is None else prompt_f} | {'' if obj_f is None else round(obj_f, 4)} | {'' if comb_f is None else round(comb_f, 4)} | {q.get('confidence', a.get('confidence', ''))} | `{s.get('segment_png', '')}` |"
        )
    lines.append('')

    lines.append('## Complete-droplet Organoid Analysis')
    lines.append('')
    lines.append('| droplet_id | analyzed | organoid_count_visual | note |')
    lines.append('|---:|:---:|---:|---|')
    for did in sorted(droplets_by_id.keys()):
        a = droplets_by_id[did]
        complete = bool(a.get('completeness', not a.get('is_partial', False)))
        rec = org_by_id.get(did)
        if not complete:
            lines.append(f"| {did} | false |  | partial droplet skipped |")
        elif rec:
            lines.append(f"| {did} | true | {rec.get('organoid_count_visual', '')} | {rec.get('droplet_quality_note', '')} |")
        else:
            lines.append(f"| {did} | false |  | complete droplet but no organoid json found |")
    lines.append('')

    lines.append('## TIFF Metadata (partial)')
    tags = tif_meta.get('tags', {}) if isinstance(tif_meta, dict) else {}
    lines.append(f"- shape: `{tif_meta.get('shape', '')}`")
    lines.append(f"- dtype: `{tif_meta.get('dtype', '')}`")
    lines.append(f"- page_count: `{tif_meta.get('page_count', '')}`")
    lines.append(f"- has_ImageDescription: `{str('ImageDescription' in tags)}`")
    lines.append('')

    lines.append('## Method Notes')
    lines.append('- Droplet geometry is vision-first prompt annotation, then refined to remove duplicate partial circles.')
    lines.append('- Droplet segmentation uses annotated circles only (no threshold/cellpose for droplet boundary).')
    lines.append('- Fusion uses dual sources: prompt-visual + objective image metrics.')
    lines.append('- Organoid-level records are generated only for complete droplets in this version.')
    lines.append('')

    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Update per-image markdown and DEO databases from prompt tools + objective metrics.')
    parser.add_argument('--source-tif', required=True)
    parser.add_argument('--source-png', required=True)
    parser.add_argument('--annotation-json', required=True)
    parser.add_argument('--quant-json', required=True)
    parser.add_argument('--segment-manifest-json', required=True)
    parser.add_argument('--tif-meta-json', default='')
    parser.add_argument('--objective-metrics-json', default='')
    parser.add_argument('--organoid-analysis-dir', default='')
    parser.add_argument('--annotation-refine-report-json', default='')
    parser.add_argument('--annotation-edgeopt-report-json', default='')
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

    obj_by_id = load_objective_metrics(Path(args.objective_metrics_json)) if args.objective_metrics_json else {}
    org_by_id = load_organoid_outputs(Path(args.organoid_analysis_dir)) if args.organoid_analysis_dir else {}
    refine_report = None
    if args.annotation_refine_report_json and Path(args.annotation_refine_report_json).exists():
        refine_report = json.loads(Path(args.annotation_refine_report_json).read_text(encoding='utf-8'))
    edgeopt_report = None
    if args.annotation_edgeopt_report_json and Path(args.annotation_edgeopt_report_json).exists():
        edgeopt_report = json.loads(Path(args.annotation_edgeopt_report_json).read_text(encoding='utf-8'))

    path_meta = parse_path_metadata(source_tif, deo_root)

    rel_parent = source_tif.relative_to(deo_root).parent
    img_name = source_tif.stem
    md_dir = markdown_root / rel_parent / img_name
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f'{img_name}.md'

    md_text = build_markdown(
        source_tif, source_png, path_meta, ann, quant, seg_manifest, tif_meta,
        obj_by_id=obj_by_id, org_by_id=org_by_id, refine_report=refine_report, edgeopt_report=edgeopt_report,
    )
    md_path.write_text(md_text, encoding='utf-8')

    now = datetime.utcnow().isoformat() + 'Z'

    ann_by_id = {int(d['droplet_id']): d for d in ann.get('droplets', [])}
    quant_by_id = {int(d['droplet_id']): d for d in quant.get('droplets', [])}
    seg_by_id = {int(d['droplet_id']): d for d in seg_manifest.get('segments', [])}

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
        'objective_metrics_available': str(bool(obj_by_id)),
        'organoid_analysis_available': str(bool(org_by_id)),
        'markdown_path': str(md_path),
        'updated_at_utc': now,
    }

    droplet_rows = []
    organoid_rows = []

    for did in sorted(ann_by_id.keys()):
        a = ann_by_id[did]
        q = quant_by_id.get(did, {})
        s = seg_by_id.get(did, {})
        o = obj_by_id.get(did, {})
        org = org_by_id.get(did)

        prompt_f = q.get('fusion_level_0_to_5', a.get('initial_fusion_level_0_to_5'))
        prompt_f = float(prompt_f) if prompt_f is not None else None
        obj_f = o.get('fusion_score_objective_0_to_5')
        obj_f = float(obj_f) if obj_f is not None else None
        comb_f = combine_fusion(prompt_f, obj_f)

        complete = bool(a.get('completeness', not a.get('is_partial', False)))

        droplet_rows.append({
            'source_tif': str(source_tif),
            'droplet_id': str(did),
            'completeness': str(complete),
            'position_label': str(a.get('position_label', '')),
            'center_x_px': str(a.get('center_x_px', '')),
            'center_y_px': str(a.get('center_y_px', '')),
            'radius_px': str(a.get('radius_px', '')),
            'is_partial': str(a.get('is_partial', '')),
            'bbox_x0': str(s.get('bbox_x0', '')),
            'bbox_y0': str(s.get('bbox_y0', '')),
            'bbox_x1': str(s.get('bbox_x1', '')),
            'bbox_y1': str(s.get('bbox_y1', '')),
            'segment_png': str(s.get('segment_png', '')),
            'organoid_count_prompt_estimated': str(q.get('organoid_count_estimated', a.get('initial_organoid_count_estimate', ''))),
            'organoid_count_visual_complete_droplet': str(org.get('organoid_count_visual', '') if org else ''),
            'fusion_score_prompt_0_to_5': '' if prompt_f is None else str(prompt_f),
            'fusion_score_objective_0_to_5': '' if obj_f is None else str(obj_f),
            'fusion_score_combined_0_to_5': '' if comb_f is None else str(comb_f),
            'confidence_prompt': str(q.get('confidence', a.get('confidence', ''))),
            'gray_mean': str(o.get('gray_mean', '')),
            'gray_std': str(o.get('gray_std', '')),
            'gradient_mean': str(o.get('gradient_mean', '')),
            'edge_density_p75': str(o.get('edge_density_p75', '')),
            'dark_component_count': str(o.get('dark_component_count', '')),
            'dark_centroid_x_px': str(o.get('dark_centroid_x_px', '')),
            'dark_centroid_y_px': str(o.get('dark_centroid_y_px', '')),
            'quant_note': q.get('quant_note', a.get('note', '')),
            'updated_at_utc': now,
        })

        # Only build organoid rows for complete droplets with dedicated organoid analysis output.
        if complete and org:
            for item in org.get('organoids', []):
                local_x = float(item.get('center_x_px_local', 0.0))
                local_y = float(item.get('center_y_px_local', 0.0))
                sx0 = float(s.get('bbox_x0', 0.0))
                sy0 = float(s.get('bbox_y0', 0.0))
                organoid_rows.append({
                    'source_tif': str(source_tif),
                    'droplet_id': str(did),
                    'organoid_id_in_droplet': str(item.get('organoid_id_local', '')),
                    'position_x_px_local': str(local_x),
                    'position_y_px_local': str(local_y),
                    'position_x_px_source': str(local_x + sx0),
                    'position_y_px_source': str(local_y + sy0),
                    'radius_px_local': str(item.get('radius_px_local', '')),
                    'size_class': str(item.get('size_class', '')),
                    'morphology': str(item.get('morphology', '')),
                    'fusion_with_neighbors_0_to_5': str(item.get('fusion_with_neighbors_0_to_5', '')),
                    'confidence': str(item.get('confidence', '')),
                    'note': str(item.get('note', '')),
                    'estimation_mode': 'prompt_visual_complete_droplet',
                    'updated_at_utc': now,
                })

    image_csv = db_root / 'image_database.csv'
    droplet_csv = db_root / 'droplet_database.csv'
    organoid_csv = db_root / 'organoid_database.csv'

    image_cols = list(image_row.keys())
    droplet_cols = [
        'source_tif', 'droplet_id', 'completeness', 'position_label',
        'center_x_px', 'center_y_px', 'radius_px', 'is_partial',
        'bbox_x0', 'bbox_y0', 'bbox_x1', 'bbox_y1', 'segment_png',
        'organoid_count_prompt_estimated', 'organoid_count_visual_complete_droplet',
        'fusion_score_prompt_0_to_5', 'fusion_score_objective_0_to_5', 'fusion_score_combined_0_to_5',
        'confidence_prompt', 'gray_mean', 'gray_std', 'gradient_mean', 'edge_density_p75',
        'dark_component_count', 'dark_centroid_x_px', 'dark_centroid_y_px',
        'quant_note', 'updated_at_utc'
    ]
    organoid_cols = [
        'source_tif', 'droplet_id', 'organoid_id_in_droplet',
        'position_x_px_local', 'position_y_px_local',
        'position_x_px_source', 'position_y_px_source',
        'radius_px_local', 'size_class', 'morphology',
        'fusion_with_neighbors_0_to_5', 'confidence', 'note',
        'estimation_mode', 'updated_at_utc'
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
