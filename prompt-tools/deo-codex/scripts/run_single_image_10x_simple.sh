#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"

source_tif="${1:-$repo_root/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif}"
source_tif="$(realpath "$source_tif")"

deo_root="$repo_root/DEO"
png_root="$repo_root/DEO-PNG"
md_root="$repo_root/DEO-MARKDOWN"
db_root="$repo_root/DEO-DATABASE"

if [[ ! -f "$source_tif" ]]; then
  echo "Source TIFF not found: $source_tif"
  exit 1
fi

file_base="$(basename "$source_tif" .tif)"
if [[ ! "$file_base" =~ 10[xX][0-9]+$ ]]; then
  echo "This simple runner is 10x-only. Got: $file_base"
  exit 1
fi

rel_path="${source_tif#$deo_root/}"
rel_parent="$(dirname "$rel_path")"
image_base="$(basename "$source_tif" .tif)"

source_png="$png_root/${rel_path%.tif}.png"
md_dir="$md_root/$rel_parent/$image_base"
mkdir -p "$md_dir" "$db_root"

meta_json="$md_dir/tif_metadata.json"
summary_json="$md_dir/single_droplet_summary.json"
objective_json="$md_dir/single_droplet_objective_metrics.json"
combined_json="$md_dir/single_droplet_combined_result.json"

echo "[1/5] Convert TIFF -> PNG"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_convert_tif_to_png.py" \
  --src "$source_tif" \
  --deo-root "$deo_root" \
  --png-root "$png_root" > "$md_dir/convert_result.json"

echo "[2/5] Extract TIFF metadata"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_extract_tif_metadata.py" \
  --src "$source_tif" \
  --out "$meta_json" > /dev/null

echo "[3/5] Analyze single-droplet 10x image"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/07_analyze_single_droplet_10x_pure.py" \
  --source-tif "$source_tif" \
  --source-png "$source_png" \
  --summary-json "$summary_json" \
  --objective-json "$objective_json" \
  --combined-json "$combined_json" > /dev/null

echo "[4/5] Prepare structured quantification outputs"
:

echo "[5/5] Update markdown + simple results CSV"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/06_update_single_droplet_10x_results.py" \
  --source-tif "$source_tif" \
  --source-png "$source_png" \
  --summary-json "$summary_json" \
  --objective-json "$objective_json" \
  --combined-json "$combined_json" \
  --tif-meta-json "$meta_json" \
  --markdown-dir "$md_dir" \
  --db-root "$db_root" \
  --deo-root "$deo_root"

echo
echo "Done (10x simple single-droplet)."
echo "- PNG: $source_png"
echo "- Markdown dir: $md_dir"
echo "- Results CSV: $db_root/app80_10x_single_droplet_results.csv"
