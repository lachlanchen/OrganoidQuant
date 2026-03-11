# GRSAI Nano Banana API Documentation

Source: user-provided API documentation snippet converted from HTML to Markdown.

## Node Information

### Hosts

- Global: `https://grsaiapi.com`
- China: `https://grsai.dakka.com.cn`

### Usage Pattern

Use `Host + Path`.

Example:

```text
https://grsai.dakka.com.cn/v1/draw/nano-banana
```

## Gemini Official API Compatibility

GRSAI supports the Gemini official API format.

Guidance:

- Replace the base URL with the GRSAI host.
- Change model name `gemini-2.5-flash-image` to `nano-banana-fast`.

Example:

```text
https://grsai.dakka.com.cn/v1beta/models/nano-banana-fast:streamGenerateContent
```

## Nano Banana API

- Method: `POST`
- Path: `/v1/draw/nano-banana`
- Response mode: `stream` or `callback`

### Request Headers

```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer apikey"
}
```

### Request Body

```json
{
  "model": "nano-banana",
  "prompt": "A beautiful girl with long hair and blue eyes",
  "aspectRatio": "auto",
  "imageSize": "1K",
  "urls": [
    "https://example.com/example.png"
  ],
  "webHook": "https://example.com/callback",
  "shutProgress": false
}
```

### Request Parameters

#### `model` (required)

- Type: `string`
- Example: `"nano-banana"`
- Supported values:
  - `nano-banana-2`
  - `nano-banana-fast`
  - `nano-banana`
  - `nano-banana-pro`
  - `nano-banana-pro-vt`
  - `nano-banana-pro-cl`
  - `nano-banana-pro-vip`
  - `nano-banana-pro-4k-vip`

#### `urls` (optional)

- Type: `array`
- Example: `["https://example.com/example.png"]`
- Description: reference image URL or Base64.

#### `prompt` (required)

- Type: `string`
- Example: `"A beautiful girl with long hair and blue eyes"`
- Description: prompt text.

#### `aspectRatio` (optional)

- Type: `string`
- Example: `"auto"`
- Supported values:
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
- Default: `auto`

#### `imageSize` (optional)

- Type: `string`
- Example: `"1K"`
- Supported on:
  - `nano-banana-2`
  - `nano-banana-pro`
- Supported values:
  - `1K`
  - `2K`
  - `4K`
- Default: `1K`
- Note: higher resolution increases generation time.

#### `webHook` (optional)

- Type: `string`
- Example: `"https://your-webhook-url.com/callback"`
- Description:
  - callback endpoint for progress and result notifications
  - default behavior is stream response
  - if `webHook` is provided, progress and result are sent by HTTP `POST`
  - request header: `Content-Type: application/json`
  - if you want polling instead of callback, set `webHook` to `"-1"` to get an `id` immediately

#### `shutProgress` (optional)

- Type: `boolean`
- Example: `false`
- Description: suppress progress updates and return only final result.
- Recommendation: use with `webHook`.
- Default: `false`

## Initial Callback / Task ID Response

Used when `webHook` is enabled and the API returns an ID for later callback matching.

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "id": "id"
  }
}
```

### Fields

- `code`: status code, `0` means success
- `msg`: status message
- `data.id`: task ID used to match callback data

## Stream / Callback Result Format

This structure is used for stream response and webhook response.

```json
{
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
}
```

### Fields

#### `id`

- Type: `string`
- Example: `"f44bcf50-f2d0-4c26-a467-26f2014a771b"`
- Description: task ID

#### `results`

- Type: `array`
- Description:
  - `url`: generated image URL, valid for 2 hours
  - `content`: text reply content

#### `progress`

- Type: `number`
- Example: `100`
- Description: task progress, range `0` to `100`

#### `status`

- Type: `string`
- Supported values:
  - `"running"`
  - `"succeeded"`
  - `"failed"`

#### `failure_reason`

- Type: `string`
- Example: `"error"`
- Supported values:
  - `"output_moderation"`
  - `"input_moderation"`
  - `"error"`
- Note: if `"error"` occurs, retrying submission may help.

#### `error`

- Type: `string`
- Example: `"Invalid input parameters"`
- Description: detailed failure message

## Get Result API

Separate polling endpoint for retrieving task results.

- Method: `POST`
- Path: `/v1/draw/result`

### Request Body

```json
{
  "id": "xxxxx"
}
```

### Response Body

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

### Fields

- `code`: status code, `0` means success, `-22` means task does not exist
- `msg`: status information
- `data`: task result object, same structure as the standard result format above
