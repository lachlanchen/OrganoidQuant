#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/lachlan/ProjectsLFS/Zhengyu
OUT="$ROOT/analysis-output/app81_main_density_curated_v1"

source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export PYTHONNOUSERSITE=1
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export ZQ_CUDA_VISIBLE_DEVICES="${ZQ_CUDA_VISIBLE_DEVICES:-0}"
export CUDA_VISIBLE_DEVICES="$ZQ_CUDA_VISIBLE_DEVICES"
export TORCHDYNAMO_DISABLE=1
export TORCH_DISABLE_DYNAMO=1
export PYTORCH_JIT=0
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export TBB_NUM_THREADS=1
export MPLBACKEND=Agg

run_low_impact() {
  if command -v ionice >/dev/null 2>&1; then
    ionice -c 2 -n 7 nice -n 10 "$@"
  else
    nice -n 10 "$@"
  fi
}

cd "$ROOT"
run_low_impact python "$ROOT/analysis-tools/app81_density_custom_cellpose/run_app81_main_density_curated_v1.py" \
  --src-root "$ROOT/DEO/DEO App81 P8" \
  --out-dir "$OUT" \
  --profile-file "$ROOT/analysis-tools/app81_density_custom_cellpose/app81_curated_profiles_v1.json"
