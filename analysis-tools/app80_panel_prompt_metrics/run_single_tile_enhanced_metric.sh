#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <source_tif> <tile_output_root> <tile_metric_json>" >&2
  exit 1
fi

source_tif="$1"
tile_output_root="$2"
tile_metric_json="$3"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
polygon_runner="$repo_root/api-tests/organoid_codex_polygon_segmentation_test/run_codex_polygon_segmentation.sh"
metric_script="$repo_root/analysis-tools/app80_panel_prompt_metrics/compute_polygon_tile_metrics.py"

mkdir -p "$tile_output_root" "$(dirname "$tile_metric_json")"
run_log="$tile_output_root/segmentation_runner.log"

runner_output="$(bash "$polygon_runner" "$source_tif" "$tile_output_root/segmentation_runs" 2>&1 | tee "$run_log")"
run_dir="$(printf '%s\n' "$runner_output" | awk -F= '/^run_dir=/{print $2}' | tail -n 1)"
if [[ -z "$run_dir" ]]; then
  run_dir="$(printf '%s\n' "$runner_output" | awk '/^Wrote: /{print $2}' | tail -n 1)"
fi
if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
  echo "Failed to determine segmentation run_dir for $source_tif" >&2
  exit 1
fi

polygon_json="$run_dir/polygon_response.json"
seg_manifest="$run_dir/run_manifest.json"
source_png="$run_dir/$(basename "$source_tif" .tif).png"

"$py_bin" "$metric_script" \
  --polygon-json "$polygon_json" \
  --out-json "$tile_metric_json" \
  --source-tif "$source_tif" \
  --source-png "$source_png" \
  --segmentation-manifest "$seg_manifest"

printf '%s\n' "$run_dir" > "$tile_output_root/segmentation_run_dir.txt"
