#!/usr/bin/env python3
"""Create first-pass stitched 10X App81 density collages and a source manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


GROUPS: list[tuple[str, list[str]]] = [
    ("group_a", ["13-十月-2025", "16-十月-2025", "20-十月-2025", "23-十月-2025", "26-十月-2025", "29-十月-2025"]),
    ("group_b", ["14-十月-2025", "17-十月-2025", "21-十月-2025", "24-十月-2025", "27-十月-2025"]),
    ("group_c", ["15-十月-2025", "18-十月-2025", "22-十月-2025", "25-十月-2025", "28-十月-2025"]),
]
DENSITIES = ["low", "middle", "high"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create App81 stitched 10X density collages")
    p.add_argument("--source-root", default="DEO/DEO App81 P8", help="App81 source root")
    p.add_argument("--output-root", required=True, help="Output folder for stitched collages and manifest")
    p.add_argument("--gap", type=int, default=48, help="Black gutter size in pixels")
    return p.parse_args()


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def is_10x_candidate(path: Path, density: str) -> bool:
    name = path.name.lower()
    if density not in name:
        return False
    if "4x" in name:
        return False
    if not any(token in name for token in ("10x", "10 x", "10 ")):
        return False
    return path.suffix.lower() in {".tif", ".tiff"}


def replicate_rank(path: Path, density: str) -> tuple[int, int, str]:
    name = path.stem.lower()
    idx = name.find(density)
    suffix = ""
    if idx != -1:
        suffix = name[idx + len(density) :].strip()
    if not suffix:
        return (0, 0, name)
    numbers = re.findall(r"\d+", suffix)
    if numbers:
        return (1, int(numbers[0]), name)
    return (1, 9999, name)


def collect_candidates(source_root: Path, date_name: str, density: str) -> list[Path]:
    date_dir = source_root / date_name
    if not date_dir.exists():
        return []
    candidates = [p for p in date_dir.iterdir() if p.is_file() and is_10x_candidate(p, density)]
    return sorted(candidates, key=lambda p: replicate_rank(p, density))


def load_images(image_paths: list[Path]) -> tuple[int, int]:
    sizes = []
    for path in image_paths:
        with Image.open(path) as img:
            sizes.append(img.size)
    widths = {s[0] for s in sizes}
    heights = {s[1] for s in sizes}
    if len(widths) != 1 or len(heights) != 1:
        raise RuntimeError(f"Panel sizes do not match: {sizes}")
    return sizes[0]


def create_collage(panel_paths: list[Path | None], output_path: Path, preview_path: Path, gap: int) -> dict[str, Any]:
    real_paths = [p for p in panel_paths if p is not None]
    if not real_paths:
        raise RuntimeError("No images selected for collage")
    panel_w, panel_h = load_images(real_paths)
    cols = 3
    rows = 3
    canvas_w = cols * panel_w + (cols + 1) * gap
    canvas_h = rows * panel_h + (rows + 1) * gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    preview = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    draw = ImageDraw.Draw(preview)
    layout = []
    for idx in range(rows * cols):
        row = idx // cols
        col = idx % cols
        x0 = gap + col * (panel_w + gap)
        y0 = gap + row * (panel_h + gap)
        x1 = x0 + panel_w
        y1 = y0 + panel_h
        panel_path = panel_paths[idx] if idx < len(panel_paths) else None
        if panel_path is not None:
            with Image.open(panel_path) as img:
                rgb = img.convert("RGB")
                canvas.paste(rgb, (x0, y0))
                preview.paste(rgb, (x0, y0))
        layout.append({
            "slot": idx + 1,
            "row": row + 1,
            "col": col + 1,
            "bbox": [x0, y0, x1, y1],
            "blank": panel_path is None,
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return {"panel_size": [panel_w, panel_h], "canvas_size": [canvas_w, canvas_h], "slots": layout, "preview_image": preview}


def annotate_preview(preview: Image.Image, slot_records: list[dict[str, Any]]) -> None:
    draw = ImageDraw.Draw(preview, "RGBA")
    for record in slot_records:
        x0, y0, x1, _ = record["bbox"]
        label = f"S{record['slot']}  {record['date']}"
        if record["selected_source"]:
            label += f"  {Path(record['selected_source']).name}"
        else:
            label += "  BLANK"
        box_h = 40
        draw.rectangle([x0, y0, x1, y0 + box_h], fill=(0, 0, 0, 180))
        draw.text((x0 + 10, y0 + 10), label, fill=(255, 255, 255, 255))


def build_manifest_text(output_root: Path, manifest: list[dict[str, Any]]) -> str:
    lines = [
        "# App81 Density Stitch Manifest",
        "",
        "This is the first-pass 10X stitching set.",
        "",
        "Rules used:",
        "- only 10X TIFFs were considered",
        "- one first-pass collage per density per date-group",
        "- if multiple 10X candidates existed for a date/density, the selection preferred the unsuffixed/base filename first, then numbered variants",
        "- blank tiles were left black",
        "- this pass does not yet iterate separate replication-index collages",
        "",
    ]
    for record in manifest:
        lines.extend([
            f"## {record['density']} {record['group_name']}",
            "",
            f"- plain collage: [{record['plain_path']}]({record['plain_path']})",
            f"- labeled preview: [{record['preview_path']}]({record['preview_path']})",
            "",
            "| Slot | Date | Selected Source | Candidate Count | Candidates |",
            "| --- | --- | --- | --- | --- |",
        ])
        for slot in record["slots"]:
            selected = slot["selected_source"] or "BLANK"
            candidates = "<br>".join(slot["candidate_sources"]) if slot["candidate_sources"] else "BLANK"
            lines.append(f"| {slot['slot']} | {slot['date']} | {selected} | {slot['candidate_count']} | {candidates} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    output_root = Path(args.output_root).resolve()
    plain_dir = output_root / "collages" / "plain"
    preview_dir = output_root / "collages" / "preview"
    output_root.mkdir(parents=True, exist_ok=True)

    manifest_records: list[dict[str, Any]] = []
    json_records: list[dict[str, Any]] = []
    for density in DENSITIES:
        for group_name, dates in GROUPS:
            selected_paths: list[Path | None] = []
            slot_records: list[dict[str, Any]] = []
            for slot_idx, date_name in enumerate(dates, start=1):
                candidates = collect_candidates(source_root, date_name, density)
                selected = candidates[0] if candidates else None
                selected_paths.append(selected)
                slot_records.append({
                    "slot": slot_idx,
                    "date": date_name,
                    "selected_source": str(selected) if selected else "",
                    "candidate_count": len(candidates),
                    "candidate_sources": [str(p) for p in candidates],
                })
            while len(selected_paths) < 9:
                slot_idx = len(selected_paths) + 1
                selected_paths.append(None)
                slot_records.append({
                    "slot": slot_idx,
                    "date": "BLANK",
                    "selected_source": "",
                    "candidate_count": 0,
                    "candidate_sources": [],
                })

            plain_path = (plain_dir / f"{density}_{group_name}_10x_stitched.png").resolve()
            preview_path = (preview_dir / f"{density}_{group_name}_10x_stitched_preview.png").resolve()
            collage_info = create_collage(selected_paths, plain_path, preview_path, args.gap)
            for layout_slot, slot_record in zip(collage_info["slots"], slot_records):
                slot_record["bbox"] = layout_slot["bbox"]
                slot_record["blank"] = layout_slot["blank"]
            preview_image = collage_info.pop("preview_image")
            annotate_preview(preview_image, slot_records)
            preview_image.save(preview_path)

            record = {
                "density": density,
                "group_name": group_name,
                "dates": dates,
                "plain_path": str(plain_path),
                "preview_path": str(preview_path),
                "panel_size": collage_info["panel_size"],
                "canvas_size": collage_info["canvas_size"],
                "slots": slot_records,
            }
            manifest_records.append(record)
            json_records.append(record)

    manifest_md = build_manifest_text(output_root, manifest_records)
    manifest_path = output_root / "app81_density_stitch_manifest.md"
    manifest_path.write_text(manifest_md + "\n", encoding="utf-8")
    write_json(output_root / "app81_density_stitch_manifest.json", json_records)

    print(json.dumps({
        "output_root": str(output_root),
        "manifest_markdown": str(manifest_path),
        "plain_dir": str(plain_dir),
        "preview_dir": str(preview_dir),
        "collage_count": len(manifest_records),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
