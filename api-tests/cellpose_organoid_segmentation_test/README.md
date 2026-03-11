# Cellpose Organoid Segmentation Test

This test runs direct Cellpose segmentation on one organoid image and saves the raw labels, filtered labels, RGB instance mask, overlay, and per-mask statistics.

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
- `cellpose_mask_stats.json`
- `run_manifest.json`

## Observed Behavior On This Image

Cellpose detects many medium and small organoids, especially around the droplet periphery.
It does not capture the two large fused central masses well, so this result is useful as a comparison baseline, not as a final overlap-aware segmentation.
