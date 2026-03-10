#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from PIL import Image


def map_output_path(src: Path, deo_root: Path, png_root: Path) -> Path:
    try:
        rel = src.relative_to(deo_root)
        return png_root / rel.with_suffix('.png')
    except ValueError:
        return png_root / src.with_suffix('.png').name


def main() -> None:
    parser = argparse.ArgumentParser(description='Convert one TIFF image to PNG with mirrored DEO path.')
    parser.add_argument('--src', required=True, help='Source TIFF path')
    parser.add_argument('--deo-root', default='DEO', help='Root of raw DEO tree')
    parser.add_argument('--png-root', default='DEO-PNG', help='Root of mirrored PNG tree')
    args = parser.parse_args()

    src = Path(args.src).resolve()
    deo_root = Path(args.deo_root).resolve()
    png_root = Path(args.png_root).resolve()

    if not src.exists():
        raise FileNotFoundError(f'Source not found: {src}')

    out = map_output_path(src, deo_root, png_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_name(f".{out.stem}.tmp.png")

    with Image.open(src) as im:
        im.save(tmp_out, format='PNG')
        with Image.open(tmp_out) as verify_im:
            verify_im.load()
        width, height = im.size
        mode = im.mode
    os.replace(tmp_out, out)

    print(json.dumps({
        'source_tif': str(src),
        'output_png': str(out),
        'width': width,
        'height': height,
        'mode': mode,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
