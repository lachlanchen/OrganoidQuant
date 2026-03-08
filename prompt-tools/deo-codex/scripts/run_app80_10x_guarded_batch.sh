#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
app80_root="${1:-$repo_root/DEO/App80 DEO}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

if [[ ! -d "$app80_root" ]]; then
  echo "App80 folder not found: $app80_root"
  exit 1
fi

log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
log_file="$log_dir/app80_10x_guarded_batch_${ts}.log"

mapfile -d '' tifs < <(find "$app80_root" -type f -iname '10x*.tif' -print0 | sort -z)
if [[ "${#tifs[@]}" -eq 0 ]]; then
  echo "No 10x TIFF files found under: $app80_root"
  exit 1
fi

echo "Batch start: $(date -Is)" | tee -a "$log_file"
echo "App80 root: $app80_root" | tee -a "$log_file"
echo "10x TIFF count: ${#tifs[@]}" | tee -a "$log_file"
echo "DEO_CELLPOSE_MODE=$cellpose_mode" | tee -a "$log_file"
echo | tee -a "$log_file"

idx=0
ok=0
fail=0
for tif in "${tifs[@]}"; do
  idx=$((idx + 1))
  echo "[$idx/${#tifs[@]}] START $tif" | tee -a "$log_file"
  if DEO_CELLPOSE_MODE="$cellpose_mode" "$repo_root/prompt-tools/deo-codex/scripts/run_single_image_10x_guarded.sh" "$tif" 2>&1 | tee -a "$log_file"; then
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
