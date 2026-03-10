#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def main() -> None:
    p = argparse.ArgumentParser(description="Combine visual and objective single-droplet 10x quantification.")
    p.add_argument("--summary-json", required=True)
    p.add_argument("--objective-json", required=True)
    p.add_argument("--out-json", required=True)
    args = p.parse_args()

    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    objective = json.loads(Path(args.objective_json).read_text(encoding="utf-8"))

    visual_count = int(summary.get("organoid_count_estimated_visual", 0))
    cellpose_count = int(objective.get("cellpose_mask_count_inside", 0))
    dark_component_count = int(objective.get("dark_component_count_inside", 0))
    fusion_visual = float(summary.get("fusion_score_visual_0_to_5", 0.0))
    fusion_objective = float(objective.get("fusion_score_objective_0_to_5", 0.0))
    fusion_combined = round(0.6 * fusion_visual + 0.4 * fusion_objective, 4)

    if cellpose_count <= 0 and dark_component_count <= 0:
        count_combined = visual_count
    else:
        visual_weight = 0.75 if fusion_combined >= 3.5 else 0.60
        objective_count = max(cellpose_count, dark_component_count)
        count_combined = int(round((visual_weight * visual_count) + ((1.0 - visual_weight) * objective_count)))

    payload = {
        "source_tif": summary.get("source_tif"),
        "source_png": summary.get("source_png"),
        "organoid_count_visual": visual_count,
        "organoid_count_cellpose_inside": cellpose_count,
        "organoid_count_dark_components_inside": dark_component_count,
        "organoid_count_combined": max(0, count_combined),
        "fusion_score_visual_0_to_5": round(fusion_visual, 4),
        "fusion_score_objective_0_to_5": round(fusion_objective, 4),
        "fusion_score_combined_0_to_5": fusion_combined,
        "droplet_diameter_px": round(float(summary.get("droplet_radius_px", 0.0)) * 2.0, 4),
        "droplet_area_px": objective.get("droplet_area_px"),
        "droplet_circumference_px": objective.get("droplet_circumference_px"),
        "reliability_note": (
            "combined from visual single-droplet estimate, edge-refined circle, Cellpose mask stats, and image-derived objective fusion metrics"
        ),
    }

    out_json = Path(args.out_json).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
