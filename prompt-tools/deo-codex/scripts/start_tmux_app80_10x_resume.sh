#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
app80_root="${1:-$repo_root/DEO/App80 DEO}"
session_name="${2:-deo_app_resume}"
max_samples_per_date="${3:-${DEO_MAX_SAMPLES_PER_DATE:-3}}"
skip_tif="${4:-}"

if [[ ! -d "$app80_root" ]]; then
  echo "App80 folder not found: $app80_root"
  exit 1
fi

if tmux has-session -t "$session_name" 2>/dev/null; then
  echo "tmux session already exists: $session_name"
  exit 1
fi

log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
log_file="$log_dir/app80_10x_resume_tmux_${ts}.log"

cmd="cd \"$repo_root\" && \"$repo_root/prompt-tools/deo-codex/scripts/run_app80_10x_resume_batch.sh\" \"$app80_root\" \"$max_samples_per_date\" \"$skip_tif\" 2>&1 | tee \"$log_file\""
tmux new-session -d -s "$session_name" "bash -lc '$cmd'"

echo "Started tmux session: $session_name"
echo "max_samples_per_date: $max_samples_per_date"
echo "skip_tif: $skip_tif"
echo "Log file: $log_file"
echo "Monitor: tmux capture-pane -pt $session_name | tail -n 40"
echo "Attach: tmux attach -t $session_name"
