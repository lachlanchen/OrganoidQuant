#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_cellpose = repo_root / "analysis-output/fusion-analysis-test/set_001_cellpose"
    p = argparse.ArgumentParser(description="Build a compact review gallery from blinded set Cellpose outputs.")
    p.add_argument("cellpose_dir", nargs="?", default=str(default_cellpose))
    p.add_argument("--output-dir", default="", help="Optional explicit gallery output dir.")
    p.add_argument("--thumb-width", type=int, default=360)
    p.add_argument("--label-height", type=int, default=34)
    p.add_argument("--pad", type=int, default=16)
    return p.parse_args()


def resolve_output_dir(cellpose_dir: Path, explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (cellpose_dir.parent / f"{cellpose_dir.name}_gallery").resolve()


def resize_keep_aspect(img: Image.Image, target_width: int) -> Image.Image:
    w, h = img.size
    scale = target_width / float(w)
    target_height = max(1, int(round(h * scale)))
    return img.resize((target_width, target_height), Image.Resampling.LANCZOS)


def paste_labeled(
    canvas: Image.Image,
    img: Image.Image,
    x: int,
    y: int,
    label: str,
    label_height: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    canvas.paste(img, (x, y + label_height))
    draw.text((x + 8, y + 8), label, fill=(20, 20, 20))


def read_rows(manifest_csv: Path) -> List[dict]:
    with manifest_csv.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    args = parse_args()
    cellpose_dir = Path(args.cellpose_dir).resolve()
    output_dir = resolve_output_dir(cellpose_dir, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_csv = cellpose_dir / "batch_manifest.csv"
    rows = read_rows(manifest_csv)
    if not rows:
        raise SystemExit(f"No rows found in {manifest_csv}")

    copied_dir = output_dir / "copied_assets"
    copied_dir.mkdir(parents=True, exist_ok=True)

    triptychs: List[Image.Image] = []
    triptych_paths: List[str] = []

    for row in rows:
        uid = row["uid"]
        diameter = row["diameter"]
        run_dir = Path(row["run_dir"])
        source_png = run_dir / f"{uid}.png"
        overlay_png = run_dir / "cellpose_overlay.png"
        instance_png = run_dir / "cellpose_instance_rgb.png"

        source_img = resize_keep_aspect(Image.open(source_png).convert("RGB"), args.thumb_width)
        overlay_img = resize_keep_aspect(Image.open(overlay_png).convert("RGB"), args.thumb_width)
        instance_img = resize_keep_aspect(Image.open(instance_png).convert("RGB"), args.thumb_width)

        panel_height = max(source_img.height, overlay_img.height, instance_img.height)
        panel_width = source_img.width + overlay_img.width + instance_img.width + 2 * args.pad
        triptych = Image.new("RGB", (panel_width, panel_height + args.label_height), "white")
        paste_labeled(triptych, source_img, 0, 0, f"{uid} | original | d={diameter}", args.label_height)
        paste_labeled(triptych, overlay_img, source_img.width + args.pad, 0, "overlay", args.label_height)
        paste_labeled(triptych, instance_img, source_img.width + overlay_img.width + 2 * args.pad, 0, "instance mask", args.label_height)

        triptych_name = f"{uid}_triptych.png"
        triptych.save(output_dir / triptych_name)
        triptychs.append(triptych)
        triptych_paths.append(triptych_name)

        shutil.copy2(source_png, copied_dir / f"{uid}_original.png")
        shutil.copy2(overlay_png, copied_dir / f"{uid}_overlay.png")
        shutil.copy2(instance_png, copied_dir / f"{uid}_instance.png")

    total_height = sum(img.height for img in triptychs) + args.pad * (len(triptychs) - 1)
    total_width = max(img.width for img in triptychs)
    gallery = Image.new("RGB", (total_width, total_height), "white")
    y = 0
    for img in triptychs:
        gallery.paste(img, (0, y))
        y += img.height + args.pad
    gallery_path = output_dir / "set_001_cellpose_all_segmentations.png"
    gallery.save(gallery_path)

    readme_lines = [
        "# Cellpose Segmentation Gallery",
        "",
        f"- Combined gallery: [set_001_cellpose_all_segmentations.png]({gallery_path.name})",
        "- Copied assets: `copied_assets/`",
        "",
        "| UID | Triptych |",
        "|---|---|",
    ]
    for row, triptych_name in zip(rows, triptych_paths):
        readme_lines.append(f"| `{row['uid']}` | [{triptych_name}]({triptych_name}) |")
    (output_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
