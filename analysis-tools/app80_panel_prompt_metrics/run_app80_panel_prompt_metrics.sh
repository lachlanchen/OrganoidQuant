#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
py_bin="${DEO_PYTHON:-/home/lachlan/miniconda3/envs/organoid/bin/python}"
output_root="${1:-$repo_root/analysis-output/app80_panel_prompt_metrics}"
workers="${DEO_PANEL_PROMPT_WORKERS:-3}"
export OPENCV_LOG_LEVEL=ERROR

mkdir -p "$output_root"

"$py_bin" "$repo_root/analysis-tools/app80_panel_prompt_metrics/build_contact_sheets.py" \
  --app80-root "$repo_root/DEO/App80 DEO" \
  --output-root "$output_root"

"$py_bin" "$repo_root/analysis-tools/app80_panel_prompt_metrics/run_panel_metric_batch.py" \
  --manifest "$output_root/contact_sheet_manifest.json" \
  --output-root "$output_root/panel_prompt_raw" \
  --workers "$workers"

"$py_bin" "$repo_root/analysis-tools/app80_panel_prompt_metrics/aggregate_panel_metrics.py" \
  --manifest "$output_root/contact_sheet_manifest.json" \
  --raw-root "$output_root/panel_prompt_raw" \
  --output-root "$output_root/databases"

"$py_bin" "$repo_root/analysis-tools/app80_panel_prompt_metrics/plot_panel_metrics.py" \
  --summary-csv "$output_root/databases/app80_panel_metric_daily_summary.csv" \
  --pvalues-csv "$output_root/databases/app80_panel_metric_pvalues_vs_no.csv" \
  --output-root "$output_root/figures"
