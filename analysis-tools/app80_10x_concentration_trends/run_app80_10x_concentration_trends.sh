#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
organoid_py="/home/lachlan/miniconda3/envs/organoid/bin/python"
base_py="/home/lachlan/miniconda3/bin/python"
script="$repo_root/analysis-tools/app80_10x_concentration_trends/plot_app80_10x_concentration_trends.py"

if "$organoid_py" - <<'PY' >/dev/null 2>&1
import matplotlib
PY
then
  py_bin="$organoid_py"
else
  py_bin="$base_py"
fi

"$py_bin" "$script" "$@"
