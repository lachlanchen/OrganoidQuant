#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "test_app81_hybrid_soft_prior_v2.py"
DEFAULT_OUT = Path("/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test_app81_density_custom_hybrid_v2")

EXAMPLES = [
    Path("/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8/14-十月-2025/10X middle.tif"),
    Path("/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8/17-十月-2025/10X middle.tif"),
    Path("/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8/18-十月-2025/10X middle.tif"),
    Path("/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8/29-十月-2025/10X middle10.tif"),
    Path("/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8/29-十月-2025/10X middle11.tif"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run App81 hybrid v2 on selected failure examples.")
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--gpu", action="store_true", default=True)
    return p.parse_args()


def normalize_condition(path: Path) -> str:
    name = path.stem.lower()
    if "high" in name:
        return "high"
    if "middle" in name:
        return "middle"
    if "low" in name:
        return "low"
    return "unknown"


def main() -> int:
    args = parse_args()
    out_root = args.out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for tif in EXAMPLES:
        condition = normalize_condition(tif)
        date_key = tif.parent.name
        run_dir = out_root / "runs" / condition / date_key / f"{date_key}_{tif.stem}_hybrid_soft_prior_v2"
        cmd = [sys.executable, str(SCRIPT), "--tif", str(tif), "--out-dir", str(run_dir)]
        if args.gpu:
            cmd.append("--gpu")
        subprocess.run(cmd, check=True)
        summary_path = run_dir / "step05_final" / "step57_final_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "source_tif": str(tif),
                "condition": condition,
                "date_key": date_key,
                "out_dir": str(run_dir),
                "overlay_path": str(run_dir / "step05_final" / "step52_final_overlay.png"),
                "mask_path": str(run_dir / "step05_final" / "step50_final_mask_16bit.png"),
                "final_count": summary["final_count"],
                "candidate_count_before_merge": summary["candidate_count_before_merge"],
            }
        )
    with (out_root / "comparison_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["source_tif"])
        writer.writeheader()
        if rows:
            writer.writerows(rows)
    print(out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
