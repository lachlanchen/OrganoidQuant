# SAM Prompted GPU Segmentation

Runs prompt-box-guided Segment Anything on the blinded fusion-analysis test set.

Inputs:
- `analysis-output/fusion-analysis-test/set_001/blinded_images/*.tif`
- existing blinded Cellpose boxes from `set_001_cellpose/runs/.../cellpose_mask_stats.json`
- additional image-derived dark-mass boxes from the source image itself

Environment:
- `/home/lachlan/miniconda3/envs/organoid-gpu`
- requires `PYTHONNOUSERSITE=1` and `TORCH_DISABLE_DYNAMO=1`

Run:
```bash
analysis-tools/fusion_analysis_test_sam_prompted/run_fusion_analysis_test_sam_prompted.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001
```

Outputs:
- sibling folder `analysis-output/fusion-analysis-test/set_001_sam_prompted_gpu`
- per-image folders under `runs/<uid>/`
- a combined gallery image
