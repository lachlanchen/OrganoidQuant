# GRSAI Nano Banana Mask Test

This test submits one organoid image to the GRSAI Nano Banana API and saves the generated segmentation-style mask plus all run metadata.

## Script

- `run_grsai_mask_test.py`

## Default Input

- `DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif`

## API Flow

1. Load `GRSAI` from repo-root `.env`.
2. Convert the TIFF to a local PNG copy for reference.
3. Build a smaller request image for API upload.
4. Submit to global host `https://grsaiapi.com` with `webHook="-1"`.
5. Capture the returned task ID.
6. Poll `POST /v1/draw/result` until status becomes `succeeded`.
7. Download the generated mask to the run folder.

## Example Command

```bash
PYTHONUNBUFFERED=1 /home/lachlan/miniconda3/envs/organoid/bin/python \
  api-tests/grsai_nano_banana_mask_test/run_grsai_mask_test.py \
  --host https://grsaiapi.com \
  --reference-format jpeg \
  --jpeg-quality 88 \
  --resize-max-dim 1024 \
  --request-timeout 600 \
  --poll-interval 10 \
  --max-wait-seconds 1800
```

## Latest Successful Run

- `output/05-十二月-2025_10x00_20260311_212149/`

Key files:

- `generated_mask.png`: downloaded API result
- `run_manifest.json`: input, host, model, task ID, output path
- `submit_response.json`: initial task-ID response
- `result_response.json`: final polled result payload
- `prompt.txt`: exact prompt used
- `10x00_request.jpg`: resized request image sent to the API
