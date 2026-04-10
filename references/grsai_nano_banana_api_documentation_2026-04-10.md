# GRS AI Nano Banana API Documentation

Date: 2026-04-10

This note records the current GRS AI Nano Banana API usage with the preferred global host:

- Preferred host: `https://grsaiapi.com`
- China host: `https://grsai.dakka.com.cn`

Use the global host by default unless there is a region-specific reason not to.

## Base URLs

- Global host: `https://grsaiapi.com`
- China host: `https://grsai.dakka.com.cn`

Endpoint construction is:

- `host + path`

Example:

- `https://grsaiapi.com/v1/draw/nano-banana`

## Primary Image Generation API

- Method: `POST`
- Path: `/v1/draw/nano-banana`
- Full global URL: `https://grsaiapi.com/v1/draw/nano-banana`

### Request Headers

```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer <API_KEY>"
}
```

### Request Body

```json
{
  "model": "nano-banana",
  "prompt": "A clean segmentation-style mask of true organoids only",
  "aspectRatio": "auto",
  "imageSize": "1K",
  "urls": [
    "https://example.com/example.png"
  ],
  "webHook": "-1",
  "shutProgress": false
}
```

### Main Parameters

- `model`:
  - required
  - string
  - supported examples from the provided documentation:
    - `nano-banana-2`
    - `nano-banana-2-cl`
    - `nano-banana-2-4k-cl`
    - `nano-banana-fast`
    - `nano-banana`
    - `nano-banana-pro`
    - `nano-banana-pro-vt`
    - `nano-banana-pro-cl`
    - `nano-banana-pro-vip`
    - `nano-banana-pro-4k-vip`
- `urls`:
  - optional
  - array
  - reference image URLs or base64 payloads
- `prompt`:
  - required
  - string
- `aspectRatio`:
  - optional
  - examples:
    - `auto`
    - `1:1`
    - `16:9`
    - `9:16`
    - `4:3`
    - `3:4`
    - `3:2`
    - `2:3`
    - `5:4`
    - `4:5`
    - `21:9`
  - additional ratios in the provided documentation for some models:
    - `1:4`
    - `4:1`
    - `1:8`
    - `8:1`
- `imageSize`:
  - optional
  - examples:
    - `1K`
    - `2K`
    - `4K`
  - higher resolution increases generation time
- `webHook`:
  - optional
  - if using polling instead of a callback, set to `"-1"` so the API returns a task id immediately
- `shutProgress`:
  - optional boolean
  - closes progress replies and returns only the final result when applicable

## Immediate Submit Response

If using the task-id workflow:

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "id": "id"
  }
}
```

Important:

- `data.id` is the task id
- store it and reuse it for polling
- this avoids resubmitting the same request and wasting credits/tokens

## Result Polling API

- Method: `POST`
- Path: `/v1/draw/result`
- Full global URL: `https://grsaiapi.com/v1/draw/result`

### Poll Request

```json
{
  "id": "xxxxx"
}
```

### Poll Response

```json
{
  "code": 0,
  "data": {
    "id": "xxxxx",
    "results": [
      {
        "url": "https://example.com/example.png",
        "content": "A beautiful girl with long hair and blue eyes"
      }
    ],
    "progress": 100,
    "status": "succeeded",
    "failure_reason": "",
    "error": ""
  },
  "msg": "success"
}
```

### Important Response Fields

- `code`:
  - `0` means success
  - the provided documentation also mentions `-22` for missing task
- `data.id`:
  - task id
- `data.results`:
  - generated result list
  - each item may include:
    - `url`
    - `content`
- `data.progress`:
  - `0` to `100`
- `data.status`:
  - `running`
  - `succeeded`
  - `failed`
- `data.failure_reason`:
  - may include:
    - `output_moderation`
    - `input_moderation`
    - `error`
- `data.error`:
  - detailed failure message when present

## Gemini-Compatible Format

The provided documentation also states that GRS AI supports a Gemini-style API format.

Guidance:

- replace the base address with the GRS AI host
- replace model `gemini-2.5-flash-image` with `nano-banana-fast`

Example URL shown in the provided documentation:

- `https://grsaiapi.com/v1beta/models/nano-banana-fast:generateContent`

Note:

- the provided UI text appears to contain a typo in one example where `generateContent` was missing the leading `g`
- use `generateContent`

## Recommended Operational Pattern

For reliable programmatic use:

1. Submit once to `https://grsaiapi.com/v1/draw/nano-banana`
2. Save:
   - prompt
   - request payload
   - submit response
   - task id
3. Poll `https://grsaiapi.com/v1/draw/result` with the saved task id
4. If the process is interrupted, resume polling with the saved task id instead of resubmitting

This is the correct pattern for long-running image generation tasks.

## Recommended Segmentation-Mask Prompt Style

For organoid mask generation, the prompt should be explicit and restrictive.

Recommended characteristics:

- ask for a segmentation-style image, not a natural-image redraw
- require pure black background
- require one clean filled color region per true organoid
- explicitly exclude:
  - outer droplet boundary
  - well/container boundary
  - speckles
  - faint debris
  - tiny fragments
- include:
  - small true organoids
  - large fused organoids
  - irregular true organoids when biologically real

Example prompt pattern:

```text
Return only a clean segmentation-style instance mask for true organoids in this brightfield image. Use a pure black background. Each true organoid should be a single clean filled region in a bright, visually distinct color. Include both small cystic organoids and large fused organoids. Exclude the outer droplet boundary, enclosing container/well boundary, halos, debris, speckles, and thin fragmental edge artifacts. Do not redraw the microscope image. Do not add labels, text, arrows, or shading. Preserve true irregular organoid shapes, but do not create noisy or fragmental boundaries.
```

## Practical Note

Based on current local testing, the global host appears to behave better and should be preferred:

- use `https://grsaiapi.com`

