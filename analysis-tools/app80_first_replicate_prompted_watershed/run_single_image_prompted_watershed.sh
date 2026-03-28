#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "Usage: $0 <source_tif> <date_label> <day_rank> <stage_label> <output_dir>"
  exit 1
fi

source_tif="$1"
date_label="$2"
day_rank="$3"
stage_label="$4"
output_dir="$5"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script_dir="$repo_root/analysis-tools/app80_first_replicate_prompted_watershed"
model="${DEO_CODEX_MODEL:-gpt-5.4}"
py_bin="/home/lachlan/miniconda3/envs/organoid-gpu/bin/python"

mkdir -p "$output_dir"
artifact_dir="$output_dir/prompt_artifacts"
"$py_bin" "$script_dir/build_prompt_artifacts.py" "$source_tif" "$artifact_dir" >/dev/null
manifest="$artifact_dir/artifact_manifest.json"
source_png="$("$py_bin" - <<'PY' "$manifest"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj['source_png'])
PY
)"
gray_png="$("$py_bin" - <<'PY' "$manifest"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj['gray_png'])
PY
)"
inv_png="$("$py_bin" - <<'PY' "$manifest"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj['gray_inv_png'])
PY
)"
residual_png="$("$py_bin" - <<'PY' "$manifest"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj['residual_png'])
PY
)"
edges_png="$("$py_bin" - <<'PY' "$manifest"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj['edges_overlay_png'])
PY
)"

prompt_file="$output_dir/prompted_watershed_params_prompt.txt"
"$py_bin" - <<'PY' \
  "$script_dir/prompted_watershed_params_prompt.md" "$prompt_file" \
  "$source_tif" "$date_label" "$day_rank" "$stage_label"
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text(encoding='utf-8')
repl = {
  '__SOURCE_TIF__': sys.argv[3],
  '__DATE_LABEL__': sys.argv[4],
  '__DAY_RANK__': sys.argv[5],
  '__STAGE_LABEL__': sys.argv[6],
}
for k, v in repl.items():
  text = text.replace(k, v)
Path(sys.argv[2]).write_text(text, encoding='utf-8')
PY

params_json="$output_dir/prompted_watershed_params.json"
cmd=(codex exec
  --model "$model"
  -c 'model_reasoning_effort="medium"'
  --dangerously-bypass-approvals-and-sandbox
  --skip-git-repo-check
  -C "$repo_root"
  --output-schema "$script_dir/prompted_watershed_params.schema.json"
  --image "$source_png"
  --image "$gray_png"
  --image "$inv_png"
  --image "$residual_png"
  --image "$edges_png"
  --output-last-message "$params_json"
  -)
"${cmd[@]}" < "$prompt_file"

"$py_bin" "$script_dir/apply_prompted_watershed.py" "$source_tif" "$params_json" "$output_dir"
