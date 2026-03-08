#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--source-png', required=True)
    p.add_argument('--annotation-json', required=True)
    p.add_argument('--out-png', required=True)
    args = p.parse_args()

    src = Path(args.source_png).resolve()
    ann = json.loads(Path(args.annotation_json).read_text(encoding='utf-8'))
    out = Path(args.out_png).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    im = Image.open(src).convert('RGB')
    draw = ImageDraw.Draw(im)

    for d in ann.get('droplets', []):
        did = int(d.get('droplet_id', 0))
        cx = float(d.get('center_x_px', 0.0))
        cy = float(d.get('center_y_px', 0.0))
        r = float(d.get('radius_px', 1.0))
        partial = bool(d.get('is_partial', False))

        color = (255, 64, 64) if partial else (64, 255, 128)
        width = 2 if partial else 3
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)
        draw.text((cx + 4, cy - 10), str(did), fill=(255, 255, 0))

    im.save(out)
    print(str(out))


if __name__ == '__main__':
    main()
