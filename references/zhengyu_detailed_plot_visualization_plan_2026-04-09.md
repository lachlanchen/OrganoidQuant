# Zhengyu Detailed Plot And Visualization Plan (2026-04-09)

## Source Material
This plan integrates all currently available guidance from Zhengyu's comments.

Primary source files:
- DOCX summary: `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_selection_comments_2026-04-07.docx`
- Handwritten figure note image: `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_metric_selection_handwritten_note_2026-04-07.jpeg`
- Structured conversion note: [zhengyu_plot_comment_conversion_2026-04-09.md](/home/lachlan/ProjectsLFS/Zhengyu/references/zhengyu_plot_comment_conversion_2026-04-09.md)
- Earlier chat-derived note: [zhengyu_feedback_plot_optimization_2026-04-06.md](/home/lachlan/ProjectsLFS/Zhengyu/references/zhengyu_feedback_plot_optimization_2026-04-06.md)

Related transcript markdown under `references-plots/`:
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/density_metric_selection_and_statistics_feedback_transcript.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/plot_annotation_significance_and_color_scheme_feedback_transcript.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/nazen_art_demo_unrelated_transcript.md`

## Why This Plan Exists
The previous figures already established usable metrics. The next step is not new quantification. It is figure refinement:
- choose one primary metric per biology question when possible
- standardize plot style across datasets
- simplify significance display
- move pairwise detail out of crowded longitudinal plots and into focused comparison panels or text
- remove labels or styling elements that Zhengyu explicitly does not want

## Global Design Rules
### Layout
- Time-course plots should use evenly spaced x-axis positions.
- Do not display `Relative day` as an axis label in final manuscript-style plots.
- Use simple day labels such as `D0`, `D1`, `D2`, etc.
- Remove panel titles where they are redundant with the figure legend.
- Remove unnecessary horizontal reference lines.
- Remove scale bars from statistical summary figures unless there is a strong reason to keep them.

### Styling
- Use one consistent style family across App80, App65, App81, and density pre-experiment figures.
- Keep significance markers black.
- Keep significance connector lines black.
- Do not use colored stars.
- Use a consistent group-color palette across all plots.
- Use the same plotting grammar for all focused same-day comparison panels, preferably box plots or a single consistent alternative.

### Statistical display policy
- On longitudinal plots with 3 groups or more, show only the overall same-day significance result on the plot.
- Do not clutter longitudinal plots with multiple pairwise comparison connectors.
- Keep pairwise comparisons for:
  - focused same-day comparison figures
  - manuscript text
  - supplementary tables if needed
- Do not print raw `ANOVA p = ...` text on the figure if Zhengyu only wants stars.
- Use `ns` only where it clarifies a point Zhengyu explicitly wants to make.

### Naming policy for final figures
Use manuscript-friendly condition names.
- `No` -> `Control`
- `0.02% Alginate` -> `Low Alginate`
- `0.05% Alginate` -> `High Alginate`
- `NO` in App80 focused plots -> `Control`

For App80 Y-27632, keep concentration labels readable and standardized:
- `Control`
- `10 uM`
- `20 uM`
- `50 uM`
- `100 uM`

## Statistics Policy By Dataset
### App81 density
- Treat App81 as low-`n` and statistically weak.
- If many time points have only 1 to 3 images, avoid formal same-day significance annotation.
- Show error bars only where `n` allows a meaningful spread estimate.
- A descriptive figure is acceptable and probably preferable.

### App65 alginate
- Longitudinal plots can support same-day ANOVA because per-day image counts are much larger.
- Pairwise comparisons should mostly be shown in focused same-day panels and described in text.

### App80 Y-27632
- Longitudinal plots can support same-day ANOVA.
- The dedicated Day 6 focused comparison is the right place for pairwise significance connectors.

### Density pre-experiment (`DEO test 2025.10.1`)
- Treat similarly to App81 unless `n` is clearly adequate at each day.
- Prefer descriptive trends over over-annotated significance if the per-timepoint sample size is weak.

## Dataset-Specific Plot Plan

# 1. App81 Density Main Experiment
Output root:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery`

## Biology message
- Medium and high density are better than low density for growth.
- Low density grows more slowly and remains less differentiated.
- Fusion is directionally consistent with more interaction in medium/high density, but this dataset is weak for strong statistical claims.

## Primary metric choices
### Growth
Primary:
- `average_perimeter_px`

Supportive:
- `total_area_px`

Reason:
- Zhengyu repeatedly preferred perimeter for density growth.
- Area can remain supplementary.

### Differentiation
Primary recommendation:
- `organoid_darkness_p90` if available and visually coherent

Fallback if darkness is not convincing:
- `roundness_deviation_norm`

Reason:
- Zhengyu wants cross-experiment consistency in differentiation metrics.
- But App81 may still visually read better with roundness-based differentiation if darkness is weak.

### Fusion
Primary descriptive metric:
- `normalized_edge_over_count_curvature`

Reason:
- This was discussed as the best available fusion trend for density.
- However, statistical overclaiming should be avoided.

## Figure plan
### Main longitudinal figure
Panels:
- Growth: `average_perimeter_px`
- Differentiation: choose one of:
  - `organoid_darkness_p90`, or
  - `roundness_deviation_norm`
- Fusion: `normalized_edge_over_count_curvature`

Style:
- lines + points
- optional error bars only where `n >= 2`
- no ANOVA stars by default unless the per-day counts are adequate and consistent

### Optional supplementary longitudinal figure
Panels:
- `total_area_px`
- `roundness`
- `curvature`

### Statistics policy
- Default: no formal same-day statistical stars on the main App81 figure.
- If statistics are kept, add a clear note that the sample size is small.

## Explicit removals
- remove `Relative day`
- remove scale bars
- remove crowded significance annotations

# 2. App65 Alginate
Output root:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`
- ongoing alternative segmentation root:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_v3_direct_brightfield`

## Biology message
- Growth is similar across groups, with control slightly stronger at some times.
- Differentiation is lower in alginate than control.
- Alginate maintains cystic morphology longer and delays darkened/thickened morphology.
- Fusion differences are present but less visually obvious than differentiation.

## Primary metric choices
### Growth
Primary:
- `average_perimeter_px`

Supportive:
- `total_area_px`

Reason:
- Zhengyu explicitly prefers perimeter here.
- Growth only needs to show that all groups increase over time and control is similar or slightly higher.

### Differentiation
Primary:
- `organoid_darkness_p90`

Supportive:
- `core_darkness_mean`
- `roundness_deviation_norm`

Reason:
- Zhengyu repeatedly pointed to darkness-based differentiation in alginate.
- Roundness-based metrics remain useful but are not the primary manuscript metric here.

### Fusion
Primary recommendation:
- choose one for the main longitudinal panel:
  - `peripheral_over_central`, or
  - `normalized_edge_over_count_curvature`

Focused comparison metric:
- use the cleaner of the two for Day 8 and Day 11 panels

Reason:
- Zhengyu’s comments leave both open, but the final plot should not show both as equal main claims.
- One should be selected as the narrative metric, the other can go supplementary.

## Longitudinal main figure
Panels:
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: selected primary fusion metric

Significance display:
- one black star label per same-day ANOVA result only
- pairwise detail moved to text or focused plots

Specific day notes from Zhengyu comments:
### Growth
- Day 6: highlight if ANOVA is significant
- Day 7: highlight if ANOVA is significant
- Day 11: highlight if ANOVA is significant

### Differentiation
- Day 11 is important
- Day 0 and Day 1 may be reviewed but should not dominate the message

### Fusion
- Day 8 is important
- Day 11 should be added as a focused comparison day
- handwritten note also says control should show more fusion around Day 7

## Focused same-day figures
### Focus 1: Day 8 fusion
Plot type:
- box plot preferred

Groups:
- `Control`
- `Low Alginate`
- `High Alginate`

Annotations:
- black pairwise connectors
- black stars only
- remove ANOVA label text

### Focus 2: Day 11 fusion or differentiation
Use whichever metric tells the stronger story.

Recommended order:
1. Differentiation: `organoid_darkness_p90`
2. Fusion: chosen primary fusion metric

If only one Day 11 focus panel is kept, it should probably be differentiation unless the fusion contrast is clearly stronger.

## Supplemental App65 panels
- `total_area_px` growth support
- `core_darkness_mean`
- `roundness_deviation_norm`
- alternate fusion metric not chosen as primary

# 3. App80 Y-27632
Output root:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

## Biology message
- Growth increases over time across conditions.
- Y-27632 influences fusion, especially around Day 5 to Day 6.
- Later differentiation can be captured by darkness-based metrics.

## Primary metric choices
### Growth
Primary:
- `average_perimeter_px`

Supportive:
- `total_area_px`

Reason:
- Zhengyu wants perimeter, but area remains useful and should not be discarded.

### Differentiation
Primary:
- `organoid_darkness_p90`

Supportive:
- `roundness_deviation_norm`
- `roundness`

Reason:
- Zhengyu shifted toward `Darkness P90` for consistency.

### Fusion
Primary:
- `center_weighted_edge_sum`

Supportive:
- `total_area_px`
- possibly `normalized_edge_over_count_curvature` as a secondary exploration metric

Reason:
- Zhengyu explicitly selected `Center-Weighted Edge Sum` as the final fusion metric for App80.
- Handwritten note also says area is informative for fusion.

## Longitudinal main figure
Panels:
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `center_weighted_edge_sum`

ANOVA stars on important days only, in black.

Important days from comments:
- Differentiation: Day 2, Day 5, Day 7
- Fusion: Day 0, Day 4, Day 5, Day 6

## Focused same-day figure
### Day 6 fusion
Plot type:
- box plot preferred

Metric:
- `center_weighted_edge_sum`

Supportive alternate version:
- `total_area_px`

Group labels:
- `Control`
- `10 uM`
- `20 uM`
- `50 uM`
- `100 uM`

Annotations:
- black pairwise connectors
- black stars only
- no printed ANOVA result text
- no horizontal reference line

Special handling note:
- Zhengyu’s docx suggests testing whether removing the minimum `50 uM` outlier changes the Day 6 significance result.
- This should be handled explicitly and transparently:
  - keep the main reported figure with all points by default
  - only generate the outlier-removed version as a sensitivity check

# 4. Density Pre-Experiment (`DEO test 2025.10.1`)
Output root:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery`

## Biology message
- This is a pre-experiment trend dataset.
- It should support the main density story, not replace it.

## Primary metric choices
### Growth
- `average_perimeter_px`

### Differentiation
- `organoid_darkness_p90` if consistent
- otherwise `roundness_deviation_norm`

### Fusion
- `normalized_edge_over_count_curvature`

## Figure policy
- treat as supportive / secondary
- avoid over-annotated significance if `n` is limited or irregular
- keep the styling matched to App81

## Detailed figure inventory to generate later
### App81
1. `app81_density_primary_longitudinal.pdf`
   - perimeter / differentiation / fusion
2. `app81_density_supporting_longitudinal.pdf`
   - area / roundness / curvature
3. Optional no-statistics version if Zhengyu prefers the simplest presentation

### App65
1. `app65_alginate_primary_longitudinal.pdf`
   - perimeter / darkness p90 / primary fusion metric
2. `app65_alginate_growth_supporting_longitudinal.pdf`
   - area support if needed
3. `app65_alginate_focus_day8_fusion.pdf`
4. `app65_alginate_focus_day11.pdf`
   - differentiation or fusion depending on the strongest result
5. `app65_alginate_pairwise_stats_table.csv`
   - for manuscript text use

### App80
1. `app80_y27632_primary_longitudinal.pdf`
   - perimeter / darkness p90 / center-weighted edge sum
2. `app80_y27632_supporting_longitudinal.pdf`
   - area / roundness deviation / other support metrics
3. `app80_y27632_focus_day6_fusion.pdf`
4. Optional sensitivity figure:
   - `app80_y27632_focus_day6_fusion_outlier_check.pdf`

### Density pre-experiment
1. `densityB_primary_longitudinal.pdf`
2. `densityB_supporting_longitudinal.pdf`

## Concrete implementation rules for plotting code
- longitudinal panels:
  - equal x spacing by ordered day labels
  - black significance stars only
  - no pairwise connectors unless the panel is a focused same-day comparison
- focused same-day panels:
  - box plot or one unified style
  - pairwise connectors allowed
  - no ANOVA text label
  - black connectors and black stars
- legends:
  - use consistent ordering across all figures
- fonts and sizes:
  - keep the same font family and sizing rules across all datasets
- color mapping must not change between the longitudinal and focused figures of the same dataset

## Recommended execution order
1. Finalize App65 metric choice for fusion:
   - pick `peripheral_over_central` or `normalized_edge_over_count_curvature`
2. Finalize App81 differentiation choice:
   - `organoid_darkness_p90` or `roundness_deviation_norm`
3. Regenerate all primary longitudinal figures with the unified visual style.
4. Regenerate focused same-day figures.
5. Add black-only significance annotations.
6. Export pairwise tables separately for manuscript writing.

## Practical interpretation guardrails
- App81 should not carry the statistical burden of the paper.
- App65 should emphasize delayed differentiation under alginate more than fusion.
- App80 should emphasize fusion around Day 5 to Day 6 and use darkness for later differentiation.
- Focused same-day plots should support the main biological claim, not simply the largest p-value contrast.

## Current best primary metric set
If a single standardized figure set is needed now, the most aligned selection is:

### App81
- Growth: `average_perimeter_px`
- Differentiation: `roundness_deviation_norm` or `organoid_darkness_p90` after visual check
- Fusion: `normalized_edge_over_count_curvature`

### App65
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `peripheral_over_central` or `normalized_edge_over_count_curvature`

### App80
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `center_weighted_edge_sum`
