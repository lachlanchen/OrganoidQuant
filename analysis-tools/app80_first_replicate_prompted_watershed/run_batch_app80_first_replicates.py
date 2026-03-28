#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_FOLDERS = [
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025",
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/07-十二月-2025",
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/08-十二月-2025",
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/09-十二月-2025",
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/10-十二月-2025",
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/11-十二月-2025",
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/12-十二月-2025",
]


def parse_args():
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser()
    p.add_argument("folders", nargs="*", default=DEFAULT_FOLDERS)
    p.add_argument("--output-dir", default=str(root / "analysis-output/app80_10uM_first_replicate_prompted_watershed"))
    return p.parse_args()


def select_first_replicates(folders):
    folders = [Path(f).resolve() for f in folders]
    folders_sorted = sorted(folders, key=lambda p: p.name)
    rows = []
    for idx, folder in enumerate(folders_sorted, start=1):
        cands = sorted(
            [
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in {".tif", ".tiff"} and "10x" in p.stem.lower()
            ],
            key=lambda p: p.name.lower(),
        )
        if not cands:
            continue
        tif = cands[0]
        if idx == 1:
            stage = "cluster"
        elif idx == len(folders_sorted):
            stage = "differentiated_colon_like"
        else:
            stage = "cystic"
        rows.append({"source_tif": tif, "date_label": folder.name, "day_rank": idx, "stage_label": stage})
    return rows


def build_gallery(rows, output_dir: Path):
    strips = []
    for row in rows:
        run_dir = Path(row["run_dir"])
        orig = Image.open(run_dir / f"{Path(row['source_tif']).stem}.png").convert("RGB").resize((256, 192))
        signal = Image.open(run_dir / "signal.png").convert("L").resize((256, 192)).convert("RGB")
        overlay = Image.open(run_dir / "watershed_overlay.png").convert("RGB").resize((256, 192))
        inst = Image.open(run_dir / "watershed_instance_rgb.png").convert("RGB").resize((256, 192))
        canvas = Image.new("RGB", (1060, 228), "white")
        draw = ImageDraw.Draw(canvas)
        canvas.paste(orig, (0, 32))
        canvas.paste(signal, (268, 32))
        canvas.paste(overlay, (536, 32))
        canvas.paste(inst, (804, 32))
        draw.text((8, 6), f"{row['date_label']} | {row['stage_label']} | masks={row['filtered_mask_count']}", fill=(20, 20, 20))
        draw.text((8, 208), "original", fill=(20, 20, 20))
        draw.text((276, 208), "signal", fill=(20, 20, 20))
        draw.text((544, 208), "overlay", fill=(20, 20, 20))
        draw.text((812, 208), "instance", fill=(20, 20, 20))
        strips.append(canvas)
    total_h = sum(img.height for img in strips) + 16 * max(0, len(strips) - 1)
    gallery = Image.new("RGB", (1060, total_h), "white")
    y = 0
    for img in strips:
        gallery.paste(img, (0, y))
        y += img.height + 16
    gallery.save(output_dir / "app80_10uM_first_replicate_prompted_watershed_gallery.png")


def main():
    args = parse_args()
    rows = select_first_replicates(args.folders)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = Path(__file__).resolve().parent / "run_single_image_prompted_watershed.sh"
    summary = []
    for row in rows:
        run_dir = output_dir / f"{row['date_label']}__{Path(row['source_tif']).stem}"
        cmd = [str(runner), str(row["source_tif"]), row["date_label"], str(row["day_rank"]), row["stage_label"], str(run_dir)]
        subprocess.run(cmd, check=True)
        mask_stats = json.loads((run_dir / "watershed_mask_stats.json").read_text(encoding="utf-8"))
        params = json.loads((run_dir / "prompted_watershed_params.json").read_text(encoding="utf-8"))
        summary.append(
            {
                "source_tif": str(row["source_tif"]),
                "date_label": row["date_label"],
                "day_rank": row["day_rank"],
                "stage_label": row["stage_label"],
                "filtered_mask_count": len(mask_stats),
                "confidence_0_to_1": params["confidence_0_to_1"],
                "signal_mode": params["signal_mode"],
                "threshold_mode": params["threshold_mode"],
                "run_dir": str(run_dir),
            }
        )
    summary.sort(key=lambda r: int(r["day_rank"]))
    with (output_dir / "batch_manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    (output_dir / "batch_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    build_gallery(summary, output_dir)
    (output_dir / "README.md").write_text(
        "# App80 10uM First Replicate Prompted Watershed\n\n"
        f"- Images processed: {len(summary)}\n"
        "- Gallery: [app80_10uM_first_replicate_prompted_watershed_gallery.png](app80_10uM_first_replicate_prompted_watershed_gallery.png)\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
