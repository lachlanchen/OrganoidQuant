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
src=Path(sys.argv[1]); dst=Path(sys.argv[2])
with Image.open(src) as im:
    im.save(dst, format="PNG")
PY

cellpose_dir="$run_dir/cellpose_prior"
mkdir -p "$cellpose_dir"
small_manifest=""
if "$repo_root/api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.sh" \
  --input-tif "$source_tif" \
  --output-root "$cellpose_dir" \
  --diameter 32 \
  --cellprob-threshold -1.5 \
  --flow-threshold 0.4 \
  --min-area-px 60 \
  --max-area-fraction 0.18 \
  --resize-max-dim 1536 >"$cellpose_dir/subprocess.log" 2>&1; then
  small_manifest="$(find "$cellpose_dir" -name run_manifest.json | sort | tail -n 1 || true)"
fi

cellpose_overlay=""
if [[ -n "$small_manifest" ]]; then
  cellpose_overlay="$("$py_bin" - <<'PY' "$small_manifest"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj.get("overlay_png",""))
PY
)"
fi

prior_json="$run_dir/general_prior.json"
prior_dir="$run_dir/general_prior_artifacts"
"$py_bin" "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/build_general_image_prior.py" \
  --source-png "$source_png" \
  --out-json "$prior_json" \
  --out-dir "$prior_dir" \
  --cellpose-overlay "$cellpose_overlay" > /dev/null

readarray -t prior_paths < <("$py_bin" - <<'PY' "$prior_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
a=obj["artifacts"]
print(a.get("gradient_png",""))
print(a.get("edge_overlay_png",""))
print(a.get("blob_overlay_png",""))
print(a.get("mass_overlay_png",""))
print(a.get("cellpose_overlay_png",""))
PY
)
gradient_png="${prior_paths[0]:-}"
edge_overlay_png="${prior_paths[1]:-}"
blob_overlay_png="${prior_paths[2]:-}"
mass_overlay_png="${prior_paths[3]:-}"
cellpose_overlay_png="${prior_paths[4]:-}"

tmp_prompt="$(mktemp)"
trap 'rm -f "$tmp_prompt"' EXIT
"$py_bin" - <<'PY' \
  "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/prompt.md" \
  "$tmp_prompt" \
  "$source_tif" "$source_png" "$prior_json" \
  "$gradient_png" "$edge_overlay_png" "$blob_overlay_png" "$mass_overlay_png" "$cellpose_overlay_png"
from pathlib import Path
import json, re, sys
tpl_path=Path(sys.argv[1]); out_path=Path(sys.argv[2])
source_tif=sys.argv[3]; source_png=sys.argv[4]; prior_json_path=Path(sys.argv[5])
gradient_png, edge_overlay_png, blob_overlay_png, mass_overlay_png, cellpose_overlay_png = sys.argv[6:11]
prior=json.loads(prior_json_path.read_text(encoding='utf-8'))
m=re.search(r'(\d+x)', Path(source_tif).name, flags=re.IGNORECASE)
magnification=m.group(1).lower() if m else "unknown"
repl={
  "__SOURCE_TIF__": source_tif,
  "__SOURCE_PNG__": source_png,
  "__MAGNIFICATION_TOKEN__": magnification,
  "__GRADIENT_PNG__": gradient_png,
  "__EDGE_OVERLAY_PNG__": edge_overlay_png,
  "__BLOB_OVERLAY_PNG__": blob_overlay_png,
  "__MASS_OVERLAY_PNG__": mass_overlay_png,
  "__CELLPOSE_OVERLAY_PNG__": cellpose_overlay_png or "N/A",
  "__PRIOR_JSON__": json.dumps(prior, ensure_ascii=False, indent=2),
}
text=tpl_path.read_text(encoding='utf-8')
for k,v in repl.items():
    text=text.replace(k,v)
out_path.write_text(text, encoding='utf-8')
PY

cp "$tmp_prompt" "$run_dir/prompt.txt"

output_json="$run_dir/polygon_response.json"
image_args=(--image "$source_png")
[[ -f "$gradient_png" ]] && image_args+=(--image "$gradient_png")
[[ -f "$edge_overlay_png" ]] && image_args+=(--image "$edge_overlay_png")
[[ -f "$blob_overlay_png" ]] && image_args+=(--image "$blob_overlay_png")
[[ -f "$mass_overlay_png" ]] && image_args+=(--image "$mass_overlay_png")
[[ -f "$cellpose_overlay_png" ]] && image_args+=(--image "$cellpose_overlay_png")

codex exec \
  --model "$model" \
  --dangerously-bypass-approvals-and-sandbox \
  --skip-git-repo-check \
  -C "$repo_root" \
  --output-schema "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/schema.json" \
  "${image_args[@]}" \
  --output-last-message "$output_json" \
  - < "$tmp_prompt"

"$py_bin" "$repo_root/api-tests/organoid_codex_polygon_segmentation_test/render_polygon_outputs.py" \
  --source-png "$source_png" \
  --polygon-json "$output_json" \
  --out-dir "$run_dir"

"$py_bin" - <<'PY' "$run_dir" "$source_png"
import json, sys
from pathlib import Path
run_dir = Path(sys.argv[1])
source_png = Path(sys.argv[2])
manifest = {
    "run_dir": str(run_dir),
    "source_png": str(source_png),
    "prompt_file": str(run_dir / "prompt.txt"),
    "prior_json": str(run_dir / "general_prior.json"),
    "polygon_response_json": str(run_dir / "polygon_response.json"),
    "polygon_overlay_png": str(run_dir / "polygon_overlay.png"),
    "polygon_instance_rgb_png": str(run_dir / "polygon_instance_rgb.png"),
    "polygon_labels_16bit_png": str(run_dir / "polygon_labels_16bit.png"),
    "polygon_stats_json": str(run_dir / "polygon_stats.json"),
}
(run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
PY

echo "Wrote: $run_dir"
