# App80 First Replicate Prompted Watershed

This toolchain uses a Codex vision prompt to choose image-specific parameters for a deterministic OpenCV segmentation pipeline.

Pipeline per image:
1. convert TIFF to PNG and build prompt artifacts
2. run `codex exec` with the original image plus grayscale, inverse, residual, and edge previews
3. receive segmentation parameters as strict JSON
4. run threshold + Otsu/adaptive threshold + watershed deterministically
5. post-filter large smooth droplet-like masks
6. write labels, overlays, mask stats, and a batch gallery

Default run:

```bash
analysis-tools/app80_first_replicate_prompted_watershed/run_batch_app80_first_replicates.sh
```
