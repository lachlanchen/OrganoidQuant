# SAM2 Prompted GPU Segmentation

Runs metadata-aware SAM2.1 large segmentation on the blinded fusion-analysis set.

Key behavior:
- uses GPU in `organoid-gpu`
- uses stage-aware prompt candidates derived from the image plus private day-rank metadata
- penalizes masks that expand into smooth enclosing droplet regions
- keeps organoid instances only

Run:

```bash
analysis-tools/fusion_analysis_test_sam2_prompted/run_fusion_analysis_test_sam2_prompted.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001
```
