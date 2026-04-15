# Zhengyu Plot Feedback 2026-04-15

Source:
- [DEO+0415.docx](/home/lachlan/ProjectsLFS/Zhengyu/references-plots/DEO+0415.docx)

This note is a cleaned Markdown conversion of the DOCX plus an explicit mapping of the embedded screenshots to the datasets they refer to.

## Embedded Image Mapping

The DOCX contains three embedded screenshots. They correspond to:

1. App81:
   - [app81_peripheral_over_central_feedback_2026-04-15.png](/home/lachlan/ProjectsLFS/Zhengyu/references-plots/derivatives/packages/DEO+0415_extracted_media/app81_peripheral_over_central_feedback_2026-04-15.png)
   - this screenshot shows the `Peripheral / Central` timecourse figure
   - the visible issue is that the vertical error bars still appear
   - the color request in the note is: `low = black`, `middle = blue`, `high = red`

2. App65:
   - [app65_primary_metrics_feedback_2026-04-15.png](/home/lachlan/ProjectsLFS/Zhengyu/references-plots/derivatives/packages/DEO+0415_extracted_media/app65_primary_metrics_feedback_2026-04-15.png)
   - this screenshot shows the three-panel primary metrics figure
   - the visible issue is that the upper-right legend / annotation placement can overlap or crowd the plot area
   - the note also asks for focused `D6` and `D11` outputs as standalone PDF or image files

3. App80:
   - [app80_center_weighted_edge_sum_feedback_2026-04-15.png](/home/lachlan/ProjectsLFS/Zhengyu/references-plots/derivatives/packages/DEO+0415_extracted_media/app80_center_weighted_edge_sum_feedback_2026-04-15.png)
   - this screenshot shows the `Center-weighted edge sum` timecourse figure
   - the note again asks for the upper-right legend / annotation to be positioned so it does not overlap the figure
   - the note also asks for focused `D6` output as a standalone PDF or image file

## Cleaned Text Conversion

### General

Each figure should also be exported separately as a PDF or image, with the figure note / annotation placed in an appropriate location.

### 1. App81

- The bar is still not removed.
  - Based on the screenshot, this most likely refers to the visible vertical error bars still being present.
- Use these colors:
  - `low density = black`
  - `middle density = blue`
  - `high density = red`
- Move the upper-right figure note / legend to a suitable position so it does not overlap the plot.

### 2. App65

- Move the upper-right figure note / legend to a suitable position so it does not overlap the plot.
- Output `Focused D6` and `Focused D11` as standalone PDF or image files.

### 3. App80

- Move the upper-right figure note / legend to a suitable position so it does not overlap the plot.
- Output `Focused D6` as a standalone PDF or image file.

## Practical Interpretation

The main actionable points from this DOCX are:

- export individual figures separately, not only combined panels
- for App81, remove the remaining bars if they are not desired in the final style
- use the requested App81 color mapping exactly
- shift legends / figure notes away from the upper-right plot content when they crowd the figure
- export the requested focused comparison figures as their own PDF and image outputs
