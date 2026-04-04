# App81 Density Main-Phase Run

Date: 2026-04-04
Source root: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8`
Output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery`

## Experimental interpretation

Based on the thesis notes, figure design notes, handwritten summary, and transcription notes, `DEO App81 P8` is the initial cell-density screening experiment.

Main variable:

- initial cell density
- three conditions: `low`, `middle`, `high`

Main biological question:

- how density affects growth and differentiation timing
- with fusion / interaction treated as a supporting morphology consequence

Expected message from the reference material:

- `low` grows more slowly and shows less interaction
- `middle` and `high` grow better than `low`
- `high` can show earlier fusion and earlier differentiation risk
- middle-to-high density was considered more suitable for later experiments

## Why this first run uses only main-phase labeled 10x images

The folder contains two different data structures:

1. main phase:
- `DEO App81 P8/<date>/*.tif`
- explicit `low / middle / high` labels in filenames

2. transfer phase:
- `DEO App81 P8/low transfer/<date>/*.tif`
- many files do not carry explicit density labels
- this is a phase-specific branch, not the cleanest basis for the main density kinetics

This first automated run therefore uses only:

- `phase = main`
- `magnification = 10x`
- explicit density labels only: `low`, `middle`, `high`

That keeps the main density comparison scientifically coherent and avoids mixing transfer-stage low-density follow-up images into the core time-series figure.

## Scope processed

Processed images:

- total used: `63`
- conditions:
  - `low`
  - `middle`
  - `high`
- phase: `main_only`
- magnification: `10x_only`

Skipped during this first pass:

- transfer-phase TIFFs: `47`
- non-10x main-phase TIFFs: `72`

These counts are recorded in:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/run_manifest.json`

## Pipeline

This run reuses the same multiscale Cellpose + large-mass recovery framework used previously for App65 and App80.

Saved per-image intermediates:

- `*_mask_16bit.png`
- `*_instance_rgb.png`
- `*_overlay.png`
- `*_signal.png`
- `*_metrics.json`
- `*_segmentation_stats.json`

## Metrics in the main App81 database

Per-image database:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`

Daily summary:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

Current metrics saved:

- `count`
- `curvature`
- `roundness`
- `roundness_deviation_norm`
- `roundness_deviation_px_total`
- `edge_intensity`
- `total_area_px`
- `average_perimeter_px`
- `count_norm`
- `curvature_norm`
- `edge_norm`
- `normalized_edge_over_count_curvature`

## Figures produced

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/figures/app81_main_density_segmentation_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/figures/app81_main_density_normalized_edge_over_count_curvature.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/figures/app81_main_density_roundness.png`

## Practical reading

For this first pass:

- growth should be read mainly from:
  - `total_area_px`
  - `count`
- differentiation should be read mainly from:
  - `roundness`
  - `roundness_deviation_norm`
- fusion / interaction context can be read from:
  - `normalized_edge_over_count_curvature`
  - `edge_intensity`
  - `count`

## Recommended next step

If the goal is a stronger differentiation readout for App81, the next useful extension is to add the App65-style darkness metrics to this completed App81 segmentation without rerunning segmentation:

- `organoid_darkness_mean`
- `organoid_darkness_p90`
- `very_dark_area_ratio_gt035`
- `wall_darkness_mean`
- `wall_darkness_p90`
- `wall_core_darkness_ratio`

That would make the App81 density experiment more aligned with the intended biological message of growth plus differentiation timing.
