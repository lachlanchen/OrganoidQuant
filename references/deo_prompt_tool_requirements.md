# DEO Prompt Tool Requirements (Draft from User Request)

## Scope
Target image for initial focus:
- `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/4x00.tif`

Goal:
- Build a set of prompt tools (Codex exec based), each focused on a single task, to analyze DEO image data and produce structured outputs.

## Required Prompt Tools

### Tool 0: TIF -> PNG Utility
- Convert `.tif` to `.png`.
- Save output with mirrored folder structure under `DEO-PNG/...`.

### Tool 1: Metadata + Structure Analyzer
- Parse folder structure and filename information.
- Extract experiment parameters such as:
- date
- control/condition parameters (e.g., concentration)
- amplification/magnification (e.g., 4x/10x)
- sample number / repeated imaging info
- possible additional encoded info
- If possible, read TIFF embedded metadata.
- Output per-image markdown using mirrored structure:
- `DEO-MARKDOWN/.../<image_name>/<image_name>.md`
- Maintain an experiment-level database at Droplet-Engineered-Organoid level.
- For now, update database using the current target image row.
- Include fields for:
- experiment information
- number of droplets
- number of organoids inside each droplet
- droplet size
- droplet position
- organoid position
- fusion-level quantification

### Tool 2: Droplet Segmentation Tool
- Segment droplets based on droplet location information.
- Output separate droplet images into a folder named after the source image.

### Tool 3: Image + Segment Reader
- Read both original image and segmented droplet images.
- Produce final structured quantification records.

### Tool 4: Prompt Architecture Requirement
- Keep each prompt tool focused on a single task.
- Use multiple prompt tools to handle different subtasks.
- Each prompt should include detailed and redundant context/information.

## Final Output Databases

1. Image-level database
- one row per source image
- includes parsed experiment metadata and global quantification summaries

2. Droplet-level database
- one row per droplet
- droplet geometry, position, and per-droplet quantification

3. Organoid-level database (additional requirement)
- one row per organoid (linked to droplet and image)
- organoid position/size/morphology/fusion-related measurements

## Current Instruction from User
Before implementation, first save the above requirements into `references/`.
This document fulfills that instruction.
