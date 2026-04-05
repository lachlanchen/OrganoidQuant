# Test2025 Density B Experiment Design and Quantification Rules

Date: 2026-04-05
Raw source: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO test 2025.10.1`
Planned output root: `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/test2025_density_B_multiscale_large_recovery`

## Role In The Project

This dataset is the confirmed density-experiment `B` branch, complementary to:

- density `A`: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO App81 P8`
- density `B`: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/DEO test 2025.10.1`

Reference support:

- `/home/lachlan/ProjectsLFS/Zhengyu/references/deo_experiment_mapping_confirmed.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/05_figure2_density_design.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/references/experiment_design/09_comprehensive_experiment_design_and_quantification_plan.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/data-docs/DEO_DATA_STRUCTURE_GUIDE.md`
- `/home/lachlan/ProjectsLFS/Zhengyu/data-docs/DEO_DATA_STRUCTURE_GUIDE_CN_DETAILED.md`

## Biological Question

This branch is an independent confirmation of the density effect:

- low density grows more slowly and interacts less
- middle density grows better and begins to fuse more
- high density grows fastest and may differentiate earlier

The quantitative focus remains:

- growth
- fusion / interaction
- later morphology / differentiation tendency

## Important Naming Rule

For this raw branch, the prefix-like `1x / 5x / 10x` in names is part of the density-group naming, not the microscope magnification.

The true microscope magnification is taken from the last `2X / 4X / 10X` token in the filename.

Examples:

- `4well 1x low 10X D7-1.tif`
  - density: `low`
  - microscopy magnification: `10x`
  - day token: `D7`
- `4well 10x high 4X D8-2.tif`
  - density: `high`
  - microscopy magnification: `4x`
  - day token: `D8`

## Main Quantified Inclusion Rule

The main quantified dataset includes only files that satisfy all of the following:

- non-`_RGB`
- explicit density label: `low`, `middle`, or `high`
- explicit day token `D#`
- true microscopy magnification `10x`
- from the structured `D0/` tree rather than top-level `before D6-*`

This is intentionally strict because the branch naming is noisy.

## Review Queue Rule

The top-level `before D6-*` files are not mixed into the main quantitative database automatically because:

- they do not carry explicit density labels
- they do not fit the main structured parser cleanly
- they should be treated as low-confidence review data unless manually mapped

They are written into a review queue rather than silently ignored.

## Expected Deliverables

The dedicated branch should produce:

- per-image segmentation intermediates under `runs/`
- per-image metrics database
- daily summary database
- audit tables for included vs skipped files
- overview figures
- full grouped metric figures

## Current Main Quantified Selection

Validated selection for the strict main quantified set:

- `130` images included

Main skip classes:

- `_RGB` duplicates
- non-`10x`
- missing `D#` token
- top-level `before D6-*` low-confidence files

## Why This Differs From App81 A

`DEO App81 P8` uses date folders and clearer condition labels.

`DEO test 2025.10.1` uses:

- embedded `D#` day tokens instead of clean date folders
- mixed apparent `1x / 5x / 10x` density naming in the prefix
- separate `2X / 4X / 10X` microscopy tokens later in the filename
- additional low-confidence `before D6-*` files at the top level

So this branch needs a dedicated parser and should not reuse the App81 A metadata logic unchanged.
