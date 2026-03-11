# GRSAI Nano Banana Prior-Assisted Mask Test

This test improves the earlier Nano Banana mask generation by sending three reference images together:

1. the source microscopy image
2. a locally generated prior overlay showing likely organoid positions and fused regions
3. the previous coarse mask as a rough starting guess

## Script

- `run_grsai_mask_with_prior_test.py`

## Goal

Help the model recognize:

- the two dominant fused organoid masses
- medium round organoids along the right side of the droplet
- smaller scattered organoids inside the droplet
- overlap/fusion without collapsing everything into one blob

## API Flow

1. Load the API key from repo-root `.env`
2. Convert the TIFF to a local PNG and a resized JPEG request image
3. Build a prior overlay with:
   - droplet boundary
   - warm-color large fused regions
   - cool-color medium/small organoid candidates
4. Include the previous coarse mask as a third reference
5. Submit to `https://grsaiapi.com/v1/draw/nano-banana` with `webHook="-1"`
6. Poll `/v1/draw/result` until `succeeded`
7. Download the refined mask

## Latest Successful Run

- `output/05-十二月-2025_10x00_20260311_213115/`

Key files:

- `generated_mask_refined.png`
- `prior_overlay.png`
- `prior_summary.json`
- `coarse_mask_reference.png`
- `prompt.txt`
- `run_manifest.json`
