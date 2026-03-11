# Cellpose Organoid Segmentation Test

This test runs direct Cellpose segmentation on the full microscopy image and saves the raw labels, filtered labels, RGB instance mask, overlay, Cellpose internal flow/cell-probability artifacts, and per-mask statistics.

## Files

- `run_cellpose_organoid_segmentation_test.py`: main segmentation script
- `run_cellpose_organoid_segmentation_test.sh`: launcher with compatibility shim

## Why the launcher exists

The available `cellpose 3.0.8` installation is in user-site packages and expects `numpy < 2`.
The repository default Python environment currently uses `numpy 2.2.6`.

The launcher solves that by:

1. installing a local `numpy 1.26.4` shim into `vendor_legacy/` if needed
2. prepending that shim and the user-site Cellpose path via `PYTHONPATH`
3. running with `PYTHONNOUSERSITE=1` so the import order is controlled

## Example

```bash
api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.sh
```

## Latest Successful Run

- `output/05-十二月-2025_10x00_20260311_214045/`

Key outputs:

- `cellpose_labels_raw_16bit.png`
- `cellpose_labels_filtered_16bit.png`
- `cellpose_instance_rgb.png`
- `cellpose_overlay.png`
- `cellpose_flow_rgb.png`
- `cellpose_flow_x.png`
- `cellpose_flow_y.png`
- `cellpose_flow_magnitude.png`
- `cellpose_cellprob_heatmap.png`
- `cellpose_mask_stats.json`
- `run_manifest.json`

## Observed Behavior On This Image

The current path now uses the full image, not a droplet-masked crop.
If the original frame is too large for a stable Cellpose run, it is resized internally for inference and the label masks are mapped back to the original image size.
Cellpose still tends to detect many medium and small organoids more readily than the two large fused central masses, so this remains a comparison baseline rather than a final overlap-aware solution.
