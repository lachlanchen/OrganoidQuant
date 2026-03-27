# Fusion Blind Prompt Tool

This toolset analyzes a blinded microscopy image cohort without exposing date or condition metadata to the prompt tool.

## Components
- `run_blind_fusion_set_prompt.sh`: first-pass cohort scoring from blinded images only.
- `run_blind_fusion_refine_prompt.sh`: second-pass review that sees the same blinded images plus the first-pass JSON draft.
- `build_blinded_image_bundle.py`: converts blinded TIFFs to PNG and builds a UID-labeled contact sheet in an isolated temp workspace.
- `build_day_order_markdown_report.py`: combines the refined JSON with the private UID-to-source mapping to produce a human-readable day-ordered Markdown report.
- `plot_day_order_metrics.py`: exports a metric table plus a multi-panel figure for the blinded day-ordered cohort.

## Design
- converts blinded TIFFs to PNG in an isolated temp workspace
- builds a contact sheet labeled only by UID
- attaches the contact sheet plus all individual images to `codex exec`
- uses strict JSON schemas
- explicitly warns the model about the known fusion-analysis pitfalls:
  - large irregular fused masses are valid organoid structures
  - fusion is confounded with growth and differentiation
  - the cohort must be compared jointly, not one image at a time only

## Usage
First pass:
```bash
analysis-tools/fusion_blind_prompt/run_blind_fusion_set_prompt.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001 \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_analysis.json \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_prompt.txt
```

Refine pass:
```bash
analysis-tools/fusion_blind_prompt/run_blind_fusion_refine_prompt.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001 \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_analysis.json \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_analysis_refined.json \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_refine_prompt.txt
```

Day-ordered report:
```bash
/home/lachlan/miniconda3/envs/organoid/bin/python analysis-tools/fusion_blind_prompt/build_day_order_markdown_report.py \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_analysis_refined.json \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/internal_mapping/uid_to_source.csv \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001_report
```

Metric figure:
```bash
/home/lachlan/miniconda3/envs/organoid/bin/python analysis-tools/fusion_blind_prompt/plot_day_order_metrics.py \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_analysis_refined.json \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/internal_mapping/uid_to_source.csv \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001_report
```

## Input visibility
The prompt model should only see:
- the blinded UID images
- the contact sheet built from those UID images
- the prompt text
- for the refine pass only: the first-pass JSON draft

It should not see:
- date folders
- concentration folders
- internal mapping files

## Outputs
Prompt outputs under the ignored analysis folder:
- `blind_fusion_analysis.json`
- `blind_fusion_analysis_refined.json`
- optional saved prompt text for audit/debugging

Report and plots under the ignored analysis folder:
- `analysis-output/fusion-analysis-test/set_001_report/set_001_day_order_report.md`
- `analysis-output/fusion-analysis-test/set_001_report/set_001_compact_review_table.md`
- `analysis-output/fusion-analysis-test/set_001_report/set_001_row_strip.png`
- `analysis-output/fusion-analysis-test/set_001_report/set_001_metric_table.csv`
- `analysis-output/fusion-analysis-test/set_001_report/set_001_metric_summary.png`
