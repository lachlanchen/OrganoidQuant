#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
python_bin="${PYTHON_BIN:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
runner="$repo_root/analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py"

if [ $# -lt 2 ]; then
  echo "Usage: $0 /path/to/source.png /path/to/output_dir" >&2
  exit 1
fi

exec "$python_bin" "$runner" --image "$1" --output-dir "$2" --resume --verbose
