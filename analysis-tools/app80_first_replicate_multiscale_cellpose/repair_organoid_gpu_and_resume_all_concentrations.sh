#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/lachlan/ProjectsLFS/Zhengyu"
ENV_NAME="organoid-gpu"
TORCH_INDEX="https://download.pytorch.org/whl/cu124"
LOG_PREFIX="[repair-resume]"

echo "$LOG_PREFIX start $(date '+%Y-%m-%d %H:%M:%S')"
source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda deactivate >/dev/null 2>&1 || true
conda env remove -n "$ENV_NAME" -y || true
conda create -n "$ENV_NAME" -y python=3.10 pip numpy=1.26 scipy pandas matplotlib tifffile -c conda-forge
conda activate "$ENV_NAME"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=0
export PYTHONNOUSERSITE=1
export TORCHDYNAMO_DISABLE=1
export TORCH_DISABLE_DYNAMO=1
export PYTORCH_JIT=0
export PYTHONDONTWRITEBYTECODE=1
python -m pip install --no-cache-dir torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url "$TORCH_INDEX"
python -m pip install --no-cache-dir --no-deps cellpose==4.1.0 opencv-python-headless segment_anything fastremap roifile imagecodecs fill-voids tqdm natsort
find /home/lachlan/miniconda3/envs/$ENV_NAME -type d -name '__pycache__' -prune -exec rm -rf {} + || true
find /home/lachlan/miniconda3/envs/$ENV_NAME -type f -name '*.pyc' -delete || true
cat > /home/lachlan/miniconda3/envs/$ENV_NAME/lib/python3.10/site-packages/segment_anything/__init__.py <<'PY'
# Minimal init for Cellpose-SAM use in Zhengyu batch.
from .build_sam import (
    build_sam,
    build_sam_vit_h,
    build_sam_vit_l,
    build_sam_vit_b,
    sam_model_registry,
)
PY
python -B - <<'PY'
import torch
print('cuda_available', torch.cuda.is_available())
print('device_name', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')
from cellpose import models
m = models.CellposeModel(gpu=True)
print('model_device', m.device)
PY
cd "$ROOT"
analysis-tools/app80_first_replicate_multiscale_cellpose/run_app80_all_concentrations_large_recovery.sh
