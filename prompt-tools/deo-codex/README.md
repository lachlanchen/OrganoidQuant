# DEO Codex Prompt Tools (Single-Image First)

This toolkit implements a prompt-driven DEO analysis pipeline for one image, then can scale to batch later.

## Pipeline

1. `00_convert_tif_to_png.py`
- Convert TIFF to PNG under mirrored `DEO-PNG/...`.

2. `00_extract_tif_metadata.py`
- Extract TIFF metadata/tags to JSON.

3. `01_prompt_image_context_and_droplets.sh`
- Use `codex exec + image` to parse folder/file metadata and annotate droplet circles by vision.

4. `02_segment_droplets_from_annotations.py`
- Generate droplet-level segment PNGs from annotated circles.
- No threshold/cellpose used.

5. `03_prompt_droplet_level_quantification.sh`
- Use `codex exec + original image + segment images` to estimate organoid count and fusion level per droplet.

6. `04_update_markdown_and_databases.py`
- Write per-image markdown and maintain:
- `DEO-DATABASE/image_database.csv`
- `DEO-DATABASE/droplet_database.csv`
- `DEO-DATABASE/organoid_database.csv`

## Single image test

```bash
prompt-tools/deo-codex/scripts/run_single_image_test.sh \
  "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/4x00.tif"
```

Default Python interpreter:
- `/home/lachlan/miniconda3/envs/organoid/bin/python`
