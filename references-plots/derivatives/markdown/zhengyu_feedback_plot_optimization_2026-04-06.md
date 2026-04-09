# Zhengyu Feedback And Plot Optimization Notes (2026-04-06)

Participants:
- `陈苗`: Lachlan Chen
- `Five`: Zhengyu

Purpose:
- Record Zhengyu's feedback on the current segmentation-derived metrics and plots.
- Preserve dataset-specific biological interpretation and preferred metrics for later plot refinement.
- Capture requested next-step plot improvements, especially statistical testing and clearer panel selection.

Status:
- This note is a working interpretation guide for plot optimization.
- It is not a replacement for the formal experiment-design notes.
- It should be read together with the experiment-specific references and output figures.

## High-Level Conclusions From The Discussion

1. The current segmentation quality is considered good enough for downstream quantification.
2. Growth does not need to show large between-group separation in every experiment; the main requirement is that the overall trajectory is increasing over time and biologically plausible.
3. Differentiation is the most important readout for `App65 DEO+Alginate`.
4. Fusion is the most important special-day readout for `App80 DEO`.
5. In density experiments, early counts are unreliable because organoids are not yet sufficiently formed for stable segmentation.
6. Plot selection should prioritize metrics whose trend matches prior biological expectation, even if some other derived metrics are noisier.

## Segmentation Quality Feedback

Zhengyu's assessment of the segmentation:
- once cystic structures start to form, the segmentation is broadly correct
- hand segmentation would likely not be substantially better for the usable images
- early-stage images remain intrinsically harder to segment

Implication:
- keep current segmentation pipeline as the production baseline
- treat very early time points more cautiously during interpretation, especially for `count`

## App65 DEO+Alginate

Primary biological message discussed:
- control and alginate groups should have similar growth, or control may be slightly stronger
- the main difference should be differentiation
- alginate-containing DEOs should maintain cystic morphology longer
- alginate groups should show delayed thickened epithelial walls and delayed darker appearances
- control should differentiate earlier and therefore become darker earlier

### Growth Metrics Preferred In Discussion

Preferred / acceptable:
- `average_perimeter_px`
- `total_area_px`

Interpretation target:
- all groups should generally increase over time
- control can be slightly higher
- exact point-to-point fluctuations are less important than overall trend

### Differentiation Metrics Preferred In Discussion

Preferred:
- `organoid_darkness_p90`
- `wall_darkness_mean`
- `core_darkness_mean`
- `roundness`
- `curvature`
- `roundness_deviation_norm`
- optionally `1 / roundness`
- optionally inverse-curvature style interpretation for differentiation severity

Biological logic captured in the discussion:
- differentiation produces thickened epithelial walls, budded-like morphology, and darker appearance
- differentiated organoids are less cystic and less circular
- therefore:
  - `roundness` should decrease with differentiation
  - `curvature` should decrease with differentiation when interpreted as a circularity-like shape measure
  - `roundness_deviation_norm` should increase with irregularity
  - darkness-based measures should increase in control later in time

Specific feedback on darkness metric choice:
- `P90` was considered convincing because it is robust to outliers and emphasizes the darker tail without being driven by extreme minima or maxima
- Zhengyu explicitly agreed that later control should be darker than alginate groups

### Fusion Metrics Mentioned For App65

Mentioned as possible but not the main claim:
- `peripheral_over_central`
- `normalized_edge_over_count_curvature`

Interpretation from the discussion:
- fusion in alginate is less visually obvious than in the Y-27632 experiment
- it can still be quantified, but it is not the primary story

## App80 DEO (Y-27632)

Primary biological message discussed:
- growth can be shown using size-like metrics
- fusion is more visible and important here
- differentiation can also be shown later using darkness-based or shape-based metrics

### Growth Metrics Preferred In Discussion

Preferred:
- `average_perimeter_px`
- `total_area_px`

Discussion note:
- if `area` is used both for growth and for a fusion-related story, those panels should be conceptually separated to avoid mixed interpretation

### Fusion Metrics Preferred In Discussion

Preferred / most discussed:
- `total_area_px` for the special fusion-focused context
- `normalized_edge_over_count_curvature`
- `organoid_pixel_count`
- `core_pixel_count`
- `center_weighted_edge_weight_sum`

Interpretation from discussion:
- Y-27632 fusion can be captured by a formula where higher fusion corresponds to lower `count`, lower `curvature`, and stronger internal edge structure
- Zhengyu explicitly explained the logic of:
  - `normalized_edge_over_count_curvature`
- Five agreed that this trend matched the expected biology in the density/fusion context

### Differentiation Metrics Preferred In Discussion

Preferred:
- `organoid_darkness_p90`
- darkness-based metrics in general
- `roundness`
- `curvature`

Interpretation target:
- later differentiation should correspond to darker appearance and lower cystic roundness

## Density Experiments

Primary biological message discussed:
- middle and high density should generally perform better than low density
- low density grows slower and differentiates less
- middle/high density should show more interaction and potentially more fusion

### Growth Metrics Preferred In Discussion

Preferred:
- `average_perimeter_px`
- `total_area_px`
- `count` only after the earliest days are excluded or down-weighted

Important caution from the discussion:
- early `count` is not trustworthy because the organoids have not formed enough for stable segmentation
- Zhengyu explicitly agreed that the first two days are unreliable for `count`

### Differentiation Metrics Preferred In Discussion

Preferred:
- `roundness`
- `curvature`
- `roundness_deviation_norm`
- optionally `1 / roundness`

Biological logic from discussion:
- low density grows slower and differentiates less
- therefore low density retains more cystic morphology
- that means low density should have higher roundness-like values and lower irregularity later

### Fusion Metrics Preferred In Discussion

Preferred:
- `normalized_edge_over_count_curvature`

Discussion note:
- Five said the trend of this metric looked more biologically plausible than some other fusion metrics for density
- both agreed that middle/high density should have more contact and more fusion than low density
- there was also explicit acknowledgment that fusion metrics in the density experiment are noisier and less obvious than in the Y-27632 experiment

## Statistical Plotting Requests From Zhengyu / Five Discussion

Requested additions for later plot refinement:
- add error bars at each time point
- perform same-day between-condition statistical comparisons
- for multiple groups on the same day, use ANOVA when appropriate
- for pairwise same-day comparisons, use t-test when appropriate
- annotate significant comparisons with `*` when `p < 0.05`

Important practical implication:
- subexperiment panels should not only be descriptive trend plots
- they should support same-day significance testing once the final set of chosen metrics is fixed

## Special-Day / Subexperiment Notes From The Discussion

### App80
- the singled-out `Day 6` App80 fusion panel was explicitly discussed as a standalone figure
- Five asked whether other time points could also be run with same-day statistical comparisons

### App65
- `Day 7` and `Day 13` were already being treated as focused comparison days
- Five asked whether other times could also be run similarly

### Density
- Five questioned why the density result extended to `Day 23`
- Zhengyu clarified that this referred to a separate density-related pre-experiment branch rather than the main App81 branch
- Five said the resulting trend still looked directionally consistent and could be treated as a density pre-experiment

## Practical Plot-Selection Guidance

When optimizing figures later, prioritize the following narrative mapping.

### App65
- growth:
  - `average_perimeter_px`
  - `total_area_px`
- differentiation:
  - `organoid_darkness_p90`
  - `wall_darkness_mean`
  - `core_darkness_mean`
  - `roundness`
  - `curvature`
  - `roundness_deviation_norm`
- fusion:
  - only secondary/supportive
  - prefer `peripheral_over_central` or `normalized_edge_over_count_curvature` if needed

### App80
- growth:
  - `average_perimeter_px`
  - `total_area_px`
- fusion:
  - `total_area_px` in the fusion-focused context
  - `normalized_edge_over_count_curvature`
  - `organoid_pixel_count`
  - `core_pixel_count`
  - `center_weighted_edge_weight_sum`
- differentiation:
  - darkness metrics and shape metrics later in time

### Density
- growth:
  - `average_perimeter_px`
  - `total_area_px`
  - cautious use of `count`
- differentiation:
  - `roundness`
  - `curvature`
  - `roundness_deviation_norm`
  - optionally `1 / roundness`
- fusion:
  - `normalized_edge_over_count_curvature`
  - interpret conservatively because the signal is noisier

## Notes On Metric Meanings Raised In Discussion

### `organoid_darkness_p90`
Interpretation used in the discussion:
- a robust darkness-tail metric
- emphasizes darker tissue without being dominated by extreme outliers
- useful for showing that later control organoids are darker and more differentiated

### `roundness_deviation_norm`
Explanation given by Zhengyu:
- draw a reference circle centered on the organoid
- measure the total area that deviates from that circle
- interpret it as irregularity of the organoid boundary / shape

### `normalized_edge_over_count_curvature`
Explanation given by Zhengyu:
- intended fusion heuristic
- higher fusion should correspond to:
  - lower `count`
  - lower `curvature`
  - more internal edge structure
- therefore the ratio was designed to rise with fusion severity

## Recommended Next Plot-Optimization Tasks

1. For each dataset, pick a small primary metric set instead of showing every available metric in the main figure.
2. Add error bars to all selected time-series plots.
3. Add same-day significance testing for the selected primary metrics.
4. Treat very early `count` cautiously, especially in density experiments.
5. Keep growth, fusion, and differentiation panels conceptually separated when the same metric can support more than one interpretation.
6. Prefer the metrics explicitly endorsed in this note when making presentation-ready panels.

## Relationship To Existing Outputs

This note should be read together with:
- `App80` outputs under:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`
- `App65` outputs under:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`
- `App81` outputs under:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery`
- metric catalog:
  - `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_metric_catalog_growth_fusion_differentiation.md`

## Provenance

Source of this note:
- user-provided WeChat-style chat history between `Five` and `陈苗`
- user clarified that `Five` refers to Zhengyu
- note created to support later plot optimization and metric selection
