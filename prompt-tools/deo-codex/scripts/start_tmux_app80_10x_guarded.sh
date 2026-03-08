#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
app80_root="${1:-$repo_root/DEO/App80 DEO}"
session_name="${2:-deo_app}"
cellpose_mode="${DEO_CELLPOSE_MODE:-auto}"

if [[ ! -d "$app80_root" ]]; then
  echo "App80 folder not found: $app80_root"
  exit 1
fi

if tmux has-session -t "$session_name" 2>/dev/null; then
  tmux kill-session -t "$session_name"
  echo "Stopped existing tmux session: $session_name"
fi

archive_root="$($repo_root/prompt-tools/deo-codex/scripts/archive_app80_outputs.sh)"
# Last line contains concrete archive path.
archive_path="$(printf '%s\n' "$archive_root" | tail -n 2 | head -n 1 | sed 's/^Archive root: //')"

log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
log_file="$log_dir/app80_10x_guarded_tmux_${ts}.log"

cmd="cd \"$repo_root\" && DEO_CELLPOSE_MODE=\"$cellpose_mode\" \"$repo_root/prompt-tools/deo-codex/scripts/run_app80_10x_guarded_batch.sh\" \"$app80_root\" 2>&1 | tee \"$log_file\""

tmux new-session -d -s "$session_name" "bash -lc '$cmd'"

echo "Archive path: $archive_path"
echo "Started tmux session: $session_name"
echo "Log file: $log_file"
echo "Monitor: tmux capture-pane -pt $session_name | tail -n 40"
echo "Attach: tmux attach -t $session_name"
