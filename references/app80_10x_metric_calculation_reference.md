# App80 10x Metric Calculation Reference

This note records how the current App80 10x trend figures were calculated from the per-image analysis outputs.

## Source Values Used in the Plots

The published trend plots use three per-image fields from:

- `DEO-DATABASE/app80_10x_single_droplet_results.csv`

The key columns are:

- `fusion_score_combined_0_to_5`
- `droplet_area_px`
- `droplet_circumference_px`

## How Droplet Size and Circumference Are Calculated

Per-image analysis is implemented in:

- `prompt-tools/deo-codex/scripts/07_analyze_single_droplet_10x_pure.py`

Current logic assumes that each 10x image contains one main droplet near the center.

Processing summary:

1. Smooth the grayscale image.
2. Find a central dark blob using a percentile-based threshold.
3. Search candidate circles around that central structure.
4. Score each candidate using boundary gradient strength and visibility.
5. Choose the best-supported circle as the droplet estimate.

The final size metrics are then:

- `droplet_area_px = pi * radius_px^2`
- `droplet_circumference_px = 2 * pi * radius_px`

Important:

- These are droplet-level geometric proxies.
- Units are pixels, not microns.
- They are not direct organoid-only size measurements.

## How Fusion Score Is Calculated

Within the detected droplet region, darker internal structures are segmented using a percentile threshold.

The script then derives several internal morphology features:

- `fill_fraction`: central dark structure area divided by droplet area
- `largest_fraction`: largest dark component area divided by total dark component area
- `dark_fraction`: fraction of dark pixels inside the droplet
- `count_factor`: fewer disconnected components imply stronger fusion

Two heuristic fusion scores are calculated:

- `fusion_visual = 5 * min(1, 0.45 * fill_fraction + 0.35 * largest_fraction + 0.20 * count_factor)`
- `fusion_objective = 5 * min(1, 0.40 * dark_fraction + 0.35 * largest_fraction + 0.25 * count_factor)`

The stored fusion value is:

- `fusion_score_combined_0_to_5 = (fusion_visual + fusion_objective) / 2`

Important:

- This is a heuristic morphology score.
- It is not a manual label.
- It is not produced by a trained fusion classifier.

## How the Trend Plots Use These Values

Trend plotting is implemented in:

- `analysis-tools/app80_10x_concentration_trends/plot_app80_10x_concentration_trends.py`

Processing summary:

1. Read the full App80 10x results CSV.
2. Build a publication subset by selecting the first 3 sorted `10x` TIFF files for each concentration/date folder.
3. Include the control group `No`.
4. Skip the known bad file:
   - `DEO/App80 DEO/No/10-十二月-2025/10x02.tif`
5. Use the replacement sample `10x03.tif` for that date folder.
6. Group by concentration and date.
7. Compute mean and standard deviation across the 3 selected replicates.

Plot semantics:

- line = daily mean
- shaded band = daily standard deviation

## Interpretation Caveat

In the current figure set, "growth" means:

- droplet area trend
- droplet circumference trend

It does **not** currently mean:

- calibrated micron-scale growth
- organoid-only area
- 3D volume

If a stricter biological growth metric is needed later, a separate organoid-focused measurement should be added and plotted independently.
