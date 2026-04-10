#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import traceback
from collections import defaultdict
from datetime import date
from pathlib import Path

from PIL import Image


CONDITION_ORDER = ["low", "middle", "high"]
MONTH_MAP = {"十月": 10, "十一月": 11}
DATE_RE = re.compile(r"^(\d{2})-(十月|十一月)-(\d{4})$")
MAG_RE = re.compile(r"(10x|10X|4x|4X)(\d+)?", re.I)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Full App81 GRS-AI clean-fill batch runner.")
    p.add_argument("--src-root", required=True, help="Root DEO App81 directory")
    p.add_argument("--out-dir", required=True, help="Output root for the batch run")
    p.add_argument("--conditions", default="low,middle,high", help="Comma-separated conditions")
    p.add_argument("--overwrite", action="store_true", help="Recreate outputs even if present")
    p.add_argument("--limit", type=int, default=0, help="Optional image limit for testing")
    p.add_argument("--checkpoint-every", type=int, default=1, help="Write CSV/manifest every N images")
    return p.parse_args()


def normalize_condition(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip().lower()
    if raw in CONDITION_ORDER:
        return raw
    raise RuntimeError(f"Unsupported density condition: {raw}")


def resolve_conditions(raw: str) -> list[str]:
    asked = [normalize_condition(part) for part in raw.split(",") if part.strip()]
    invalid = [c for c in asked if c not in CONDITION_ORDER]
    if invalid:
        raise SystemExit(f"Unsupported conditions: {invalid}")
    return [c for c in CONDITION_ORDER if c in asked]


def parse_date_dir(name: str) -> tuple[str, date]:
    m = DATE_RE.match(name)
    if not m:
        raise RuntimeError(f"Cannot parse date dir: {name}")
    day = int(m.group(1))
    month = MONTH_MAP[m.group(2)]
    year = int(m.group(3))
    dt = date(year, month, day)
    date_label = f"{day:02d}-{'Oct' if month == 10 else 'Nov'}"
    return date_label, dt


def natural_key(path: Path) -> tuple[int, str]:
    m = MAG_RE.search(path.stem)
    idx = int(m.group(2)) if m and m.group(2) else 10**9
    return (idx, path.stem.lower())


def parse_condition_from_name(name: str) -> str | None:
    name_l = name.lower()
    for cond in CONDITION_ORDER:
        if cond in name_l:
            return cond
    return None


def discover_images(src_root: Path, conditions: list[str]) -> tuple[list[tuple[str, str, str, date, Path]], dict]:
    rows: list[tuple[str, str, str, date, Path]] = []
    transfer_dir = src_root / "low transfer"
    skipped = {
        "non_main_phase": sum(1 for p in transfer_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".tif")
        if transfer_dir.exists()
        else 0,
        "non_tif": 0,
        "non_10x": 0,
        "no_density_label": 0,
        "condition_filtered": 0,
    }
    date_dirs = sorted(
        [p for p in src_root.iterdir() if p.is_dir() and p.name != "low transfer"],
        key=lambda p: parse_date_dir(p.name)[1],
    )
    for date_dir in date_dirs:
        date_key = date_dir.name
        date_label, dt = parse_date_dir(date_key)
        for tif in sorted(date_dir.iterdir(), key=natural_key):
            if not tif.is_file() or tif.suffix.lower() != ".tif":
                skipped["non_tif"] += 1
                continue
            stem = tif.stem
            if "10x" not in stem.lower() and not stem.lower().startswith("10 "):
                skipped["non_10x"] += 1
                continue
            condition = parse_condition_from_name(stem)
            if condition is None:
                skipped["no_density_label"] += 1
                continue
            if condition not in conditions:
                skipped["condition_filtered"] += 1
                continue
            rows.append((condition, date_key, date_label, dt, tif))
    rows.sort(key=lambda row: (CONDITION_ORDER.index(row[0]), row[3], natural_key(row[4])))
    return rows, skipped


def ensure_source_png(tif_path: Path, png_path: Path, overwrite: bool) -> None:
    if png_path.exists() and png_path.stat().st_size > 0 and not overwrite:
        return
    png_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(tif_path).convert("RGB")
    image.save(png_path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_daily_summary(path: Path, rows: list[dict]) -> None:
    groups: dict[tuple[str, str, int], dict] = {}
    for row in rows:
        if row.get("status_generation") != "succeeded" or row.get("status_separation") != "succeeded":
            continue
        key = (row["condition"], row["date_key"], int(row["relative_day"]))
        g = groups.setdefault(
            key,
            {
                "condition": row["condition"],
                "date_key": row["date_key"],
                "date_label": row["date_label"],
                "relative_day": int(row["relative_day"]),
                "n_images": 0,
                "seed_primary_count_mean": 0.0,
                "final_count_mean": 0.0,
            },
        )
        g["n_images"] += 1
        g["seed_primary_count_mean"] += float(row.get("seed_primary_count") or 0)
        g["final_count_mean"] += float(row.get("final_count") or 0)
    out_rows = []
    for _key, g in sorted(groups.items(), key=lambda kv: (CONDITION_ORDER.index(kv[1]["condition"]), kv[1]["relative_day"], kv[1]["date_key"])):
        n = max(1, int(g["n_images"]))
        out_rows.append(
            {
                **g,
                "seed_primary_count_mean": round(g["seed_primary_count_mean"] / n, 6),
                "final_count_mean": round(g["final_count_mean"] / n, 6),
            }
        )
    write_csv(
        path,
        out_rows,
        [
            "condition",
            "date_key",
            "date_label",
            "relative_day",
            "n_images",
            "seed_primary_count_mean",
            "final_count_mean",
        ],
    )


def write_task_registry(path: Path, rows: list[dict]) -> None:
    write_csv(
        path,
        rows,
        [
            "condition",
            "date_key",
            "date_label",
            "relative_day",
            "image_name",
            "source_tif",
            "source_png",
            "output_dir",
            "task_id",
            "status_generation",
            "status_separation",
            "generated_mask_path",
            "generated_overlay_path",
            "seed_primary_instance_rgb_path",
            "simple_instance_rgb_path",
            "seed_primary_count",
            "final_count",
        ],
    )


def append_failure_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames = [
        "phase",
        "condition",
        "date_key",
        "date_label",
        "relative_day",
        "image_name",
        "source_tif",
        "error_type",
        "error_message",
    ]
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def run_subprocess(cmd: list[str], env: dict | None = None) -> None:
    subprocess.run(cmd, check=True, env=env)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    src_root = Path(args.src_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    source_root = out_dir / "source_pngs"
    gen_root = out_dir / "generated_masks"
    db_dir = out_dir / "profiling" / "quantification"
    db_dir.mkdir(parents=True, exist_ok=True)

    conditions = resolve_conditions(args.conditions)
    images, skipped = discover_images(src_root, conditions)
    if args.limit:
        images = images[: args.limit]
    if not images:
        raise SystemExit(f"No main-phase labeled 10x TIFFs found under {src_root} for {conditions}")

    day0 = min(dt for _, _, _, dt, _ in images)
    per_image_csv = db_dir / "per_image_results.csv"
    task_registry_csv = db_dir / "task_registry.csv"
    daily_csv = db_dir / "daily_summary.csv"
    failure_csv = db_dir / "failed_images.csv"
    failure_log = db_dir / "failed_images_tracebacks.log"
    manifest_path = out_dir / "run_manifest.json"

    manifest = {
        "src_root": str(src_root),
        "out_dir": str(out_dir),
        "conditions": conditions,
        "phase": "main_only",
        "magnification": "10x_only",
        "pipeline": "app81_grsai_clean_fill_v1",
        "prompt_style": "concise_clean_fill_accuracy",
        "expected_images": len(images),
        "n_images": 0,
        "skipped": skipped,
        "per_image_csv": str(per_image_csv),
        "task_registry_csv": str(task_registry_csv),
        "daily_summary_csv": str(daily_csv),
        "failure_csv": str(failure_csv),
        "limit": args.limit,
    }

    runner_gen = repo_root / "analysis-tools" / "app81_grsai_mask_generation" / "run_app81_grsai_mask_generation.py"
    runner_sep = repo_root / "analysis-tools" / "app81_grsai_mask_generation" / "separate_generated_mask_simple.py"
    python_bin = sys.executable

    results: list[dict] = []
    failures: list[dict] = []
    total = len(images)

    def checkpoint() -> None:
        write_task_registry(task_registry_csv, results)
        write_task_registry(per_image_csv, results)
        write_daily_summary(daily_csv, results)
        manifest["n_images"] = len(results)
        manifest["n_failures"] = len(failures)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for idx, (condition, date_key, date_label, dt, tif) in enumerate(images, start=1):
        relative_day = (dt - day0).days
        stem = f"{date_key}_{tif.stem}"
        source_png = source_root / condition / date_key / f"{stem}_source.png"
        gen_dir = gen_root / condition / date_key / stem
        sep_dir = gen_dir / "simple_separator"
        result_row = {
            "condition": condition,
            "date_key": date_key,
            "date_label": date_label,
            "relative_day": relative_day,
            "image_name": tif.name,
            "source_tif": str(tif),
            "source_png": str(source_png),
            "output_dir": str(gen_dir),
            "task_id": "",
            "status_generation": "",
            "status_separation": "",
            "generated_mask_path": str(gen_dir / "generated_instance_mask.png"),
            "generated_overlay_path": str(gen_dir / "generated_overlay.png"),
            "seed_primary_instance_rgb_path": str(sep_dir / "seed_primary_instance_rgb.png"),
            "simple_instance_rgb_path": str(sep_dir / "simple_instance_rgb.png"),
            "seed_primary_count": "",
            "final_count": "",
        }
        try:
            ensure_source_png(tif, source_png, args.overwrite)
            run_subprocess(
                [
                    python_bin,
                    str(runner_gen),
                    "--image",
                    str(source_png),
                    "--output-dir",
                    str(gen_dir),
                    "--resume",
                    "--verbose",
                ]
            )
            manifest_json = read_json(gen_dir / "task_manifest.json")
            result_row["task_id"] = manifest_json.get("task_id", "")
            result_row["status_generation"] = manifest_json.get("status", "succeeded")
            print(f"[{idx}/{total}] generated {condition} {date_key} {tif.name}", flush=True)
        except Exception as exc:
            failure = {
                "phase": "generation",
                "condition": condition,
                "date_key": date_key,
                "date_label": date_label,
                "relative_day": relative_day,
                "image_name": tif.name,
                "source_tif": str(tif),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            failures.append(failure)
            append_failure_row(failure_csv, failure)
            with failure_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(failure, ensure_ascii=False) + "\n")
                fh.write(traceback.format_exc() + "\n")
            result_row["status_generation"] = "failed"
            results.append(result_row)
            if len(results) % args.checkpoint_every == 0 or idx == total:
                checkpoint()
            continue

        try:
            run_subprocess(
                [
                    python_bin,
                    str(runner_sep),
                    "--source",
                    str(source_png),
                    "--generated-mask",
                    str(gen_dir / "generated_instance_mask.png"),
                    "--output-dir",
                    str(sep_dir),
                ]
            )
            summary = read_json(sep_dir / "simple_instance_summary.json")
            result_row["status_separation"] = "succeeded"
            result_row["seed_primary_count"] = summary.get("seed_primary_count", "")
            result_row["final_count"] = summary.get("final_count", "")
            print(
                f"[{idx}/{total}] separated {condition} {date_key} {tif.name} "
                f"seed_primary={result_row['seed_primary_count']} final={result_row['final_count']}",
                flush=True,
            )
        except Exception as exc:
            failure = {
                "phase": "separation",
                "condition": condition,
                "date_key": date_key,
                "date_label": date_label,
                "relative_day": relative_day,
                "image_name": tif.name,
                "source_tif": str(tif),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            failures.append(failure)
            append_failure_row(failure_csv, failure)
            with failure_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(failure, ensure_ascii=False) + "\n")
                fh.write(traceback.format_exc() + "\n")
            result_row["status_separation"] = "failed"
            results.append(result_row)
            if len(results) % args.checkpoint_every == 0 or idx == total:
                checkpoint()
            continue

        results.append(result_row)
        if len(results) % args.checkpoint_every == 0 or idx == total:
            checkpoint()

    checkpoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
