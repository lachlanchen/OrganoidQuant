#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT_ROOT = REPO_ROOT / "analysis-output" / "app81_density_stitched_cellpose_v5_final_single_exports_v2"
DEFAULT_METRICS_ROOT = REPO_ROOT / "analysis-output" / "app81_density_stitched_cellpose_v5_final_metrics_v1"
DEFAULT_OUT_DIR = REPO_ROOT / "analysis-output" / "app81_density_stitched_cellpose_v5_final_metrics_audit_v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit App81 final stitched export -> metrics input chain")
    p.add_argument("--export-root", default=str(DEFAULT_EXPORT_ROOT))
    p.add_argument("--metrics-root", default=str(DEFAULT_METRICS_ROOT))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return p.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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


def classify_final_variant(final_result_dir: str) -> str:
    name = Path(final_result_dir).name
    if "nanobanana" in name.lower() or "_nb_" in name.lower():
        return "merged_with_nanobanana"
    if "v3" in name and "v5" in name:
        return "merged_v3_into_v5"
    if "v4" in name and "v5" in name:
        return "merged_v4_into_v5"
    if "merged_from_v3" in name:
        return "merged_v3_into_v5"
    if "merged_from_v5_with_nb" in name:
        return "merged_with_nanobanana"
    if "r3c2_merged_from_nanobanana" in name:
        return "merged_with_nanobanana"
    return "base_4x_cellpose"


def audit_exports(export_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    export_records = read_json(export_root / "export_records.json")
    rows: list[dict[str, Any]] = []
    variant_counter: Counter[str] = Counter()
    mismatch_counter: Counter[str] = Counter()

    for record in export_records:
        export_dir = Path(record["exports"]["instance_mask_rgb_png"]).resolve().parent
        meta = read_json(export_dir / "panel_export_metadata.json")
        final_raw = Path(meta["final_raw_mask_path"])
        final_flat = Path(meta["final_flat_mask_path"])
        bbox = meta["source_bbox_in_collage"]
        source_size = tuple(meta["source_size"][::-1])  # (w, h)

        exported_raw = np.array(Image.open(export_dir / "instance_mask_rgb.png").convert("RGB"))
        exported_flat = np.array(Image.open(export_dir / "instance_mask_flat.png").convert("RGB"))
        exported_labels = cv2.imread(str(export_dir / "instance_labels_16bit.png"), cv2.IMREAD_UNCHANGED)
        expected_raw = crop_resize_rgb(final_raw, bbox, source_size)
        expected_flat = crop_resize_rgb(final_flat, bbox, source_size)
        recomputed_labels = rgb_mask_to_labels(exported_raw)

        raw_equal = bool(np.array_equal(exported_raw, expected_raw))
        flat_equal = bool(np.array_equal(exported_flat, expected_flat))
        labels_match_foreground = bool(np.array_equal((exported_labels > 0), np.any(exported_raw > 0, axis=2)))
        label_count_equal = int(exported_labels.max()) == int(recomputed_labels.max())

        if not raw_equal:
            mismatch_counter["raw_mask_crop_mismatch"] += 1
        if not flat_equal:
            mismatch_counter["flat_mask_crop_mismatch"] += 1
        if not labels_match_foreground:
            mismatch_counter["label_foreground_mismatch"] += 1
        if not label_count_equal:
            mismatch_counter["label_count_mismatch"] += 1

        variant = classify_final_variant(meta["final_result_dir"])
        variant_counter[variant] += 1

        rows.append(
            {
                "selected_source": meta["selected_source"],
                "date": meta["date"],
                "density": meta["density"],
                "collage_name": meta["collage_name"],
                "slot": int(meta["slot"]),
                "panel_row": int(meta["panel_row"]),
                "panel_col": int(meta["panel_col"]),
                "selection_mode": meta.get("selection_mode"),
                "replicate_index": int(meta["replicate_index"]),
                "final_result_dir": meta["final_result_dir"],
                "final_variant_type": variant,
                "raw_mask_exact_crop_match": raw_equal,
                "flat_mask_exact_crop_match": flat_equal,
                "labels_match_foreground": labels_match_foreground,
                "label_count_equal": label_count_equal,
                "export_label_count": int(exported_labels.max()),
                "recomputed_label_count": int(recomputed_labels.max()),
            }
        )

    summary = {
        "export_records": len(rows),
        "variant_counts": dict(sorted(variant_counter.items())),
        "mismatch_counts": dict(sorted(mismatch_counter.items())),
        "all_raw_masks_match": mismatch_counter["raw_mask_crop_mismatch"] == 0,
        "all_flat_masks_match": mismatch_counter["flat_mask_crop_mismatch"] == 0,
        "all_label_foregrounds_match": mismatch_counter["label_foreground_mismatch"] == 0,
        "all_label_counts_match": mismatch_counter["label_count_mismatch"] == 0,
    }
    return rows, summary


def audit_metrics(metrics_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_rows = read_csv(metrics_root / "database" / "source_image_database.csv")
    dup_rows = read_csv(metrics_root / "database" / "ignored_backfill_duplicates.csv")
    metric_rows = read_csv(metrics_root / "profiling" / "quantification" / "per_image_metrics.csv")

    canonical_by_source = {row["selected_source"]: row for row in source_rows}
    per_rows: list[dict[str, Any]] = []
    mismatch_counter: Counter[str] = Counter()

    for row in metric_rows:
        source_tif = row["source_tif"]
        db = canonical_by_source.get(source_tif)
        in_database = db is not None
        paths_exist = all(
            Path(row[key]).exists()
            for key in ["mask_path", "instance_rgb_path", "signal_path", "stats_path"]
        )
        overlay_exists = (not row["overlay_path"]) or Path(row["overlay_path"]).exists()
        metric_json_exists = Path(row["stats_path"].replace("_segmentation_stats.json", "_metrics.json")).exists()
        db_metric_match = in_database and db["metric_path"] == row["stats_path"].replace("_segmentation_stats.json", "_metrics.json")

        if not in_database:
            mismatch_counter["missing_source_database_entry"] += 1
        if not paths_exist:
            mismatch_counter["missing_metric_input_path"] += 1
        if not overlay_exists:
            mismatch_counter["missing_overlay_path"] += 1
        if not metric_json_exists:
            mismatch_counter["missing_metric_json"] += 1
        if in_database and not db_metric_match:
            mismatch_counter["database_metric_path_mismatch"] += 1

        per_rows.append(
            {
                "source_tif": source_tif,
                "condition": row["condition"],
                "relative_day": int(row["relative_day"]),
                "image_name": row["image_name"],
                "source_in_database": in_database,
                "all_required_paths_exist": paths_exist,
                "overlay_exists": overlay_exists,
                "metric_json_exists": metric_json_exists,
                "database_metric_path_match": db_metric_match if in_database else False,
            }
        )

    summary = {
        "per_image_rows": len(metric_rows),
        "canonical_database_rows": len(source_rows),
        "ignored_duplicate_rows": len(dup_rows),
        "mismatch_counts": dict(sorted(mismatch_counter.items())),
        "all_metric_rows_have_database_entry": mismatch_counter["missing_source_database_entry"] == 0,
        "all_required_metric_paths_exist": mismatch_counter["missing_metric_input_path"] == 0,
        "all_overlays_exist": mismatch_counter["missing_overlay_path"] == 0,
        "all_metric_jsons_exist": mismatch_counter["missing_metric_json"] == 0,
        "all_database_metric_paths_match": mismatch_counter["database_metric_path_mismatch"] == 0,
    }
    return per_rows, summary


def write_markdown(path: Path, export_summary: dict[str, Any], metric_summary: dict[str, Any]) -> None:
    lines = [
        "# App81 Final Metrics Input Audit",
        "",
        "## Export audit",
        f"- export records audited: `{export_summary['export_records']}`",
        f"- all raw mask crops match final stitched source: `{export_summary['all_raw_masks_match']}`",
        f"- all flat mask crops match final stitched source: `{export_summary['all_flat_masks_match']}`",
        f"- all label foregrounds match raw instance masks: `{export_summary['all_label_foregrounds_match']}`",
        f"- all label counts match recomputed instance counts: `{export_summary['all_label_counts_match']}`",
        "",
        "### Final variant counts",
    ]
    for key, value in export_summary["variant_counts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines += [
        "",
        "### Export mismatches",
    ]
    if export_summary["mismatch_counts"]:
        for key, value in export_summary["mismatch_counts"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Metrics audit",
        f"- per-image metric rows: `{metric_summary['per_image_rows']}`",
        f"- canonical database rows: `{metric_summary['canonical_database_rows']}`",
        f"- ignored duplicate rows: `{metric_summary['ignored_duplicate_rows']}`",
        f"- all metric rows have database entry: `{metric_summary['all_metric_rows_have_database_entry']}`",
        f"- all required metric paths exist: `{metric_summary['all_required_metric_paths_exist']}`",
        f"- all overlays exist: `{metric_summary['all_overlays_exist']}`",
        f"- all metric JSONs exist: `{metric_summary['all_metric_jsons_exist']}`",
        f"- all database metric paths match: `{metric_summary['all_database_metric_paths_match']}`",
        "",
        "### Metrics mismatches",
    ]
    if metric_summary["mismatch_counts"]:
        for key, value in metric_summary["mismatch_counts"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    export_root = Path(args.export_root).resolve()
    metrics_root = Path(args.metrics_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    export_rows, export_summary = audit_exports(export_root)
    metric_rows, metric_summary = audit_metrics(metrics_root)

    write_csv(
        out_dir / "export_audit.csv",
        export_rows,
        fieldnames=list(export_rows[0].keys()) if export_rows else [],
    )
    write_csv(
        out_dir / "metrics_audit.csv",
        metric_rows,
        fieldnames=list(metric_rows[0].keys()) if metric_rows else [],
    )
    write_json(out_dir / "export_audit_summary.json", export_summary)
    write_json(out_dir / "metrics_audit_summary.json", metric_summary)
    write_markdown(out_dir / "audit_report.md", export_summary, metric_summary)

    manifest = {
        "export_root": str(export_root),
        "metrics_root": str(metrics_root),
        "outputs": {
            "export_audit_csv": str((out_dir / "export_audit.csv").resolve()),
            "metrics_audit_csv": str((out_dir / "metrics_audit.csv").resolve()),
            "export_audit_summary_json": str((out_dir / "export_audit_summary.json").resolve()),
            "metrics_audit_summary_json": str((out_dir / "metrics_audit_summary.json").resolve()),
            "audit_report_md": str((out_dir / "audit_report.md").resolve()),
        },
    }
    write_json(out_dir / "audit_manifest.json", manifest)
    print(out_dir)


if __name__ == "__main__":
    main()
