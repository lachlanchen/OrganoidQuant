#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/lachlan/ProjectsLFS/Zhengyu"
SRC_ROOT="$REPO_ROOT/DEO/DEO test 2025.10.1"
OUT_DIR="$REPO_ROOT/analysis-output/test2025_density_B_multiscale_large_recovery"

source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export MPLBACKEND=Agg

python "$REPO_ROOT/analysis-tools/test2025_density_B_multiscale_cellpose/run_test2025_density_B_large_recovery.py" \
  --src-root "$SRC_ROOT" \
  --out-dir "$OUT_DIR"

python "$REPO_ROOT/analysis-tools/test2025_density_B_multiscale_cellpose/backfill_test2025_density_B_full_metrics.py" \
  --out-dir "$OUT_DIR"

python "$REPO_ROOT/analysis-tools/test2025_density_B_multiscale_cellpose/plot_test2025_density_B_metrics.py" \
  --daily-csv "$OUT_DIR/profiling/quantification/daily_summary.csv"

python "$REPO_ROOT/analysis-tools/test2025_density_B_multiscale_cellpose/plot_test2025_density_B_full_metric_groups.py" \
  --daily-csv "$OUT_DIR/profiling/quantification/daily_summary.csv"
