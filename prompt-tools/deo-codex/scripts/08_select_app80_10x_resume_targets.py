#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Set


def is_10x_tif(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".tif" and re.match(r"(?i)^10x", path.stem) is not None


def load_completed_from_csv(csv_path: Path) -> Set[Path]:
    if not csv_path.exists():
        return set()
    completed: Set[Path] = set()
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            source_tif = row.get("source_tif", "").strip()
            if source_tif:
                completed.add(Path(source_tif).resolve())
    return completed


def markdown_complete(tif_path: Path, deo_root: Path, md_root: Path) -> bool:
    rel = tif_path.relative_to(deo_root)
    image_base = tif_path.stem
    md_dir = md_root / rel.parent / image_base
    required = [
        md_dir / f"{image_base}.md",
        md_dir / "single_droplet_summary.json",
        md_dir / "single_droplet_objective_metrics.json",
        md_dir / "single_droplet_combined_result.json",
    ]
    return all(p.exists() for p in required)


def main() -> None:
    p = argparse.ArgumentParser(description="Select resume-only App80 10x targets from current partial outputs.")
    p.add_argument("--app80-root", required=True)
    p.add_argument("--results-csv", required=True)
    p.add_argument("--max-samples-per-date", type=int, default=3)
    p.add_argument("--skip-tif", action="append", default=[])
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    app80_root = Path(args.app80_root).resolve()
    results_csv = Path(args.results_csv).resolve()
    out_json = Path(args.out_json).resolve()
    deo_root = app80_root.parent.resolve()
    md_root = deo_root.parent.resolve() / "DEO-MARKDOWN"

    completed_csv = load_completed_from_csv(results_csv)
    skip_set = {Path(x).resolve() for x in args.skip_tif}

    folder_summaries: List[Dict] = []
    pending: List[str] = []

    concentration_dirs = sorted([p for p in app80_root.iterdir() if p.is_dir()], key=lambda x: x.name)
    for concentration_dir in concentration_dirs:
        date_dirs = sorted([p for p in concentration_dir.iterdir() if p.is_dir()], key=lambda x: x.name)
        for date_dir in date_dirs:
            tifs = sorted([p.resolve() for p in date_dir.iterdir() if is_10x_tif(p)], key=lambda x: x.name)
            chosen: List[Dict[str, str]] = []
            completed_count = 0
            pending_count = 0
            skipped_candidates: List[str] = []
            for tif in tifs:
                if len(chosen) >= args.max_samples_per_date:
                    break
                if tif in skip_set:
                    skipped_candidates.append(str(tif))
                    continue
                is_completed = tif in completed_csv or markdown_complete(tif, deo_root, md_root)
                status = "completed" if is_completed else "pending"
                chosen.append({"source_tif": str(tif), "status": status})
                if is_completed:
                    completed_count += 1
                else:
                    pending_count += 1
                    pending.append(str(tif))
            folder_summaries.append(
                {
                    "concentration": concentration_dir.name,
                    "date": date_dir.name,
                    "quota": args.max_samples_per_date,
                    "chosen_count": len(chosen),
                    "completed_count": completed_count,
                    "pending_count": pending_count,
                    "chosen": chosen,
                    "skipped_candidates": skipped_candidates,
                }
            )

    payload = {
        "app80_root": str(app80_root),
        "results_csv": str(results_csv),
        "max_samples_per_date": args.max_samples_per_date,
        "skip_tif": [str(x) for x in sorted(skip_set)],
        "pending_total": len(pending),
        "pending": pending,
        "folders": folder_summaries,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_json), "pending_total": len(pending)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
