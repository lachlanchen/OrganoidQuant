# Organoid Multiscale + Hybrid Segmentation Test

This test runs two instance-segmentation strategies on one microscopy image and writes both result sets into a single output folder.

Methods:

- `multiscale_combined`: combines a small-object Cellpose pass with a large-object Cellpose pass.
- `hybrid_combined`: combines the small-object Cellpose pass with a deterministic large fused-mass detector on the full image.

Why this exists:

- the small-object Cellpose pass tracks many peripheral organoids well
- the larger fused central organoids are often missed by Cellpose alone
- the hybrid branch promotes those larger fused masses into explicit instances before merging the smaller masks

Run:

```bash
api-tests/organoid_multiscale_hybrid_segmentation_test/run_multiscale_hybrid_segmentation_test.sh \
  --input-tif '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif'
```

Outputs inside one run folder:

- `multiscale_combined_labels_16bit.png`
- `multiscale_combined_instance_rgb.png`
- `multiscale_combined_overlay.png`
- `hybrid_combined_labels_16bit.png`
- `hybrid_combined_instance_rgb.png`
- `hybrid_combined_overlay.png`
- `hybrid_large_detector_overlay.png`
- `comparison_panel.png`
- `run_manifest.json`

Branch subfolders are also preserved:

- `branch_cellpose_small/`
- `branch_cellpose_large/`

Those branch folders contain the intermediate Cellpose artifacts, including flow and cell-probability images.
