#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
app80_root="${1:-$repo_root/DEO/App80 DEO}"
max_samples_per_date="${2:-${DEO_MAX_SAMPLES_PER_DATE:-0}}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

if [[ ! -d "$app80_root" ]]; then
  echo "App80 folder not found: $app80_root"
  exit 1
fi

log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
log_file="$log_dir/app80_10x_simple_batch_${ts}.log"

mapfile -d '' raw_tifs < <(find "$app80_root" -type f \( -iname '10x*.tif' -o -iname '10X*.tif' \) -print0 | sort -z)
if [[ "${#raw_tifs[@]}" -eq 0 ]]; then
  echo "No 10x TIFF files found under: $app80_root"
  exit 1
fi

declare -a tifs=()
declare -A dir_counts=()
for tif in "${raw_tifs[@]}"; do
  parent_dir="$(dirname "$tif")"
  current_count="${dir_counts["$parent_dir"]:-0}"
  if [[ "$max_samples_per_date" =~ ^[0-9]+$ ]] && (( max_samples_per_date > 0 )) && (( current_count >= max_samples_per_date )); then
    continue
  fi
  tifs+=("$tif")
  dir_counts["$parent_dir"]=$((current_count + 1))
done

echo "Batch start: $(date -Is)" | tee -a "$log_file"
echo "App80 root: $app80_root" | tee -a "$log_file"
echo "10x TIFF raw count: ${#raw_tifs[@]}" | tee -a "$log_file"
echo "max_samples_per_date=$max_samples_per_date" | tee -a "$log_file"
echo "10x TIFF filtered count: ${#tifs[@]}" | tee -a "$log_file"
echo "DEO_CELLPOSE_MODE=$cellpose_mode" | tee -a "$log_file"
echo | tee -a "$log_file"

idx=0
ok=0
fail=0
for tif in "${tifs[@]}"; do
  idx=$((idx + 1))
  echo "[$idx/${#tifs[@]}] START $tif" | tee -a "$log_file"
  if DEO_CELLPOSE_MODE="$cellpose_mode" "$repo_root/prompt-tools/deo-codex/scripts/run_single_image_10x_simple.sh" "$tif" 2>&1 | tee -a "$log_file"; then
    ok=$((ok + 1))
    echo "[$idx/${#tifs[@]}] DONE  $tif" | tee -a "$log_file"
  else
    fail=$((fail + 1))
    echo "[$idx/${#tifs[@]}] FAIL  $tif" | tee -a "$log_file"
  fi
  echo | tee -a "$log_file"
done

echo "Batch end: $(date -Is)" | tee -a "$log_file"
echo "Success: $ok  Failed: $fail" | tee -a "$log_file"
echo "Log: $log_file" | tee -a "$log_file"
