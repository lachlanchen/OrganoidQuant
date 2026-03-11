#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
subtree_root="${1:?subtree_root is required}"
session_name="${2:-deo_app}"
skip_tif="${3:-}"

if [[ ! -d "$subtree_root" ]]; then
  echo "Subtree folder not found: $subtree_root"
  exit 1
fi

if tmux has-session -t "$session_name" 2>/dev/null; then
  echo "tmux session already exists: $session_name"
  exit 1
fi

log_dir="$repo_root/data-docs/logs"
mkdir -p "$log_dir"
ts="$(date +%Y%m%d_%H%M%S)"
log_file="$log_dir/remaining_10x_subtree_tmux_${ts}.log"

cmd="cd \"$repo_root\" && \"$repo_root/prompt-tools/deo-codex/scripts/run_remaining_10x_subtree_batch.sh\" \"$subtree_root\" \"$skip_tif\" 2>&1 | tee \"$log_file\""
tmux new-session -d -s "$session_name" "bash -lc '$cmd'"

echo "Started tmux session: $session_name"
echo "subtree_root: $subtree_root"
echo "skip_tif: $skip_tif"
echo "Log file: $log_file"
echo "Monitor: tmux capture-pane -pt $session_name | tail -n 40"
echo "Attach: tmux attach -t $session_name"
