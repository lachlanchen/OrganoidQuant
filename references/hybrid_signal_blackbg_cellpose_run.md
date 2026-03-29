# Hybrid Signal Black-Background Cellpose Run

This note records the completed Cellpose batch run on the black-background hybrid signal images derived from the first-replication `10x` App80 `10uM` dates.

## Source Inputs

Original selected first-replication `10x` TIFFs were organized under:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/first_replication_selected_dates/10x`

The derived black-background hybrid signal images used for Cellpose were stored under:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/first_replication_selected_dates/hybrid_signal_blackbg`

These images are the same "second-column" signal family discussed earlier. They are not simple grayscale inversions. They are computed from a fixed hybrid signal transform:

- CLAHE contrast enhancement
- small foreground blur
- large background blur
- normalized inverse blur term
- normalized residual term
- final blend: `0.45 * inv_norm + 0.55 * residual_norm`

## Environment

The run reused the existing conda environment:

- `organoid-gpu`

No new environment was created.

The environment was repaired in place before the batch was run. The repair was done because Cellpose inference had been failing with inconsistent Python/runtime behavior. The repair session kept the same environment name and then reran the batch from that repaired environment.

## GPU Usage

This run was executed with GPU enabled.

The intent of the repair was specifically to make the existing `organoid-gpu` environment stable enough to run Cellpose on GPU rather than continuing with the much slower CPU probe path.

## Output Folder

Flat outputs were written to:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/first_replication_selected_dates/hybrid_signal_blackbg_cellpose_flat`

This folder contains one flat set of outputs per image, rather than nested run directories.

### Files written per image

For each source PNG, the flat output folder contains:

- `*_cellpose_mask_16bit.png`
- `*_cellpose_overlay.png`
- `*_cellpose_stats.json`

### Batch summary

The batch summary file is:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/first_replication_selected_dates/hybrid_signal_blackbg_cellpose_flat/cellpose_batch_summary.json`

## Recorded Mask Counts

The batch summary recorded the following kept mask counts:

| Date | Source file | Mask count |
|---|---|---:|
| 05-十二月-2025 | `05-十二月-2025_10x00_gallery_column2_hybrid_signal.png` | 6 |
| 07-十二月-2025 | `07-十二月-2025_10X00_gallery_column2_hybrid_signal.png` | 3 |
| 08-十二月-2025 | `08-十二月-2025_10x00_gallery_column2_hybrid_signal.png` | 7 |
| 09-十二月-2025 | `09-十二月-2025_10x00_gallery_column2_hybrid_signal.png` | 15 |
| 10-十二月-2025 | `10-十二月-2025_10x00_gallery_column2_hybrid_signal.png` | 2 |
| 11-十二月-2025 | `11-十二月-2025_10x00_gallery_column2_hybrid_signal.png` | 4 |
| 12-十二月-2025 | `12-十二月-2025_10x00_gallery_column2_hybrid_signal.png` | 8 |

The batch summary also recorded a working scale of `0.5333333333333333` for each image in this run.

## Interpretation Note

This note only records what was run and where the outputs are.

It does **not** claim that the Cellpose segmentation quality was biologically correct. In later review, the segmentation quality on these hybrid-signal images was considered unsatisfactory for the organoid-level interpretation task. The folder is still useful as a recorded baseline and for comparison against later methods.
