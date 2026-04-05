# App65 Two-Subexperiment Analysis

Date: 2026-04-05
Source experiment: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App65 DEO+Alginate`
Segmentation output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`

## Purpose

This note records the correct App65 experiment split from the references and the focused post-analysis generated from the finished segmentation/database outputs.

No segmentation rerun was performed.

The analysis uses the saved App65 databases:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

## Correct Subexperiment Structure

For `App65 DEO+Alginate`, the references support two linked subexperiments inside the same dataset:

1. `Panel A`: full longitudinal alginate time course
2. `Panel B`: dedicated `Day 7` and `Day 13` detailed comparison across conditions

This is explicitly supported by:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/06_figure3_alginate_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/01_thesis_deo_chapter_notes.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/03_transcription_notes_2.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/04_handwritten_experiment_note.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`

## Generated Outputs

A dedicated subexperiment-analysis folder was created under the finished App65 output root:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis`

### Panel A: longitudinal time-course

Outputs:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/app65_panel_a_longitudinal_primary_metrics.pdf`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/app65_panel_a_longitudinal_primary_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/panel_a_selected_daily_summary.csv`

Included metrics:

- `total_area_px`
- `count`
- `center_weighted_edge_sum`
- `roundness`
- `wall_darkness_mean`
- `very_dark_area_ratio_gt035`

### Panel B: dedicated Day 7 and Day 13 comparison

Outputs:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/app65_panel_b_day7_day13_detailed_metrics.pdf`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/app65_panel_b_day7_day13_detailed_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/panel_b_day7_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/panel_b_day7_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/panel_b_day13_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/panel_b_day13_summary.csv`

Included metrics:

- `total_area_px`
- `center_weighted_edge_sum`
- `area_normalized_center_weighted_edge_instance_mean`
- `roundness`
- `wall_darkness_mean`
- `very_dark_area_ratio_gt035`

## Panel A Reading

Panel A should support the broad mechanobiology story:

- control and alginate groups all grow over time
- alginate mainly changes differentiation timing and morphology persistence rather than simply eliminating growth
- the alginate groups preserve a more cystic appearance for longer

Practical reading from the saved daily summary:

- `total_area_px` increases across the time course in all groups
- `count` is not a pure growth metric because fusion and splitting both change object number
- `roundness`, `wall_darkness_mean`, and `very_dark_area_ratio_gt035` are the most useful morphology context metrics for the longitudinal panel

## Panel B Reading

Panel B is the dedicated late-time morphology and fusion comparison.

The references indicate that `Day 7` and `Day 13` were chosen because one representative image per time point is too sparse, and these later days better expose fusion and differentiation differences.

### Day 7

From `panel_b_day7_summary.csv`:

- `0.02% Alginate` has the largest mean and median `total_area_px`
- `0.02% Alginate` also has the highest `center_weighted_edge_sum`
- `roundness` is slightly higher in both alginate groups than control
- darkness metrics are still relatively close between groups at this stage

Conservative reading:

- by Day 7, alginate has not simply suppressed organoid growth
- `0.02% Alginate` supports large connected structures while still keeping slightly more cystic morphology than control
- this is compatible with delayed differentiation rather than pure growth failure

### Day 13

From `panel_b_day13_summary.csv`:

- control has the highest mean `total_area_px`
- control also has the highest `center_weighted_edge_sum`
- control remains slightly rounder than `0.02% Alginate`, but the morphology spread is wider in all groups
- `0.05% Alginate` shows the highest `wall_darkness_mean` and `very_dark_area_ratio_gt035`

Conservative reading:

- by Day 13, the groups are more heterogeneous
- control still supports large connected masses
- the stronger dark-wall metrics in `0.05% Alginate` suggest that late morphology should not be reduced to one scalar interpretation
- the safest App65 claim remains that alginate changes the timing and style of differentiation rather than simply producing one monotonic late-day ranking

## Recommended App65 Interpretation

The current App65 segmentation/database supports the following reading:

1. `Panel A`:
   - control and alginate all grow over time
   - alginate effects are most important in morphology timing, not just in total size
2. `Panel B Day 7`:
   - alginate, especially `0.02%`, can still support large connected structures while preserving cystic morphology
3. `Panel B Day 13`:
   - late-stage morphology becomes more heterogeneous
   - differentiation-related darkness and wall-thickening metrics should be read together rather than reduced to one score
4. the safest top-level biological message remains:
   - alginate delays differentiation-associated morphology changes
   - control differentiates earlier
   - growth can remain similar or only modestly different across groups

## Code

The analysis is generated by:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app65_alginate_multiscale_cellpose/analyze_app65_subexperiments.py`

This script reads the finished App65 CSVs only and does not touch segmentation outputs.
