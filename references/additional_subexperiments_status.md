# Additional Subexperiments Status

Date: 2026-04-05
Repo root: `/home/lachlan/ProjectsLFS/Zhengyu`

## Purpose

This note records the additional subexperiments confirmed by the references beyond the main completed output roots:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery`

## Confirmed Additional Subexperiments

### 1. App65 DEO+Alginate

Confirmed dedicated subexperiment:

- `Day 7`
- `Day 13`

Reference support:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/06_figure3_alginate_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/03_transcription_notes_2.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/04_handwritten_experiment_note.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/DEO experiment.md`

Status:

- completed from the finished App65 segmentation/database outputs
- no segmentation rerun was needed

Output folder:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis`

Key outputs:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_a_longitudinal/app65_panel_a_longitudinal_primary_metrics.pdf`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_multiscale_large_recovery/subexperiment_analysis/panel_b_day7_day13/app65_panel_b_day7_day13_detailed_metrics.pdf`

Code:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app65_alginate_multiscale_cellpose/analyze_app65_subexperiments.py`

### 2. App80 DEO

Confirmed dedicated subexperiment:

- `Day 6`

Reference support:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/07_figure5_y27632_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/03_transcription_notes_2.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`

Status:

- already completed earlier from the finished App80 segmentation/database outputs
- no segmentation rerun was needed

Output folder:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/subexperiment_analysis`

Code:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/analyze_app80_two_subexperiments.py`

### 3. Density Figure B branch

This is the important clarification.

The references indicate that the density experiment is split into:

- A branch: `DEO App81 P8`
- B branch: `DEO test 2025.10.1`

Reference support:

- `/home/lachlan/ProjectsLFS/Zhengyu/data-docs/DEO_DATA_STRUCTURE_GUIDE.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_experiment_mapping_confirmed.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/05_figure2_density_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`

Important implication:

- the current finished App81 output root only covers the main A branch:
  - `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_main_density_multiscale_large_recovery`
- the true B branch is not something that can be backfilled from the current App81 database
- it requires a separate segmentation run on:
  - `/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO test 2025.10.1`

Current status:

- not segmented in this step
- should be treated as a separate output root, not as a subfolder under the existing App81 A-branch output

Recommended future output root:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery`

## Bottom Line

The additional reference-supported subexperiments are:

- App65 dedicated `Day 7 / Day 13` comparison: completed
- App80 dedicated `Day 6` comparison: completed
- Density B branch at `DEO test 2025.10.1`: confirmed by references, but still needs its own segmentation run
