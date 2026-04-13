#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_ROOTS = [
    "/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1",
    "/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_v3_direct_brightfield",
    "/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill average_area_px into DEO metric tables and create/refresh database files."
    )
    p.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS)
    return p.parse_args()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_float(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return repr(float(value))


def detect_group_field(fieldnames: list[str]) -> str:
    for name in ["condition", "concentration"]:
        if name in fieldnames:
            return name
    raise KeyError(f"Cannot find grouping field in {fieldnames}")


def backup_file(path: Path) -> Path:
    backup = path.with_name(path.stem + "_before_average_area_backfill" + path.suffix)
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def add_average_area_to_per_image(fieldnames: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    out_rows: list[dict[str, str]] = []
    if "average_area_px" not in fieldnames:
        insert_after = "total_area_px"
        idx = fieldnames.index(insert_after) + 1 if insert_after in fieldnames else len(fieldnames)
        fieldnames = fieldnames[:idx] + ["average_area_px"] + fieldnames[idx:]

    for row in rows:
        total_area = maybe_float(row.get("total_area_px"))
        count = maybe_float(row.get("count"))
        avg = None
        if total_area is not None and count is not None and count > 0:
            avg = total_area / count
        new_row = dict(row)
        new_row["average_area_px"] = fmt_float(avg)
        out_rows.append(new_row)
    return fieldnames, out_rows


def compute_group_stats(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    n = len(values)
    mean = sum(values) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        std = math.sqrt(var)
        sem = std / math.sqrt(n)
    else:
        std = 0.0
        sem = 0.0
    return mean, std, sem


def add_average_area_to_daily(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    per_image_rows: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, str]]]:
    needed = ["average_area_px_mean", "average_area_px_std", "average_area_px_sem"]
    if "average_area_px_mean" not in fieldnames:
        insert_after = "total_area_px_sem"
        idx = fieldnames.index(insert_after) + 1 if insert_after in fieldnames else len(fieldnames)
        fieldnames = fieldnames[:idx] + needed + fieldnames[idx:]

    daily_group_field = detect_group_field(fieldnames)
    per_group_field = detect_group_field(list(per_image_rows[0].keys())) if per_image_rows else daily_group_field

    by_group: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in per_image_rows:
        avg = maybe_float(row.get("average_area_px"))
        if avg is None:
            continue
        by_group[(row[per_group_field], row["relative_day"])].append(avg)

    out_rows: list[dict[str, str]] = []
    for row in rows:
        key = (row[daily_group_field], row["relative_day"])
        mean, std, sem = compute_group_stats(by_group.get(key, []))
        new_row = dict(row)
        new_row["average_area_px_mean"] = fmt_float(mean)
        new_row["average_area_px_std"] = fmt_float(std)
        new_row["average_area_px_sem"] = fmt_float(sem)
        out_rows.append(new_row)
    return fieldnames, out_rows


def build_database_rows(root: Path, per_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not per_rows:
        return out
    group_field = detect_group_field(list(per_rows[0].keys()))
    for row in per_rows:
        stats_path = row.get("stats_path", "")
        metric_path = ""
        if stats_path:
            metric_path = stats_path.replace("_segmentation_stats.json", "_metrics.json")
        out.append(
            {
                "source_tif": row.get("source_tif", ""),
                "image_name": row.get("image_name", ""),
                "group_field": group_field,
                "group_value": row.get(group_field, ""),
                "condition": row.get("condition", ""),
                "concentration": row.get("concentration", ""),
                "date_key": row.get("date_key", ""),
                "date_label": row.get("date_label", ""),
                "relative_day": row.get("relative_day", ""),
                "stage": row.get("stage", ""),
                "count": row.get("count", ""),
                "total_area_px": row.get("total_area_px", ""),
                "average_area_px": row.get("average_area_px", ""),
                "average_perimeter_px": row.get("average_perimeter_px", ""),
                "mask_path": row.get("mask_path", ""),
                "instance_rgb_path": row.get("instance_rgb_path", ""),
                "overlay_path": row.get("overlay_path", ""),
                "signal_path": row.get("signal_path", ""),
                "stats_path": stats_path,
                "metric_path": metric_path,
                "root": str(root),
            }
        )
    return out


def process_root(root: Path) -> dict[str, Any]:
    quant_dir = root / "profiling" / "quantification"
    per_csv = quant_dir / "per_image_metrics.csv"
    daily_csv = quant_dir / "daily_summary.csv"
    if not per_csv.exists() or not daily_csv.exists():
        raise FileNotFoundError(f"Missing quantification CSVs under {root}")

    per_backup = backup_file(per_csv)
    daily_backup = backup_file(daily_csv)

    per_fields, per_rows = read_csv(per_csv)
    per_fields, per_rows = add_average_area_to_per_image(per_fields, per_rows)
    write_csv(per_csv, per_fields, per_rows)

    daily_fields, daily_rows = read_csv(daily_csv)
    daily_fields, daily_rows = add_average_area_to_daily(daily_fields, daily_rows, per_rows)
    write_csv(daily_csv, daily_fields, daily_rows)

    db_dir = root / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_rows = build_database_rows(root, per_rows)
    db_fields = list(db_rows[0].keys()) if db_rows else []
    write_csv(db_dir / "source_image_database.csv", db_fields, db_rows)
    write_json(db_dir / "source_image_database.json", db_rows)

    ignored_dup_csv = db_dir / "ignored_backfill_duplicates.csv"
    ignored_dup_json = db_dir / "ignored_backfill_duplicates.json"
    if not ignored_dup_csv.exists():
        write_csv(ignored_dup_csv, ["source_tif", "ignored_reason"], [])
    if not ignored_dup_json.exists():
        write_json(ignored_dup_json, [])

    manifest = {
        "root": str(root),
        "per_image_csv": str(per_csv),
        "daily_summary_csv": str(daily_csv),
        "per_image_backup_csv": str(per_backup),
        "daily_summary_backup_csv": str(daily_backup),
        "database_csv": str(db_dir / "source_image_database.csv"),
        "database_json": str(db_dir / "source_image_database.json"),
        "n_per_image_rows": len(per_rows),
        "n_daily_rows": len(daily_rows),
        "added_per_image_field": "average_area_px",
        "added_daily_fields": [
            "average_area_px_mean",
            "average_area_px_std",
            "average_area_px_sem",
        ],
    }
    write_json(db_dir / "average_area_backfill_manifest.json", manifest)
    return manifest


def main() -> None:
    args = parse_args()
    manifests = []
    for root_str in args.roots:
        manifests.append(process_root(Path(root_str).resolve()))
    print(json.dumps(manifests, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
