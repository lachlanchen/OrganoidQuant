#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <panel_png> <rows> <cols> <output_json> [prompt_txt]"
  exit 1
fi

panel_png="$1"
rows="$2"
cols="$3"
output_json="$4"
prompt_txt="${5:-}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"
script_dir="$repo_root/analysis-tools/app80_panel_prompt_metrics"

validate_json() {
  python - <<'PY' "$1" "$2" "$3"
import json, sys
from pathlib import Path
path=Path(sys.argv[1])
rows=int(sys.argv[2])
cols=int(sys.argv[3])
obj=json.loads(path.read_text(encoding='utf-8'))
for key in ('fusion_2d','size_2d','perimeter_2d'):
    arr=obj[key]
    if len(arr)!=rows:
        raise SystemExit(1)
    for r in arr:
        if len(r)!=cols:
            raise SystemExit(1)
for row in obj['fusion_2d']:
    for v in row:
        if v is not None and not (0 <= float(v) <= 5):
            raise SystemExit(1)
for key in ('size_2d','perimeter_2d'):
    for row in obj[key]:
        for v in row:
            if v is not None and not (0 <= float(v) <= 100):
                raise SystemExit(1)
print('ok')
PY
}

build_prompt() {
  python - <<'PY' "$script_dir/panel_metric_prompt.md" "$1" "$2" "$3"
from pathlib import Path
import sys
src=Path(sys.argv[1])
out=Path(sys.argv[2])
rows=sys.argv[3]
cols=sys.argv[4]
text=src.read_text(encoding='utf-8')
text=text.replace('__ROWS__', rows).replace('__COLS__', cols)
out.write_text(text, encoding='utf-8')
PY
}

tmp_prompt="$(mktemp)"
trap 'rm -f "$tmp_prompt"' EXIT
build_prompt "$tmp_prompt" "$rows" "$cols"
if [[ -n "$prompt_txt" ]]; then
  cp "$tmp_prompt" "$prompt_txt"
fi

run_once() {
  local prompt_file="$1"
  codex exec \
    --model "$model" \
    -c 'model_reasoning_effort="low"' \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    -C "$repo_root" \
    --output-schema "$script_dir/panel_metric.schema.json" \
    --image "$panel_png" \
    --output-last-message "$output_json" \
    - < "$prompt_file"
}

mkdir -p "$(dirname "$output_json")"
run_once "$tmp_prompt"
if ! validate_json "$output_json" "$rows" "$cols" >/dev/null; then
  cat >> "$tmp_prompt" <<'RETRY'

Retry override:
- The previous answer was invalid or incomplete.
- Return only final JSON.
- Keep arrays exactly aligned to the visible grid.
- Use null for blank tiles.
RETRY
  if [[ -n "$prompt_txt" ]]; then
    cp "$tmp_prompt" "${prompt_txt%.txt}_retry.txt"
  fi
  run_once "$tmp_prompt"
fi
validate_json "$output_json" "$rows" "$cols" >/dev/null
