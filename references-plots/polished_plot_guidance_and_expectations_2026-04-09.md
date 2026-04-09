# Polished Plot Guidance And Expectations (2026-04-09)

This note consolidates the current plot guidance from the materials in `references-plots/` and the later implementation choices used for the improved segmentation outputs.

Related source materials:
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/density_metric_selection_and_statistics_feedback_transcript.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/plot_annotation_significance_and_color_scheme_feedback_transcript.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_metric_selection_handwritten_note_2026-04-07_transcription.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_selection_comments_2026-04-07.docx`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_metric_selection_handwritten_note_2026-04-07.jpeg`

Supporting derived notes:
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/derivatives/markdown/zhengyu_feedback_plot_optimization_2026-04-06.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/derivatives/markdown/zhengyu_plot_comment_conversion_2026-04-09.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/derivatives/markdown/zhengyu_detailed_plot_visualization_plan_2026-04-09.md`

## Purpose
This file records the current manuscript-style plotting guidance:
- which metrics should be emphasized
- how significance should be displayed
- what the expected biological trends are
- how colors, labels, and titles should be standardized

It is intended to guide regenerated figures for the improved segmentation outputs.

## Global Figure Rules

### Layout
- Use three main panels when possible:
  - `Growth`
  - `Differentiation`
  - `Fusion`
- Use evenly spaced day labels such as `D0`, `D1`, `D2`, etc.
- Do not display `Relative day` as an axis label.
- Remove redundant panel titles where the caption/legend already explains the figure.
- Remove unnecessary horizontal reference lines.
- Remove scale bars from statistical summary plots.

### Significance display
- Use black significance lines and black stars only.
- Do not use colored stars.
- Do not print raw `ANOVA p=...` text on the main figures.
- On longitudinal plots, show only the same-day global significance result.
- Put pairwise comparisons into:
  - focused same-day panels
  - manuscript text
  - supplementary tables
- Do not crowd the main longitudinal plots with many pairwise brackets.
- For early unstable stages, especially density experiments, do not place stars on the first two days.

### Labeling
Use manuscript-friendly condition names:
- `No` -> `Control`
- `0.02% Alginate` -> `Low Alginate`
- `0.05% Alginate` -> `High Alginate`

For App80:
- `No` -> `Control`
- `10uM` -> `10 uM`
- `20uM` -> `20 uM`
- `50uM` -> `50 uM`
- `100uM` -> `100 uM`

### Color style
Use one consistent palette across datasets.

Recommended mapping:
- `Control`: `#222222`
- `Low`: `#2C6FB7`
- `Middle`: `#3FA7A3`
- `Mid-high`: `#F08A24`
- `High`: `#C73832`

Applied interpretation:
- App65:
  - `Control`: black
  - `Low Alginate`: blue
  - `High Alginate`: red
- App81:
  - `low`: blue
  - `middle`: teal
  - `high`: red
- App80:
  - `Control`: black
  - `10 uM`: blue
  - `20 uM`: teal
  - `50 uM`: orange
  - `100 uM`: red

## Metric Bank

### Growth candidates
- `average_perimeter_px`
- `total_area_px`

### Differentiation candidates
- `organoid_darkness_p90`
- `wall_darkness_mean`
- `core_darkness_mean`
- `roundness`
- `curvature`
- `roundness_deviation_norm`

### Fusion candidates
- `normalized_edge_over_count_curvature`
- `peripheral_over_central`
- `total_area_px` in the App80 fusion context
- `center_weighted_edge_sum`

## Dataset-Specific Guidance

## App81 Density

### Main biological expectation
- `middle` and `high` density should grow better than `low`
- `low` should stay more cystic and less differentiated
- fusion should trend higher in `middle/high`, but this is the weakest claim

### Preferred metrics
- Growth: `average_perimeter_px`
- Differentiation: `roundness_deviation_norm`
- Fusion: `normalized_edge_over_count_curvature`

### Supportive metrics
- `total_area_px`
- `roundness`
- `curvature`
- optionally `organoid_darkness_p90` if darkness becomes visually convincing

### Statistics policy
- first two days: no stars
- generally avoid strong statistical claims if per-day `n` is small
- use descriptive interpretation unless sample size is clearly adequate

## App65 Alginate

### Main biological expectation
- growth should be similar across groups, with `Control` slightly stronger at some times
- differentiation is the main story
- `Control` should become darker earlier
- alginate groups should maintain cystic morphology longer
- fusion exists but is secondary

### Preferred metrics
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `peripheral_over_central`

### Supportive metrics
- Growth support: `total_area_px`
- Differentiation support:
  - `core_darkness_mean`
  - `roundness_deviation_norm`
- Fusion support:
  - `normalized_edge_over_count_curvature`

### Expected emphasis days
- Growth:
  - `D6`
  - `D7`
  - `D11`
- Differentiation:
  - `D11`
- Fusion:
  - `D8`

### Significance policy
- no stars on the first two days
- longitudinal figure: same-day global stars only
- focused same-day panels: pairwise comparisons vs `Control`

### Practical implementation note
For the improved App65 `v3` segmentation output, the polished figure set now uses:
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `peripheral_over_central`

## App80 Y-27632

### Main biological expectation
- growth should increase across groups
- differentiation should rise later and can be shown with darkness
- fusion is the main special readout here
- strongest fusion signal should be in the mid/high Y-27 conditions around the special days

### Preferred metrics
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `total_area_px`

### Supportive fusion metric
- `center_weighted_edge_sum`

### Expected emphasis days
- Differentiation:
  - `D2`
  - `D5`
  - `D7`
- Fusion with `Area`:
  - `D4`
  - `D5`
  - `D6`
- Fusion with `Center-weighted edge sum`:
  - `D4`
  - `D5`
  - `D6`

### Practical interpretation from the handwritten note
- `Day 5 Area` looks more significant
- `Day 6 center` looks more significant

So the preferred narrative is:
- main fusion metric: `Area`
- supportive focused fusion metric: `Center-weighted edge sum`

### Growth note
- `Perimeter` may be mostly `ns`
- growth is not the main App80 headline

## Density Pre-Experiment

### Main biological expectation
- same direction as App81
- treat as a pre-experiment rather than the strongest quantitative result

### Preferred metrics
- Growth: `average_perimeter_px`
- Differentiation: `roundness_deviation_norm` or `organoid_darkness_p90` if visually coherent
- Fusion: `normalized_edge_over_count_curvature`

### Statistics policy
- first two days: no stars
- likely minimal or no stars unless per-day `n` is clearly sufficient

## Final Figure Set Recommendation

For each dataset, the preferred manuscript-style output is:

1. One main 3-panel longitudinal figure
2. One focused same-day figure for the biologically important days
3. One supplementary figure with supportive metrics only
4. One same-day global statistics table
5. One pairwise comparison table

## What Should Not Appear On Final Main Figures
- colored stars
- raw ANOVA labels
- too many pairwise brackets
- `Relative day`
- crowded titles
- early-day stars on weak/unstable data
- excessive `ns` labels

## Best Single-Metric Choices Per Dataset

### App81
- Growth: `average_perimeter_px`
- Differentiation: `roundness_deviation_norm`
- Fusion: `normalized_edge_over_count_curvature`

### App65
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `peripheral_over_central`

### App80
- Growth: `average_perimeter_px`
- Differentiation: `organoid_darkness_p90`
- Fusion: `total_area_px`
