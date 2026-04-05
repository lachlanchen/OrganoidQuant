# App80 Two-Subexperiment Analysis

Date: 2026-04-05
Source experiment: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO`
Segmentation output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

## Purpose

This note records the correct App80 experiment split from the references and the focused post-analysis generated from the finished segmentation/database outputs.

No segmentation rerun was performed.

The analysis uses the saved App80 databases:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

## Correct Subexperiment Structure

For `App80 DEO`, the references support two subexperiments inside the same Y-27632 dataset:

1. `Panel A`: full longitudinal concentration time course
2. `Panel B`: dedicated `Day 6` `10x` fusion comparison across concentrations

This is explicitly supported by:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/07_figure5_y27632_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/01_thesis_deo_chapter_notes.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/03_transcription_notes_2.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_experiment_mapping_confirmed.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/data-docs/DEO_DATA_STRUCTURE_GUIDE.md`

Important clarification:

- App80 has one dedicated specific-day subexperiment: `Day 6`
- the "two specific days" logic belongs to `App65 DEO+Alginate` (`Day 7` and `Day 13`), not App80

## Generated Outputs

A dedicated subexperiment-analysis folder was created under the finished App80 output root:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis`

### Panel A: longitudinal time-course

Outputs:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/app80_panel_a_longitudinal_primary_metrics.pdf`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/app80_panel_a_longitudinal_primary_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/panel_a_selected_daily_summary.csv`

Included metrics:

- `total_area_px`
- `count`
- `center_weighted_edge_sum`
- `normalized_edge_over_count_curvature`
- `roundness`
- `wall_darkness_mean`

### Panel B: dedicated Day 6 fusion comparison

Outputs:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_b_day6_fusion/app80_panel_b_day6_fusion_metrics.pdf`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_b_day6_fusion/app80_panel_b_day6_fusion_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_b_day6_fusion/panel_b_day6_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_b_day6_fusion/panel_b_day6_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis/panel_b_day6_fusion/panel_b_day6_trend_stats.csv`

Included metrics:

- `total_area_px`
- `count`
- `center_weighted_edge_sum`
- `central_inside_over_peripheral`
- `area_normalized_center_weighted_edge_instance_mean`
- `normalized_edge_over_count_curvature`

## Panel A Reading

Panel A should be used to support the time-course story:

- all concentration groups grow over time
- control is not the strongest late connected-mass condition
- by late time points, larger connected structures are more prominent in treated groups, especially the higher concentrations
- differentiation should be interpreted from later morphology-oriented metrics, not from the Day 6 panel alone

Practical reading from the saved daily summary:

- `total_area_px` rises in all groups from early to late days
- by `Day 6`, the largest mean segmented area is at `100uM`, followed by `20uM`, `50uM`, `10uM`, then control
- `count` is not a pure growth metric here because count can drop or stay low when organoids fuse into larger connected masses
- `roundness` and `wall_darkness_mean` should be read as late-stage morphology context rather than the primary fusion endpoint

## Panel B Reading

Panel B is the biologically important dedicated fusion comparison.

The references indicate that `Day 6` is the correct comparison point because it is:

- late enough for fusion to be visible
- early enough that stronger `Day 7` differentiation morphology does not dominate the visual interpretation

### What the Day 6 metrics actually show

The strongest positive dose trends at Day 6 are:

- `center_weighted_edge_sum`: Spearman rank rho vs dose `0.4437`
- `total_area_px`: Spearman rank rho vs dose `0.4180`

This means the cleanest concentration-dependent signal at Day 6 is:

- larger connected masses
- stronger internalized edge structure inside those masses

These are both compatible with stronger fusion under higher Y-27632.

### Condition-level Day 6 pattern

From `panel_b_day6_summary.csv`:

- `100uM` has the highest Day 6 mean and median `total_area_px`
- `20uM` and `100uM` have the highest Day 6 `center_weighted_edge_sum`
- `20uM` has the highest `central_inside_over_peripheral` mean, but this metric does not show a strong monotonic dose trend across all images

So the safer Day 6 App80 statement is:

- fusion-supporting structure is stronger in the treated groups, especially `20uM` to `100uM`
- `100uM` is the clearest large-connected-mass condition at Day 6
- `20uM` also scores strongly in internal-edge mass metrics and should not be ignored

### Important caveat about the normalized fusion proxy

`normalized_edge_over_count_curvature` shows a negative dose trend at Day 6:

- Spearman rank rho vs dose `-0.3332`

This does not mean control truly has the strongest fusion.

The reason is structural:

- this metric divides by `count * curvature`
- when control images have fewer connected objects, the denominator can become small
- that can artificially inflate the ratio even when the biological picture is not stronger fusion

Therefore:

- do not use `normalized_edge_over_count_curvature` alone as the Day 6 App80 fusion score
- use it only as a secondary proxy
- prefer `center_weighted_edge_sum`, `total_area_px`, and the internal-edge family for the dedicated Day 6 comparison

## Recommended App80 Interpretation

The current App80 segmentation/database supports the following reading:

1. `Panel A`:
   - Y-27632-treated groups maintain larger connected cystic structures through the time course
   - growth continues in all groups, but count alone should not be read as growth because fusion changes object number
2. `Panel B`:
   - the dedicated Day 6 fusion comparison is best supported by fused-mass area and internal-edge mass metrics
   - the strongest support is in `20uM` to `100uM`, with `100uM` showing the clearest large-mass phenotype
3. differentiation:
   - should be evaluated mainly from later morphology metrics and the full differentiation panels, not from the Day 6 fusion panel alone

## Code

The analysis is generated by:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/analyze_app80_two_subexperiments.py`

This script reads the finished App80 CSVs only and does not touch segmentation outputs.
