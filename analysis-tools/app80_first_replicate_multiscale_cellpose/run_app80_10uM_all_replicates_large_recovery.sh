#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_ROOT="${1:-$ROOT_DIR/DEO/App80 DEO/10uM}"
OUT_DIR="${2:-$ROOT_DIR/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery}"
source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export TORCHDYNAMO_DISABLE=1
export PYTORCH_JIT=0
python "$ROOT_DIR/analysis-tools/app80_first_replicate_multiscale_cellpose/run_app80_10uM_all_replicates_large_recovery.py" --src-root "$SRC_ROOT" --out-dir "$OUT_DIR"
python3 "$ROOT_DIR/analysis-tools/app80_first_replicate_multiscale_cellpose/plot_app80_10uM_all_replicates_metrics.py" --daily-csv "$OUT_DIR/databases/daily_summary.csv"
