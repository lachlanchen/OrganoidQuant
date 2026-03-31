#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/lachlan/ProjectsLFS/Zhengyu"
SRC_ROOT="$ROOT/DEO/App80 DEO"
OUT_DIR="$ROOT/analysis-output/app80_all_concentrations_multiscale_large_recovery"
SEED_10UM="$ROOT/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/runs"

source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=0
export PYTHONNOUSERSITE=1
export TORCHDYNAMO_DISABLE=1
export PYTORCH_JIT=0
export TORCH_DISABLE_DYNAMO=1
export PYTHONDONTWRITEBYTECODE=1

mkdir -p "$OUT_DIR/runs/10uM" "$OUT_DIR/profiling/quantification" "$OUT_DIR/figures"
if [ -d "$SEED_10UM" ]; then
  rsync -a --ignore-existing "$SEED_10UM"/ "$OUT_DIR/runs/10uM"/
fi

cd "$ROOT"
python -B - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit('GPU is required for this batch, but torch.cuda.is_available() is False')
print(f'Using GPU: {torch.cuda.get_device_name(0)}')
PY

python -B - <<PY
import sys
sys.path.insert(0, "$ROOT/analysis-tools/app80_first_replicate_multiscale_cellpose")
import run_app80_all_concentrations_large_recovery as mod
sys.argv = [
    "run_app80_all_concentrations_large_recovery.py",
    "--src-root", "$SRC_ROOT",
    "--out-dir", "$OUT_DIR",
]
raise SystemExit(mod.main())
PY

python3 -B - <<PY
import sys
sys.path.insert(0, "$ROOT/analysis-tools/app80_first_replicate_multiscale_cellpose")
import plot_app80_all_concentrations_metrics as mod
sys.argv = [
    "plot_app80_all_concentrations_metrics.py",
    "--daily-csv", "$OUT_DIR/profiling/quantification/daily_summary.csv",
]
raise SystemExit(mod.main())
PY
