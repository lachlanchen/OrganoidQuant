# DEO Publication Figure Export Guidance (2026-05-09)

## Source Request

This note records Zhengyu's figure-export requirements after reviewing the 2026-05-09 manuscript figure drafts.

## Main Corrections

- The 12 pt font in the DOCX is a visual reference, not something that can be directly copied blindly into Matplotlib exports.
- The previous large-font option was visually too heavy.
- The preferred practical route is to export clean SVG figures with labels removed, then manually adjust labels in the SVG editor.
- In the no-label SVG export, statistical significance stars and brackets should not be removed.
- Focused single-date comparison figures must be exported in addition to the longitudinal line plots.

## Figure 2

- Draw the AAPS/agentic analysis workflow as an editable SVG.
- The SVG should be treated as a layout draft for manual adjustment.
- The figure should explain the agentic analysis story: dataset and metadata management, vision QC, method routing, segmentation, metric design, database, plots, and conclusions.

## Quantitative Figures

- Figure 3: Density / App81.
- Figure 4: Alginate / App65.
- Figure 6: Y-27632 / App80.
- All quantitative figures should have the same visual size and export to both PDF and SVG.
- Legends should be exported as separate files and not placed inside the main plot.
- App65 labels should use `0.02%` and `0.05%`, not `Low Alginate` or `High Alginate`.

## Tick Label Policy

- All measured time points must remain in the line plots.
- For manual SVG exports, remove tick labels so they can be edited manually later.
- For reference exports with text, reduce printed tick labels to a small set of evenly spaced `Dxx` labels to avoid crowding.
- Reducing printed tick labels does not mean deleting data points.

## Significance Policy

- In no-label SVG exports, keep significance stars and brackets.
- Main longitudinal plots may keep global same-day stars when enabled by the dataset configuration.
- Pairwise significance should be shown in focused same-day panels rather than crowding the longitudinal plots.
- Use black stars and black brackets only.

## Focused Dates To Export

### App65 Alginate

- Growth: `average_perimeter_px` at `D6`.
- Growth: `average_perimeter_px` at `D7`.
- Fusion: `peripheral_over_central` at `D6`.
- Fusion: `peripheral_over_central` at `D8`.
- Differentiation: `wall_darkness_p90` at `D11`.
- Differentiation reference: `wall_darkness_p90` at `D13`.

Rationale: the notes and transcript mention D6/D7 growth, D6/D8 fusion, and D11 differentiation. D13 is retained as an older representative reference date because the discussion mentioned replacing earlier D7/D13 choices with D8/D11.

### App80 Y-27632

- Growth: `average_area_px` at `D5`.
- Differentiation: `organoid_darkness_p90` at `D2`.
- Differentiation: `organoid_darkness_p90` at `D5`.
- Differentiation: `organoid_darkness_p90` at `D7`.
- Fusion: `center_weighted_edge_sum` at `D4`.
- Fusion: `center_weighted_edge_sum` at `D5`.
- Fusion: `center_weighted_edge_sum` at `D6`.

Rationale: the handwritten reference highlights D5 area, D2/D5/D7 darkness, and D4/D5/D6 fusion. The manuscript discussion also emphasizes Day 6 Y-27632 fusion.

### App81 Density

- No focused statistical date is currently exported for App81 because the density dataset is small and previous guidance treated its statistical claims conservatively.

## Supplementary Image Panel Dataset

Ma's comment that the attachment should contain all image panels as a dataset means the supplementary material should include a traceable collection of image panels, not only final plots.

Two acceptable implementations:

- A complete panel dataset: downsampled review panels plus a manifest mapping every panel to condition, date, replicate, original image path, mask path, and overlay path.
- A representative segmentation set: selected representative original/overlay/mask panels for each condition, with the same manifest structure.

The complete panel dataset is more auditable. The representative set is more compact and more manuscript-friendly.

## Current Export Script

- Script: `analysis-tools/deo_plotting/generate_publication_0509_figure_options.py`
- Main corrected option: `option_1_manual_svg_no_labels_keep_stars`
- Reference text option: `option_2_arial12_reduced_date_labels`

