# Zhengyu Plot Comment Conversion (2026-04-09)

## Sources
- DOCX: `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_selection_comments_2026-04-07.docx`
- JPEG: `/home/lachlan/ProjectsLFS/Zhengyu/references-plots/deo_quantification_metric_selection_handwritten_note_2026-04-07.jpeg`
- Related earlier note: [zhengyu_feedback_plot_optimization_2026-04-06.md](/home/lachlan/ProjectsLFS/Zhengyu/references/zhengyu_feedback_plot_optimization_2026-04-06.md)

## Purpose
This note converts Zhengyu's figure-selection and statistical-annotation comments into structured Markdown so later plotting work can follow a consistent specification.

## Global Figure Rules
- Use equal spacing on the x-axis for time points.
- Remove `Relative day` from axis labels when preparing final figures.
- Remove titles where possible.
- Keep annotation color black.
- Use black lines and black `*` for significance markers.
- Keep color scheme and plotting style consistent across datasets.
- Prefer a unified visual style such as box plots for focused same-day comparisons.
- For longitudinal figures, show only the overall ANOVA-style same-day significance result on the plot.
- Put pairwise comparisons into the main text or focused comparison figures rather than overcrowding the longitudinal plot.
- Remove visible `ANOVA` labels and raw ANOVA result text from the final plotted panels.
- Remove horizontal reference lines where they are not necessary.
- Consider removing scale bars from statistical summary plots.

## Statistical Annotation Rules
- Same-day multi-group comparison: use one-way ANOVA as the primary on-plot test when there are three groups.
- Pairwise comparisons: keep for text or focused comparison figures.
- Significance should be shown with black stars only.
- `ns` should be used only where Zhengyu explicitly expects non-significance to be conveyed.

## Dataset 1: App81 Density
### Preferred metrics
- Growth: `Average Perimeter`
- Differentiation: originally `Roundness Deviation (Norm)`
- Fusion: `Normalized Edge / (Counts * Curvature)`

### Zhengyu's comments
- This dataset has very small `n` in some places (`n = 1/2/3`), so formal statistics may be inappropriate.
- Consider removing statistical analysis from this dataset.
- Consider removing scale bars.
- `Roundness Deviation (Norm)` appears to be `ns` under ANOVA.
- Differentiation metric may be better replaced with `Darkness P90` so all three major experiments use the same differentiation standard.

### Current implication
- Keep density figures simple and conservative.
- Avoid overclaiming statistics for App81.
- If a unified differentiation metric across experiments is desired, prefer `Organoid Darkness P90` over `Roundness Deviation (Norm)`.

## Dataset 2: App65 Alginate
### Preferred metrics
- Growth: `Average Perimeter`
- Differentiation: `Organoid Darkness P90`
- Fusion: `Peripheral / Central` or `Normalized Edge / (Counts * Curvature)`

### Growth panel comments
- Use `Perimeter` as the growth metric.
- Use ANOVA for same-day significance.
- Highlighted days from the docx:
  - Day 6: `**`, with `No / 0.02% Alginate` pair noted as `*`
  - Day 7: `**`, with `No / 0.05% Alginate` pair noted as `**`
  - Day 11: `*`, with `No / 0.05% Alginate` pair noted as `*`
- On-plot annotation should show the overall same-day significance only.
- Pairwise comparisons should be reflected in text.

### Differentiation panel comments
- Use `Organoid Darkness P90`.
- Same-day ANOVA significance should be shown only as stars.
- Days explicitly noted in the docx:
  - Day 0 / Day 1 were flagged for ANOVA review
  - Day 11: `*`, with `No / 0.02% Alginate` pair noted as `**`
- Pairwise comparisons should be moved to text.

### Fusion panel comments
- Candidate metrics listed:
  - `Peripheral / Central`
  - `Normalized Edge / (Counts * Curvature)`
- Same-day ANOVA significance should be shown only as stars.
- Days explicitly noted:
  - Day 0 flagged for ANOVA review
  - Day 8: `**`, with pairwise `No / 0.02% Alginate **` and `No / 0.05% Alginate **`
- Add focused comparison figures for Day 8 and Day 11.
- In focused comparison figures:
  - rename `No` to `Control`
  - rename `0.02% Alginate` to `Low Alginate`
  - rename `0.05% Alginate` to `High Alginate`
  - remove ANOVA labels/result text
  - remove horizontal lines
  - use unified colors and style
  - show pairwise significance with black lines and black stars
- Handwritten note also emphasizes:
  - `Day 7` fusion should show more fusion in control
  - Day 11 should also be examined as a focused comparison

## Dataset 3: App80 Y-27632
### Preferred metrics
- Growth: `Perimeter`, with `Area` as a companion metric
- Differentiation: `Organoid Darkness P90`
- Fusion: `Center-Weighted Edge Sum`
- Day 6 focused comparison remains important

### Growth panel comments
- Use `Growth area` and `Growth perimeter`.
- ANOVA appears `ns` overall.
- On-plot significance should use black stars only.
- Pairwise comparisons should be reflected in text.

### Differentiation panel comments
- Use `Organoid Darkness P90`.
- Days noted in the docx for ANOVA significance review:
  - Day 2
  - Day 5
  - Day 7

### Fusion panel comments
- Use `Center-Weighted Edge Sum`.
- Days noted for ANOVA significance review:
  - Day 0
  - Day 4
  - Day 5
  - Day 6
- Handwritten note also says `Area` is informative for fusion and should be checked, especially around Day 5 and Day 6.

### Day 6 focused comparison comments
- Keep the dedicated Day 6 figure.
- For `50uM`, try removing the minimum outlier and check whether significance appears.
- If significance still does not appear, it is acceptable not to remove it.
- Rename `NO` to `Control`.
- Remove horizontal lines.
- Use unified colors and plot style.
- Show pairwise significance with black lines and black stars.

## Handwritten Image Additions
The handwritten page is consistent with the docx and reinforces these preferences:
- Density:
  - Growth: `Perimeter`
  - Differentiation: `Roundness deviation`
  - Fusion: `Normalized edge / (count * curvature)`
  - Many of these are marked `ns`, reinforcing the need for caution.
- App65:
  - Growth: `Perimeter`
  - Differentiation: `Darkness p90`
  - Fusion: `Peripheral / Central internal edge`
  - Day 7 and Day 11 are explicitly circled as important comparison points.
- App80 / Y-27:
  - Growth: `Perimeter`
  - Differentiation: `Darkness p90`
  - Fusion: `Area` and `Center-weighted edge sum`
  - Day 5 and Day 6 are emphasized.
- Additional layout reminder in the handwritten note:
  - unify font, line color, and figure style
  - remove or simplify extra labels
  - consider dropping scale bars from statistical summary figures

## Practical Plotting Checklist
### App81 density
- Prefer a simplified descriptive figure.
- If statistics are retained, be explicit that low `n` weakens inference.
- Consider switching differentiation to `Organoid Darkness P90` for cross-experiment consistency.

### App65 alginate
- Longitudinal primary figures:
  - Growth: `Average Perimeter`
  - Differentiation: `Organoid Darkness P90`
  - Fusion: choose between `Peripheral / Central` and `Normalized Edge / (Counts * Curvature)` based on cleaner trend
- Focused same-day figures:
  - Day 8 fusion
  - Day 11 fusion or differentiation as needed
- Relabel groups to `Control`, `Low Alginate`, `High Alginate` for focused figures.

### App80 Y-27632
- Longitudinal primary figures:
  - Growth: `Average Perimeter` plus `Total Area`
  - Differentiation: `Organoid Darkness P90`
  - Fusion: `Center-Weighted Edge Sum`
- Focused same-day figure:
  - Day 6
- Consider checking `Area` as a supportive fusion metric.

## Notes For Future Plot Refinement
- The docx comments are prescriptive rather than fully statistical.
- Where Zhengyu specifies a preferred day or metric, plotting should follow that preference first and only then check whether the statistics still support the message.
- App81 should be treated as the weakest statistical case due to small `n`.
- App65 and App80 are the clearer manuscript-level figures to refine first.
