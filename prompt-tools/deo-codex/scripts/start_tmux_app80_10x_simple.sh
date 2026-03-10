#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
app80_root="${1:-$repo_root/DEO/App80 DEO}"
session_name="${2:-deo_app}"
max_samples_per_date="${3:-${DEO_MAX_SAMPLES_PER_DATE:-0}}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

if [[ ! -d "$app80_root" ]]; then
  echo "App80 folder not found: $app80_root"
  exit 1
fi

if tmux has-session -t "$session_name" 2>/dev/null; then
  tmux kill-session -t "$session_name"
  echo "Stopped existing tmux session: $session_name"
fi

archive_output="$("$repo_root/prompt-tools/deo-codex/scripts/archive_app80_outputs.sh")"
archive_path="$(printf '%s\n' "$archive_output" | sed -n 's/^Archive root: //p' | tail -n 1)"

log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
log_file="$log_dir/app80_10x_simple_tmux_${ts}.log"

cmd="cd \"$repo_root\" && DEO_CELLPOSE_MODE=\"$cellpose_mode\" DEO_MAX_SAMPLES_PER_DATE=\"$max_samples_per_date\" \"$repo_root/prompt-tools/deo-codex/scripts/run_app80_10x_simple_batch.sh\" \"$app80_root\" \"$max_samples_per_date\" 2>&1 | tee \"$log_file\""

tmux new-session -d -s "$session_name" "bash -lc '$cmd'"

echo "Archive path: $archive_path"
echo "Started tmux session: $session_name"
echo "max_samples_per_date: $max_samples_per_date"
echo "Log file: $log_file"
echo "Monitor: tmux capture-pane -pt $session_name | tail -n 40"
echo "Attach: tmux attach -t $session_name"
