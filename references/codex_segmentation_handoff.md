# Codex Segmentation Handoff

Date: 2026-04-05
Repo root: `/home/lachlan/ProjectsLFS/Zhengyu`

## Purpose

This note is for another Codex session that needs to understand and reuse the DEO segmentation pipeline used in this project.

It is not the primary scientific interpretation note.
It is the practical handoff for reproducing or adapting the segmentation algorithm and the downstream metric workflow.

## Canonical Method Document

Read this PDF first:

- English PDF:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_segmentation_metric_method_tex/main.pdf`
- Chinese PDF:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_segmentation_metric_method_tex/zh/main.pdf`

These PDFs contain:

- the full segmentation pipeline structure
- the hybrid signal definition
- the support-mask logic
- multiscale Cellpose plus large-mass recovery
- merge logic
- the metric definitions in math form

If a future Codex session needs the editable source, use:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_segmentation_metric_method_tex/main.tex`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_segmentation_metric_method_tex/zh/main.tex`

## Core Algorithm Summary

The accepted segmentation framework in this repo is:

1. load TIFF brightfield image
2. convert to grayscale and prepare normalized image features
3. build a black-background hybrid `signal.png`
4. build a support mask from the signal image
5. run Cellpose at multiple diameters on the same image
6. score candidate masks using signal support and boundary evidence
7. recover very large irregular masses directly from the signal image when needed
8. merge all candidates with overlap-aware selection
9. save all intermediates and per-image metrics
10. aggregate per-image metrics into daily and condition-level databases

This is a reusable framework, not a universal plug-and-play model.
For a new dataset, the framework should stay the same, but the date/stage mapping and diameter settings usually need retuning.

## Production Baseline Scripts

Use these as the real production baselines.
Do not invent a new pipeline unless there is a concrete reason.

### App80: Y-27632 concentration

Main run script:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/run_app80_all_concentrations_large_recovery.py`

Related notes:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/app80_multiscale_cellpose_large_recovery_method.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/app80_full_metric_interpretation.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/app80_two_subexperiments_analysis.md`

Completed output root:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

### App65: Alginate concentration

Main run script:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app65_alginate_multiscale_cellpose/run_app65_all_conditions_large_recovery.py`

Completed output root:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`

### App81: Density experiment

Main run script:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_density_multiscale_cellpose/run_app81_main_density_large_recovery.py`

Completed output root:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery`

## What Another Codex Session Should Reuse

Another Codex session should reuse these design rules:

- keep `10x` brightfield as the primary segmentation scope unless the task explicitly changes magnification
- keep all per-image intermediates
- do not overwrite raw data
- do not rerun segmentation if the saved masks and databases already exist and only metric backfill is needed
- keep new analyses in separate output subfolders instead of mixing them into production `runs/`

## Required Saved Intermediates

For each segmented image, the accepted output set is:

- `*_mask_16bit.png`
- `*_instance_rgb.png`
- `*_overlay.png`
- `*_signal.png`
- `*_metrics.json`
- `*_segmentation_stats.json`

These files are the backbone for all later metric backfill work.
A future Codex session should avoid deleting or bypassing them.

## Main Database Files

These are the main reusable outputs after segmentation.

### App80

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

### App65

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

### App81

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

## Metric Catalog

For the full cross-project metric list, read:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_metric_catalog_growth_fusion_differentiation.md`

This is the main metric inventory for:

- growth
- fusion
- differentiation
- helper normalization fields

## Experiment Design References

A future Codex session should read the experiment-design notes before changing metrics or figure logic.

Main design folder:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design`

Important notes:

- App80 / Y-27632:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/07_figure5_y27632_design.md`
- App65 / Alginate:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/06_figure3_alginate_design.md`
- App81 / Density:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/05_figure2_density_design.md`
- global plan:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`

## Practical Reuse Order

If another Codex session needs to apply the method to a new but similar brightfield DEO dataset, the correct order is:

1. read the canonical PDF method note first
2. read the relevant experiment-design note
3. inspect one completed production script from App80, App65, or App81
4. inspect one completed output root to understand the file structure
5. reuse the same output conventions
6. retune only the dataset-specific stage mapping, diameter triplets, and large-mass recovery thresholds
7. keep all new exploratory outputs in a separate output folder

## Do Not Do These Things

A future Codex session should avoid these mistakes:

- do not replace the whole pipeline with plain single-diameter Cellpose
- do not trust `count` alone as growth or fusion
- do not rerun a finished dataset just to add a new metric if the saved masks already exist
- do not save trace/debug outputs inside the main production output tree unless explicitly requested
- do not mix experiment-specific interpretation across App65, App80, and App81

## Environment Note

The repo-level default environment note says `organoid`, but the GPU segmentation work in practice has been run with the existing GPU-capable environment when needed.
A future Codex session should check the currently working environment already used by the finished pipeline before reinstalling anything.

That means:

- prefer the existing working environment over rebuilding from scratch
- verify imports first
- only change environment state if the current one is actually broken

## Short Instruction For Another Codex Session

If another Codex session asks "what should I read first to understand the segmentation algorithm in this repo?", the answer should be:

1. `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_segmentation_metric_method_tex/main.pdf`
2. the relevant production run script for the target experiment
3. `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_metric_catalog_growth_fusion_differentiation.md`
4. the relevant experiment-design note

That is the shortest correct handoff path.
