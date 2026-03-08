# DEO Codex Prompt Tools (Single-Image First)

This toolkit implements a prompt-driven DEO analysis pipeline for one image, then can scale to batch later.

## Pipeline

1. `00_convert_tif_to_png.py`
- Convert TIFF to PNG under mirrored `DEO-PNG/...`.

2. `00_extract_tif_metadata.py`
- Extract TIFF metadata/tags to JSON.

3. `00_build_vision_priors.py` (called inside prompt scripts)
- Build gradient/edge/circle/blob priors from PNG.
- Optional Cellpose priors are supported.

4. `01_prompt_image_context_and_droplets.sh`
- Use `codex exec + source image + prior overlays` to parse metadata and annotate droplet circles.
- Prompt is magnification-aware (`4x` vs `10x`) and does not force fixed droplet counts.

5. `01_refine_droplet_annotations.py`
- Normalize annotation fields and remove duplicate/high-overlap partial droplets.

6. `01_optimize_droplet_circles_by_edge.py`
- Apply local edge-gradient circle micro-adjustment to reduce small center/radius shift.

7. `02_segment_droplets_from_annotations.py`
- Generate droplet-level segment PNGs from annotated circles.

8. `03_prompt_droplet_level_quantification.sh`
- Use `codex exec + original image + segment images` to estimate organoid count and fusion level per droplet.

9. `03_compute_droplet_objective_metrics.py`
- Compute objective metrics (gradient, edge density, dark-centroid, fusion heuristic).

10. `05_prompt_organoid_analysis_complete_droplets.sh`
- Analyze organoids per droplet for complete droplets only (`is_partial=false`).
- Uses droplet-local prior overlays (gradient/blob/optional Cellpose) in the prompt context.

11. `04_update_markdown_and_databases.py`
- Write per-image markdown and maintain:
- `DEO-DATABASE/image_database.csv`
- `DEO-DATABASE/droplet_database.csv`
- `DEO-DATABASE/organoid_database.csv`

## Single image test

```bash
prompt-tools/deo-codex/scripts/run_single_image_test.sh \
  "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/4x00.tif"
```

## 10x Guarded Pipeline (Recommended for App80 10x)

- `run_single_image_10x_guarded.sh`
- Runs full analysis for one `10x*.tif` with a dedicated guard stage.
- Guard checks droplet detection quality and can trigger a single-center fallback correction.

```bash
prompt-tools/deo-codex/scripts/run_single_image_10x_guarded.sh \
  "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"
```

- `run_app80_10x_guarded_batch.sh`
- Batch runs all `10x*.tif` under `DEO/App80 DEO`, one-by-one.

- `archive_app80_outputs.sh`
- Moves existing App80 outputs under `DEO-PNG/`, `DEO-MARKDOWN/`, `DEO-SEGMENTS/` to `archived-result/...`.

- `start_tmux_app80_10x_guarded.sh`
- Stops existing `deo_app` session, archives old App80 outputs, and launches guarded batch in tmux.

```bash
DEO_CELLPOSE_MODE=auto \
prompt-tools/deo-codex/scripts/start_tmux_app80_10x_guarded.sh \
  "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO" \
  deo_app
```

Default Python interpreter:
- `/home/lachlan/miniconda3/envs/organoid/bin/python`

Cellpose toggle:
- `DEO_CELLPOSE_MODE=auto` (default): run Cellpose priors for organoid mode only.
- `DEO_CELLPOSE_MODE=on`: force Cellpose priors in both droplet and organoid modes.
- `DEO_CELLPOSE_MODE=off`: disable Cellpose priors.
