# App80 All-Concentration Multiscale Segmentation Next Step

## Purpose

This note records the currently accepted segmentation workflow for the `App80 DEO` `10x` images and defines the next batch-analysis step:

- run the same segmentation method on all concentrations, including control
- keep all intermediate per-image outputs in a `runs/` tree
- preserve readable instance segmentation outputs, not just 16-bit label masks
- aggregate metrics by day within each concentration
- plot all concentrations together on shared figures with clean legend/title layout

This is the reference specification for the next batch run.

## Current Accepted Method

The currently accepted method is the multiscale, date-aware Cellpose workflow with large-mass recovery.

Core scripts:

- [run_multiscale_dateaware_cellpose.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/run_multiscale_dateaware_cellpose.py)
- [run_app80_10uM_all_replicates_large_recovery.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/run_app80_10uM_all_replicates_large_recovery.py)
- [backfill_instance_rgb_overlays.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/backfill_instance_rgb_overlays.py)

Accepted characteristics:

- `10x` images only
- multiscale Cellpose with three diameters per image
- date-aware stage handling
- recovery of large irregular fused masses from the hybrid signal
- saved readable outputs for inspection

The user judged this version as good enough to use as the basis for broader analysis.

## Current Verified Output Structure

The current all-replicate `10uM` output root is:

- [app80_10uM_all_replicates_multiscale_large_recovery](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery)

Per-image outputs are stored under:

- [runs](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/runs)

Each image run should keep these files:

- `*_mask_16bit.png`
- `*_instance_rgb.png`
- `*_overlay.png`
- `*_signal.png`
- `*_segmentation_stats.json`
- `*_metrics.json`

This structure should be preserved for the next all-concentration run.

## Why This Intermediate Output Must Be Kept

The readable inspection files are necessary because:

- `*_mask_16bit.png` is not convenient for manual review
- `*_instance_rgb.png` shows instance separation directly
- `*_overlay.png` shows whether the segmentation aligns with the raw image
- `*_signal.png` preserves the second-column hybrid signal used in downstream metrics
- JSON files preserve enough detail to debug branch behavior without rerunning

For future batch runs, the `runs/` directory should remain part of the final output, not a temporary scratch artifact.

## Next Full Batch Scope

The next batch should cover all `App80 DEO` concentrations:

- `No`
- `10uM`
- `20uM`
- `50uM`
- `100uM`

Only `10x` TIFFs should be used.

Input root:

- `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO`

The run should discover all date folders under each concentration and all `10x` images within those date folders.

## Expected Output Layout For The Next Batch

Recommended output root naming pattern:

- `analysis-output/app80_all_concentration_multiscale_large_recovery`

Recommended structure:

- `runs/<concentration>/<date>/...`
- `databases/per_image_metrics.csv`
- `databases/daily_summary.csv`
- `figures/...`
- `run_manifest.json`

Per-image files should still include:

- `mask_16bit`
- `instance_rgb`
- `overlay`
- `signal`
- segmentation stats JSON
- metrics JSON

## Metrics To Aggregate

The existing metric family should be preserved unless explicitly replaced:

- count
- curvature
- edge intensity on the hybrid signal
- total area
- average perimeter
- normalized edge intensity over `(count * curvature)`

Aggregation rules:

- compute metrics per image
- aggregate by `concentration x day`
- record mean, standard deviation, standard error, and replicate count

## Plotting Requirement For The Next Batch

The next plot should compare concentrations directly on shared axes.

Required plotting behavior:

- one line per concentration
- common x-axis by day
- clean layout with no title/legend overlap
- legends placed outside the axes when needed
- sufficient top margin and right margin
- publication-clean formatting

Recommended figure outputs:

- one combined multi-panel figure for all metrics
- one dedicated figure for the normalized `edge / (count * curvature)` metric

Recommended layout rules:

- use `constrained_layout=True` or explicit `subplots_adjust`
- move legend to upper right outside plotting area if crowded
- keep titles short
- use consistent concentration colors across all panels
- avoid duplicating the same legend in every subplot if a single shared legend is enough

## Generalization Note

This workflow is reusable as a framework, but not fully plug-and-play universal.

What should remain stable:

- multiscale strategy
- date/stage-aware parameterization
- large-mass recovery branch
- saved inspection outputs
- per-image plus per-day metric aggregation

What may need retuning on different datasets:

- diameter triplets
- large-mass recovery thresholds
- stage assignments
- candidate merge logic

For `App80 DEO`, however, the current method is the accepted baseline for scaling from `10uM` to all concentrations.

## Immediate Next Action

When the next batch is run, it should:

1. use the same accepted segmentation method
2. run over all concentrations including control
3. keep the full `runs/` intermediates with `instance_rgb` and `overlay`
4. aggregate all requested metrics by day within each concentration
5. produce concentration-comparison figures with clean layout and non-overlapping legend/title placement

## Reference Outputs From The Current 10uM Batch

Current data:

- [daily_summary.csv](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/databases/daily_summary.csv)
- [per_image_metrics.csv](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/databases/per_image_metrics.csv)

Current figures:

- [app80_10uM_all_replicates_segmentation_metrics.png](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/figures/app80_10uM_all_replicates_segmentation_metrics.png)
- [app80_10uM_all_replicates_normalized_edge_over_count_curvature.png](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_all_replicates_multiscale_large_recovery/figures/app80_10uM_all_replicates_normalized_edge_over_count_curvature.png)
