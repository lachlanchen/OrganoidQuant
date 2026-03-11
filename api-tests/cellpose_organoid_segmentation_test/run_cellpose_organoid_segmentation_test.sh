#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
vendor_dir="$repo_root/api-tests/cellpose_organoid_segmentation_test/vendor_legacy"
user_site="$HOME/.local/lib/python3.10/site-packages"

mkdir -p "$vendor_dir"

if [[ ! -f "$vendor_dir/numpy/__init__.py" ]]; then
  "$py_bin" -m pip install --target "$vendor_dir" 'numpy==1.26.4'
fi

export PYTHONNOUSERSITE=1
export PYTHONPATH="$vendor_dir:$user_site${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

exec "$py_bin" "$repo_root/api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.py" "$@"
