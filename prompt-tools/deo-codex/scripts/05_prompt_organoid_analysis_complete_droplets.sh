#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "Usage: $0 <source_tif> <source_png> <annotation_json> <segment_manifest_json> <output_dir>"
  exit 1
fi

source_tif="$1"
source_png="$2"
annotation_json="$3"
segment_manifest_json="$4"
output_dir="$5"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
vision_py_bin="$py_bin"
prompt_tpl="$repo_root/prompt-tools/deo-codex/prompts/05_organoid_analysis_per_complete_droplet.md"
schema="$repo_root/prompt-tools/deo-codex/schemas/05_organoid_analysis_per_complete_droplet.schema.json"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

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

mkdir -p "$output_dir"

job_file="$(mktemp)"
trap 'rm -f "$job_file"' EXIT

python3 - << 'PY' "$annotation_json" "$segment_manifest_json" "$job_file"
import json,sys
ann=json.load(open(sys.argv[1],encoding='utf-8'))
man=json.load(open(sys.argv[2],encoding='utf-8'))
seg_by_id={int(s['droplet_id']):s for s in man.get('segments',[])}
rows=[]
for d in ann.get('droplets',[]):
    did=int(d['droplet_id'])
    is_partial=bool(d.get('is_partial',False))
    completeness=bool(d.get('completeness', not is_partial))
    if is_partial or not completeness:
        continue
    s=seg_by_id.get(did)
    if not s:
        continue
    rows.append({
        'droplet_id': did,
        'segment_png': s['segment_png'],
        'bbox_x0': s.get('bbox_x0',''),
        'bbox_y0': s.get('bbox_y0',''),
        'bbox_x1': s.get('bbox_x1',''),
        'bbox_y1': s.get('bbox_y1',''),
    })
open(sys.argv[3],'w',encoding='utf-8').write('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows))
PY

count=$(python3 - << 'PY' "$job_file"
import sys
n=0
for line in open(sys.argv[1], encoding="utf-8"):
    if line.strip():
        n += 1
print(n)
PY
)
if [[ "$count" == "0" ]]; then
  echo "No complete droplets found for organoid analysis."
  exit 0
fi

echo "Complete droplets to analyze: $count"

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -n "$line" ]] || continue
  did=$(python3 - << 'PY' "$line"
import json,sys
print(json.loads(sys.argv[1])['droplet_id'])
PY
)
  seg_png=$(python3 - << 'PY' "$line"
import json,sys
print(json.loads(sys.argv[1])['segment_png'])
PY
)
  bx0=$(python3 - << 'PY' "$line"
import json,sys
print(json.loads(sys.argv[1])['bbox_x0'])
PY
)
  by0=$(python3 - << 'PY' "$line"
import json,sys
print(json.loads(sys.argv[1])['bbox_y0'])
PY
)
  bx1=$(python3 - << 'PY' "$line"
import json,sys
print(json.loads(sys.argv[1])['bbox_x1'])
PY
)
  by1=$(python3 - << 'PY' "$line"
import json,sys
print(json.loads(sys.argv[1])['bbox_y1'])
PY
)

  out_json="$output_dir/droplet_$(printf '%03d' "$did")_organoids.json"
  tmp_prompt="$(mktemp)"
  tmp_compact_json="$(mktemp)"

  vision_prior_json="$output_dir/droplet_$(printf '%03d' "$did")_vision_prior.json"
  vision_prior_dir="$output_dir/droplet_$(printf '%03d' "$did")_vision_prior_artifacts"
  "$vision_py_bin" "$repo_root/prompt-tools/deo-codex/scripts/00_build_vision_priors.py" \
    --source-png "$seg_png" \
    --out-json "$vision_prior_json" \
    --out-dir "$vision_prior_dir" \
    --mode organoid \
    --cellpose-mode "$cellpose_mode" > /dev/null

  python3 - << 'PY' "$vision_prior_json" "$tmp_compact_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
compact={
  "mode": obj.get("mode"),
  "magnification_token": obj.get("magnification_token"),
  "image_size": [obj.get("image_width_px"), obj.get("image_height_px")],
  "stats": obj.get("stats",{}),
  "blob_candidates_top": obj.get("blob_candidates",[])[:20],
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
print(a.get("blob_overlay_png","N/A"))
print(a.get("cellpose_overlay_png","N/A"))
PY
)
  prior_gradient="${_prior[0]:-N/A}"
  prior_edges="${_prior[1]:-N/A}"
  prior_blob_overlay="${_prior[2]:-N/A}"
  prior_cellpose_overlay="${_prior[3]:-N/A}"

  python3 - << 'PY' \
    "$prompt_tpl" "$tmp_prompt" \
    "$source_tif" "$source_png" "$did" "$seg_png" \
    "$bx0" "$by0" "$bx1" "$by1" \
    "$magnification_token" \
    "$prior_gradient" "$prior_edges" "$prior_blob_overlay" "$prior_cellpose_overlay" \
    "$tmp_compact_json"
from pathlib import Path
import sys
tpl_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
vision_json = Path(sys.argv[16]).read_text(encoding="utf-8")
repl = {
  "__SOURCE_TIF__": sys.argv[3],
  "__SOURCE_PNG__": sys.argv[4],
  "__DROPLET_ID__": str(sys.argv[5]),
  "__SEGMENT_PNG__": sys.argv[6],
  "__BBOX_X0__": str(sys.argv[7]),
  "__BBOX_Y0__": str(sys.argv[8]),
  "__BBOX_X1__": str(sys.argv[9]),
  "__BBOX_Y1__": str(sys.argv[10]),
  "__MAGNIFICATION_TOKEN__": str(sys.argv[11]),
  "__VISION_PRIOR_GRADIENT__": sys.argv[12],
  "__VISION_PRIOR_EDGES__": sys.argv[13],
  "__VISION_PRIOR_BLOB_OVERLAY__": sys.argv[14],
  "__VISION_PRIOR_CELLPOSE_OVERLAY__": sys.argv[15],
  "__VISION_PRIOR_JSON__": vision_json,
}
text = tpl_path.read_text(encoding="utf-8")
for k, v in repl.items():
  text = text.replace(k, v)
out_path.write_text(text, encoding="utf-8")
PY

  image_args=(--image "$source_png" --image "$seg_png")
  [[ -f "$prior_gradient" ]] && image_args+=(--image "$prior_gradient")
  [[ -f "$prior_edges" ]] && image_args+=(--image "$prior_edges")
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
      --output-last-message "$out_json" \
      - < "$tmp_prompt"

    if python3 - << 'PY' "$out_json" "$did"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
did=int(sys.argv[2])
ok=obj.get("droplet_id")==did and isinstance(obj.get("organoids",[]), list) and "organoid_count_visual" in obj
raise SystemExit(0 if ok else 1)
PY
    then
      break
    fi
    if [[ "$attempt" -eq 2 ]]; then
      echo "Organoid prompt returned invalid payload for droplet $did: $out_json"
      rm -f "$tmp_prompt" "$tmp_compact_json"
      exit 1
    fi
    echo "[retry] organoid payload looked invalid for droplet $did; retrying..."
  done

  rm -f "$tmp_prompt" "$tmp_compact_json"
  echo "Wrote: $out_json"
done < "$job_file"
