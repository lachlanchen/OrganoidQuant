#!/usr/bin/env python3
"""Build an organoid-level App80 table from 16-bit instance masks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


DEFAULT_INPUT = Path(
    "analysis-output/app80_all_concentrations_multiscale_large_recovery/"
    "profiling/quantification/per_image_metrics.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def existing_path(path_value: object) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    return path if path.exists() else None


def fallback_run_path(row: pd.Series, suffix: str) -> Path:
    image_stem = Path(str(row["image_name"])).stem
    return (
        Path("analysis-output/app80_all_concentrations_multiscale_large_recovery/runs")
        / str(row["concentration"])
        / str(row["date_key"])
        / f"{row['date_key']}_{image_stem}_{suffix}"
    )


def resolve_mask_path(row: pd.Series) -> Path:
    direct = existing_path(row.get("mask_path"))
    if direct is not None:
        return direct
    fallback = fallback_run_path(row, "mask_16bit.png")
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Could not find mask for {row['concentration']} {row['date_key']} {row['image_name']}")


def optional_run_path(row: pd.Series, column: str, suffix: str) -> str:
    direct = existing_path(row.get(column))
    if direct is not None:
        return str(direct)
    fallback = fallback_run_path(row, suffix)
    return str(fallback) if fallback.exists() else ""


def build_table(per_image: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "concentration",
        "date_key",
        "date_label",
        "relative_day",
        "image_name",
        "stage",
        "count",
        "total_area_px",
        "mask_path",
        "source_tif",
    }
    missing = required.difference(per_image.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    rows: list[dict[str, object]] = []
    image_rows: list[dict[str, object]] = []

    for _, row in per_image.iterrows():
        mask_path = resolve_mask_path(row)
        mask = np.asarray(Image.open(mask_path))
        labels = mask[mask > 0]
        if labels.size:
            instance_ids, areas = np.unique(labels, return_counts=True)
        else:
            instance_ids = np.array([], dtype=np.int64)
            areas = np.array([], dtype=np.int64)

        image_stem = Path(str(row["image_name"])).stem
        image_uid = "|".join(
            [
                str(row["concentration"]),
                str(row["date_key"]),
                image_stem,
            ]
        )

        count_from_mask = int(len(instance_ids))
        total_area_from_mask = int(areas.sum())
        count_expected = int(row["count"])
        total_area_expected = int(row["total_area_px"])

        image_rows.append(
            {
                "image_uid": image_uid,
                "concentration": row["concentration"],
                "date_key": row["date_key"],
                "date_label": row["date_label"],
                "relative_day": row["relative_day"],
                "image_name": row["image_name"],
                "stage": row["stage"],
                "count_expected": count_expected,
                "count_from_mask": count_from_mask,
                "total_area_expected": total_area_expected,
                "total_area_from_mask": total_area_from_mask,
                "count_matches": count_expected == count_from_mask,
                "total_area_matches": total_area_expected == total_area_from_mask,
                "mask_path": str(mask_path),
                "source_tif": row.get("source_tif", ""),
                "overlay_path": optional_run_path(row, "overlay_path", "overlay.png"),
                "instance_rgb_path": optional_run_path(row, "instance_rgb_path", "instance_rgb.png"),
            }
        )

        for instance_id, area_px in zip(instance_ids.tolist(), areas.tolist(), strict=True):
            organoid_uid = f"{image_uid}|label_{int(instance_id):05d}"
            rows.append(
                {
                    "organoid_uid": organoid_uid,
                    "image_uid": image_uid,
                    "concentration": row["concentration"],
                    "date_key": row["date_key"],
                    "date_label": row["date_label"],
                    "relative_day": row["relative_day"],
                    "image_name": row["image_name"],
                    "stage": row["stage"],
                    "instance_label": int(instance_id),
                    "area_px": int(area_px),
                    "mask_path": str(mask_path),
                    "source_tif": row.get("source_tif", ""),
                }
            )

    organoid_table = pd.DataFrame(rows)
    image_summary = pd.DataFrame(image_rows)
    return organoid_table, image_summary


def main() -> None:
    args = parse_args()
    input_path = args.input
    if not input_path.is_absolute():
        input_path = args.repo_root / input_path

    per_image = pd.read_csv(input_path)
    organoid_table, image_summary = build_table(per_image)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    organoid_table.to_csv(args.output, index=False)

    summary_output = args.summary_output or args.output.with_name("app80_organoid_level_image_summary.csv")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    image_summary.to_csv(summary_output, index=False)

    quality = {
        "input": str(input_path),
        "organoid_table": str(args.output),
        "image_summary": str(summary_output),
        "n_images": int(len(image_summary)),
        "n_organoids": int(len(organoid_table)),
        "all_counts_match": bool(image_summary["count_matches"].all()),
        "all_total_areas_match": bool(image_summary["total_area_matches"].all()),
    }
    quality_path = args.output.with_name("app80_organoid_level_table_quality.json")
    quality_path.write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps(quality, indent=2))


if __name__ == "__main__":
    main()
