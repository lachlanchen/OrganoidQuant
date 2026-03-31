# App80 Internal Edge Centrality Metric

Date: 2026-03-31

## Purpose

This note records a post-processing fusion proxy computed from the finished App80 all-concentration segmentation results.

No segmentation rerun was performed.

The metric uses:

- saved `mask_16bit` segmentation labels
- saved `signal.png` images
- existing `per_image_metrics.csv`

## Intuition

The saved `signal.png` image is the dark-background hybrid signal image that was previously used as the gallery second-column representation.

The new idea is:

- if strong edge response is concentrated deeper inside the segmented organoid body, that suggests heavier fusion or internal structure
- if strong edge response stays mainly near the segmented periphery, that suggests less fusion and stronger boundary alignment

## Per-Image Computation

For each image:

1. Load the saved segmentation label image.
2. Load the saved `signal.png` grayscale image.
3. Compute a gradient-magnitude edge map from the signal image using Sobel derivatives.
4. Normalize the gradient magnitude by the image `99.5` percentile and clip it into `[0, 1]`.
5. For each segmented instance:
   - compute an instance centrality map using the distance-to-boundary inside the instance
   - normalize centrality to `[0, 1]` per instance
   - use centrality as an inside-weight map
   - use `1 - centrality` as a peripheral-weight map
6. Aggregate across all instances in the image.

This produces:

- `central_inside_edge_mean`
- `peripheral_inside_edge_mean`
- `outer_ring_edge_mean`
- `central_inside_fraction`
- `central_inside_over_peripheral`
- `central_inside_over_outer`

## Main Fusion Proxy

The main fusion proxy used for plotting is:

- `central_inside_over_peripheral = central_inside_edge_mean / peripheral_inside_edge_mean`

Interpretation:

- larger value: stronger edge signal lies more centrally inside segmented organoids
- smaller value: stronger edge signal stays closer to the segmented periphery

## Zero / Undefined Handling

Some images had zero or undefined values in earlier metrics because no usable segmented instances were present.

For this internal-edge-centrality metric:

- if an image has no valid segmented instances, its per-image values are written as `NaN`
- daily means/SEM are computed from valid images only
- the number of valid images is recorded in the daily summary CSV

## Output Files

All files are under:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

Per-image metric table:

- `profiling/quantification/internal_edge_centrality_per_image.csv`

Daily summary:

- `profiling/quantification/internal_edge_centrality_daily_summary.csv`

Figures:

- `figures/app80_all_concentrations_internal_edge_centrality_metrics.png`
- `figures/app80_all_concentrations_internal_edge_centrality_metrics.pdf`
- `figures/app80_all_concentrations_internal_edge_centrality_fusion_proxy.png`
- `figures/app80_all_concentrations_internal_edge_centrality_fusion_proxy.pdf`

## Plot Meaning

The combined metric figure contains:

- central inside edge
- peripheral inside edge
- central inside fraction
- central / peripheral edge ratio

The single-metric fusion figure contains:

- `central_inside_over_peripheral`

This is the most directly interpretable fusion proxy from this new idea.

## Script

The metric is reproducible with:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/plot_internal_edge_centrality_all_concentrations.py`

It reads the existing `per_image_metrics.csv` and saved segmentation outputs only.
