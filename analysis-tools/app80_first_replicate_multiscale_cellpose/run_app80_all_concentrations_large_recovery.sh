#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/lachlan/ProjectsLFS/Zhengyu"
SRC_ROOT="$ROOT/DEO/App80 DEO"
OUT_DIR="$ROOT/analysis-output/app80_all_concentrations_multiscale_large_recovery"
SEED_10UM="$ROOT/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/runs"

source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export TORCHDYNAMO_DISABLE=1
export PYTORCH_JIT=0

mkdir -p "$OUT_DIR/runs/10uM" "$OUT_DIR/databases" "$OUT_DIR/figures"
if [ -d "$SEED_10UM" ]; then
  cp -an "$SEED_10UM"/. "$OUT_DIR/runs/10uM"/ || true
fi

cd "$ROOT"
python analysis-tools/app80_first_replicate_multiscale_cellpose/run_app80_all_concentrations_large_recovery.py \
  --src-root "$SRC_ROOT" \
  --out-dir "$OUT_DIR"

python3 analysis-tools/app80_first_replicate_multiscale_cellpose/plot_app80_all_concentrations_metrics.py \
  --daily-csv "$OUT_DIR/databases/daily_summary.csv"
