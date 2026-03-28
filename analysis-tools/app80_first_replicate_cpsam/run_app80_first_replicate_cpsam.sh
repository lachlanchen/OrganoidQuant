#!/usr/bin/env bash
set -euo pipefail
export PYTHONNOUSERSITE=1
export TORCH_DISABLE_DYNAMO=1
exec /home/lachlan/miniconda3/envs/organoid-gpu/bin/python -B \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_cpsam/run_app80_first_replicate_cpsam.py \
  "$@"
