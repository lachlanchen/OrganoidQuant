# Fusion Analysis Test micro-sam Prompted

Promptable segmentation for blinded fusion-analysis image sets using `micro_sam`.

This pipeline uses:

- `micro_sam` with the microscopy-finetuned `vit_b_lm` model
- box prompts from existing Cellpose masks
- extra box prompts from large dark image components

The goal is not fully blind automatic segmentation. The goal is to give a promptable
microscopy segmentation model stronger priors than Cellpose alone.

## Usage

```bash
analysis-tools/fusion_analysis_test_microsam_prompted/run_fusion_analysis_test_microsam_prompted.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001
```

Default output folder:

```text
/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001_microsam_prompted
```

## Notes

- Runs with `PYTHONNOUSERSITE=1` so the conda-installed `micro_sam` stack is used consistently.
- Uses `vit_b_lm`, the light-microscopy finetuned model recommended by `micro_sam`.
- Prompt boxes come from image-derived priors rather than date or concentration metadata.
