#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Build panel 2D metric arrays from enhanced tile metric outputs.')
    p.add_argument('--manifest', required=True)
    p.add_argument('--tile-root', required=True)
    p.add_argument('--output-root', required=True)
    return p.parse_args()


def load_metric(path: Path) -> Dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def main() -> int:
    args = parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    tile_root = Path(args.tile_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    for panel in manifest['panels']:
        conc = panel['concentration']
        sample_rank = int(panel['sample_rank'])
        rows = int(panel['rows'])
        cols = int(panel['cols'])
        fusion_2d: List[List[Any]] = [[None for _ in range(cols)] for _ in range(rows)]
        size_2d: List[List[Any]] = [[None for _ in range(cols)] for _ in range(rows)]
        perimeter_2d: List[List[Any]] = [[None for _ in range(cols)] for _ in range(rows)]
        missing: List[str] = []
        used = 0

        for slot in panel['slots']:
            r = int(slot['row'])
            c = int(slot['col'])
            if slot['empty'] or not slot['source_tif']:
                continue
            tif = Path(slot['source_tif'])
            metric_json = tile_root / conc / (slot['date_name'] or 'unknown_date') / tif.stem / 'tile_metric.json'
            obj = load_metric(metric_json)
            if obj is None:
                missing.append(slot['slot_id'])
                continue
            fusion_2d[r][c] = obj['fusion_0_to_5']
            size_2d[r][c] = obj['combined_area_px']
            perimeter_2d[r][c] = obj['combined_perimeter_px']
            used += 1

        payload = {
            'rows': rows,
            'cols': cols,
            'fusion_2d': fusion_2d,
            'size_2d': size_2d,
            'perimeter_2d': perimeter_2d,
            'panel_note': f'Enhanced segmentation-based metrics. used_tiles={used}; missing_slots={"none" if not missing else ",".join(missing)}',
        }
        out_dir = output_root / conc / f'sample_{sample_rank:02d}'
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'panel_metrics.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({'output_root': str(output_root)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
