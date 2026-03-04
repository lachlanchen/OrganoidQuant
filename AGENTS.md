# Repository Guidelines

## Project Structure & Module Organization
This repository is data- and documentation-centric (no application source tree yet).

- `DEO/`: primary experiment data and summary TIFFs.
- `DEO/App65 DEO+Alginate/`: Alginate concentration experiment (date-based folders).
- `DEO/App80 DEO/`: Y-27632 concentration experiment (`No`, `10uM`, `20uM`, `50uM`, `100uM`).
- `DEO/DEO App81 P8/`: DEO density experiment (`low/middle/high`, plus `low transfer`).
- `data-docs/`: working docs and forms (`.md`, `.docx`, `.pdf`).
- `data-docs/tex-artifacts/`: LaTeX source and build artifacts.
- `references/`: external/reference materials (thesis PDF, confirmed mapping notes).

## Build, Test, and Development Commands
No software build pipeline is defined. Use these utility commands:

- `find DEO -maxdepth 3 -print | sort`: inspect folder organization.
- `pdftotext references/DEO+part+thesis.pdf - | less`: extract thesis text for verification.
- `cd data-docs/tex-artifacts && xelatex -interaction=nonstopmode DEO_Experiment_Clarification_Form.tex`: rebuild interactive PDF form.

## Environment Setup
- Default Python environment for this repository: `organoid`.
- Expected interpreter path: `/home/lachlan/miniconda3/envs/organoid/bin/python`.
- Quick check:
- `conda activate organoid`
- `which python`

## Coding Style & Naming Conventions
For documentation/scripts added later:

- Use UTF-8 Markdown with clear section headings and short paragraphs.
- Prefer descriptive filenames with stable prefixes, e.g. `deo_experiment_*.md`.
- Keep generated artifacts grouped under `data-docs/tex-artifacts/`.
- Do not rename or overwrite raw experiment files in `DEO/` unless explicitly requested.

## Testing Guidelines
There is no automated test framework currently.

- For docs: validate links/paths and ensure tables map to actual folders.
- For PDF forms: open in a form-capable viewer and verify fields are editable.
- For data mapping changes: cross-check against `references/deo_experiment_mapping_confirmed.md`.

## Commit & Pull Request Guidelines
Git metadata is not available in this directory, so follow this convention:

- Commit message format: `docs: ...`, `data-docs: ...`, `mapping: ...`.
- Keep commits atomic (one logical change per commit).
- PRs should include: purpose, affected paths, before/after structure, and any mapping assumptions.

## Security & Data Handling
- Treat `DEO/` as source-of-truth raw data.
- Avoid destructive operations (`rm`, mass rename) without explicit confirmation.
- Store derived summaries and templates in `data-docs/` or `references/`, not mixed into raw data folders.

## Agent Workflow Policy
- After each meaningful edit, create a commit and push to the configured remote branch.
- If push fails (e.g., auth/network), keep the local commit and report the exact failure.
