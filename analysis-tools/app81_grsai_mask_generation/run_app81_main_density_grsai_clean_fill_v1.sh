#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
RUNNER="$ROOT/analysis-tools/app81_grsai_mask_generation/run_app81_main_density_grsai_clean_fill_v1.py"

run_low_impact() {
  env \
    MPLBACKEND=Agg \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    TBB_NUM_THREADS=1 \
    "$@"
}

run_low_impact nice -n 10 ionice -c2 -n7 \
  "$PYTHON_BIN" "$RUNNER" \
  --src-root "$ROOT/DEO/DEO App81 P8" \
  --out-dir "$ROOT/analysis-output/app81_main_density_grsai_clean_fill_v1" \
  "$@"
