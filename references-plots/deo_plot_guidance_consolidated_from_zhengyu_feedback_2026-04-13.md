# DEO Plot Guidance Consolidated From Zhengyu Feedback (2026-04-13)

## Purpose
This note consolidates the plotting guidance implied by four reference sources:
- `references-plots/deo_quantification_selection_comments_2026-04-13.md`
- `references-plots/deo_quantification_selection_handwritten_note_2026-04-13.jpeg`
- `references-plots/deo_metric_selection_and_segmentation_feedback_transcript.md`
- `references-plots/DEO定量选择260413.docx`

The goal is to convert the comments into one operational plotting specification that can be used to regenerate final manuscript-style figures.

This file intentionally distinguishes between:
- current preferred decisions
- acceptable fallback choices
- unresolved items that should remain explicit rather than being silently fixed by the plotting code

## Executive Summary

### Core figure philosophy
- Figures should be optimized for biological clarity and manuscript readability, not for maximizing the number of metrics shown.
- If two technically valid segmentation results exist, the visually clearer and biologically more convincing one is acceptable for representative overlays and figure panels.
- Main time-course figures should remain simple.
- Pairwise comparisons should not clutter the main longitudinal panels.
- Use one consistent plotting language across App81, App65, and App80.

### Global preferred figure language
- white background
- consistent condition colors across datasets
- consistent panel ordering
- even time spacing on the x-axis
- day labels shown as `D0`, `D1`, `D2`, etc.
- remove `Relative day`
- use black significance brackets and black stars only
- do not print raw ANOVA text on the figure
- do not crowd the main figures with pairwise brackets
- remove unnecessary horizontal guide lines
- remove redundant panel titles where possible
- use focused same-day panels for pairwise comparisons when needed

### Segmentation philosophy for plotting
- For microscopy overlays and stitched representative panels, the chosen segmentation should be biologically correct and visually comfortable.
- It does not need to preserve strict model purity if manual replacement or merged selection gives a more convincing biological result.
- For quantitative analysis, use one final chosen mask per source image consistently.
- Representative overlays should avoid visibly wrong merges, obviously missing major organoids, and distracting fragmental masks.

## Global Plotting Rules

### Layout and axis rules
- Use equal visual spacing between days, even if calendar gaps differ.
- Convert time labels to `D0`, `D1`, `D2`, etc.
- Remove `Relative day` as an axis label.
- Keep condition order fixed within a dataset.
- Keep panel order and metric order stable between figures.
- Do not overcrowd the figure with extra subtitles when the panel heading already states the metric.

### Significance display
- Show black stars only.
- Show black brackets only.
- Do not use colored stars.
- Do not print raw `ANOVA p=...` text directly on the main figure.
- Main longitudinal plots should show only same-day global significance if shown at all.
- Pairwise comparisons should go into:
  - focused same-day panels
  - manuscript text
  - supplementary tables
- If early time points are unstable or low-n, suppress stars there.
- If n is too small for a defensible claim, omit the significance display rather than over-annotating.

### Legends, colors, and naming
- Use one consistent palette across datasets.
- The working preferred palette is:
  - `Control`: black or very dark gray
  - `Low`: blue
  - `Middle`: teal or green-blue
  - `High`: red
- Condition labels should be manuscript-friendly:
  - `No` -> `Control`
  - `0.02 alginate` -> `Low Alginate`
  - `0.05 alginate` -> `High Alginate`
  - `10uM` -> `10 uM`
  - `20uM` -> `20 uM`
  - `50uM` -> `50 uM`
  - `100uM` -> `100 uM`
- Use the same color assignment consistently once chosen.
- Do not let one figure use a different semantic color mapping unless there is a very strong reason.

### Styling details
- Remove unnecessary background horizontal lines.
- Keep grid lines minimal or remove them entirely if they are visually noisy.
- In focused comparison panels, use one consistent plot type such as box plots.
- Use the same box/violin/bar style across comparable focused panels.
- Remove unnecessary titles from individual panels if they repeat caption information.
- Scale bars should not appear on statistical summary plots.
- For microscopy image panels, preserve scale bars only where they are actually informative.

## Segmentation and Overlay Guidance

### What Zhengyu’s feedback implies
The transcript makes an important practical point:
- the segmentation used for the figure should be one that “looks comfortable” and biologically convincing to a human viewer
- it is acceptable if a manually selected or merged segmentation is visually better than the default algorithm output

This means:
- final representative overlays can be selected from different segmentation versions
- panel-level replacement is acceptable when it corrects clear misses or merges
- the chosen final result must then be propagated consistently into the single-image exports and metric pipeline

### Overlay quality rules
- avoid fragmental hollow masks when a solid object is expected
- avoid clearly wrong merged adjacent organoids
- avoid missing large biologically obvious organoids
- use distinct instance colors for adjacent touching organoids when possible
- keep the final overlay readable at publication scale

### Quantification rule
- Quantification should use the final selected mask for each source image, not an earlier discarded stitched version.
- Once a stitched panel has been manually replaced, the downstream single-image export and metrics should inherit that corrected panel rather than the base segmentation.

## Metric Selection Principles

### General metric-selection rules
- Prefer metrics that preserve the biological trend clearly after the segmentation is corrected.
- If one metric is theoretically appealing but visually unstable, do not force it into the main figure.
- If a summed metric is being distorted by variable organoid count, consider an average-based version.
- If two related metrics tell a similar story, pick one as the main metric and keep the other as supportive.

### Area interpretation rule
A major theme in the transcript is that:
- `total area` can be misleading when image-to-image organoid count changes a lot
- `average area` may be more reasonable in those settings

Operational guidance:
- Do not treat `total area` as automatically superior.
- When count heterogeneity is strong, prefer `average area` if available.
- If `average area` is not yet implemented, note that `total area` may partly reflect count rather than growth alone.

### Darkness interpretation rule
Another repeated theme is that `Darkness` is relatively stable and interpretable.

Operational guidance:
- `Darkness P90` is a preferred differentiation metric across datasets because it gives a more unified story.
- `Wall Darkness P90` and `Wall Darkness Mean` are acceptable alternatives when wall-specific differentiation is more convincing biologically.
- If two darkness metrics both make sense, one can be main and the other supplementary.

### Fusion metric interpretation rule
The transcript suggests that more complicated fusion-like metrics can still be valid if they are biologically interpretable.

Operational guidance:
- If using `center_weighted_edge_sum`, explain that it weights internal central structural signal more heavily than peripheral boundary signal.
- If that explanation is weak or the metric is hard to communicate, prefer a simpler metric such as `Peripheral / Central` or `Normalized Edge / (Counts * Curvature)`.
- If a fusion metric closely tracks area, say so explicitly and do not oversell it as independent biology.

## Dataset-Specific Guidance

## App81 Density

### Current preferred direction from the latest notes
The handwritten note shifts App81 away from the older preference.

Current preferred hierarchy:
- Growth main: `Area`
- Growth supportive: `Perimeter`
- Differentiation main: `Darkness P90`
- Differentiation supportive: `Roundness Deviation (Pixels)` or normalized roundness-deviation variant
- Fusion main: `Normalized Edge / (Counts * Curvature)`
- Fusion alternative/supportive: `Peripheral / Central`

### Why this changed
Earlier guidance used perimeter and roundness-deviation more heavily.
The later written and spoken feedback suggests:
- `Perimeter` became less convincing for App81 after the updated segmentation
- `Area` looks stronger for the growth story
- `Darkness P90` provides a more unified differentiation readout across all three experiments
- fusion remains the least stable narrative and should stay conservative

### App81 plotting rules
- Treat App81 as the weakest dataset statistically when per-day n is only `1/2/3`.
- Do not force strong statistical claims on low-n time points.
- Remove significance annotations entirely if the data do not support them.
- Remove scale bars from App81 statistical plots.
- Use perimeter only as a supportive growth metric if the area panel is clearly stronger.
- If `Darkness P90` is used as the main differentiation metric, roundness-deviation becomes supplementary, not the main headline.
- If `Peripheral / Central` looks more interpretable than a more abstract fusion metric, it can be used as the alternate fusion panel.

### App81 unresolved item
There is a preference shift in the references:
- older note: `Average Perimeter` and `Roundness Deviation (Norm)`
- later note: `Area` and `Darkness P90`

Current recommendation:
- use the later preference as the main figure direction
- keep the older metrics in supportive or supplementary panels
- make the shift explicit in the figure notes rather than pretending there was never a change

## App65 Alginate

### Current preferred metrics
- Growth main: `Average Perimeter`
- Growth alternative/supportive: `Average Area` if count variation makes summed area unstable
- Differentiation main: `Darkness P90`
- Differentiation alternatives: `Wall Darkness P90`, `Wall Darkness Mean`
- Fusion main: `Peripheral / Central` internal edge
- Fusion supportive: `Normalized Edge / (Counts * Curvature)`

### Focused-day guidance
The references contain two layers of focused-day guidance.

Older/document guidance:
- focused fusion around `D8`
- focused differentiation around `D11`

Latest handwritten guidance:
- focused fusion may need to move to `D6`
- keep `D11` as the key differentiation-focused day

Current recommendation:
- Differentiation focused day: `D11`
- Fusion focused day: prefer `D6` in the latest version, but verify visually against `D8`

### App65 style and statistics rules
- rename groups to `Control`, `Low Alginate`, `High Alginate`
- remove `Relative day`
- use black significance annotations only
- show same-day global significance on the longitudinal figure
- put pairwise comparisons into focused panels
- remove ANOVA text from the panel itself
- remove unnecessary horizontal lines
- unify color scheme and focused-panel plot style

### App65 interpretation note
The transcript suggests that count variation can distort area-based summaries.
Therefore:
- avoid over-relying on summed total area
- add `average area` if needed
- use perimeter as the primary growth metric unless average area clearly tells the cleaner story

## App80 Y-27632

### Current preferred metrics
- Growth main: `Perimeter`
- Growth supportive: `Average Area` if implemented and helpful
- Differentiation main: `Darkness P90`
- Fusion main: `Center-Weighted Edge Sum`
- Fusion alternative/supportive: `Area` if the fusion story is visually stronger there

### App80 interpretation notes
- Zhengyu’s comments suggest the segmentation for App80 is already relatively stable.
- `Darkness` is considered fairly stable.
- `Center-Weighted Edge Sum` is acceptable if its biological explanation is made explicit.
- If outlier removal is required to make a result significant, do not do that silently.

### App80 focused-day guidance
- fusion-focused comparison: around `D6`
- differentiation signal: around `D2`, `D5`, `D7`

### App80 style rules
- rename `NO` to `Control`
- remove `Relative day`
- unify colors and plot type
- use black significance marks only
- remove extra horizontal lines

## Statistics Policy

### What belongs on main time-course figures
- same-day global result only, if n is adequate
- no pairwise clutter
- no raw p-value text
- no first-two-day stars when early biology is unstable or n is weak

### What belongs in focused same-day panels
- pairwise comparisons against the biologically relevant control or reference group
- black brackets and black stars only
- no decorative clutter
- no unnecessary titles or repeated labels

### What belongs in supplementary material
- supportive metrics that are not part of the main story
- alternative metric definitions
- pairwise tables
- same-day global statistics tables
- robustness checks when the preferred metric changed during iteration

### Low-n rule
If the number of images is too small to support inference:
- show the descriptive trajectory only
- remove the stars
- keep the biological wording conservative

## Figure Construction Rules

### Main figure set per dataset
For each dataset, the preferred final set is:
1. one main 3-panel longitudinal figure
2. one focused same-day comparison figure
3. one supplementary figure for supportive metrics
4. one statistics table for same-day global tests
5. one pairwise table for focused comparisons

### Main-panel metric priority by dataset
- App81:
  - Growth: `Area`
  - Differentiation: `Darkness P90`
  - Fusion: `Normalized Edge / (Counts * Curvature)`
- App65:
  - Growth: `Average Perimeter`
  - Differentiation: `Darkness P90`
  - Fusion: `Peripheral / Central`
- App80:
  - Growth: `Perimeter`
  - Differentiation: `Darkness P90`
  - Fusion: `Center-Weighted Edge Sum`

### Supportive metric bank
- `Perimeter`
- `Area`
- `Average Area` when implemented
- `Roundness Deviation (Norm)`
- `Roundness Deviation (Pixels)`
- `Roundness`
- `Wall Darkness P90`
- `Wall Darkness Mean`
- `Normalized Edge / (Counts * Curvature)`
- `Peripheral / Central`
- `Center-Weighted Edge Sum`

## Items That Should Not Appear On Final Main Figures
- colored stars
- raw ANOVA text inside the panel
- excessive pairwise brackets
- `Relative day`
- unnecessary horizontal background lines
- redundant panel titles
- scale bars on statistical summary panels
- over-detailed legends that repeat the caption

## Open Decisions That Should Stay Explicit

### App81 growth
There is a real preference shift from `Perimeter` toward `Area`.
Do not hide that.
Current recommendation is to use `Area` for the main panel and keep `Perimeter` as supportive.

### App81 differentiation
There is a shift from `Roundness Deviation` toward `Darkness P90`.
Current recommendation is to use `Darkness P90` as the main figure metric and keep roundness-deviation as supportive.

### App65 fusion focused day
Older notes emphasized `D8`, but the latest handwritten note points to `D6`.
This should be chosen deliberately after looking at the actual updated plots.

### Area metric type
Whenever area is used, explicitly decide whether the figure should use:
- total area
- average area

If count heterogeneity is strong, average area is preferred.

## Practical Implementation Checklist
- confirm final segmentation version for each source image before recomputing metrics
- keep representative overlays visually convincing and biologically correct
- regenerate the per-image metric table from the final masks
- build daily summaries from the corrected per-image table
- generate the main 3-panel figure first
- generate focused-day plots second
- generate supportive plots third
- export `PNG` and `PDF`
- save the summary tables and pairwise tables next to the figures
- document which metric choices were final and which were supportive

## Recommended Current Default If No Further Human Adjustment Is Made
- App81:
  - Growth: `Area`
  - Differentiation: `Darkness P90`
  - Fusion: `Normalized Edge / (Counts * Curvature)`
- App65:
  - Growth: `Average Perimeter`
  - Differentiation: `Darkness P90`
  - Fusion: `Peripheral / Central`
- App80:
  - Growth: `Perimeter`
  - Differentiation: `Darkness P90`
  - Fusion: `Center-Weighted Edge Sum`

This is the most defensible consolidated interpretation of the written notes, the handwritten update, and the Zhengyu discussion transcript.
