# Test2025 Density B Run Summary

Date: 2026-04-05
Raw source: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO test 2025.10.1`
Output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery`

## What Was Run

This is the dedicated segmentation and quantification run for the density experiment `B` branch.

It was run as a separate branch from `DEO App81 P8` because the references confirm:

- density `A`: `DEO App81 P8`
- density `B`: `DEO test 2025.10.1`

## Main Inclusion Rule

The main quantified set includes only files that are:

- non-`_RGB`
- explicitly labeled `low`, `middle`, or `high`
- explicitly labeled with a `D#` day token
- true microscope magnification `10x`
- inside the structured `D0/` tree

The top-level `before D6-*` files were not mixed into the main quantified database and are instead recorded in the audit / review outputs.

## Output Structure

### Per-image intermediates

Under `runs/` each image keeps:

- `*_mask_16bit.png`
- `*_instance_rgb.png`
- `*_overlay.png`
- `*_signal.png`
- `*_metrics.json`
- `*_segmentation_stats.json`

### Databases

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/profiling/quantification/daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/run_manifest.json`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/backfill_manifest.json`

### Audit files

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/profiling/audit/metadata_audit.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/profiling/audit/review_queue.csv`

### Figures

- overview metrics:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/figures/overview_segmentation_metrics/test2025_density_B_segmentation_metrics.pdf`
- fusion proxy:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/figures/fusion_proxy_metrics/test2025_density_B_normalized_edge_over_count_curvature.pdf`
- roundness:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/figures/differentiation_roundness/test2025_density_B_roundness.pdf`
- full metric panels:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery/figures/full_metric_panels/`

## Completeness

- per-image rows: `130`
- per-image columns: `58`
- daily summary rows: `49`

This branch therefore has a complete saved segmentation output tree plus complete database and figure products.

## Conservative Biological Reading

This branch should be read as an independent confirmation panel for the density effect.

The safe reading from the finished quantification is:

- low density remains smaller and simpler at late time points
- middle density can reach the largest connected masses in this branch
- high density shows stronger late fusion / irregularity than low density
- low density stays rounder at late time points, which is consistent with less interaction and less fused growth
- differentiation-like dark wall metrics become stronger in middle / high density than in low density

That is consistent with the project-level density interpretation from the references:

- low density grows more slowly and interacts less
- middle / high density grow better and fuse more
- denser conditions also move earlier toward thicker / darker / less simple morphology

## Code

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/test2025_density_B_multiscale_cellpose/run_test2025_density_B_large_recovery.py`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/test2025_density_B_multiscale_cellpose/backfill_test2025_density_B_full_metrics.py`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/test2025_density_B_multiscale_cellpose/plot_test2025_density_B_metrics.py`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/test2025_density_B_multiscale_cellpose/plot_test2025_density_B_full_metric_groups.py`
