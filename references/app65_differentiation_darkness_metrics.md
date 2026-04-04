# App65 Differentiation Darkness Metrics

Date: 2026-04-04
Output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`

## Purpose

These metrics were added to quantify differentiation-related morphology in `App65 DEO+Alginate` using the completed segmentation results, without rerunning segmentation.

The experimental interpretation behind these metrics is:

- growth is similar between control and alginate groups, with control possibly slightly stronger
- the main phenotype of interest is differentiation
- more differentiated organoids tend to show:
  - darker appearance
  - thickened epithelial walls
  - budded / irregular epithelial morphology

## Data Used

This analysis reuses the existing completed segmentation outputs under:

- `runs/*/*/*_mask_16bit.png`
- `runs/*/*/*_metrics.json`
- `runs/*/*/*_signal.png`
- original source TIFFs referenced by each per-image metrics JSON

No segmentation rerun was performed.

## Darkness Normalization

For each image, grayscale darkness is normalized relative to a per-image background estimate:

- background region = outside a dilated organoid mask
- background statistic = median grayscale value of that background region
- normalized darkness:
  - `max(0, background_median - gray) / background_median`

This keeps the metric comparable across images with different illumination levels.

## Added Per-Image Metrics

The following fields were added to the main App65 per-image database:

- `background_gray_median`
- `organoid_darkness_mean`
- `organoid_darkness_p90`
- `organoid_darkness_p95`
- `very_dark_area_ratio_gt035`
- `wall_darkness_mean`
- `wall_darkness_p90`
- `core_darkness_mean`
- `wall_core_darkness_ratio`
- `organoid_pixel_count`
- `wall_pixel_count`
- `core_pixel_count`

### Metric meanings

- `organoid_darkness_mean`: average normalized darkness inside segmented organoids
- `organoid_darkness_p90`: upper-tail darkness signal inside organoids
- `organoid_darkness_p95`: stronger peak-darkness summary
- `very_dark_area_ratio_gt035`: fraction of organoid pixels above a fixed darkness threshold
- `wall_darkness_mean`: mean darkness inside an adaptive inner wall band
- `wall_darkness_p90`: high-end wall darkness
- `core_darkness_mean`: mean darkness in the eroded core region
- `wall_core_darkness_ratio`: wall darkness divided by core darkness

## Wall / Core Definition

For each segmented instance:

- equivalent radius is computed from area
- erosion band width is `round(equivalent_radius * 0.12)`
- band width is clamped to `5..30` px
- wall = object minus eroded object
- core = eroded object

This makes the wall band scale with organoid size instead of using a fixed thickness.

## Empty-Mask Handling

Two images had empty saved segmentation masks:

- `23-十一月-2025_no-10x22`
- `23-十一月-2025_no-10x29`

These are now handled as valid rows with:

- `organoid_pixel_count = 0`
- darkness metrics recorded as `NaN`

This prevents the post-processing run from crashing while preserving database completeness.

## Output Files

### Main databases updated in place

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

### Dedicated darkness-analysis tables

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/differentiation_darkness_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/differentiation_darkness_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/differentiation_darkness_manifest.json`

### Figures

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_metrics.pdf`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_focus.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_focus.pdf`

## Code

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app65_alginate_multiscale_cellpose/plot_app65_differentiation_darkness_metrics.py`

## Practical Reading

The most differentiation-oriented indicators from this pass are:

- `organoid_darkness_p90`
- `very_dark_area_ratio_gt035`
- `wall_darkness_mean`
- `wall_core_darkness_ratio`

These are better aligned with the stated biological phenotype than plain area or count alone because they target darker and thickened epithelial structure inside already segmented organoids.
