#!/home/lachlan/miniconda3/envs/organoid/bin/python
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import uuid
from pathlib import Path

TENX_RE = re.compile(r"10x(\d+)\.tif$", re.IGNORECASE)


def first_tenx_file(folder: Path) -> Path:
    matches = []
    for child in folder.iterdir():
        if not child.is_file():
            continue
        match = TENX_RE.search(child.name)
        if match:
            matches.append((int(match.group(1)), child.name.lower(), child))
    if not matches:
        raise FileNotFoundError(f"No 10x tif files found in {folder}")
    matches.sort(key=lambda item: (item[0], item[1]))
    return matches[0][2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy first 10x replicate from each folder into a blinded test set")
    parser.add_argument("folders", nargs="+", type=Path, help="Date folders to sample")
    parser.add_argument("--output-root", type=Path, required=True, help="Output root for the blinded set")
    args = parser.parse_args()

    output_root = args.output_root
    blinded_dir = output_root / "blinded_images"
    internal_dir = output_root / "internal_mapping"
    blinded_dir.mkdir(parents=True, exist_ok=True)
    internal_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for folder in args.folders:
        source = first_tenx_file(folder)
        uid = f"uid_{uuid.uuid4().hex[:12]}"
        dest = blinded_dir / f"{uid}.tif"
        shutil.copy2(source, dest)
        records.append(
            {
                "uid": uid,
                "blinded_filename": dest.name,
                "source_path": str(source.resolve()),
                "source_folder": str(folder.resolve()),
                "source_basename": source.name,
            }
        )

    (output_root / "README.md").write_text(
        "# Fusion Analysis Test Set\n\n"
        "Use only `blinded_images/` for blind prompt-tool evaluation.\n\n"
        "Do not provide `internal_mapping/` to the model if you want to hide date and condition metadata.\n",
        encoding="utf-8",
    )
    (output_root / "set_summary.json").write_text(json.dumps({"image_count": len(records), "images": records}, indent=2), encoding="utf-8")
    with (internal_dir / "uid_to_source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["uid", "blinded_filename", "source_path", "source_folder", "source_basename"])
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps({"output_root": str(output_root), "image_count": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
