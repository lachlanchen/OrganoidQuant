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
prompt_tpl="$repo_root/prompt-tools/deo-codex/prompts/01_image_context_and_droplet_annotation.md"
schema="$repo_root/prompt-tools/deo-codex/schemas/01_image_context_and_droplets.schema.json"
model="${DEO_CODEX_MODEL:-gpt-5.3-codex}"

if [[ ! -f "$source_png" ]]; then
  echo "PNG not found: $source_png"
  exit 1
fi

tmp_prompt="$(mktemp)"
trap 'rm -f "$tmp_prompt"' EXIT

experiment_root="$(dirname "$(dirname "$(dirname "$source_tif")")")"

sed \
  -e "s|__SOURCE_TIF__|$source_tif|g" \
  -e "s|__SOURCE_PNG__|$source_png|g" \
  -e "s|__EXPERIMENT_ROOT__|$experiment_root|g" \
  "$prompt_tpl" > "$tmp_prompt"

mkdir -p "$(dirname "$output_json")"

codex exec \
  --model "$model" \
  --dangerously-bypass-approvals-and-sandbox \
  --skip-git-repo-check \
  -C "$repo_root" \
  --output-schema "$schema" \
  --image "$source_png" \
  --output-last-message "$output_json" \
  - < "$tmp_prompt"

echo "Wrote: $output_json"
