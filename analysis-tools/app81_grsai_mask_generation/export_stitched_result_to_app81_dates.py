#!/usr/bin/env python3
"""Export stitched App81 result panels into per-date folders."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "DEO" / "DEO App81 P8"
DEFAULT_STITCH_MANIFEST = REPO_ROOT / "analysis-output" / "app81_density_stitched_inputs_v3_replicates_backfill_rep1" / "app81_density_stitch_manifest_replicates.json"
RESULT_IMAGE_NAMES = [
    "generated_instance_mask.png",
    "generated_instance_mask_flat.png",
    "generated_overlay.png",
    "generated_overlay_flat.png",
]
RESULT_TEXT_NAMES = [
    "prompt.txt",
    "prompt_guidance.json",
    "task_manifest.json",
    "mask_cleanup_report.json",
]
RESULT_LOG_NAMES = [
    "submit_response.raw.txt",
    "poll_response.json",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export stitched App81 result panels into per-date folders")
    p.add_argument("--result-root", action="append", required=True, help="One stitched result folder to export; pass multiple times")
    p.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT), help="App81 date-root")
    p.add_argument("--stitch-manifest", default=str(DEFAULT_STITCH_MANIFEST), help="Stitch manifest JSON")
    p.add_argument(
        "--dest-subdir",
        default="stitched_result_exports",
        help="Subdirectory to create inside each date folder",
    )
    return p.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def find_record(stitch_records: list[dict[str, Any]], collage_path: Path) -> dict[str, Any]:
    collage_str = str(collage_path.resolve())
    for record in stitch_records:
        if str(Path(record["plain_path"]).resolve()) == collage_str:
            return record
    raise RuntimeError(f"Could not find stitched record for {collage_path}")


def crop_image(src: Path, dest: Path, bbox: list[int]) -> None:
    image = Image.open(src).convert("RGB")
    x0, y0, x1, y1 = bbox
    image.crop((x0, y0, x1, y1)).save(dest)


def copy_if_exists(src: Path, dest: Path) -> None:
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def export_result(result_root: Path, source_root: Path, stitch_records: list[dict[str, Any]], dest_subdir: str) -> dict[str, Any]:
    task_manifest = read_json(result_root / "task_manifest.json")
    collage_path = resolve_path(task_manifest["image_path"])
    record = find_record(stitch_records, collage_path)
    export_summary = {
        "result_root": str(result_root.resolve()),
        "input_collage_path": str(collage_path),
        "exports": [],
    }

    # Keep root-level metadata near every date-specific export for traceability.
    for slot in record["slots"]:
        if slot.get("blank"):
            continue
        date_name = slot["date"]
        date_dir = source_root / date_name / dest_subdir / result_root.name
        date_dir.mkdir(parents=True, exist_ok=True)

        source_panel_path = date_dir / "source_panel.png"
        crop_image(collage_path, source_panel_path, slot["bbox"])

        for image_name in RESULT_IMAGE_NAMES:
            src = result_root / image_name
            if src.exists():
                crop_image(src, date_dir / image_name, slot["bbox"])

        for text_name in RESULT_TEXT_NAMES:
            copy_if_exists(result_root / text_name, date_dir / text_name)

        for log_name in RESULT_LOG_NAMES:
            copy_if_exists(result_root / "logs" / log_name, date_dir / "logs" / log_name)

        panel_metadata = {
            "slot": slot["slot"],
            "date": date_name,
            "density": record["density"],
            "batch_name": record["batch_name"],
            "replicate_index": record["replicate_index"],
            "selection_mode": slot.get("selection_mode"),
            "selected_source": slot.get("selected_source"),
            "bbox": slot["bbox"],
            "source_panel_path": str(source_panel_path.resolve()),
            "result_root": str(result_root.resolve()),
            "input_collage_path": str(collage_path),
        }
        write_json(date_dir / "panel_export_metadata.json", panel_metadata)
        export_summary["exports"].append(
            {
                "date": date_name,
                "dest_dir": str(date_dir.resolve()),
                "selected_source": slot.get("selected_source"),
                "slot": slot["slot"],
            }
        )

    write_json(result_root / "per_date_export_summary.json", export_summary)
    return export_summary


def main() -> None:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    stitch_records = read_json(Path(args.stitch_manifest).resolve())
    summaries = []
    for result_root_str in args.result_root:
        result_root = Path(result_root_str).resolve()
        if not result_root.exists():
            raise FileNotFoundError(result_root)
        summaries.append(export_result(result_root, source_root, stitch_records, args.dest_subdir))
    print(json.dumps({"count": len(summaries), "summaries": summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
