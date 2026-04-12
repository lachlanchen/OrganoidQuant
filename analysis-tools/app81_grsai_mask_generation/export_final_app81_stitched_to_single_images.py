#!/usr/bin/env python3
"""Export final stitched App81 masks back into single-image outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "DEO" / "DEO App81 P8"
DEFAULT_STITCH_MANIFEST = (
    REPO_ROOT
    / "analysis-output"
    / "app81_density_stitched_inputs_v3_replicates_backfill_rep1"
    / "app81_density_stitch_manifest_replicates.json"
)
DEFAULT_V5_RESULTS = (
    REPO_ROOT
    / "analysis-output"
    / "app81_density_stitched_cellpose_v5_all_batches_all_replicates_4x_diameter"
    / "results"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "analysis-output" / "app81_density_stitched_cellpose_v5_final_single_exports_v1"
)


FINAL_VARIANT_SUBDIRS: dict[str, str | None] = {
    "high_batch_1_replicate_01_10x_stitched": None,
    "high_batch_1_replicate_02_10x_stitched": "high_batch_1_replicate_02_10x_stitched_r3c2_merged_from_nanobanana_v2",
    "high_batch_2_replicate_01_10x_stitched": "panel_merged_from_v3_v4_into_v5_v1",
    "high_batch_2_replicate_02_10x_stitched": "panel_merged_from_v3_v4_nb_into_v5_v1",
    "low_batch_1_replicate_01_10x_stitched": None,
    "low_batch_1_replicate_02_10x_stitched": None,
    "low_batch_2_replicate_01_10x_stitched": None,
    "low_batch_2_replicate_02_10x_stitched": None,
    "low_batch_2_replicate_03_10x_stitched": None,
    "middle_batch_1_replicate_01_10x_stitched": "panel_merged_from_v3_into_v5_v1",
    "middle_batch_1_replicate_02_10x_stitched": "panel_merged_from_v3_with_v5_panels_v1",
    "middle_batch_1_replicate_03_10x_stitched": "panel_merged_from_v3_with_v5_r1c3_r3c1_v1",
    "middle_batch_2_replicate_01_10x_stitched": "panel_merged_from_v5_with_nb_r1c3_r3c2_v1",
    "middle_batch_2_replicate_02_10x_stitched": "panel_merged_from_v5_with_nb_r1c3_r3c1_v1",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export final stitched App81 masks back to single-image outputs")
    p.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT), help="App81 source root")
    p.add_argument("--stitch-manifest", default=str(DEFAULT_STITCH_MANIFEST), help="Stitch manifest JSON")
    p.add_argument("--v5-results-root", default=str(DEFAULT_V5_RESULTS), help="4x stitched results root")
    p.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output directory")
    return p.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def collage_name_from_record(record: dict[str, Any]) -> str:
    return Path(record["plain_path"]).stem


def resolve_final_result_dir(v5_results_root: Path, collage_name: str) -> Path:
    base_dir = v5_results_root / collage_name
    if collage_name not in FINAL_VARIANT_SUBDIRS:
        raise KeyError(f"Missing final variant mapping for {collage_name}")
    subdir = FINAL_VARIANT_SUBDIRS[collage_name]
    return base_dir if subdir is None else base_dir / subdir


def resolve_mask_paths(final_dir: Path) -> tuple[Path, Path]:
    candidates = [
        ("merged_instance_mask.png", "merged_instance_mask_flat.png"),
        ("generated_instance_mask.png", "generated_instance_mask_flat.png"),
        ("cellpose_instance_rgb.png", None),
    ]
    for raw_name, flat_name in candidates:
        raw_path = final_dir / raw_name
        if not raw_path.exists():
            continue
        if flat_name:
            flat_path = final_dir / flat_name
            return raw_path, flat_path if flat_path.exists() else raw_path
        return raw_path, raw_path
    raise FileNotFoundError(f"No supported mask image found in {final_dir}")


def panel_row_col(slot: int) -> tuple[int, int]:
    return ((slot - 1) // 3) + 1, ((slot - 1) % 3) + 1


def crop_resize_rgb(image_path: Path, bbox: list[int], output_size: tuple[int, int]) -> np.ndarray:
    image = np.array(Image.open(image_path).convert("RGB"))
    x0, y0, x1, y1 = bbox
    crop = image[y0:y1, x0:x1]
    if crop.shape[1] != output_size[0] or crop.shape[0] != output_size[1]:
        crop = cv2.resize(crop, output_size, interpolation=cv2.INTER_NEAREST)
    return crop


def rgb_mask_to_labels(mask_rgb: np.ndarray) -> np.ndarray:
    labels = np.zeros(mask_rgb.shape[:2], dtype=np.uint16)
    next_id = 1
    flat = mask_rgb.reshape(-1, 3)
    unique_colors = np.unique(flat, axis=0)
    for color in unique_colors:
        if int(color.max()) == 0:
            continue
        color_mask = np.all(mask_rgb == color, axis=2).astype(np.uint8)
        count, cc = cv2.connectedComponents(color_mask, connectivity=8)
        for idx in range(1, count):
            labels[cc == idx] = next_id
            next_id += 1
    return labels


def save_overlay(source_rgb: np.ndarray, mask_rgb: np.ndarray, out_path: Path, alpha: float = 0.55) -> None:
    overlay = np.clip(
        (1.0 - alpha) * source_rgb.astype(np.float32) + alpha * mask_rgb.astype(np.float32),
        0,
        255,
    ).astype(np.uint8)
    Image.fromarray(overlay).save(out_path)


def export_single_panel(
    output_root: Path,
    source_root: Path,
    collage_name: str,
    final_dir: Path,
    raw_mask_path: Path,
    flat_mask_path: Path,
    slot: dict[str, Any],
) -> dict[str, Any]:
    selected_source = Path(slot["selected_source"]).resolve()
    rel_source = selected_source.relative_to(source_root)
    usage_dir = output_root / rel_source.with_suffix("") / f"from_{collage_name}"
    usage_dir.mkdir(parents=True, exist_ok=True)

    source_image = Image.open(selected_source).convert("RGB")
    source_rgb = np.array(source_image)
    output_size = source_image.size

    raw_mask_rgb = crop_resize_rgb(raw_mask_path, slot["bbox"], output_size)
    flat_mask_rgb = crop_resize_rgb(flat_mask_path, slot["bbox"], output_size)
    labels = rgb_mask_to_labels(raw_mask_rgb)

    source_png_path = usage_dir / "source_original.png"
    raw_mask_out = usage_dir / "instance_mask_rgb.png"
    flat_mask_out = usage_dir / "instance_mask_flat.png"
    labels_out = usage_dir / "instance_labels_16bit.png"
    overlay_out = usage_dir / "overlay.png"
    overlay_flat_out = usage_dir / "overlay_flat.png"
    metadata_out = usage_dir / "panel_export_metadata.json"

    source_image.save(source_png_path)
    Image.fromarray(raw_mask_rgb).save(raw_mask_out)
    Image.fromarray(flat_mask_rgb).save(flat_mask_out)
    cv2.imwrite(str(labels_out), labels)
    save_overlay(source_rgb, raw_mask_rgb, overlay_out)
    save_overlay(source_rgb, flat_mask_rgb, overlay_flat_out)

    row, col = panel_row_col(int(slot["slot"]))
    metadata = {
        "collage_name": collage_name,
        "final_result_dir": str(final_dir.resolve()),
        "final_raw_mask_path": str(raw_mask_path.resolve()),
        "final_flat_mask_path": str(flat_mask_path.resolve()),
        "selected_source": str(selected_source),
        "selected_source_relative": str(rel_source),
        "density": collage_name.split("_", 1)[0],
        "slot": int(slot["slot"]),
        "panel_row": row,
        "panel_col": col,
        "date": slot["date"],
        "replicate_index": int(slot["replicate_index"]),
        "selection_mode": slot.get("selection_mode"),
        "source_bbox_in_collage": slot["bbox"],
        "source_size": [int(output_size[1]), int(output_size[0])],
        "label_count": int(labels.max()),
        "exports": {
            "source_original_png": str(source_png_path.resolve()),
            "instance_mask_rgb_png": str(raw_mask_out.resolve()),
            "instance_mask_flat_png": str(flat_mask_out.resolve()),
            "instance_labels_16bit_png": str(labels_out.resolve()),
            "overlay_png": str(overlay_out.resolve()),
            "overlay_flat_png": str(overlay_flat_out.resolve()),
        },
    }
    write_json(metadata_out, metadata)
    return metadata


def main() -> None:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    stitch_manifest_path = Path(args.stitch_manifest).resolve()
    v5_results_root = Path(args.v5_results_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    stitch_records = read_json(stitch_manifest_path)
    final_versions: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []

    for record in stitch_records:
        collage_name = collage_name_from_record(record)
        final_dir = resolve_final_result_dir(v5_results_root, collage_name)
        raw_mask_path, flat_mask_path = resolve_mask_paths(final_dir)
        version_record = {
            "collage_name": collage_name,
            "density": record["density"],
            "batch_name": record["batch_name"],
            "replicate_index": int(record["replicate_index"]),
            "plain_path": record["plain_path"],
            "final_result_dir": str(final_dir.resolve()),
            "raw_mask_path": str(raw_mask_path.resolve()),
            "flat_mask_path": str(flat_mask_path.resolve()),
        }
        final_versions.append(version_record)

        for slot in record["slots"]:
            if slot.get("blank"):
                continue
            exports.append(
                export_single_panel(
                    output_root=output_root,
                    source_root=source_root,
                    collage_name=collage_name,
                    final_dir=final_dir,
                    raw_mask_path=raw_mask_path,
                    flat_mask_path=flat_mask_path,
                    slot=slot,
                )
            )

    summary = {
        "source_root": str(source_root),
        "stitch_manifest": str(stitch_manifest_path),
        "v5_results_root": str(v5_results_root),
        "output_root": str(output_root),
        "final_versions": final_versions,
        "export_count": len(exports),
    }
    write_json(output_root / "final_stitched_versions.json", final_versions)
    write_json(output_root / "export_summary.json", summary)
    write_json(output_root / "export_records.json", exports)

    md_lines = [
        "# App81 Final Single-Image Exports",
        "",
        f"- Output root: `{output_root}`",
        f"- Stitch manifest: `{stitch_manifest_path}`",
        f"- Source root: `{source_root}`",
        f"- Final stitched result root: `{v5_results_root}`",
        f"- Exported single-image records: `{len(exports)}`",
        "",
        "## Final Stitched Versions",
        "",
    ]
    for item in final_versions:
        md_lines.extend(
            [
                f"### {item['collage_name']}",
                f"- Density: `{item['density']}`",
                f"- Batch: `{item['batch_name']}`",
                f"- Replicate index: `{item['replicate_index']}`",
                f"- Final result dir: `{item['final_result_dir']}`",
                f"- Raw mask path: `{item['raw_mask_path']}`",
                f"- Flat mask path: `{item['flat_mask_path']}`",
                "",
            ]
        )
    write_markdown(output_root / "final_stitched_versions.md", md_lines)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
