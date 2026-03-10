#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "Usage: $0 <source_tif> <source_png> <annotation_json> <segment_manifest_json> <output_json>"
  exit 1
fi

source_tif="$1"
source_png="$2"
annotation_json="$3"
segment_manifest_json="$4"
output_json="$5"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
prompt_tpl="$repo_root/prompt-tools/deo-codex/prompts/03_droplet_level_quantification.md"
schema="$repo_root/prompt-tools/deo-codex/schemas/03_droplet_level_quantification.schema.json"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"

for f in "$source_png" "$annotation_json" "$segment_manifest_json"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing file: $f"
    exit 1
  fi
done

segment_images_file="$(mktemp)"
tmp_prompt="$(mktemp)"
trap 'rm -f "$segment_images_file" "$tmp_prompt"' EXIT

python3 - << 'PY' "$segment_manifest_json" "$segment_images_file"
import json,sys
manifest=json.load(open(sys.argv[1],encoding='utf-8'))
with open(sys.argv[2],'w',encoding='utf-8') as f:
    for seg in manifest.get('segments',[]):
        p=seg.get('segment_png')
        if p:
            f.write(p+'\n')
PY

python3 - << 'PY' "$prompt_tpl" "$source_tif" "$source_png" "$segment_manifest_json" "$annotation_json" "$tmp_prompt"
import json,sys
from pathlib import Path

prompt_tpl=Path(sys.argv[1]).read_text(encoding='utf-8')
source_tif=sys.argv[2]
source_png=sys.argv[3]
manifest_path=sys.argv[4]
annotation=json.loads(Path(sys.argv[5]).read_text(encoding='utf-8'))
out_path=Path(sys.argv[6])

rendered=(prompt_tpl
    .replace('__SOURCE_TIF__', source_tif)
    .replace('__SOURCE_PNG__', source_png)
    .replace('__SEGMENT_MANIFEST_PATH__', manifest_path)
    .replace('__ANNOTATION_JSON_CONTENT__', json.dumps(annotation, ensure_ascii=False, indent=2))
)
out_path.write_text(rendered, encoding='utf-8')
PY

mkdir -p "$(dirname "$output_json")"

cmd=(codex exec --model "$model" --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C "$repo_root" --output-schema "$schema" --image "$source_png" --output-last-message "$output_json" -)
while IFS= read -r img; do
  [[ -n "$img" ]] || continue
  cmd+=(--image "$img")
done < "$segment_images_file"

for attempt in 1 2; do
  "${cmd[@]}" < "$tmp_prompt"
  if python3 - << 'PY' "$output_json"
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
ok=bool(obj.get('source_tif')) and bool(obj.get('source_png')) and len(obj.get('droplets',[]))>0 and obj.get('image_level',{}).get('droplet_count_including_partials',0)>0
raise SystemExit(0 if ok else 1)
PY
  then
    break
  fi
  if [[ "$attempt" -eq 2 ]]; then
    echo "Quant prompt returned invalid/empty payload after retries: $output_json"
    exit 1
  fi
  echo "[retry] quant payload looked empty; retrying prompt..."
done

echo "Wrote: $output_json"
