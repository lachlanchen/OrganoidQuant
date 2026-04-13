# DEO Quantification Selection Comments (2026-04-13)

Source:
- DOCX: `DEO定量选择260413.docx`
- Handwritten note image: `deo_quantification_selection_handwritten_note_2026-04-13.jpeg`

This Markdown note is a cleaned text conversion of the DOCX comments. Embedded figure snapshots from the Word file are omitted; only the written guidance is retained.

## App81 Density

### Growth
- Preferred metric noted in the file: `Average Perimeter`.
- Statistical note: current `n=1/2/3` is likely too small for strong statistical analysis.
- Consider removing scale bars from the statistical figure.
- Figure label in the file: `Growth: Perimeter (px)`.

### Differentiation
- Current metric shown in the file: `Roundness Deviation (Norm)`.
- Note in the file: ANOVA appears `ns`.
- Suggested replacement: `Darkness P90`, so all three experiments use a more unified differentiation metric.
- Suggested cleanup:
  - remove scale bar
  - remove statistical analysis from that panel if the signal is weak

### Fusion
- Metric shown in the file: `Normalized Edge / (Counts * Curvature)`.
- Suggested cleanup: remove scale bar.

### Additional update dated 2026-04-10
- Growth:
  - `Perimeter` looks less convincing than before.
  - `Area` may look better.
- Differentiation:
  - reconsider the chosen metric.
- Fusion:
  - reconsider the chosen metric as needed.

## App65 Alginate

### Growth
- Preferred metric: `Average Perimeter`.
- Explicit note: choose `Perimeter`.
- Statistical notes written in the file:
  - `Day 6 **`, with `No / 0.02 alginate *`
  - `Day 7 **`, with `No / 0.05 alginate **`
  - `Day 11 *`, with `No / 0.05 alginate *`
- Plot-style guidance:
  - keep x-axis time spacing consistent
  - remove `Relative day`
  - use black significance marks only
  - show only ANOVA/global result on the main figure
  - leave pairwise comparisons to the main text
  - remove redundant titles

### Differentiation
- Preferred metric in the file: `Organoid Darkness P90`.
- Statistical note: meaningful difference around `Day 11`; early days are weak.
- Plot-style guidance:
  - keep x-axis spacing consistent
  - remove `Relative day`
  - use black stars only
  - only show global significance on main figure
  - pairwise comparison details go in the text
  - remove redundant titles

### Fusion
- Metrics discussed:
  - `Peripheral / Central`
  - `Normalized Edge / (Counts * Curvature)`
- Statistical note written in the file:
  - `Day 8 **`, with both alginate groups differing from control
- Requested focused plots:
  - add focused `Day 8`
  - add focused `Day 11`
- Figure cleanup/style guidance:
  - remove ANOVA text and results from the panel
  - rename conditions:
    - `No` -> `Control`
    - `0.02 alginate` -> `Low Alginate`
    - `0.05 alginate` -> `High Alginate`
  - remove horizontal reference lines
  - unify color palette
  - unify plot style, e.g. box plots
  - show pairwise differences with black lines and black stars only
- Additional note in the file:
  - `Day 7 Fusion` appears higher in control
  - one focused panel should be changed to `D11`

### Additional update dated 2026-04-10
- Growth: revisit choice if needed.
- Differentiation:
  - previously chosen `Darkness P90` at `Day 11` was marked as significant
  - alternatives suggested:
    - `Wall Darkness P90`
    - `Wall Darkness mean`
- Fusion:
  - previous fusion metric was still considered acceptable
  - `Normalized Edge / (Counts * Curvature)` is repeated in the note
- Focused panel note:
  - fusion focused panel may need to move to `D6`

## App80 Y-27632

### Growth
- Metric shown in the file: `Perimeter`.
- Statistical note: perimeter appears mostly `ns`.
- Plot-style guidance:
  - keep x-axis spacing consistent
  - remove `Relative day`
  - use black significance marks only
  - show only global significance on main figure
  - pairwise details go in text
  - remove redundant titles

### Differentiation
- Preferred metric: `Organoid Darkness P90`.
- Statistical note in the file: differences around `Day 2 / 5 / 7`.
- Plot-style guidance:
  - consistent x-axis spacing
  - remove `Relative day`
  - black stars only
  - keep pairwise details out of the main panel
  - remove redundant titles

### Fusion
- Metric shown in the file: `Center-Weighted Edge Sum`.
- Statistical note in the file: fusion signal around `Day 4 / 5 / 6`.
- Focused panel note:
  - `Day 6`
  - try dropping the minimum in `50 uM` and recheck whether significance appears
  - if significance still does not appear, it may not be worth forcing
- Plot-style guidance:
  - `NO` should be renamed to `Control`
  - remove horizontal reference lines
  - unify colors
  - unify plot style, e.g. box plots
  - use black lines and black stars only

## Cross-dataset style guidance
- Use consistent x-axis spacing across time-series plots.
- Remove `Relative day` from axes.
- Use black significance annotations only.
- Do not crowd main plots with pairwise results.
- Keep condition naming consistent and manuscript-friendly.
- Unify the palette and plot type across datasets.
- Remove extra horizontal lines and redundant titles.
- One palette suggestion written in the file: use a unified red/blue/black or red/green/blue scheme.
