#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def main() -> None:
    parser = argparse.ArgumentParser(description='Create droplet-level crops from vision-provided circle annotations.')
    parser.add_argument('--source-png', required=True)
    parser.add_argument('--annotation-json', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--manifest-out', required=True)
    args = parser.parse_args()

    source_png = Path(args.source_png).resolve()
    ann_path = Path(args.annotation_json).resolve()
    out_dir = Path(args.out_dir).resolve()
    manifest_out = Path(args.manifest_out).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)

    for old_seg in out_dir.glob('droplet_*.png'):
        old_seg.unlink()

    ann = json.loads(ann_path.read_text(encoding='utf-8'))
    droplets = sorted(ann.get('droplets', []), key=lambda d: d['droplet_id'])

    base = Image.open(source_png).convert('RGBA')
    w, h = base.size

    segment_rows = []

    for d in droplets:
        did = int(d['droplet_id'])
        cx = float(d['center_x_px'])
        cy = float(d['center_y_px'])
        r = float(d['radius_px'])

        x0 = clamp(int(round(cx - r)), 0, w)
        y0 = clamp(int(round(cy - r)), 0, h)
        x1 = clamp(int(round(cx + r)), 0, w)
        y1 = clamp(int(round(cy + r)), 0, h)
        if x1 <= x0 or y1 <= y0:
            continue

        crop = base.crop((x0, y0, x1, y1))
        cw, ch = crop.size

        mask = Image.new('L', (cw, ch), 0)
        draw = ImageDraw.Draw(mask)
        local_cx = cx - x0
        local_cy = cy - y0
        draw.ellipse((local_cx - r, local_cy - r, local_cx + r, local_cy + r), fill=255)

        rgba = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        rgba.paste(crop, (0, 0), mask)

        is_partial = bool(d.get('is_partial', False))
        completeness = bool(d.get('completeness', not is_partial))
        suffix = 'complete' if completeness and not is_partial else 'partial'
        seg_name = f'droplet_{did:03d}_{suffix}.png'
        seg_path = out_dir / seg_name
        rgba.save(seg_path)

        segment_rows.append({
            'droplet_id': did,
            'segment_png': str(seg_path),
            'bbox_x0': x0,
            'bbox_y0': y0,
            'bbox_x1': x1,
            'bbox_y1': y1,
            'center_x_px': cx,
            'center_y_px': cy,
            'radius_px': r,
            'is_partial': is_partial,
            'completeness': completeness,
            'segment_suffix': suffix,
            'visible_fraction_0_to_1': float(d.get('visible_fraction_0_to_1', 0.0)),
            'position_label': d.get('position_label', ''),
            'initial_organoid_count_estimate': int(d.get('initial_organoid_count_estimate', 0)),
            'initial_fusion_level_0_to_5': float(d.get('initial_fusion_level_0_to_5', 0)),
            'confidence': float(d.get('confidence', 0)),
            'note': d.get('note', ''),
        })

    payload = {
        'source_png': str(source_png),
        'annotation_json': str(ann_path),
        'segment_count': len(segment_rows),
        'segments': segment_rows,
    }
    manifest_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
