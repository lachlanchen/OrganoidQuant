#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <source_tif> [output_root]"
  exit 1
fi

source_tif="$1"
output_root="${2:-}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"
codex_timeout_sec="${DEO_CODEX_TIMEOUT_SEC:-600}"

if [[ -z "$output_root" ]]; then
  output_root="$repo_root/api-tests/organoid_codex_polygon_segmentation_test/output"
fi

mkdir -p "$output_root"

date_label="$(basename "$(dirname "$source_tif")")"
stem="$(basename "$source_tif" .tif)"
stamp="$(date +%Y%m%d_%H%M%S)"
run_dir="$output_root/${date_label}_${stem}_${stamp}"
mkdir -p "$run_dir"
echo "run_dir=$run_dir"

source_png="$run_dir/${stem}.png"
"$py_bin" - <<'PY' "$source_tif" "$source_png"
from pathlib import Path
from PIL import Image
import sys
src = Path(sys.argv[1])
dst = Path(sys.argv[2])
with Image.open(src) as im:
    im.save(dst, format="PNG")
PY

run_cellpose_branch() {
  local branch_name="$1"
  shift
  local branch_root="$run_dir/$branch_name"
  mkdir -p "$branch_root"
  if "$repo_root/api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.sh" \
      --input-tif "$source_tif" \
      --output-root "$branch_root" \
      "$@" >"$branch_root/subprocess.log" 2>&1; then
    find "$branch_root" -name run_manifest.json | sort | tail -n 1 || true
  fi
}

run_cellpose_branch_with_retry() {
  local branch_name="$1"
  shift
  local manifest
  manifest="$(run_cellpose_branch "$branch_name" "$@")"
  if [[ -z "$manifest" ]]; then
    manifest="$(run_cellpose_branch "${branch_name}_retry" "$@")"
  fi
  printf '%s\n' "$manifest"
}

validate_polygon_json() {
  "$py_bin" - <<'PY' "$1" "$2" "$3"
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
if not json_path.is_file():
    raise SystemExit(1)
obj = json.loads(json_path.read_text(encoding="utf-8"))
if int(obj.get("image_width_px", 0)) < 2 or int(obj.get("image_height_px", 0)) < 2:
    raise SystemExit(1)
if len(obj.get("organoids", [])) < 1:
    raise SystemExit(1)
if not isinstance(obj.get("source_tif"), str) or not obj.get("source_tif"):
    raise SystemExit(1)
if not isinstance(obj.get("source_png"), str) or not obj.get("source_png"):
    raise SystemExit(1)
raise SystemExit(0)
PY
}

run_codex_pass() {
  local prompt_file="$1"
  local output_json="$2"
  shift 2
  local image_args=("$@")
  timeout --preserve-status "$codex_timeout_sec" \
    codex exec \
    --model "$model" \
    -c 'model_reasoning_effort="low"' \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    -C "$repo_root" \
    --output-schema "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/schema.json" \
    "${image_args[@]}" \
    --output-last-message "$output_json" \
    - < "$prompt_file"
}

small_manifest="$(
  run_cellpose_branch_with_retry cellpose_small \
    --diameter 32 \
    --cellprob-threshold -1.5 \
    --flow-threshold 0.4 \
    --min-area-px 60 \
    --max-area-fraction 0.18 \
    --resize-max-dim 1280
)"

large_manifest="$(
  run_cellpose_branch_with_retry cellpose_large \
    --diameter 140 \
    --cellprob-threshold -3.0 \
    --flow-threshold 0.2 \
    --min-area-px 900 \
    --max-area-fraction 0.75 \
    --resize-max-dim 1280
)"

prior_json="$run_dir/general_prior.json"
prior_dir="$run_dir/general_prior_artifacts"
"$py_bin" "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/build_general_image_prior.py" \
  --source-png "$source_png" \
  --out-json "$prior_json" \
  --out-dir "$prior_dir" \
  --cellpose-small-manifest "$small_manifest" \
  --cellpose-large-manifest "$large_manifest" > /dev/null

readarray -t prior_paths < <("$py_bin" - <<'PY' "$prior_json"
import json
import sys

obj = json.load(open(sys.argv[1], encoding="utf-8"))
art = obj["artifacts"]
print(art.get("combined_prior_overlay_png", ""))
print(art.get("mass_overlay_png", ""))
print(art.get("edge_overlay_png", ""))
print(art.get("cellpose_small_overlay_png", ""))
print(art.get("cellpose_large_overlay_png", ""))
PY
)

combined_prior_overlay_png="${prior_paths[0]:-}"
mass_overlay_png="${prior_paths[1]:-}"
edge_overlay_png="${prior_paths[2]:-}"
cellpose_small_overlay_png="${prior_paths[3]:-}"
cellpose_large_overlay_png="${prior_paths[4]:-}"

tmp_coarse_prompt="$(mktemp)"
tmp_refine_prompt="$(mktemp)"
trap 'rm -f "$tmp_coarse_prompt" "$tmp_refine_prompt"' EXIT

"$py_bin" - <<'PY' \
  "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/prompt_coarse.md" \
  "$tmp_coarse_prompt" \
  "$source_tif" "$source_png" "$prior_json" \
  "$combined_prior_overlay_png" "$mass_overlay_png" "$edge_overlay_png"
from pathlib import Path
import json
import re
import sys

tpl_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
source_tif = sys.argv[3]
source_png = sys.argv[4]
prior_json_path = Path(sys.argv[5])
combined_prior_overlay_png = sys.argv[6]
mass_overlay_png = sys.argv[7]
edge_overlay_png = sys.argv[8]
prior = json.loads(prior_json_path.read_text(encoding="utf-8"))
prompt_prior = {
    "image_width_px": prior.get("image_width_px"),
    "image_height_px": prior.get("image_height_px"),
    "blob_candidates": prior.get("blob_candidates", [])[:8],
    "large_mass_candidates": prior.get("large_mass_candidates", [])[:8],
    "cellpose_small": {
        "filtered_mask_count": prior.get("cellpose_small", {}).get("filtered_mask_count", 0),
        "stats_top": prior.get("cellpose_small", {}).get("stats_top", [])[:8],
    },
    "cellpose_large": {
        "filtered_mask_count": prior.get("cellpose_large", {}).get("filtered_mask_count", 0),
        "stats_top": prior.get("cellpose_large", {}).get("stats_top", [])[:8],
    },
}
m = re.search(r'(\d+x)', Path(source_tif).name, flags=re.IGNORECASE)
magnification = m.group(1).lower() if m else "unknown"
repl = {
    "__SOURCE_TIF__": source_tif,
    "__SOURCE_PNG__": source_png,
    "__MAGNIFICATION_TOKEN__": magnification,
    "__PRIOR_JSON__": json.dumps(prompt_prior, ensure_ascii=False, indent=2),
}
text = tpl_path.read_text(encoding="utf-8")
for k, v in repl.items():
    text = text.replace(k, v)
out_path.write_text(text, encoding="utf-8")
PY

cp "$tmp_coarse_prompt" "$run_dir/coarse_prompt.txt"

coarse_output_json="$run_dir/coarse_polygon_response.json"
coarse_images=(
  --image "$source_png" \
  --image "$combined_prior_overlay_png" \
  --image "$mass_overlay_png" \
  --image "$edge_overlay_png" \
)
run_codex_pass "$tmp_coarse_prompt" "$coarse_output_json" "${coarse_images[@]}"
if ! validate_polygon_json "$coarse_output_json" "$source_tif" "$source_png"; then
  cat >> "$tmp_coarse_prompt" <<'EOF'

Retry override:
- The previous attempt was placeholder, empty, or invalid.
- Do not output progress or analysis text.
- Do not use tools or shell commands.
- Return final concrete JSON with real polygon coordinates now.
EOF
  cp "$tmp_coarse_prompt" "$run_dir/coarse_prompt_retry.txt"
  run_codex_pass "$tmp_coarse_prompt" "$coarse_output_json" "${coarse_images[@]}"
fi
validate_polygon_json "$coarse_output_json" "$source_tif" "$source_png"

"$py_bin" "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/render_polygon_outputs.py" \
  --source-png "$source_png" \
  --polygon-json "$coarse_output_json" \
  --out-dir "$run_dir" \
  --prefix "coarse_"

"$py_bin" - <<'PY' \
  "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/prompt_refine.md" \
  "$tmp_refine_prompt" \
  "$source_tif" "$source_png" "$prior_json" "$coarse_output_json" \
  "$run_dir/coarse_polygon_overlay.png" "$combined_prior_overlay_png" "$edge_overlay_png"
from pathlib import Path
import json
import re
import sys

tpl_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
source_tif = sys.argv[3]
source_png = sys.argv[4]
prior_json_path = Path(sys.argv[5])
coarse_json_path = Path(sys.argv[6])
coarse_overlay_png = sys.argv[7]
combined_prior_overlay_png = sys.argv[8]
edge_overlay_png = sys.argv[9]
prior = json.loads(prior_json_path.read_text(encoding="utf-8"))
coarse = json.loads(coarse_json_path.read_text(encoding="utf-8"))
prompt_prior = {
    "image_width_px": prior.get("image_width_px"),
    "image_height_px": prior.get("image_height_px"),
    "blob_candidates": prior.get("blob_candidates", [])[:8],
    "large_mass_candidates": prior.get("large_mass_candidates", [])[:8],
    "cellpose_small": {
        "filtered_mask_count": prior.get("cellpose_small", {}).get("filtered_mask_count", 0),
        "stats_top": prior.get("cellpose_small", {}).get("stats_top", [])[:8],
    },
    "cellpose_large": {
        "filtered_mask_count": prior.get("cellpose_large", {}).get("filtered_mask_count", 0),
        "stats_top": prior.get("cellpose_large", {}).get("stats_top", [])[:8],
    },
}
m = re.search(r'(\d+x)', Path(source_tif).name, flags=re.IGNORECASE)
magnification = m.group(1).lower() if m else "unknown"
repl = {
    "__SOURCE_TIF__": source_tif,
    "__SOURCE_PNG__": source_png,
    "__MAGNIFICATION_TOKEN__": magnification,
    "__PRIOR_JSON__": json.dumps(prompt_prior, ensure_ascii=False, indent=2),
    "__COARSE_JSON__": json.dumps(coarse, ensure_ascii=False, indent=2),
}
text = tpl_path.read_text(encoding="utf-8")
for k, v in repl.items():
    text = text.replace(k, v)
out_path.write_text(text, encoding="utf-8")
PY

cp "$tmp_refine_prompt" "$run_dir/refine_prompt.txt"

output_json="$run_dir/polygon_response.json"
refine_images=(
  --image "$source_png" \
  --image "$run_dir/coarse_polygon_overlay.png" \
  --image "$combined_prior_overlay_png" \
  --image "$edge_overlay_png" \
)
refine_ok=0
if run_codex_pass "$tmp_refine_prompt" "$output_json" "${refine_images[@]}"; then
  if validate_polygon_json "$output_json" "$source_tif" "$source_png"; then
    refine_ok=1
  fi
fi
if [[ "$refine_ok" -ne 1 ]]; then
  cat >> "$tmp_refine_prompt" <<'EOF'

Retry override:
- The previous attempt was placeholder, empty, or invalid.
- Do not output progress or analysis text.
- Do not use tools or shell commands.
- Keep the same organoid IDs where possible.
- Return final concrete JSON with corrected polygon coordinates now.
EOF
  cp "$tmp_refine_prompt" "$run_dir/refine_prompt_retry.txt"
  if run_codex_pass "$tmp_refine_prompt" "$output_json" "${refine_images[@]}"; then
    if validate_polygon_json "$output_json" "$source_tif" "$source_png"; then
      refine_ok=1
    fi
  fi
fi
if [[ "$refine_ok" -ne 1 ]]; then
  cp "$coarse_output_json" "$output_json"
fi
validate_polygon_json "$output_json" "$source_tif" "$source_png"

"$py_bin" "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/render_polygon_outputs.py" \
  --source-png "$source_png" \
  --polygon-json "$output_json" \
  --out-dir "$run_dir"

"$py_bin" - <<'PY' \
  "$run_dir" "$source_png" "$prior_json" "$small_manifest" "$large_manifest"
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
source_png = Path(sys.argv[2])
prior_json = sys.argv[3]
small_manifest = sys.argv[4]
large_manifest = sys.argv[5]
manifest = {
    "pipeline": "cellpose_small_large_plus_codex_coarse_refine",
    "run_dir": str(run_dir),
    "source_png": str(source_png),
    "prior_json": prior_json,
    "cellpose_small_manifest": small_manifest,
    "cellpose_large_manifest": large_manifest,
    "coarse_prompt_file": str(run_dir / "coarse_prompt.txt"),
    "coarse_polygon_response_json": str(run_dir / "coarse_polygon_response.json"),
    "coarse_polygon_overlay_png": str(run_dir / "coarse_polygon_overlay.png"),
    "coarse_polygon_instance_rgb_png": str(run_dir / "coarse_polygon_instance_rgb.png"),
    "coarse_polygon_labels_16bit_png": str(run_dir / "coarse_polygon_labels_16bit.png"),
    "coarse_polygon_stats_json": str(run_dir / "coarse_polygon_stats.json"),
    "refine_prompt_file": str(run_dir / "refine_prompt.txt"),
    "polygon_response_json": str(run_dir / "polygon_response.json"),
    "polygon_overlay_png": str(run_dir / "polygon_overlay.png"),
    "polygon_instance_rgb_png": str(run_dir / "polygon_instance_rgb.png"),
    "polygon_labels_16bit_png": str(run_dir / "polygon_labels_16bit.png"),
    "polygon_stats_json": str(run_dir / "polygon_stats.json"),
}
(run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
PY

echo "Wrote: $run_dir"
