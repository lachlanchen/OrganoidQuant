#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
app80_root="${1:-$repo_root/DEO/App80 DEO}"
max_samples_per_date="${2:-${DEO_MAX_SAMPLES_PER_DATE:-3}}"
skip_tif="${3:-}"

if [[ ! -d "$app80_root" ]]; then
  echo "App80 folder not found: $app80_root"
  exit 1
fi

results_csv="$repo_root/DEO-DATABASE/app80_10x_single_droplet_results.csv"
log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
selector_json="$log_dir/app80_10x_resume_targets_${ts}.json"
log_file="$log_dir/app80_10x_resume_batch_${ts}.log"

selector_cmd=(
  "$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/08_select_app80_10x_resume_targets.py"
  --app80-root "$app80_root"
  --results-csv "$results_csv"
  --max-samples-per-date "$max_samples_per_date"
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

echo "Resume start: $(date -Is)" | tee -a "$log_file"
echo "App80 root: $app80_root" | tee -a "$log_file"
echo "max_samples_per_date=$max_samples_per_date" | tee -a "$log_file"
echo "skip_tif=$skip_tif" | tee -a "$log_file"
echo "selector_json=$selector_json" | tee -a "$log_file"
echo "pending_total=${#tifs[@]}" | tee -a "$log_file"
echo | tee -a "$log_file"

if [[ "${#tifs[@]}" -eq 0 ]]; then
  echo "No pending resume targets." | tee -a "$log_file"
  echo "Resume end: $(date -Is)" | tee -a "$log_file"
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

echo "Resume end: $(date -Is)" | tee -a "$log_file"
echo "Success: $ok  Failed: $fail" | tee -a "$log_file"
echo "Log: $log_file" | tee -a "$log_file"
echo "Selector: $selector_json" | tee -a "$log_file"
