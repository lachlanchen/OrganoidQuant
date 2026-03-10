#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"

source_tif="${1:-$repo_root/DEO/App80 DEO/10uM/05-十二月-2025/4x00.tif}"

deo_root="$repo_root/DEO"
png_root="$repo_root/DEO-PNG"
md_root="$repo_root/DEO-MARKDOWN"
seg_root="$repo_root/DEO-SEGMENTS"
db_root="$repo_root/DEO-DATABASE"

if [[ ! -f "$source_tif" ]]; then
  echo "Source TIFF not found: $source_tif"
  exit 1
fi

rel_path="${source_tif#$deo_root/}"
rel_parent="$(dirname "$rel_path")"
image_base="$(basename "$source_tif" .tif)"

source_png="$png_root/${rel_path%.tif}.png"
md_dir="$md_root/$rel_parent/$image_base"
seg_dir="$seg_root/$rel_parent/$image_base"
mkdir -p "$md_dir" "$seg_dir" "$db_root"

meta_json="$md_dir/tif_metadata.json"
ann_raw_json="$md_dir/droplet_annotation_raw.json"
ann_json="$md_dir/droplet_annotation.json"
ann_refine_report_json="$md_dir/droplet_annotation_refine_report.json"
ann_edgeopt_report_json="$md_dir/droplet_annotation_edge_opt_report.json"
seg_manifest_json="$md_dir/droplet_segments_manifest.json"
quant_json="$md_dir/droplet_quantification.json"
objective_json="$md_dir/droplet_objective_metrics.json"
organoid_dir="$md_dir/organoid_analysis"

echo "[1/10] Convert TIFF -> PNG"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_convert_tif_to_png.py" \
  --src "$source_tif" \
  --deo-root "$deo_root" \
  --png-root "$png_root" > "$md_dir/convert_result.json"

echo "[2/10] Extract TIFF metadata"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_extract_tif_metadata.py" \
  --src "$source_tif" \
  --out "$meta_json" > /dev/null

echo "[3/10] Prompt tool: image context + droplet annotation"
"$repo_root/prompt-tools/deo-codex/scripts/01_prompt_image_context_and_droplets.sh" \
  "$source_tif" "$source_png" "$ann_raw_json"

echo "[4/10] Refine/normalize droplet annotation (dedupe partial overlaps)"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/01_refine_droplet_annotations.py" \
  --annotation-json "$ann_raw_json" \
  --source-png "$source_png" \
  --out-json "$ann_json" \
  --report-json "$ann_refine_report_json" > /dev/null

echo "[5/10] Edge-based micro-optimization of droplet circles"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/01_optimize_droplet_circles_by_edge.py" \
  --annotation-json "$ann_json" \
  --source-png "$source_png" \
  --out-json "$ann_json" \
  --report-json "$ann_edgeopt_report_json" > /dev/null

echo "[6/10] Segment droplets from annotations"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/02_segment_droplets_from_annotations.py" \
  --source-png "$source_png" \
  --annotation-json "$ann_json" \
  --out-dir "$seg_dir" \
  --manifest-out "$seg_manifest_json" > /dev/null

echo "[7/10] Prompt tool: droplet-level quantification"
"$repo_root/prompt-tools/deo-codex/scripts/03_prompt_droplet_level_quantification.sh" \
  "$source_tif" "$source_png" "$ann_json" "$seg_manifest_json" "$quant_json"

echo "[8/10] Objective droplet metrics (gradient/edge/centroid/fusion heuristic)"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/03_compute_droplet_objective_metrics.py" \
  --segment-manifest-json "$seg_manifest_json" \
  --out-json "$objective_json" > /dev/null

echo "[9/10] Prompt tool: organoid analysis for complete droplets only"
"$repo_root/prompt-tools/deo-codex/scripts/05_prompt_organoid_analysis_complete_droplets.sh" \
  "$source_tif" "$source_png" "$ann_json" "$seg_manifest_json" "$organoid_dir"

echo "[10/10] Update markdown + databases"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/04_update_markdown_and_databases.py" \
  --source-tif "$source_tif" \
  --source-png "$source_png" \
  --annotation-json "$ann_json" \
  --quant-json "$quant_json" \
  --segment-manifest-json "$seg_manifest_json" \
  --tif-meta-json "$meta_json" \
  --objective-metrics-json "$objective_json" \
  --organoid-analysis-dir "$organoid_dir" \
  --annotation-refine-report-json "$ann_refine_report_json" \
  --annotation-edgeopt-report-json "$ann_edgeopt_report_json" \
  --deo-root "$deo_root" \
  --markdown-root "$md_root" \
  --db-root "$db_root"

echo

echo "Done. Outputs:"
echo "- PNG: $source_png"
echo "- Markdown dir: $md_dir"
echo "- Segments dir: $seg_dir"
echo "- Databases: $db_root"
