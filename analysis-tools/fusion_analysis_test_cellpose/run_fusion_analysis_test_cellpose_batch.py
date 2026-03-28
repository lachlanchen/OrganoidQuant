#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
from PIL import Image


VISUAL_DIAMETER_PRIORS: Dict[str, float] = {
    # Small cystic and fragmented structures.
    "uid_4c9aeeaf4c2a": 36.0,
    # Many medium organoids packed together.
    "uid_b7994011c9ae": 44.0,
    # Medium-large rounded organoids.
    "uid_0184600f4483": 56.0,
    # Larger rounded cystic organoids.
    "uid_4a5bcda58697": 72.0,
    # Very large fused masses.
    "uid_bcb41b6edfeb": 110.0,
    # Dominant giant cystic/fused structures.
    "uid_5cd5b219af3c": 130.0,
    # Large irregular fused clusters.
    "uid_8df5c90572c3": 90.0,
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_set = repo_root / "analysis-output/fusion-analysis-test/set_001"
    p = argparse.ArgumentParser(description="Run Cellpose on all blinded images in one fusion-analysis test set.")
    p.add_argument("set_dir", nargs="?", default=str(default_set))
    p.add_argument(
        "--output-dir",
        default="",
        help="Optional explicit output directory. Defaults to sibling folder <set_name>_cellpose.",
    )
    p.add_argument("--model-type", default="cyto3")
    p.add_argument("--cellprob-threshold", type=float, default=-1.5)
    p.add_argument("--flow-threshold", type=float, default=0.4)
    p.add_argument("--min-area-px", type=int, default=60)
    p.add_argument("--max-area-fraction", type=float, default=0.18)
    p.add_argument("--resize-max-dim", type=int, default=1536)
    return p.parse_args()


def resolve_output_dir(set_dir: Path, explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (set_dir.parent / f"{set_dir.name}_cellpose").resolve()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run_dir(runs_dir: Path, uid: str) -> Path | None:
    candidates = sorted(runs_dir.glob(f"blinded_images_{uid}_*"))
    return candidates[-1] if candidates else None


def has_completed_manifest(runs_dir: Path, uid: str) -> bool:
    run_dir = latest_run_dir(runs_dir, uid)
    return bool(run_dir and (run_dir / "run_manifest.json").exists())


def build_summary_markdown(rows: List[dict]) -> str:
    lines = [
        "# Cellpose Batch Summary",
        "",
        "| UID | Diameter Prior | Filtered Masks | Overlay | Instance Mask | Notes |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in rows:
        overlay_rel = row["overlay_png_rel"]
        rgb_rel = row["instance_rgb_png_rel"]
        note = row["prior_note"]
        lines.append(
            f"| `{row['uid']}` | {row['diameter']} | {row['filtered_mask_count']} | "
            f"[overlay]({overlay_rel}) | [instance]({rgb_rel}) | {note} |"
        )
    lines.append("")
    lines.append("`diameter` is a soft Cellpose object-scale prior, not a hard segmentation size.")
    return "\n".join(lines) + "\n"


def load_single_image_module(repo_root: Path):
    module_path = repo_root / "api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.py"
    spec = importlib.util.spec_from_file_location("cellpose_single_image_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_summary_row(output_dir: Path, uid: str, diameter: float, prior_note: str, run_dir: Path, manifest: dict) -> dict:
    artifacts = manifest.get("intermediate_artifacts", {})
    return {
        "uid": uid,
        "diameter": diameter,
        "prior_note": prior_note,
        "run_dir": str(run_dir),
        "filtered_mask_count": manifest["filtered_mask_count"],
        "raw_mask_count": manifest["raw_mask_count"],
        "overlay_png_rel": str(Path(manifest["overlay_png"]).resolve().relative_to(output_dir)),
        "instance_rgb_png_rel": str(Path(manifest["instance_rgb_png"]).resolve().relative_to(output_dir)),
        "raw_label_png_rel": str(Path(manifest["raw_label_png"]).resolve().relative_to(output_dir)),
        "filtered_label_png_rel": str(Path(manifest["filtered_label_png"]).resolve().relative_to(output_dir)),
        "cellprob_png_rel": (
            str(Path(artifacts["cellprob_png"]).resolve().relative_to(output_dir))
            if artifacts.get("cellprob_png")
            else ""
        ),
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    helper = load_single_image_module(repo_root)
    from cellpose import models  # type: ignore

    set_dir = Path(args.set_dir).resolve()
    blinded_dir = set_dir / "blinded_images"
    output_dir = resolve_output_dir(set_dir, args.output_dir)
    runs_dir = output_dir / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    input_files = sorted(blinded_dir.glob("*.tif"))
    if not input_files:
        raise SystemExit(f"No TIFF files found in {blinded_dir}")

    model = models.Cellpose(model_type=args.model_type, gpu=False)
    prior_rows: List[dict] = []
    summary_rows: List[dict] = []

    for tif_path in input_files:
        uid = tif_path.stem
        diameter = VISUAL_DIAMETER_PRIORS.get(uid, 56.0)
        prior_note = (
            "visual estimate from blinded row strip; soft prior only"
            if uid in VISUAL_DIAMETER_PRIORS
            else "fallback default prior"
        )
        prior_rows.append(
            {
                "uid": uid,
                "source_tif": str(tif_path),
                "diameter_px_prior": diameter,
                "note": prior_note,
            }
        )

        run_dir = latest_run_dir(runs_dir, uid)
        if run_dir is None or not (run_dir / "run_manifest.json").exists():
            run_dir = helper.make_run_dir(runs_dir, tif_path)
            source_png = run_dir / f"{tif_path.stem}.png"
            helper.save_png_from_tif(tif_path, source_png)
            source_rgb = helper.load_rgb(source_png)
            working_rgb, working_scale = helper.resize_if_needed(source_rgb, args.resize_max_dim)
            prepared_rgb = helper.preprocess_for_cellpose(working_rgb)
            prepared_png = run_dir / "prepared_for_cellpose.png"
            Image.fromarray(prepared_rgb).save(prepared_png)

            masks_working, flows, styles, diams = model.eval(
                prepared_rgb,
                channels=[0, 0],
                diameter=diameter,
                cellprob_threshold=args.cellprob_threshold,
                flow_threshold=args.flow_threshold,
            )
            if working_scale != 1.0:
                masks = cv2.resize(
                    masks_working.astype(np.uint16),
                    (source_rgb.shape[1], source_rgb.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )
            else:
                masks = masks_working

            raw_labels = [int(x) for x in np.unique(masks) if int(x) > 0]
            filtered_masks, stats = helper.filter_masks(
                masks.astype(np.int32),
                min_area_px=args.min_area_px,
                max_area_fraction=args.max_area_fraction,
            )

            raw_label_png = run_dir / "cellpose_labels_raw_16bit.png"
            filtered_label_png = run_dir / "cellpose_labels_filtered_16bit.png"
            cv2.imwrite(str(raw_label_png), masks.astype(np.uint16))
            cv2.imwrite(str(filtered_label_png), filtered_masks.astype(np.uint16))
            intermediate_artifacts = helper.save_cellpose_intermediates(run_dir, flows)

            instance_rgb = helper.render_instance_rgb(filtered_masks)
            instance_rgb_png = run_dir / "cellpose_instance_rgb.png"
            Image.fromarray(instance_rgb).save(instance_rgb_png)

            overlay = helper.render_overlay(source_rgb, filtered_masks)
            overlay_png = run_dir / "cellpose_overlay.png"
            Image.fromarray(overlay).save(overlay_png)

            manifest = {
                "input_tif": str(tif_path),
                "source_png": str(source_png),
                "prepared_png": str(prepared_png),
                "preprocessing_mode": "full_image_clahe_gaussian_blur",
                "working_scale": round(working_scale, 6),
                "working_image_shape": [int(prepared_rgb.shape[1]), int(prepared_rgb.shape[0])],
                "source_image_shape": [int(source_rgb.shape[1]), int(source_rgb.shape[0])],
                "model_type": args.model_type,
                "diameter": diameter,
                "cellprob_threshold": args.cellprob_threshold,
                "flow_threshold": args.flow_threshold,
                "raw_mask_count": len(raw_labels),
                "filtered_mask_count": len(stats),
                "raw_label_png": str(raw_label_png),
                "filtered_label_png": str(filtered_label_png),
                "instance_rgb_png": str(instance_rgb_png),
                "overlay_png": str(overlay_png),
                "mask_stats_json": str(run_dir / "cellpose_mask_stats.json"),
                "intermediate_artifacts": intermediate_artifacts,
            }
            (run_dir / "cellpose_mask_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
            (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = load_json(run_dir / "run_manifest.json")
        summary_rows.append(build_summary_row(output_dir, uid, diameter, prior_note, run_dir, manifest))
        print(json.dumps({"uid": uid, "run_dir": str(run_dir), "filtered_mask_count": manifest["filtered_mask_count"]}, ensure_ascii=False))

    (output_dir / "diameter_priors_visual_estimate.json").write_text(
        json.dumps(prior_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "diameter_priors_visual_estimate.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["uid", "source_tif", "diameter_px_prior", "note"])
        writer.writeheader()
        writer.writerows(prior_rows)

    with (output_dir / "batch_manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "uid",
                "diameter",
                "prior_note",
                "run_dir",
                "raw_mask_count",
                "filtered_mask_count",
                "overlay_png_rel",
                "instance_rgb_png_rel",
                "raw_label_png_rel",
                "filtered_label_png_rel",
                "cellprob_png_rel",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    (output_dir / "batch_manifest.json").write_text(
        json.dumps(
            {
                "set_dir": str(set_dir),
                "blinded_dir": str(blinded_dir),
                "output_dir": str(output_dir),
                "image_count": len(input_files),
                "model_type": args.model_type,
                "cellprob_threshold": args.cellprob_threshold,
                "flow_threshold": args.flow_threshold,
                "min_area_px": args.min_area_px,
                "max_area_fraction": args.max_area_fraction,
                "resize_max_dim": args.resize_max_dim,
                "rows": summary_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(build_summary_markdown(summary_rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
