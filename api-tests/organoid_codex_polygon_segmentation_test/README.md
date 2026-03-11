# Organoid Codex Polygon Segmentation Test

This test is a general, single-image polygon segmentation workflow.

Pipeline:

- convert the input TIFF to PNG
- run a small-object Cellpose pass
- run a large-object Cellpose pass
- build one combined image-derived prior from the image itself plus both Cellpose branches
- call `codex exec` for a coarse polygon pass
- render the coarse polygons
- call `codex exec` again for a refine polygon pass
- render the final polygons
- render:
  - `coarse_polygon_labels_16bit.png`
  - `coarse_polygon_instance_rgb.png`
  - `coarse_polygon_overlay.png`
  - `polygon_labels_16bit.png`
  - `polygon_instance_rgb.png`
  - `polygon_overlay.png`

The prior is general and image-derived. It is built from:

- gradient / edge overlays
- blob candidates
- a general large-mass overlay
- Cellpose small-object contours
- Cellpose large-object contours
- one combined prior overlay used by the prompt tool

Run:

```bash
api-tests/organoid_codex_polygon_segmentation_test/run_codex_polygon_segmentation.sh \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif'
```

Output:

- one timestamped folder under `api-tests/organoid_codex_polygon_segmentation_test/output/`
- coarse and refine prompts
- priors and Cellpose branch outputs
- coarse JSON + final JSON
- coarse polygon mask / RGB / overlay
- final polygon mask / RGB / overlay
- `run_manifest.json`
