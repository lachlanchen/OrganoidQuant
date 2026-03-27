#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def tif_to_png(source: Path, dest: Path) -> tuple[int, int]:
    with Image.open(source) as image:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        image.save(dest)
        return image.size


def build_contact_sheet(image_paths: list[Path], output_path: Path, columns: int = 3) -> None:
    images = [Image.open(path).convert("RGB") for path in image_paths]
    try:
        width, height = images[0].size
        rows = (len(images) + columns - 1) // columns
        margin = 28
        header_h = 42
        gutter_x = 24
        gutter_y = 24
        canvas_w = margin * 2 + columns * width + (columns - 1) * gutter_x
        canvas_h = margin * 2 + rows * (height + header_h) + (rows - 1) * gutter_y
        sheet = Image.new("RGB", (canvas_w, canvas_h), "white")
        draw = ImageDraw.Draw(sheet)
        font = load_font(22)
        for idx, (path, img) in enumerate(zip(image_paths, images)):
            row = idx // columns
            col = idx % columns
            x = margin + col * (width + gutter_x)
            y = margin + row * (height + header_h + gutter_y)
            label = path.stem
            bbox = draw.textbbox((0, 0), label, font=font)
            label_w = bbox[2] - bbox[0]
            draw.text((x + (width - label_w) / 2, y), label, fill="black", font=font)
            img_y = y + header_h
            sheet.paste(img, (x, img_y))
            draw.rectangle((x, img_y, x + width - 1, img_y + height - 1), outline="#555555", width=1)
        sheet.save(output_path)
    finally:
        for img in images:
            img.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build isolated PNG bundle and contact sheet from blinded TIFF folder")
    parser.add_argument("blinded_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    blinded_dir = args.blinded_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    png_dir = output_dir / "pngs"
    png_dir.mkdir(parents=True, exist_ok=True)

    tifs = sorted(blinded_dir.glob("*.tif"))
    if not tifs:
        raise FileNotFoundError(f"No tif files found in {blinded_dir}")

    images = []
    for tif in tifs:
        png_path = png_dir / f"{tif.stem}.png"
        width, height = tif_to_png(tif, png_path)
        images.append({
            "uid": tif.stem,
            "source_tif": str(tif.resolve()),
            "png_path": str(png_path.resolve()),
            "width": width,
            "height": height,
        })

    contact_sheet = output_dir / "contact_sheet.png"
    build_contact_sheet([Path(item["png_path"]) for item in images], contact_sheet)

    manifest = {
        "image_count": len(images),
        "uids_in_order": [item["uid"] for item in images],
        "contact_sheet": str(contact_sheet.resolve()),
        "images": images,
    }
    (output_dir / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "image_count": len(images)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
