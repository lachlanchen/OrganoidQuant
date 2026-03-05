#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import tifffile


def safe_value(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


def main() -> None:
    parser = argparse.ArgumentParser(description='Extract TIFF metadata and tags to JSON.')
    parser.add_argument('--src', required=True, help='Source TIFF path')
    parser.add_argument('--out', default='', help='Optional JSON output path')
    args = parser.parse_args()

    src = Path(args.src).resolve()
    if not src.exists():
        raise FileNotFoundError(f'Source not found: {src}')

    with tifffile.TiffFile(src) as tif:
        page = tif.pages[0]
        tags = {}
        for t in page.tags.values():
            tags[str(t.name)] = safe_value(t.value)

        meta = {
            'source_tif': str(src),
            'series_count': len(tif.series),
            'page_count': len(tif.pages),
            'shape': list(page.shape),
            'dtype': str(page.dtype),
            'is_ome': bool(getattr(tif, 'is_ome', False)),
            'is_lsm': bool(getattr(tif, 'is_lsm', False)),
            'imagej_metadata': safe_value(getattr(tif, 'imagej_metadata', None)),
            'ome_metadata': safe_value(getattr(tif, 'ome_metadata', None)),
            'tags': tags,
        }

    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
