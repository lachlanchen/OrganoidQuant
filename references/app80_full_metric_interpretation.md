# App80 Full Metric Interpretation

Date: 2026-04-05
Source root: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO`
Output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

## Scope

This note explains how to read the completed App80 all-concentration metric panels after the full backfill from the saved segmentation intermediates.

Main figure folder:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/full_metrics`

Main databases:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/daily_summary.csv`

## Experimental Design Reading

`App80 DEO` is the Y-27632 concentration experiment.

Conditions:

- `No`
- `10uM`
- `20uM`
- `50uM`
- `100uM`

Based on the thesis and figure-design references, the main intended biological message is:

- Y-27632 increases fusion in a concentration-dependent way
- Y-27632 keeps organoids more cystic
- Y-27632 delays differentiation relative to control
- `Day 6` is the cleanest dedicated fusion-comparison day because `Day 7` begins to carry stronger differentiation confounding

This means the App80 metrics should not be read as a single scalar ranking. They should be separated into:

- growth
- fusion
- differentiation

and interpreted on the correct time scale.

## Figure Set

The grouped App80 full-metric panels are:

- Growth:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/full_metrics/app80_all_concentrations_growth_full.pdf`
- Fusion core:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/full_metrics/app80_all_concentrations_fusion_core_full.pdf`
- Fusion internal-edge:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/full_metrics/app80_all_concentrations_fusion_internal_edge_full.pdf`
- Differentiation:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/full_metrics/app80_all_concentrations_differentiation_full.pdf`
- Helper / normalization:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/full_metrics/app80_all_concentrations_helpers_full.pdf`

## Growth Interpretation

### Primary growth metrics

Use these first:

- `total_area_px`
- `sum_intensity`

Meaning:

- `total_area_px` is the cleanest segmentation-based growth readout in this pipeline
- `sum_intensity` is a signal-based morphology/growth proxy from the hybrid black-background signal image

Expected App80 reading:

- all groups can grow over time
- growth alone is not the main thesis claim here
- stronger Y-27632 may produce larger connected cystic masses, so area can rise together with fusion

### Supportive growth/context metrics

- `count`
- `average_perimeter_px`
- `reciprocal_sum_intensity`
- `sum_intensity_relative_change`
- `reciprocal_relative_change`

Important caveat:

- `count` is not a pure growth metric in App80
- count can fall because of fusion, not because growth is weaker
- perimeter can rise because objects become larger or more irregular

Practical reading:

- if `total_area_px` rises while `count` falls, that is compatible with fusion plus growth
- if `sum_intensity` and `total_area_px` move together, that supports a real size/material increase
- if relative-change curves spike only at isolated time points, treat them as kinetics/context rather than the main biological endpoint

## Fusion Interpretation

Fusion is the central App80 question.

The most important design point is:

- compare fusion most seriously around `Day 6`
- by `Day 7`, differentiation begins to confound morphology more strongly

### Primary fusion metrics

Use these first:

- `normalized_edge_over_count_curvature`
- `inverse_edge_count_curvature`
- `central_inside_over_peripheral`
- `central_inside_fraction`
- `center_weighted_edge_sum`
- `area_normalized_center_weighted_edge_instance_mean`

What they mean:

- `normalized_edge_over_count_curvature`
  - higher edge support after normalization by count and curvature
  - useful as a compact cross-condition fusion proxy
- `inverse_edge_count_curvature`
  - inverse composite of edge, count, and curvature
  - useful when the inverse visually separates fused states better
- `central_inside_over_peripheral`
  - higher values mean stronger edge structure lies deeper inside the segmented object
  - this is close to the biological idea of internalized interfaces during fusion
- `central_inside_fraction`
  - larger fraction means more of the edge signal is concentrated centrally rather than near the periphery
- `center_weighted_edge_sum`
  - sums internal edge signal with stronger weight near the object center
  - larger value suggests stronger internalized structure in fused masses
- `area_normalized_center_weighted_edge_instance_mean`
  - same center-weighted idea but normalized by instance area and averaged per object
  - less dominated by simply having larger objects

### Supportive fusion metrics

- `edge_intensity`
- `edge_density`
- `edge_reciprocal`
- `gradient_mean`
- `gradient_reciprocal`
- `central_inside_edge_mean`
- `peripheral_inside_edge_mean`
- `outer_ring_edge_mean`
- `central_inside_over_outer`
- `peripheral_over_central`
- `center_weighted_edge_mean`
- `instance_center_weighted_edge_sum_mean`

Practical reading:

- higher Y-27632 should generally shift edge structure inward and support larger connected cystic masses
- control may still show contact/aggregation, but the strongest fusion claim should come from the internal-edge family around `Day 6`
- if a metric rises mainly because `count` collapsed but internal-edge metrics do not support it, do not call that strong fusion by itself

Recommended App80 fusion panel reading order:

1. `central_inside_over_peripheral`
2. `center_weighted_edge_sum`
3. `area_normalized_center_weighted_edge_instance_mean`
4. `normalized_edge_over_count_curvature`
5. `count` and `total_area_px` as context

## Differentiation Interpretation

In App80, differentiation means loss of clean cystic morphology and emergence of thicker, darker, more irregular epithelial structures.

This becomes more confounding later in the time course, especially by `Day 7`.

### Primary differentiation metrics

Use these first:

- `roundness`
- `roundness_deviation_norm`
- `organoid_darkness_p90`
- `very_dark_area_ratio_gt035`
- `wall_darkness_mean`
- `wall_core_darkness_ratio`

What they mean:

- `roundness`
  - closer to `1` means closer to a same-area circle
  - lower values suggest more irregular, budded, or thickened morphology
- `roundness_deviation_norm`
  - normalized area deviation from a same-area circle
  - higher values mean less cystic / more irregular morphology
- `organoid_darkness_p90`
  - upper-tail darkness inside segmented organoids
  - useful for picking up dark differentiated subregions
- `very_dark_area_ratio_gt035`
  - fraction of organoid pixels exceeding a high darkness threshold
  - useful for thickened/dark states
- `wall_darkness_mean`
  - average darkness in the adaptive wall region
  - biologically relevant when differentiated walls thicken and darken
- `wall_core_darkness_ratio`
  - compares wall darkness to the core darkness
  - higher values suggest darker walls relative to the lumen/core

### Supportive differentiation metrics

- `roundness_deviation_px_total`
- `organoid_darkness_mean`
- `organoid_darkness_p95`
- `wall_darkness_p90`
- `core_darkness_mean`
- `average_perimeter_px`

Practical reading:

- control is expected to differentiate earlier
- higher Y-27632 is expected to preserve cystic morphology longer and delay differentiation
- if a high-concentration group stays rounder with lower wall darkness at late days, that supports delayed differentiation
- use late days for differentiation reading, not `Day 6` alone

Recommended App80 differentiation panel reading order:

1. `roundness`
2. `roundness_deviation_norm`
3. `wall_darkness_mean`
4. `wall_core_darkness_ratio`
5. `very_dark_area_ratio_gt035`
6. `organoid_darkness_p90`

## Helper Metrics

These are not primary biological endpoints by themselves:

- `count_norm`
- `curvature_norm`
- `edge_norm`
- `background_gray_median`
- `organoid_pixel_count`
- `wall_pixel_count`
- `core_pixel_count`
- `center_weighted_edge_weight_sum`
- `area_normalized_center_weighted_edge_instance_std`
- `area_normalized_center_weighted_edge_instance_median`

Use them for:

- checking scale consistency
- understanding how a composite metric was built
- quality control of the downstream summaries

Do not use them alone as the main thesis figure endpoint.

## Recommended Figure-Level Story For App80

If the goal is to support the original App80 experiment design clearly, the safest interpretation structure is:

### 1. Growth over time

Use:

- `total_area_px`
- `sum_intensity`

Claim:

- Y-27632 does not simply shrink the system; large connected cystic masses still grow over time

### 2. Fusion comparison around Day 6

Use:

- `central_inside_over_peripheral`
- `center_weighted_edge_sum`
- `area_normalized_center_weighted_edge_instance_mean`
- `normalized_edge_over_count_curvature`

Claim:

- increasing Y-27632 shifts morphology toward stronger fusion / larger connected structures
- `Day 6` is the correct comparison point because it minimizes differentiation confounding

### 3. Delayed differentiation at later time points

Use:

- `roundness`
- `roundness_deviation_norm`
- `wall_darkness_mean`
- `wall_core_darkness_ratio`
- `very_dark_area_ratio_gt035`

Claim:

- control differentiates earlier
- higher Y-27632 preserves rounder, more cystic structures longer
- darker and thicker wall-like morphology rises earlier in control than in the higher Y-27632 groups

## What Not To Overclaim

Do not claim that any one metric alone is “the fusion score” for all App80 stages.

Reason:

- App80 changes both fusion and differentiation over time
- large late objects can reflect growth, fusion, and differentiation simultaneously
- that is why the internal-edge metrics and the late-day differentiation metrics must be read separately

In practice:

- use `Day 6` for fusion comparison
- use later days for differentiation comparison
- keep growth as a parallel context track, not the only endpoint

## Related Notes

- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/07_figure5_y27632_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/app80_internal_edge_centrality_metric.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_metric_catalog_growth_fusion_differentiation.md`
