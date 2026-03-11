#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
cellpose_runner="$repo_root/api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.sh"
merge_script="$repo_root/api-tests/organoid_multiscale_hybrid_segmentation_test/run_multiscale_hybrid_segmentation_test.py"

default_input="$repo_root/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"
default_output="$repo_root/api-tests/organoid_multiscale_hybrid_segmentation_test/output"
input_tif="$default_input"
output_root="$default_output"

args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[$i]}" in
    --input-tif)
      if (( i + 1 < ${#args[@]} )); then
        input_tif="${args[$((i + 1))]}"
      fi
      ;;
    --output-root)
      if (( i + 1 < ${#args[@]} )); then
        output_root="${args[$((i + 1))]}"
      fi
      ;;
  esac
done

mkdir -p "$output_root"

stamp="$(date +%Y%m%d_%H%M%S)"
parent_name="$(basename "$(dirname "$input_tif")")"
stem="$(basename "$input_tif")"
stem="${stem%.*}"
safe_stem="$(printf '%s' "$stem" | sed 's/[^A-Za-z0-9._-]/_/g')"
run_dir="$output_root/${parent_name}_${safe_stem}_${stamp}"
small_branch_root="$run_dir/branch_cellpose_small"
large_branch_root="$run_dir/branch_cellpose_large"

mkdir -p "$small_branch_root" "$large_branch_root"

export PYTHONUNBUFFERED=1

echo "run_dir=$run_dir"

"$cellpose_runner" \
  --input-tif "$input_tif" \
  --output-root "$small_branch_root" \
  --diameter 32 \
  --cellprob-threshold -1.5 \
  --flow-threshold 0.4 \
  --min-area-px 60 \
  --max-area-fraction 0.18 \
  --resize-max-dim 1536 \
  >"$small_branch_root/subprocess.log" 2>&1

"$cellpose_runner" \
  --input-tif "$input_tif" \
  --output-root "$large_branch_root" \
  --diameter 72 \
  --cellprob-threshold -3.0 \
  --flow-threshold 0.5 \
  --min-area-px 1500 \
  --max-area-fraction 0.45 \
  --resize-max-dim 768 \
  >"$large_branch_root/subprocess.log" 2>&1

small_manifest="$(find "$small_branch_root" -name run_manifest.json | sort | tail -n 1)"
large_manifest="$(find "$large_branch_root" -name run_manifest.json | sort | tail -n 1)"

if [[ -z "$small_manifest" || -z "$large_manifest" ]]; then
  echo "Missing branch manifest." >&2
  exit 1
fi

exec "$py_bin" "$merge_script" \
  --input-tif "$input_tif" \
  --output-root "$output_root" \
  --run-dir "$run_dir" \
  --small-branch-manifest "$small_manifest" \
  --large-branch-manifest "$large_manifest" \
  "${args[@]}"
