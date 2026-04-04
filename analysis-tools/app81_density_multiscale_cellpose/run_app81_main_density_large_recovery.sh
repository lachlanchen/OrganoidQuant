#!/usr/bin/env bash
set -euo pipefail

source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export MPLBACKEND=Agg
: "${ZQ_CUDA_VISIBLE_DEVICES:=0}"
export CUDA_VISIBLE_DEVICES="$ZQ_CUDA_VISIBLE_DEVICES"

echo "python=$(which python)"
echo "env=$CONDA_DEFAULT_ENV"
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
python - <<'PY'
import torch
print('cuda_available=', torch.cuda.is_available())
print('device_count_visible=', torch.cuda.device_count())
PY

ROOT=/home/lachlan/ProjectsLFS/Zhengyu
python "$ROOT/analysis-tools/app81_density_multiscale_cellpose/run_app81_main_density_large_recovery.py" \
  --src-root "$ROOT/DEO/DEO App81 P8" \
  --out-dir "$ROOT/analysis-output/app81_main_density_multiscale_large_recovery"

python "$ROOT/analysis-tools/app81_density_multiscale_cellpose/plot_app81_main_density_metrics.py" \
  --daily-csv "$ROOT/analysis-output/app81_main_density_multiscale_large_recovery/profiling/quantification/daily_summary.csv"
