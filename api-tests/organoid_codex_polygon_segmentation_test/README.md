# Organoid Codex Polygon Segmentation Test

This test is a general, single-image polygon segmentation workflow.

Pipeline:

- convert the input TIFF to PNG
- build image-derived priors from the image itself
- call `codex exec` with the source image and prior overlays
- receive schema-constrained organoid polygons
- render:
  - `polygon_labels_16bit.png`
  - `polygon_instance_rgb.png`
  - `polygon_overlay.png`

The prior is not hard-coded for one image. It is built from:

- gradient / edge overlays
- blob candidates
- a general large-mass overlay
- optional Cellpose overlay

Run:

```bash
api-tests/organoid_codex_polygon_segmentation_test/run_codex_polygon_segmentation.sh \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif'
```

Output:

- one timestamped folder under `api-tests/organoid_codex_polygon_segmentation_test/output/`
- prompt, priors, raw JSON response, polygon mask, RGB mask, and overlay
