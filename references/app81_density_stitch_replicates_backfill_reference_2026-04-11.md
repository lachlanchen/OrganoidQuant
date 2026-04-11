# App81 Density Stitch Replicates Backfill Reference

This reference describes the backfilled replicate stitch set for App81 10X images.

## Output
- Output root: [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1)
- Markdown manifest: [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/app81_density_stitch_manifest_replicates.md](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/app81_density_stitch_manifest_replicates.md)
- JSON manifest: [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/app81_density_stitch_manifest_replicates.json](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/app81_density_stitch_manifest_replicates.json)
- Plain collages: [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain)
- Labeled previews: [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/preview](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/preview)

## Batch Layout
- `batch_1`: `13, 15, 17, 20, 22, 24, 26, 28`
- `batch_2`: `14, 16, 18, 21, 23, 25, 27, 29`

## Rules
- Only `10X` or `10x` TIFFs are used.
- Each density/batch collage remains `3x3`.
- Slots `1-8` are date slots. Slot `9` is a forced black blank.
- `replicate_01` uses the first ranked candidate for each date.
- `replicate_02` and `replicate_03` use the matching replicate when available.
- If a higher replicate is missing for a date, that slot is backfilled from `replicate_01` for the same date, density, and batch.
- The manifest records `selection_mode` as one of `replicate_match`, `backfill_from_replicate_01`, or `forced_blank`.

## Summary
- Total collages: `14`
- Backfilled slots from `replicate_01`: `49`
- Forced blank slots: `14`
- Unfilled date slots after backfill: `0`

## Example Files
- [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain/low_batch_2_replicate_03_10x_stitched.png](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain/low_batch_2_replicate_03_10x_stitched.png)
- [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain/middle_batch_1_replicate_03_10x_stitched.png](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain/middle_batch_1_replicate_03_10x_stitched.png)
- [/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain/high_batch_2_replicate_02_10x_stitched.png](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1/collages/plain/high_batch_2_replicate_02_10x_stitched.png)
