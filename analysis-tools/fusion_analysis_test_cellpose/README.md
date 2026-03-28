# Fusion Analysis Test Cellpose

Batch Cellpose runner for blinded fusion-analysis test sets under `analysis-output/fusion-analysis-test/`.

This wrapper reuses the existing single-image Cellpose launcher in:

- `api-tests/cellpose_organoid_segmentation_test/run_cellpose_organoid_segmentation_test.sh`

It adds:

- per-image diameter priors
- batch manifest output
- a compact Markdown summary for manual review

## Usage

```bash
analysis-tools/fusion_analysis_test_cellpose/run_fusion_analysis_test_cellpose_batch.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001
```

Default output folder for `set_001`:

```text
/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001_cellpose
```

## Size Prior Note

Cellpose does not strictly require a diameter prior, but it still benefits from one.
`diameter` is a soft object-scale prior, not a hard constraint.

For the current blinded set, the wrapper uses a small visually estimated prior table,
derived from the blinded image strip only, without using date or condition metadata.
