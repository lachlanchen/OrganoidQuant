# Expected Figure Style

Primary style reference:
- `data-docs/thesis+figure-style/figure-style/wechat-reference-image.jpeg`

Supporting figure logic reference:
- `data-docs/DEO Figure/*.pdf`
- `data-docs/DEO Figure/*.svg`

## Visual characteristics of the style reference
From the provided reference image, the expected style appears to be:
- clean white background
- large bold panel labels such as `E`, `F`, `G`
- microscopy images placed as representative example panels
- quantitative plots placed beside microscopy
- strong axis labels with large font size
- significance brackets and p-value stars above comparisons
- limited, consistent color palette for grouped conditions
- simple legends without decorative clutter
- scale bars preserved on microscopy examples

## Practical style rules for DEO figures
### Microscopy panels
- use aligned grids with consistent spacing
- keep condition order stable across figures
- keep day order stable and left-to-right
- use the same cropping logic within one panel
- do not mix magnification labels ambiguously
- preserve scale bars where possible

### Quantification panels
- prefer line plots for time series
- prefer grouped bar plots, violin plots, or box plots for dedicated-day comparisons
- show mean with error bars or confidence intervals
- annotate significance clearly but sparingly
- avoid too many colors; use one consistent color per condition group

### Labeling conventions
- large panel letters: `A`, `B`, `C`, etc.
- explicit condition labels under columns or above rows
- explicit day labels on the x-axis or grid headers
- use publication-style scientific labels, for example:
  - `Y-27632 concentration (μM)`
  - `Organoid size`
  - `Fusion score`
  - `Differentiation score`

## Recommended style mapping for this project
- Density figure: three-condition time series plus one supporting panel
- Alginate figure: three-condition time series plus day 7 / day 13 detailed comparison
- Y-27632 figure: five-condition time series plus day 6 detailed comparison

## Implication for output generation
The figure-making pipeline should save both:
- raw quantitative tables for replotting
- publication-ready figure exports in `PNG`, `PDF`, and optionally `SVG`

The figure code should separate:
- data aggregation
- statistical testing
- plotting theme
so the layout can be refined without recalculating measurements.
