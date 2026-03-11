#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from typing import List, Set


def is_10x_tif(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".tif" and re.search(r"(?i)10x\d+$", path.stem) is not None


def load_done(results_csv: Path) -> Set[Path]:
    if not results_csv.exists():
        return set()
    done: Set[Path] = set()
    with results_csv.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            source_tif = row.get("source_tif", "").strip()
            if source_tif:
                done.add(Path(source_tif).resolve())
    return done


def main() -> None:
    p = argparse.ArgumentParser(description="Select remaining 10x TIFFs in a subtree that are not yet in results CSV.")
    p.add_argument("--subtree-root", required=True)
    p.add_argument("--results-csv", required=True)
    p.add_argument("--skip-tif", action="append", default=[])
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    subtree_root = Path(args.subtree_root).resolve()
    results_csv = Path(args.results_csv).resolve()
    out_json = Path(args.out_json).resolve()
    skip = {Path(x).resolve() for x in args.skip_tif}
    done = load_done(results_csv)

    all_tifs = sorted([p.resolve() for p in subtree_root.rglob("*") if is_10x_tif(p)], key=lambda x: str(x))
    pending: List[str] = [str(p) for p in all_tifs if p not in done and p not in skip]

    payload = {
        "subtree_root": str(subtree_root),
        "results_csv": str(results_csv),
        "all_total": len(all_tifs),
        "done_in_csv_total": sum(1 for p in all_tifs if p in done),
        "skip_tif": [str(x) for x in sorted(skip)],
        "pending_total": len(pending),
        "pending": pending,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_json), "pending_total": len(pending)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
