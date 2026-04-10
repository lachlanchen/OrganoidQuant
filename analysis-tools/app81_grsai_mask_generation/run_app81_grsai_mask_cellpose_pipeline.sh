#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
python_bin="${PYTHON_BIN:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
gen_runner="$repo_root/analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py"
refine_runner="$repo_root/analysis-tools/app81_grsai_mask_generation/refine_app81_grsai_mask_with_cellpose.py"

if [ $# -lt 2 ]; then
  echo "Usage: $0 /path/to/source.png /path/to/output_dir" >&2
  exit 1
fi

src="$1"
out="$2"

"$python_bin" "$gen_runner" --image "$src" --output-dir "$out" --resume --verbose
"$python_bin" "$refine_runner" --source "$src" --generated-mask "$out/generated_instance_mask.png" --output-dir "$out/cellpose_refinement" --gpu
