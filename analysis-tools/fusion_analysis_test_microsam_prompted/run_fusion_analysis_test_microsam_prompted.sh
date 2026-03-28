#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"

export PYTHONNOUSERSITE=1
export PYTHONUNBUFFERED=1

exec "$py_bin" "$repo_root/analysis-tools/fusion_analysis_test_microsam_prompted/run_fusion_analysis_test_microsam_prompted.py" "$@"
