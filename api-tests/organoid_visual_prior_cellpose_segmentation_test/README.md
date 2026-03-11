# Organoid Visual-Prior + Cellpose Segmentation Test

This test uses a single fast Cellpose pass for the smaller organoids, then adds a visually guided prior for the major fused organoid masses seen in the image.

Design:

- `branch_cellpose_small/`: fast full-image Cellpose pass for small and medium organoids.
- `visual_prior_*`: image-guided prior masks for the obvious large fused regions.
- `visual_prior_cellpose_combined_*`: merged result.

Why this exists:

- the previous hybrid method captured the big masses better than Cellpose alone
- it still under-covered some parts of those fused organoids
- this branch uses explicit visual anchors for the large structures and keeps the rest simple

Run:

```bash
api-tests/organoid_visual_prior_cellpose_segmentation_test/run_visual_prior_cellpose_segmentation_test.sh \
  --input-tif '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif'
```

Key outputs:

- `visual_prior_overlay.png`
- `visual_prior_debug.json`
- `visual_prior_cellpose_combined_labels_16bit.png`
- `visual_prior_cellpose_combined_overlay.png`
- `comparison_panel.png`
