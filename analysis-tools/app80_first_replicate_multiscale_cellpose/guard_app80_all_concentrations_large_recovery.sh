#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/lachlan/ProjectsLFS/Zhengyu"
OUT_DIR="$ROOT/analysis-output/app80_all_concentrations_multiscale_large_recovery"
RUN_SCRIPT="$ROOT/analysis-tools/app80_first_replicate_multiscale_cellpose/run_app80_all_concentrations_large_recovery.sh"
SESSION="app80_allconc_full"
LOG_DIR="$ROOT/data-docs/logs"
FINAL_CSV="$OUT_DIR/profiling/quantification/daily_summary.csv"
FINAL_FIG="$OUT_DIR/figures/app80_all_concentrations_segmentation_metrics.png"

expected_total() {
  find "$ROOT/DEO/App80 DEO" -type f -iname '*.tif' | grep -i '10x' | wc -l
}

current_total() {
  find "$OUT_DIR/runs" -type f -name '*_metrics.json' 2>/dev/null | wc -l
}

launch_main() {
  local log_file
  log_file="$LOG_DIR/app80_all_concentration_multiscale_large_recovery_guard_$(date +%Y%m%d_%H%M%S).log"
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  tmux new-session -d -s "$SESSION" "bash -lc 'source /home/lachlan/miniconda3/etc/profile.d/conda.sh && conda activate organoid-gpu && cd \"$ROOT\" && \"$RUN_SCRIPT\" > \"$log_file\" 2>&1; printf \"\\nEXIT:%s\\n\" \"$?\"; exec bash'"
  echo "$(date '+%F %T') launched $SESSION -> $log_file"
}

main() {
  local expected
  expected="$(expected_total)"
  echo "$(date '+%F %T') expected_total=$expected"
  while true; do
    local current
    current="$(current_total)"
    echo "$(date '+%F %T') current_total=$current"
    if [[ -f "$FINAL_CSV" && -f "$FINAL_FIG" && "$current" -ge "$expected" ]]; then
      echo "$(date '+%F %T') completed"
      exit 0
    fi
    if ! pgrep -f 'run_app80_all_concentrations_large_recovery.sh' >/dev/null; then
      launch_main
    fi
    sleep 300
  done
}

main "$@"
