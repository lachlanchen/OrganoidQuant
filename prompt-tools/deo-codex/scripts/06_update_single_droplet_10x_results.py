#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def parse_metadata(source_tif: Path, deo_root: Path) -> Dict[str, str]:
    rel = source_tif.relative_to(deo_root)
    parts = rel.parts
    experiment_folder = parts[0] if len(parts) > 0 else ""
    concentration_label = parts[1] if len(parts) > 1 else ""
    date_label = parts[2] if len(parts) > 2 else ""
    image_name = source_tif.stem
    mag = ""
    sample = ""
    m = re.search(r"(?i)(\d+x)(\d+)", image_name)
    if m:
        mag = m.group(1).lower()
        sample = m.group(2)
    concentration_value = ""
    cl = concentration_label.lower()
    if cl == "no":
        concentration_value = "0"
    elif cl.endswith("um"):
        raw = concentration_label[:-2]
        try:
            concentration_value = str(float(raw))
        except Exception:
            concentration_value = ""
    return {
        "experiment_folder": experiment_folder,
        "concentration_label": concentration_label,
        "concentration_value_uM": concentration_value,
        "date_label": date_label,
        "magnification_token": mag,
        "sample_token": sample,
        "image_name": image_name,
        "relative_path": str(rel),
    }


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> None:
    p = argparse.ArgumentParser(description="Write single-droplet 10x markdown and results CSV.")
    p.add_argument("--source-tif", required=True)
    p.add_argument("--source-png", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--objective-json", required=True)
    p.add_argument("--combined-json", required=True)
    p.add_argument("--tif-meta-json", required=True)
    p.add_argument("--markdown-dir", required=True)
    p.add_argument("--db-root", required=True)
    p.add_argument("--deo-root", required=True)
    args = p.parse_args()

    source_tif = Path(args.source_tif).resolve()
    source_png = Path(args.source_png).resolve()
    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    objective = json.loads(Path(args.objective_json).read_text(encoding="utf-8"))
    combined = json.loads(Path(args.combined_json).read_text(encoding="utf-8"))
    tif_meta = json.loads(Path(args.tif_meta_json).read_text(encoding="utf-8"))
    markdown_dir = Path(args.markdown_dir).resolve()
    db_root = Path(args.db_root).resolve()
    deo_root = Path(args.deo_root).resolve()

    meta = parse_metadata(source_tif, deo_root)
    fusion_visual = float(combined["fusion_score_visual_0_to_5"])
    fusion_objective = float(combined["fusion_score_objective_0_to_5"])
    fusion_combined = float(combined["fusion_score_combined_0_to_5"])
    now = datetime.now(timezone.utc).isoformat()

    markdown_dir.mkdir(parents=True, exist_ok=True)
    md_path = markdown_dir / f"{meta['image_name']}.md"
    md_lines = [
        f"# 10x Single Droplet Result - {meta['image_name']}",
        "",
        "## Source",
        f"- TIFF: `{source_tif}`",
        f"- PNG: `{source_png}`",
        "",
        "## Parsed Metadata",
        f"- concentration_label: `{meta['concentration_label']}`",
        f"- concentration_value_uM: `{meta['concentration_value_uM']}`",
        f"- date_label: `{meta['date_label']}`",
        f"- magnification_token: `{meta['magnification_token']}`",
        f"- sample_token: `{meta['sample_token']}`",
        "",
        "## Single Droplet Summary",
        f"- center_x_px: `{summary['droplet_center_x_px']}`",
        f"- center_y_px: `{summary['droplet_center_y_px']}`",
        f"- radius_px: `{summary['droplet_radius_px']}`",
        f"- visible_fraction_0_to_1: `{summary['droplet_visible_fraction_0_to_1']}`",
        f"- droplet_shape_class: `{summary['droplet_shape_class']}`",
        f"- droplet_boundary_confidence_0_to_1: `{summary['droplet_boundary_confidence_0_to_1']}`",
        f"- organoid_count_estimated_visual: `{summary['organoid_count_estimated_visual']}`",
        f"- organoid_count_cellpose_inside: `{combined['organoid_count_cellpose_inside']}`",
        f"- organoid_count_combined: `{combined['organoid_count_combined']}`",
        f"- fusion_score_visual_0_to_5: `{fusion_visual}`",
        f"- fusion_score_objective_0_to_5: `{fusion_objective}`",
        f"- fusion_score_combined_0_to_5: `{fusion_combined}`",
        f"- droplet_area_px: `{objective['droplet_area_px']}`",
        f"- droplet_circumference_px: `{objective['droplet_circumference_px']}`",
        "",
        "## Notes",
        f"- size_note: {summary['size_note']}",
        f"- fusion_note: {summary['fusion_note']}",
        f"- droplet_note: {summary['droplet_note']}",
        "",
        "## Objective Metrics",
        f"- edge_density_inside_0_to_1: `{objective['edge_density_inside_0_to_1']}`",
        f"- dark_area_fraction_inside_0_to_1: `{objective['dark_area_fraction_inside_0_to_1']}`",
        f"- cellpose_mask_count_inside: `{objective['cellpose_mask_count_inside']}`",
        f"- cellpose_mean_area_inside_px: `{objective['cellpose_mean_area_inside_px']}`",
        f"- cellpose_largest_area_inside_px: `{objective['cellpose_largest_area_inside_px']}`",
        "",
        "## TIFF Metadata",
        f"- shape: `{tif_meta.get('shape', '')}`",
        f"- dtype: `{tif_meta.get('dtype', '')}`",
        f"- page_count: `{tif_meta.get('page_count', '')}`",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    row = {
        "source_tif": str(source_tif),
        "source_png": str(source_png),
        "relative_path": meta["relative_path"],
        "experiment_folder": meta["experiment_folder"],
        "concentration_label": meta["concentration_label"],
        "concentration_value_uM": meta["concentration_value_uM"],
        "date_label": meta["date_label"],
        "magnification_token": meta["magnification_token"],
        "sample_token": meta["sample_token"],
        "droplet_center_x_px": str(summary["droplet_center_x_px"]),
        "droplet_center_y_px": str(summary["droplet_center_y_px"]),
        "droplet_radius_px": str(summary["droplet_radius_px"]),
        "droplet_visible_fraction_0_to_1": str(summary["droplet_visible_fraction_0_to_1"]),
        "droplet_shape_class": str(summary["droplet_shape_class"]),
        "droplet_boundary_confidence_0_to_1": str(summary["droplet_boundary_confidence_0_to_1"]),
        "droplet_area_px": str(objective["droplet_area_px"]),
        "droplet_circumference_px": str(objective["droplet_circumference_px"]),
        "organoid_count_estimated_visual": str(combined["organoid_count_visual"]),
        "organoid_count_cellpose_inside": str(combined["organoid_count_cellpose_inside"]),
        "organoid_count_combined": str(combined["organoid_count_combined"]),
        "fusion_score_visual_0_to_5": str(fusion_visual),
        "fusion_score_objective_0_to_5": str(fusion_objective),
        "fusion_score_combined_0_to_5": str(fusion_combined),
        "edge_density_inside_0_to_1": str(objective["edge_density_inside_0_to_1"]),
        "dark_area_fraction_inside_0_to_1": str(objective["dark_area_fraction_inside_0_to_1"]),
        "cellpose_mask_count_inside": str(objective["cellpose_mask_count_inside"]),
        "cellpose_mean_area_inside_px": str(objective["cellpose_mean_area_inside_px"]),
        "cellpose_largest_area_inside_px": str(objective["cellpose_largest_area_inside_px"]),
        "size_note": summary["size_note"],
        "fusion_note": summary["fusion_note"],
        "droplet_note": summary["droplet_note"],
        "markdown_path": str(md_path),
        "updated_at_utc": now,
    }

    csv_path = db_root / "app80_10x_single_droplet_results.csv"
    rows = [r for r in read_rows(csv_path) if r.get("source_tif") != str(source_tif)]
    rows.append(row)
    fieldnames = list(row.keys())
    write_rows(csv_path, rows, fieldnames)

    print(
        json.dumps(
            {
                "markdown_path": str(md_path),
                "results_csv": str(csv_path),
                "fusion_score_combined_0_to_5": fusion_combined,
                "organoid_count_combined": combined["organoid_count_combined"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
