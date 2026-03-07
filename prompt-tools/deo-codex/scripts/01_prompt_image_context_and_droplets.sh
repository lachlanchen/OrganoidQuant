#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <source_tif> <source_png> <output_json>"
  exit 1
fi

source_tif="$1"
source_png="$2"
output_json="$3"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
vision_py_bin="$py_bin"
prompt_tpl="$repo_root/prompt-tools/deo-codex/prompts/01_image_context_and_droplet_annotation.md"
schema="$repo_root/prompt-tools/deo-codex/schemas/01_image_context_and_droplets.schema.json"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

if ! "$vision_py_bin" - << 'PY' >/dev/null 2>&1
import cv2
PY
then
  vision_py_bin="python3"
fi

if [[ ! -f "$source_png" ]]; then
  echo "PNG not found: $source_png"
  exit 1
fi

tmp_prompt="$(mktemp)"
tmp_compact_json="$(mktemp)"
trap 'rm -f "$tmp_prompt" "$tmp_compact_json"' EXIT

experiment_root="$(dirname "$(dirname "$(dirname "$source_tif")")")"
mkdir -p "$(dirname "$output_json")"

filename_stem="$(basename "$source_tif" .tif)"
magnification_token="$(python3 - << 'PY' "$filename_stem"
import re,sys
s=sys.argv[1]
m=re.match(r'^(\d+x)', s, flags=re.IGNORECASE)
print((m.group(1).lower() if m else "unknown"))
PY
)"
sample_token="$(python3 - << 'PY' "$filename_stem"
import re,sys
s=sys.argv[1]
m=re.search(r'(\d+)$', s)
print(m.group(1) if m else "unknown")
PY
)"

vision_prior_json="$(dirname "$output_json")/vision_prior_droplet.json"
vision_prior_dir="$(dirname "$output_json")/vision_prior_droplet_artifacts"
"$vision_py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_build_vision_priors.py" \
  --source-png "$source_png" \
  --out-json "$vision_prior_json" \
  --out-dir "$vision_prior_dir" \
  --mode droplet \
  --cellpose-mode "$cellpose_mode" > /dev/null

python3 - << 'PY' "$vision_prior_json" "$tmp_compact_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
compact={
  "mode": obj.get("mode"),
  "magnification_token": obj.get("magnification_token"),
  "image_size": [obj.get("image_width_px"), obj.get("image_height_px")],
  "stats": obj.get("stats",{}),
  "circle_candidates_top": obj.get("circle_candidates",[])[:10],
  "blob_candidates_top": obj.get("blob_candidates",[])[:15],
  "cellpose": {
    "available": obj.get("cellpose",{}).get("available"),
    "attempted": obj.get("cellpose",{}).get("attempted"),
    "success": obj.get("cellpose",{}).get("success"),
    "n_masks": obj.get("cellpose",{}).get("n_masks"),
    "note": obj.get("cellpose",{}).get("note"),
  },
}
open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(compact,ensure_ascii=False,indent=2))
PY

readarray -t _prior < <(python3 - << 'PY' "$vision_prior_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
a=obj.get("artifacts",{})
print(a.get("gradient_png","N/A"))
print(a.get("edges_png","N/A"))
print(a.get("circle_overlay_png","N/A"))
print(a.get("blob_overlay_png","N/A"))
print(a.get("cellpose_overlay_png","N/A"))
PY
)
prior_gradient="${_prior[0]:-N/A}"
prior_edges="${_prior[1]:-N/A}"
prior_circle_overlay="${_prior[2]:-N/A}"
prior_blob_overlay="${_prior[3]:-N/A}"
prior_cellpose_overlay="${_prior[4]:-N/A}"

python3 - << 'PY' \
  "$prompt_tpl" "$tmp_prompt" \
  "$source_tif" "$source_png" "$experiment_root" \
  "$magnification_token" "$sample_token" \
  "$prior_gradient" "$prior_edges" "$prior_circle_overlay" "$prior_blob_overlay" "$prior_cellpose_overlay" \
  "$tmp_compact_json"
from pathlib import Path
import sys
tpl_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
vision_json = Path(sys.argv[13]).read_text(encoding="utf-8")
repl = {
  "__SOURCE_TIF__": sys.argv[3],
  "__SOURCE_PNG__": sys.argv[4],
  "__EXPERIMENT_ROOT__": sys.argv[5],
  "__MAGNIFICATION_TOKEN__": sys.argv[6],
  "__SAMPLE_TOKEN__": sys.argv[7],
  "__VISION_PRIOR_GRADIENT__": sys.argv[8],
  "__VISION_PRIOR_EDGES__": sys.argv[9],
  "__VISION_PRIOR_CIRCLE_OVERLAY__": sys.argv[10],
  "__VISION_PRIOR_BLOB_OVERLAY__": sys.argv[11],
  "__VISION_PRIOR_CELLPOSE_OVERLAY__": sys.argv[12],
  "__VISION_PRIOR_JSON__": vision_json,
}
text = tpl_path.read_text(encoding="utf-8")
for k, v in repl.items():
  text = text.replace(k, v)
out_path.write_text(text, encoding="utf-8")
PY

image_args=(--image "$source_png")
[[ -f "$prior_gradient" ]] && image_args+=(--image "$prior_gradient")
[[ -f "$prior_edges" ]] && image_args+=(--image "$prior_edges")
[[ -f "$prior_circle_overlay" ]] && image_args+=(--image "$prior_circle_overlay")
[[ -f "$prior_blob_overlay" ]] && image_args+=(--image "$prior_blob_overlay")
[[ -f "$prior_cellpose_overlay" ]] && image_args+=(--image "$prior_cellpose_overlay")

for attempt in 1 2; do
  codex exec \
    --model "$model" \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    -C "$repo_root" \
    --output-schema "$schema" \
    "${image_args[@]}" \
    --output-last-message "$output_json" \
    - < "$tmp_prompt"

  if python3 - << 'PY' "$output_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
ok=bool(obj.get('source_tif')) and bool(obj.get('source_png')) and len(obj.get('droplets',[]))>0 and obj.get('image_summary',{}).get('droplet_count_including_partials',0)>0
raise SystemExit(0 if ok else 1)
PY
  then
    break
  fi

  if [[ "$attempt" -eq 2 ]]; then
    echo "Annotation prompt returned invalid/empty payload after retries: $output_json"
    exit 1
  fi
  echo "[retry] annotation payload looked empty; retrying prompt..."
done

echo "Wrote: $output_json"
