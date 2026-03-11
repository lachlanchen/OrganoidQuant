#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
subtree_root="${1:?subtree_root is required}"
skip_tif="${2:-}"

if [[ ! -d "$subtree_root" ]]; then
  echo "Subtree folder not found: $subtree_root"
  exit 1
fi

results_csv="$repo_root/DEO-DATABASE/app80_10x_single_droplet_results.csv"
log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
selector_json="$log_dir/remaining_10x_subtree_targets_${ts}.json"
log_file="$log_dir/remaining_10x_subtree_batch_${ts}.log"

selector_cmd=(
  "$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/09_select_remaining_10x_subtree.py"
  --subtree-root "$subtree_root"
  --results-csv "$results_csv"
  --out-json "$selector_json"
)
if [[ -n "$skip_tif" ]]; then
  selector_cmd+=(--skip-tif "$skip_tif")
fi
"${selector_cmd[@]}" > /dev/null

mapfile -t tifs < <("$py_bin" - <<'PY' "$selector_json"
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
for x in data.get("pending", []):
    print(x)
PY
)

echo "Subtree resume start: $(date -Is)" | tee -a "$log_file"
echo "subtree_root=$subtree_root" | tee -a "$log_file"
echo "skip_tif=$skip_tif" | tee -a "$log_file"
echo "selector_json=$selector_json" | tee -a "$log_file"
echo "pending_total=${#tifs[@]}" | tee -a "$log_file"
echo | tee -a "$log_file"

if [[ "${#tifs[@]}" -eq 0 ]]; then
  echo "No pending subtree targets." | tee -a "$log_file"
  echo "Subtree resume end: $(date -Is)" | tee -a "$log_file"
  exit 0
fi

idx=0
ok=0
fail=0
for tif in "${tifs[@]}"; do
  idx=$((idx + 1))
  echo "[$idx/${#tifs[@]}] START $tif" | tee -a "$log_file"
  if "$repo_root/prompt-tools/deo-codex/scripts/run_single_image_10x_simple.sh" "$tif" 2>&1 | tee -a "$log_file"; then
    ok=$((ok + 1))
    echo "[$idx/${#tifs[@]}] DONE  $tif" | tee -a "$log_file"
  else
    fail=$((fail + 1))
    echo "[$idx/${#tifs[@]}] FAIL  $tif" | tee -a "$log_file"
  fi
  echo | tee -a "$log_file"
done

echo "Subtree resume end: $(date -Is)" | tee -a "$log_file"
echo "Success: $ok  Failed: $fail" | tee -a "$log_file"
echo "Log: $log_file" | tee -a "$log_file"
echo "Selector: $selector_json" | tee -a "$log_file"
