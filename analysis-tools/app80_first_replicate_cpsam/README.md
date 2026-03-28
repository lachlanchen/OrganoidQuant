# App80 First Replicate Cellpose-SAM

Runs `cpsam` on the original first-replicate `10uM` App80 images.

Behavior:
- uses the original file paths, not the blinded copies
- runs `CellposeModel(pretrained_model='cpsam')` on GPU when available
- applies a stage-aware post-filter to suppress outer droplet masks
- keeps outputs under `analysis-output/app80_10uM_first_replicate_cpsam`

Run:

```bash
analysis-tools/app80_first_replicate_cpsam/run_app80_first_replicate_cpsam.sh
```
