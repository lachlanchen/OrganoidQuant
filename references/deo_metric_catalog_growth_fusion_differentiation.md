# DEO Metric Catalog: Growth, Fusion, and Differentiation

Date: 2026-04-04
Repo: `/home/lachlan/ProjectsLFS/Zhengyu`

## Scope

This note consolidates the metrics used across the DEO analysis workflows, especially the completed outputs for:

- App65 alginate experiment:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`
- App80 Y-27632 experiment:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum`

The goal is to document all metrics used so far, grouped by intended biological interpretation:

- growth
- fusion
- differentiation

Some metrics are exploratory and can belong to more than one category. The grouping below reflects the intended reading used in this project.

## Shared Segmentation Backbone

Most downstream metrics depend on the saved per-image segmentation outputs.

Per-image saved intermediates:

- `*_mask_16bit.png`
- `*_instance_rgb.png`
- `*_overlay.png`
- `*_signal.png`
- `*_metrics.json`
- `*_segmentation_stats.json`

Main completed output roots:

- App65: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`
- App80: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

## The Hybrid Signal / "Second Column"

A number of metrics use the saved `signal.png` image, which is the black-background hybrid signal used earlier as the gallery "second column".

Its construction is:

1. grayscale brightfield image
2. CLAHE contrast enhancement
3. small Gaussian blur for foreground support
4. large Gaussian blur for background estimate
5. residual and inverted grayscale are normalized
6. final signal:
   - `signal = 0.45 * inv_norm + 0.55 * residual_norm`

For App80 signal-intensity work this was fixed explicitly as:

- CLAHE clip limit `2.4`
- foreground blur kernel `3`
- background blur kernel `31`

Interpretation:

- bright in `signal.png` = stronger organoid-support / local contrast signal
- dark background = suppressed non-informative field

## Main Database Fields

### App65 main per-image database

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`

This now contains:

- base segmentation metrics
- roundness metrics
- normalized edge-over-count-curvature metric
- differentiation darkness metrics

### App80 main per-image database

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/per_image_metrics.csv`

This contains:

- base segmentation metrics
- roundness metrics
- normalized edge-over-count-curvature metric

Additional App80 fusion-oriented metrics are stored in sidecar CSVs, described below.

## Growth Metrics

These metrics are mainly intended to track how much organoid material is present over time.

### 1. `total_area_px`

Definition:

- total segmented foreground area in pixels across all instances in one image

Interpretation:

- larger value suggests more total organoid mass / growth

Current role:

- primary segmentation-based growth metric

Available in:

- App65 main database
- App80 main database

Figures:

- App65: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_segmentation_metrics.png`
- App80: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_segmentation_metrics.png`

### 2. `count`

Definition:

- number of segmented organoid instances in one image

Interpretation:

- can reflect growth, fragmentation, fusion state, or splitting depending on morphology
- not a pure growth metric on its own

Current role:

- used as a growth-associated context metric
- also used in fusion composite metrics

Available in:

- App65 main database
- App80 main database

### 3. `signal sum intensity`

Definition:

- sum of all pixel intensities in the hybrid `signal` image

Formula:

- `sum_intensity = sum(signal[pixels])`

Interpretation:

- a morphology-sensitive brightfield proxy
- used as an exploratory growth/fusion signal before segmentation-based metrics were finalized

Available in:

- App80 signal-intensity output set only

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum/app80_all_concentration_signal_sum_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum/app80_all_concentration_signal_sum_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum/app80_all_concentration_signal_sum_and_reciprocal.png`

### 4. `reciprocal_sum_intensity`

Definition:

- reciprocal of the hybrid signal sum

Formula:

- `1 / sum_intensity`

Interpretation:

- exploratory inverse proxy
- useful when lower signal sum visually matched stronger fusion-like states

Available in:

- App80 signal-intensity output set only

### 5. `sum_intensity_relative_change`

Definition:

- relative change of signal sum versus previous date

Formula:

- `(current_sum - previous_sum) / previous_sum`

Interpretation:

- dynamic trend metric rather than absolute magnitude

Available in:

- App80 signal-intensity output set only

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum/app80_all_concentration_signal_sum_relative_change.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum/app80_all_concentration_signal_sum_relative_change.png`

## Fusion Metrics

These metrics are intended to capture whether edge structure remains on the periphery versus being absorbed into the interior of fused organoid masses.

### 1. `edge_intensity`

Definition:

- mean edge magnitude derived from the hybrid `signal.png`

Interpretation:

- basic edge-structure strength
- useful but not sufficient alone for fusion

Available in:

- App65 main database
- App80 main database

### 2. `curvature`

Definition:

- area-weighted circularity proxy derived from segmented instances

Formula:

- per instance: `4πA / P²`
- per image: area-weighted mean across instances

Interpretation:

- higher values mean more circular / cystic morphology
- lower values mean more irregular / fused / non-circular morphology

Available in:

- App65 main database
- App80 main database

### 3. `normalized_edge_over_count_curvature`

Definition:

- normalized composite of edge, count, and curvature

Formula:

- `edge_norm / (count_norm * curvature_norm)`

Where:

- `count_norm`, `curvature_norm`, `edge_norm` are min-max normalized per-image metrics within the analysis set

Interpretation:

- heuristic fusion proxy combining edge strength, object number, and cystic roundness

Available in:

- App65 main database
- App80 main database

Figures:

- App65: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_normalized_edge_over_count_curvature.png`
- App80: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_normalized_edge_over_count_curvature.png`

### 4. `inverse_edge_count_curvature`

Definition:

- inverse composite

Formula:

- `1 / (edge_intensity * count * curvature)`

Interpretation:

- exploratory inverse fusion proxy
- kept as a side metric, not part of the main App80 database

Available in:

- App80 sidecar summary only

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/inverse_edge_count_curvature_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_inverse_edge_count_curvature.png`

### 5. Internal edge centrality metrics

These use the edge map derived from `signal.png` together with each segmented instance.

Core idea:

- if edge structure lies deeper inside the segmented object, that suggests stronger fusion / internalized boundaries
- if edge structure stays near the object periphery, that suggests less fusion

Per-instance centrality:

- distance transform inside each object
- centrality = `distance_to_boundary / max_distance`

Available App80 sidecar metrics:

- `central_inside_edge_mean`
- `peripheral_inside_edge_mean`
- `outer_ring_edge_mean`
- `central_inside_fraction`
- `central_inside_over_peripheral`
- `central_inside_over_outer`
- `peripheral_over_central`

Definitions:

- `central_inside_edge_mean`: edge intensity weighted by centrality
- `peripheral_inside_edge_mean`: edge intensity weighted by `(1 - centrality)`
- `outer_ring_edge_mean`: mean edge intensity just outside the union mask
- `central_inside_fraction`: `central_mean / (central_mean + peripheral_mean)`
- `central_inside_over_peripheral`: `central_mean / peripheral_mean`
- `central_inside_over_outer`: `central_mean / outer_ring_edge_mean`
- `peripheral_over_central`: `peripheral_mean / central_mean`

Interpretation:

- larger central-weighted terms imply more interiorized edge structure
- larger peripheral-over-central implies edge structure remains nearer the boundary

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/internal_edge_centrality_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/internal_edge_centrality_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/peripheral_over_central_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_internal_edge_centrality_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_internal_edge_centrality_fusion_proxy.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_peripheral_over_central_internal_edge.png`

### 6. `center_weighted_internal_edge_sum`

Definition:

- sum of edge intensity inside segmented objects with an exponential center-weight

Weight definition:

- centrality from distance transform
- `weight = expm1(alpha * centrality) / expm1(alpha)`
- default `alpha = 5`
- center approaches `1`
- boundary approaches `0`

Formula:

- per image: `sum(edge_intensity * center_weight)` over all object pixels

Interpretation:

- emphasizes internal edge signal near object centers
- intended as a fusion-sensitive score

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/center_weighted_internal_edge_sum_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/center_weighted_internal_edge_sum_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_center_weighted_internal_edge_sum.png`

### 7. `area_normalized_center_weighted_edge_instance_mean`

Definition:

- for each instance, compute:
  - `center_weighted_edge_sum / instance_area`
- then average across instances in the image

Interpretation:

- removes the bias toward larger instances in the raw center-weighted sum

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/area_normalized_center_weighted_internal_edge_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/profiling/quantification/area_normalized_center_weighted_internal_edge_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_area_normalized_center_weighted_internal_edge.png`

### 8. Earlier App80 edge-density / gradient proxies

Before the segmentation-based pipeline stabilized, an earlier exploratory App80 edge-proxy analysis used:

- `edge_density`
- `1 / edge_density`
- `gradient_mean`
- `1 / gradient_mean`

Interpretation:

- exploratory morphology proxies only
- kept historically, but the segmentation-based metrics above are the stronger current framework

Representative outputs:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_edge_proxy_all_10x/app80_all_concentration_edge_proxy_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_edge_proxy_all_10x/app80_all_concentration_edge_proxy_combined_by_day.png`

## Differentiation Metrics

These are intended to capture darker, thickened, and more budded / irregular organoids.

## A. Shape-related differentiation metrics

These can reflect differentiation-related morphology even though they are not direct darkness measurements.

### 1. `roundness`

Definition:

- circle-deviation roundness based on a same-area reference circle centered at the object centroid

Procedure:

1. compute object centroid
2. compute same-area circle radius: `sqrt(area / pi)`
3. build reference circle at the centroid
4. compute symmetric-difference area between object and circle
5. convert deviation to a bounded roundness score

Formula:

- `roundness = 1 - deviation / union_area`

Interpretation:

- larger value = more circle-like / cystic
- smaller value = more irregular / budded / non-circular

Available in:

- App65 main database
- App80 main database

Figures:

- App65: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_roundness.png`
- App80: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/figures/app80_all_concentrations_roundness.png`

### 2. `roundness_deviation_norm`

Definition:

- normalized area deviation from the same-area reference circle

Interpretation:

- larger value = stronger deviation from circularity
- raw complement of `roundness`

Available in:

- App65 main database
- App80 main database

### 3. `roundness_deviation_px_total`

Definition:

- total pixel-level area deviation from reference circles across all instances

Interpretation:

- absolute irregularity burden in an image

Available in:

- App65 main database
- App80 main database

### 4. `average_perimeter_px`

Definition:

- mean perimeter per segmented instance

Interpretation:

- larger values can reflect larger or more morphologically complex objects
- useful as a supportive morphology metric, not a standalone differentiation score

Available in:

- App65 main database
- App80 main database

## B. Darkness-based differentiation metrics

These were added explicitly for App65 to quantify the observation that more differentiated organoids look darker and have thicker, darker epithelial walls.

There are two App65 darkness figures:

- six-metric overview:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_metrics.pdf`
- three-metric focus panel:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_focus.pdf`

The focus plot is a subset of the overview plot. The union of the two is therefore these six unique metrics:

1. `organoid_darkness_mean`
2. `organoid_darkness_p90`
3. `very_dark_area_ratio_gt035`
4. `wall_darkness_mean`
5. `wall_darkness_p90`
6. `wall_core_darkness_ratio`

For completeness, the dedicated App65 per-image and daily darkness tables also include:

- `organoid_darkness_p95`
- `core_darkness_mean`
- `background_gray_median`
- `organoid_pixel_count`
- `wall_pixel_count`
- `core_pixel_count`

### Darkness normalization

For each image:

- background is estimated outside a dilated organoid mask
- background statistic = median grayscale value of that region
- normalized darkness:
  - `max(0, background_median - gray) / background_median`

This controls for image-to-image illumination differences.

### 1. `organoid_darkness_mean`

Definition:

- mean normalized darkness over all segmented organoid pixels

Interpretation:

- global darkness level of organoid material

### 2. `organoid_darkness_p90`

Definition:

- 90th percentile of normalized darkness inside organoid pixels

Interpretation:

- upper-tail darkness; useful when only part of the organoid is strongly darkened

### 3. `organoid_darkness_p95`

Definition:

- 95th percentile of normalized darkness inside organoid pixels

Interpretation:

- even more peak-oriented darkness metric

### 4. `very_dark_area_ratio_gt035`

Definition:

- fraction of organoid pixels with normalized darkness greater than `0.35`

Interpretation:

- how much of the organoid area is strongly dark

### 5. `wall_darkness_mean`

Definition:

- mean normalized darkness in an adaptive inner wall band

Wall definition per instance:

- compute equivalent radius from area
- erosion width = `round(equivalent_radius * 0.12)`
- clamp width to `5..30` px
- wall = object minus eroded object

Interpretation:

- intended to capture thickened, darkened epithelial walls

### 6. `wall_darkness_p90`

Definition:

- 90th percentile darkness within the wall band

Interpretation:

- peak dark-wall signal

### 7. `core_darkness_mean`

Definition:

- mean normalized darkness in the eroded core

Interpretation:

- comparison baseline for whether darkness is wall-concentrated or globally distributed

### 8. `wall_core_darkness_ratio`

Definition:

- `wall_darkness_mean / core_darkness_mean`

Interpretation:

- values greater than `1` indicate darker walls than cores
- especially relevant for thickened epithelial-wall phenotypes

Available in:

- App65 main database
- App65 dedicated darkness sidecar tables

Files:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/differentiation_darkness_per_image.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/profiling/quantification/differentiation_darkness_daily_summary.csv`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_metrics.png`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/figures/app65_all_conditions_differentiation_darkness_focus.png`

## Recommended Practical Reading

### Growth

Strongest current growth-oriented metrics:

- `total_area_px`
- `count`
- App80-only exploratory support: `sum_intensity`

### Fusion

Strongest current fusion-oriented metrics:

- `normalized_edge_over_count_curvature`
- `central_inside_over_peripheral`
- `peripheral_over_central`
- `center_weighted_internal_edge_sum`
- `area_normalized_center_weighted_edge_instance_mean`

### Differentiation

Strongest current differentiation-oriented metrics:

- `roundness`
- `roundness_deviation_norm`
- `organoid_darkness_p90`
- `very_dark_area_ratio_gt035`
- `wall_darkness_mean`
- `wall_core_darkness_ratio`

## Important Caveat

No single metric here should be treated as the whole biology.

- growth metrics can be affected by segmentation count and fusion state
- fusion metrics can also move with differentiation-related wall thickening
- differentiation metrics can move with illumination and segmentation quality if used alone

The intended use is:

- interpret metrics as a panel
- prefer consistent trends across multiple related metrics
- always cross-check against overlays / instance RGB outputs when a result looks surprising
