# App80 Panel Prompt Metrics

This pipeline evaluates App80 10x images by first building contact-sheet panels and then scoring each panel with a metadata-blind prompt tool.

Pipeline:
- collect valid 10x TIFFs from `DEO/App80 DEO/`
- select a consistent sample count per concentration: `min(10, smallest_valid_date_count)`
- build one date-ordered contact sheet per concentration/sample rank
- run one prompt tool per panel to return `fusion`, `size`, and `perimeter` as 2D arrays
- combine raw prompt outputs with panel metadata into databases
- compute daily summary statistics and significance versus `No`
- export publication-style figures

Important design choices:
- the prompt never sees date or concentration metadata
- the panel grid uses only slot labels and blank cells
- all intermediate artifacts are saved for replotting

Main scripts:
- `build_contact_sheets.py`
- `run_panel_metric_prompt.sh`
- `run_panel_metric_batch.py`
- `aggregate_panel_metrics.py`
- `plot_panel_metrics.py`
- `run_app80_panel_prompt_metrics.sh`
- `start_tmux_app80_panel_prompt_metrics.sh`
- `run_single_tile_enhanced_metric.sh`
- `run_tile_metric_batch.py`
- `build_panel_metrics_from_tile_metrics.py`
- `compute_polygon_tile_metrics.py`
- `plot_panel_metrics_enhanced.py`
- `run_app80_panel_prompt_metrics_enhanced.sh`
- `start_tmux_app80_panel_prompt_metrics_enhanced.sh`

Replicate stitching rule:
- for each concentration, `sample_00` contains the first valid image from each day
- `sample_01` contains the second valid image from each day
- this continues through `sample_09` or the smallest valid count across days

Tmux run:
- `analysis-tools/app80_panel_prompt_metrics/start_tmux_app80_panel_prompt_metrics.sh`
- default session name: `app80_panel`
- default output root: `analysis-output/app80_panel_prompt_metrics_YYYYMMDD_HHMMSS`

Enhanced pipeline:
- analyze each single image first instead of directly scoring the whole panel
- build image priors from Cellpose small/large branches plus gradient/edge overlays
- run Codex coarse/refine polygon segmentation on each image
- compute fusion, combined area, and combined perimeter from the final polygon masks
- rebuild the panel 2D arrays from those per-image metrics
- keep the same aggregation and publication plotting stages

Enhanced tmux run:
- `analysis-tools/app80_panel_prompt_metrics/start_tmux_app80_panel_prompt_metrics_enhanced.sh`
- default session name: `app80_panel_enhanced`
- default output root: `analysis-output/app80_panel_prompt_metrics_enhanced_YYYYMMDD_HHMMSS`
