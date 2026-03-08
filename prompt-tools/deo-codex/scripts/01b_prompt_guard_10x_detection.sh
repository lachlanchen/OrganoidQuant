#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <source_tif> <source_png> <annotation_json> <output_json>"
  exit 1
fi

source_tif="$1"
source_png="$2"
annotation_json="$3"
output_json="$4"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
vision_py_bin="$py_bin"
prompt_tpl="$repo_root/prompt-tools/deo-codex/prompts/01b_guard_10x_detection.md"
schema="$repo_root/prompt-tools/deo-codex/schemas/01b_guard_10x_detection.schema.json"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

for f in "$source_png" "$annotation_json"; do
  [[ -f "$f" ]] || { echo "Missing file: $f"; exit 1; }
done

if ! "$vision_py_bin" - << 'PY' >/dev/null 2>&1
import cv2
PY
then
  vision_py_bin="python3"
fi

filename_stem="$(basename "$source_tif" .tif)"
magnification_token="$(python3 - << 'PY' "$filename_stem"
import re,sys
s=sys.argv[1]
m=re.match(r'^(\d+x)', s, flags=re.IGNORECASE)
print((m.group(1).lower() if m else "unknown"))
PY
)"

mkdir -p "$(dirname "$output_json")"

vision_prior_json="$(dirname "$output_json")/vision_prior_guard_10x.json"
vision_prior_dir="$(dirname "$output_json")/vision_prior_guard_10x_artifacts"
"$vision_py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_build_vision_priors.py" \
  --source-png "$source_png" \
  --out-json "$vision_prior_json" \
  --out-dir "$vision_prior_dir" \
  --mode droplet \
  --cellpose-mode "$cellpose_mode" > /dev/null

annotation_overlay_png="$(dirname "$output_json")/droplet_annotation_overlay_for_guard.png"
"$py_bin" "$repo_root/prompt-tools/deo-codex/scripts/01_render_annotation_overlay.py" \
  --source-png "$source_png" \
  --annotation-json "$annotation_json" \
  --out-png "$annotation_overlay_png" > /dev/null

tmp_prompt="$(mktemp)"
trap 'rm -f "$tmp_prompt"' EXIT

python3 - << 'PY' \
  "$prompt_tpl" "$tmp_prompt" \
  "$source_tif" "$source_png" "$magnification_token" \
  "$annotation_json" "$annotation_overlay_png" "$vision_prior_json"
from pathlib import Path
import json
import sys

tpl_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
annotation_obj = json.loads(Path(sys.argv[6]).read_text(encoding='utf-8'))
vision_obj = json.loads(Path(sys.argv[8]).read_text(encoding='utf-8'))

repl = {
  "__SOURCE_TIF__": sys.argv[3],
  "__SOURCE_PNG__": sys.argv[4],
  "__MAGNIFICATION_TOKEN__": sys.argv[5],
  "__ANNOTATION_JSON__": json.dumps(annotation_obj, ensure_ascii=False, indent=2),
  "__ANNOTATION_OVERLAY__": sys.argv[7],
  "__VISION_PRIOR_JSON__": json.dumps(vision_obj, ensure_ascii=False, indent=2),
}
text = tpl_path.read_text(encoding='utf-8')
for k, v in repl.items():
  text = text.replace(k, v)
out_path.write_text(text, encoding='utf-8')
PY

image_args=(--image "$source_png" --image "$annotation_overlay_png")
readarray -t _prior < <(python3 - << 'PY' "$vision_prior_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
a=obj.get("artifacts",{})
print(a.get("gradient_png",""))
print(a.get("edges_png",""))
print(a.get("circle_overlay_png",""))
print(a.get("blob_overlay_png",""))
print(a.get("cellpose_overlay_png",""))
PY
)
for p in "${_prior[@]}"; do
  [[ -n "$p" && -f "$p" ]] && image_args+=(--image "$p")
done

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
ok=bool(obj.get('source_tif')) and obj.get('action') in {'accept','retry_with_single_center','skip'}
raise SystemExit(0 if ok else 1)
PY
  then
    break
  fi

  if [[ "$attempt" -eq 2 ]]; then
    echo "Guard prompt returned invalid payload after retries: $output_json"
    exit 1
  fi
  echo "[retry] guard payload invalid; retrying..."
done

echo "Wrote: $output_json"
