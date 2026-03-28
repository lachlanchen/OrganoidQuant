#!/usr/bin/env bash
set -euo pipefail

SET_DIR="${1:-/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001}"
export PYTHONNOUSERSITE=1
export TORCH_DISABLE_DYNAMO=1
exec /home/lachlan/miniconda3/envs/organoid-gpu/bin/python -B \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/fusion_analysis_test_sam_prompted/run_fusion_analysis_test_sam_prompted_metadata.py \
  "$SET_DIR" --device cuda --model-type vit_h
