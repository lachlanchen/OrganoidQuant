# Zhengyu Plot Feedback 2026-04-14

Source: [DEO+0414.docx](/home/lachlan/ProjectsLFS/Zhengyu/references-plots/DEO+0414.docx)

## Overall
- 对所有的数据 statistics 部分，Primary 也需要和 focused 一样有 `pairwise vs control` 或者 `pairwise group` 的两两比较。

## Clear Problems Confirmed From Embedded Images

### 1. X-axis layout is too crowded
- Embedded images show day labels packed too tightly, for example `D0 D1 D2 D3 ...` with visible overlap.
- The extra x-axis label `Day` makes the crowding worse.
- Practical instruction:
  - keep the tick labels
  - remove the axis title `Day`
  - keep equal spacing but avoid extra text below the ticks

### 2. Color language must be unified across datasets
- Embedded legend images show the desired visual language explicitly.
- App81 should visually follow the same red/blue/black scheme used in App65 Alginate.
- Practical instruction:
  - `Control` or baseline group: black
  - lower/intermediate comparison group: blue
  - higher comparison group: red
- The note is not asking for three unrelated palettes per dataset. It is asking for cross-figure consistency.

### 3. Statistical outputs are expected as files, not only figure annotations
- One embedded image is a file list showing expected outputs such as:
  - `focused_pairwise_vs_control.csv`
  - `focused_pairwise_vs_control_polished.csv`
  - `full_metric_summary.csv`
  - `primary_metric_summary.csv`
  - `primary_same_day_global_tests.csv`
  - `supportive_metric_summary.csv`
  - `supportive_same_day_global_tests.csv`
- Practical instruction:
  - figures alone are not sufficient
  - the statistics tables should be generated and kept alongside the figure outputs

### 4. Focused panels should support explicit pairwise interpretation
- The boxplot example confirms the intended focused-panel style:
  - grouped distributions
  - black significance brackets
  - black significance stars
- This supports the text note that `Primary` should also have pairwise statistics available, not only focused panels.
- Practical instruction:
  - keep pairwise results in tables
  - use black-only bracket styling if shown on focused figures
  - avoid excessive visual clutter on the main longitudinal plots

### 5. App80 has a specific outlier concern
- The note `50uM的最低值去掉试一试` is visually tied to the App80 focused comparison example.
- This is not a generic instruction to remove outliers silently.
- It is a request to test whether the lowest `50 uM` point is driving the result.
- Practical instruction:
  - keep the default figure with the full data unless explicitly changed
  - if an outlier-removed variant is explored, label it clearly as a sensitivity check

## App81
- 可去掉 Bar。
- 颜色和 65 Alginate 保持一致，都用红蓝黑。
- 横坐标不用写 `Day`，标注有重合。
- Growth 用 `Total Area`。
- Differentiation 用 `Darkness P90`。
- Fusion 用 `Peripheral/Central`。
- 图例标在每个图右上角，颜色改成红蓝黑，并和 Alginate 保持一致。

### App81 problem stated clearly
- The current App81 issue is not only metric selection.
- The presentation also needs to stop mixing a separate density palette with the Alginate palette.
- Zhengyu wants App81 to read visually like the App65 figures, with the same red/blue/black logic and a cleaner x-axis.

## App65
- 横坐标不用写 `Day`，标注有重合。
- Growth 用 `Perimeter`。
- Differentiation 用 `wall Darkness P90`。
- Fusion 用 `Peripheral/Central`。
- 图例标在每个图右上角，App81 Density 组和这个保持一致。

### App65 problem stated clearly
- App65 is acting as the visual reference standard.
- Its metric choices are more settled, and the main request is to keep App65 and App81 visually aligned.
- The key plotting problem here is label crowding and keeping the legend placement and color semantics consistent.

## App80
- 横坐标不用写 `Day`。
- Growth 用 `Average area`。
- Differentiation 用 `Darkness P90`。
- Fusion 用 `Center-weighted edge sum`。
- `50uM` 的最低值去掉试一试。

### App80 problem stated clearly
- The requested App80 change is partly metric selection and partly robustness checking.
- The image indicates concern that a single low `50 uM` point may be weakening the focused comparison.
- This should be treated as a sensitivity-analysis request, not as an unrecorded data deletion.

## Operational Interpretation
- Main figures should stay visually simple.
- Pairwise information should exist in the exported statistics tables, and can appear on focused figures when needed.
- Remove the x-axis title `Day` where it causes crowding.
- Keep colors consistent across experiments.
- Use the experiment-specific primary metrics listed above.
- Treat the `50 uM` low point note as a testable variant, not a default silent exclusion.
