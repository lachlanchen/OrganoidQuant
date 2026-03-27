#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <set_root> <output_json> [prompt_txt]"
  exit 1
fi

set_root="$1"
output_json="$2"
prompt_txt="${3:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script_dir="$repo_root/analysis-tools/fusion_blind_prompt"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"
blinded_dir="$set_root/blinded_images"
run_dir="$(mktemp -d "${TMPDIR:-/tmp}/fusion_blind_prompt_XXXXXX")"
trap 'rm -rf "$run_dir"' EXIT

mkdir -p "$(dirname "$output_json")"

/home/lachlan/miniconda3/envs/organoid/bin/python "$script_dir/build_blinded_image_bundle.py" "$blinded_dir" "$run_dir/bundle" >/dev/null
manifest="$run_dir/bundle/bundle_manifest.json"
contact_sheet="$run_dir/bundle/contact_sheet.png"
schema_copy="$run_dir/blind_set_fusion.schema.json"
cp "$script_dir/blind_set_fusion.schema.json" "$schema_copy"

uid_json="$run_dir/uids.json"
/home/lachlan/miniconda3/envs/organoid/bin/python - <<'PY' "$manifest" "$uid_json"
import json, sys
manifest = json.load(open(sys.argv[1], 'r', encoding='utf-8'))
json.dump(manifest['uids_in_order'], open(sys.argv[2], 'w', encoding='utf-8'))
PY

prompt_file="$run_dir/prompt.md"
/home/lachlan/miniconda3/envs/organoid/bin/python - <<'PY' "$script_dir/blind_set_fusion_prompt.md" "$prompt_file" "$uid_json" "$manifest"
import json, sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding='utf-8')
out = Path(sys.argv[2])
uid_list = Path(sys.argv[3]).read_text(encoding='utf-8')
manifest = json.load(open(sys.argv[4], 'r', encoding='utf-8'))
text = src.replace('__UID_LIST_JSON__', uid_list).replace('__IMAGE_COUNT__', str(manifest['image_count']))
out.write_text(text, encoding='utf-8')
PY

if [[ -n "$prompt_txt" ]]; then
  cp "$prompt_file" "$prompt_txt"
fi

validate_json() {
  /home/lachlan/miniconda3/envs/organoid/bin/python - <<'PY' "$1" "$2"
import json, sys
from pathlib import Path
obj = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
manifest = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
expected = manifest['uids_in_order']
if obj['uids_in_order'] != expected:
    raise SystemExit('uids_in_order mismatch')
if set(obj['ranking_by_fusion_uid_desc']) != set(expected):
    raise SystemExit('ranking uid set mismatch')
seen = [item['uid'] for item in obj['images']]
if seen != expected:
    raise SystemExit('image uid order mismatch')
for item in obj['images']:
    if not (0 <= float(item['fusion_score_0_to_5']) <= 5):
        raise SystemExit('fusion out of range')
    for key in ('largest_mass_relative_0_to_100', 'size_relative_0_to_100', 'perimeter_complexity_0_to_100'):
        if not (0 <= float(item[key]) <= 100):
            raise SystemExit(f'{key} out of range')
    if not (0 <= float(item['confidence_0_to_1']) <= 1):
        raise SystemExit('confidence out of range')
print('ok')
PY
}

cmd=(codex exec
  --model "$model"
  -c 'model_reasoning_effort="medium"'
  --dangerously-bypass-approvals-and-sandbox
  --skip-git-repo-check
  -C "$run_dir"
  --output-schema "$schema_copy"
  --image "$contact_sheet")
while IFS= read -r png; do
  cmd+=(--image "$png")
done < <(/home/lachlan/miniconda3/envs/organoid/bin/python - <<'PY' "$manifest"
import json, sys
manifest = json.load(open(sys.argv[1], 'r', encoding='utf-8'))
for item in manifest['images']:
    print(item['png_path'])
PY
)
cmd+=(--output-last-message "$output_json" -)
"${cmd[@]}" < "$prompt_file"

if ! validate_json "$output_json" "$manifest" >/dev/null; then
  cat >> "$prompt_file" <<'RETRY'

Retry override:
- The previous answer was invalid or incomplete.
- Return JSON only.
- Keep the same UID order as provided.
- Ensure every UID appears exactly once in images[] and in the ranking list.
RETRY
  if [[ -n "$prompt_txt" ]]; then
    cp "$prompt_file" "${prompt_txt%.txt}_retry.txt"
  fi
  "${cmd[@]}" < "$prompt_file"
fi

validate_json "$output_json" "$manifest" >/dev/null
