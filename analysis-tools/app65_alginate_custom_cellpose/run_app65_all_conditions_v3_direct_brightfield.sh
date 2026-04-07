#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/lachlan/ProjectsLFS/Zhengyu
OUT="$ROOT/analysis-output/app65_alginate_v3_direct_brightfield"
source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export ZQ_CUDA_VISIBLE_DEVICES="${ZQ_CUDA_VISIBLE_DEVICES:-0}"
export CUDA_VISIBLE_DEVICES="$ZQ_CUDA_VISIBLE_DEVICES"
export TORCHDYNAMO_DISABLE=1
export TORCH_DISABLE_DYNAMO=1
export PYTORCH_JIT=0
cd "$ROOT"
python "$ROOT/analysis-tools/app65_alginate_custom_cellpose/run_app65_all_conditions_v3_direct_brightfield.py" \
  --src-root "$ROOT/DEO/App65 DEO+Alginate" \
  --out-dir "$OUT"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/backfill_app65_full_metrics.py" \
  --out-dir "$OUT"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/plot_app65_all_conditions_metrics.py" \
  --daily-csv "$OUT/profiling/quantification/daily_summary.csv"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/plot_app65_differentiation_darkness_metrics.py" \
  --out-dir "$OUT"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/plot_app65_all_conditions_full_metric_groups.py" \
  --daily-csv "$OUT/profiling/quantification/daily_summary.csv"
python "$ROOT/analysis-tools/app65_alginate_multiscale_cellpose/analyze_app65_subexperiments.py" \
  --daily-csv "$OUT/profiling/quantification/daily_summary.csv"
