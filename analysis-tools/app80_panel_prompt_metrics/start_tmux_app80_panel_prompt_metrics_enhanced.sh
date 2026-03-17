#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runner="$repo_root/analysis-tools/app80_panel_prompt_metrics/run_app80_panel_prompt_metrics_enhanced.sh"
timestamp="$(date +%Y%m%d_%H%M%S)"
session_name="${2:-app80_panel_enhanced}"
output_root="${1:-$repo_root/analysis-output/app80_panel_prompt_metrics_enhanced_$timestamp}"
workers="${DEO_PANEL_PROMPT_WORKERS:-2}"
log_dir="$repo_root/data-docs/logs"
log_path="$log_dir/app80_panel_prompt_metrics_enhanced_${timestamp}.log"

mkdir -p "$log_dir" "$output_root"

if tmux has-session -t "$session_name" 2>/dev/null; then
  echo "tmux session already exists: $session_name" >&2
  exit 1
fi

cmd=$(cat <<EOF
cd "$repo_root"
export DEO_PANEL_PROMPT_WORKERS="$workers"
export OPENCV_LOG_LEVEL=ERROR
"$runner" "$output_root" 2>&1 | tee "$log_path"
EOF
)

tmux new-session -d -s "$session_name" "$cmd"

cat <<EOF
session_name=$session_name
output_root=$output_root
log_path=$log_path
workers=$workers
EOF
