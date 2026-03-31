#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/lachlan/ProjectsLFS/Zhengyu
source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=0
export TORCHDYNAMO_DISABLE=1
export TORCH_DISABLE_DYNAMO=1
export PYTORCH_JIT=0
cd "$ROOT"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/run_app65_all_conditions_large_recovery.py" \
  --src-root "$ROOT/DEO/App65 DEO+Alginate" \
  --out-dir "$ROOT/analysis-output/app65_alginate_multiscale_large_recovery"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/plot_app65_all_conditions_metrics.py" \
  --daily-csv "$ROOT/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/daily_summary.csv"
