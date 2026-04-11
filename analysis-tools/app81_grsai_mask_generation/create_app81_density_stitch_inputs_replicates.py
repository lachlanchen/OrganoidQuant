#!/usr/bin/env python3
"""Create App81 stitched 10X density collages by batch and replicate index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from create_app81_density_stitch_inputs import (
    DENSITIES,
    annotate_preview,
    collect_candidates,
    create_collage,
    write_json,
)


BATCHES: list[tuple[str, list[str]]] = [
    ("batch_1", ["13-十月-2025", "15-十月-2025", "17-十月-2025", "20-十月-2025", "22-十月-2025", "24-十月-2025", "26-十月-2025", "28-十月-2025"]),
    ("batch_2", ["14-十月-2025", "16-十月-2025", "18-十月-2025", "21-十月-2025", "23-十月-2025", "25-十月-2025", "27-十月-2025", "29-十月-2025"]),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create App81 stitched 10X density collages with replicate iteration")
    p.add_argument("--source-root", default="DEO/DEO App81 P8", help="App81 source root")
    p.add_argument("--output-root", required=True, help="Output folder for stitched collages and manifest")
    p.add_argument("--gap", type=int, default=48, help="Black gutter size in pixels")
    return p.parse_args()


def build_manifest_text(records: list[dict[str, Any]]) -> str:
    lines = [
        "# App81 Density Stitch Manifest V2",
        "",
        "This is the replicate-iterated 10X stitching set.",
        "",
        "Rules used:",
        "- only 10X TIFFs were considered",
        "- two date batches were used",
        "- each collage is still 3x3 with at most 9 tiles",
        "- each batch has 8 date slots and 1 forced blank slot",
        "- replicate iteration was applied per density per batch",
        "- replicate 1 uses the first ranked candidate from each date, replicate 2 uses the second ranked candidate, and so on",
        "- if a date has fewer candidates than the replicate index, that slot is left black",
        "",
    ]
    for record in records:
        lines.extend([
            f"## {record['density']} {record['batch_name']} replicate_{record['replicate_index']:02d}",
            "",
            f"- plain collage: [{record['plain_path']}]({record['plain_path']})",
            f"- labeled preview: [{record['preview_path']}]({record['preview_path']})",
            "",
            "| Slot | Date | Replicate Index | Selected Source | Candidate Count | Candidates |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for slot in record["slots"]:
            selected = slot["selected_source"] or "BLANK"
            candidates = "<br>".join(slot["candidate_sources"]) if slot["candidate_sources"] else "BLANK"
            lines.append(
                f"| {slot['slot']} | {slot['date']} | {slot['replicate_index']} | {selected} | {slot['candidate_count']} | {candidates} |"
            )
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
        for batch_name, dates in BATCHES:
            date_candidates = {date_name: collect_candidates(source_root, date_name, density) for date_name in dates}
            max_reps = max((len(cands) for cands in date_candidates.values()), default=0)
            for rep_idx in range(max_reps):
                selected_paths: list[Path | None] = []
                slot_records: list[dict[str, Any]] = []
                for slot_idx, date_name in enumerate(dates, start=1):
                    candidates = date_candidates[date_name]
                    selected = candidates[rep_idx] if rep_idx < len(candidates) else None
                    selected_paths.append(selected)
                    slot_records.append({
                        "slot": slot_idx,
                        "date": date_name,
                        "replicate_index": rep_idx + 1,
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
                        "replicate_index": rep_idx + 1,
                        "selected_source": "",
                        "candidate_count": 0,
                        "candidate_sources": [],
                    })

                plain_path = (plain_dir / f"{density}_{batch_name}_replicate_{rep_idx+1:02d}_10x_stitched.png").resolve()
                preview_path = (preview_dir / f"{density}_{batch_name}_replicate_{rep_idx+1:02d}_10x_stitched_preview.png").resolve()
                collage_info = create_collage(selected_paths, plain_path, preview_path, args.gap)
                for layout_slot, slot_record in zip(collage_info["slots"], slot_records):
                    slot_record["bbox"] = layout_slot["bbox"]
                    slot_record["blank"] = layout_slot["blank"]
                preview_image = collage_info.pop("preview_image")
                annotate_preview(preview_image, slot_records)
                preview_image.save(preview_path)

                record = {
                    "density": density,
                    "batch_name": batch_name,
                    "dates": dates,
                    "replicate_index": rep_idx + 1,
                    "plain_path": str(plain_path),
                    "preview_path": str(preview_path),
                    "panel_size": collage_info["panel_size"],
                    "canvas_size": collage_info["canvas_size"],
                    "slots": slot_records,
                }
                manifest_records.append(record)
                json_records.append(record)

    manifest_md = build_manifest_text(manifest_records)
    manifest_path = output_root / "app81_density_stitch_manifest_replicates.md"
    manifest_path.write_text(manifest_md + "\n", encoding="utf-8")
    write_json(output_root / "app81_density_stitch_manifest_replicates.json", json_records)

    print(json.dumps({
        "output_root": str(output_root),
        "manifest_markdown": str(manifest_path),
        "plain_dir": str(plain_dir),
        "preview_dir": str(preview_dir),
        "collage_count": len(manifest_records),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
