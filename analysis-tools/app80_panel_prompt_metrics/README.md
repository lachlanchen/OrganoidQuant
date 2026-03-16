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
