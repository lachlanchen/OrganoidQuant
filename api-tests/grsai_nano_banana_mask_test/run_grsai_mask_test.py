#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from PIL import Image


DEFAULT_PROMPT = """This image contains biological organoids with partial and heavy overlap. Generate an accurate instance segmentation mask for all individual organoids. Assign each organoid a unique color channel or RGB layer. For regions where organoids overlap, encode the overlap by additive RGB color composition: • If organoid A is assigned red (R) and organoid B is assigned blue (B), the overlapping region must appear as magenta (R + B). • If three organoids overlap, the overlap must be encoded by the additive combination of their assigned RGB channels. Overlapping regions must preserve separate identity information for each organoid, not merge them into a single object. Correctly separate touching and overlapping organoids by following true morphological boundaries, even when contrast is low. Preserve the true shape, size, and topology of each organoid. The output must be a clean, smooth segmentation mask with continuous boundaries (no jagged edges, no pixel noise). Do not hallucinate additional organoids. Do not remove real organoids. Output only the RGB segmentation mask, with consistent color assignment across the entire image, suitable for quantitative biological analysis and downstream computational processing."""


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_input = repo_root / "DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"
    default_output = repo_root / "api-tests/grsai_nano_banana_mask_test/output"
    default_env = repo_root / ".env"
    p = argparse.ArgumentParser(description="Test GRSAI nano-banana image-to-mask generation on one organoid image.")
    p.add_argument("--input-tif", default=str(default_input))
    p.add_argument("--host", default="https://grsaiapi.com")
    p.add_argument("--model", default="nano-banana-pro")
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--env-file", default=str(default_env))
    p.add_argument("--output-root", default=str(default_output))
    p.add_argument("--reference-format", choices=["png", "jpeg"], default="jpeg")
    p.add_argument("--jpeg-quality", type=int, default=88)
    p.add_argument("--resize-max-dim", type=int, default=1024)
    p.add_argument("--poll-interval", type=float, default=8.0)
    p.add_argument("--max-wait-seconds", type=float, default=600.0)
    p.add_argument("--request-timeout", type=float, default=600.0)
    return p.parse_args()


def load_env_value(env_path: Path, key: str) -> str:
    if not env_path.exists():
        raise FileNotFoundError(f"Env file not found: {env_path}")
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        if value:
            return value
    raise KeyError(f"{key} not found in {env_path}")


def ensure_png(src_tif: Path, output_dir: Path) -> Path:
    png_path = output_dir / f"{src_tif.stem}.png"
    with Image.open(src_tif) as im:
        im.save(png_path, format="PNG")
    return png_path


def ensure_request_image(src_tif: Path, output_dir: Path, ref_format: str, jpeg_quality: int, resize_max_dim: int | None) -> Path:
    suffix = ".png" if ref_format == "png" else ".jpg"
    out_path = output_dir / f"{src_tif.stem}_request{suffix}"
    with Image.open(src_tif) as im:
        if resize_max_dim and max(im.size) > resize_max_dim:
            scale = resize_max_dim / float(max(im.size))
            new_size = (max(1, int(im.size[0] * scale)), max(1, int(im.size[1] * scale)))
            im = im.resize(new_size, Image.Resampling.LANCZOS)
        if ref_format == "png":
            im.save(out_path, format="PNG")
        else:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            elif im.mode == "L":
                im = im.convert("RGB")
            im.save(out_path, format="JPEG", quality=jpeg_quality, optimize=True)
    return out_path


def make_data_uri(png_path: Path) -> str:
    mime = mimetypes.guess_type(png_path.name)[0] or "image/png"
    encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def post_json(url: str, payload: Dict[str, Any], token: str, timeout: float) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": raw}
        return e.code, payload


def poll_result(base_host: str, task_id: str, token: str, poll_interval: float, max_wait_seconds: float, request_timeout: float) -> Dict[str, Any]:
    url = urllib.parse.urljoin(base_host.rstrip("/") + "/", "v1/draw/result")
    start = time.time()
    last_payload: Dict[str, Any] = {}
    while True:
        _, payload = post_json(url, {"id": task_id}, token, request_timeout)
        last_payload = payload
        data = payload.get("data") or {}
        status = data.get("status")
        progress = data.get("progress")
        print(f"poll status={status!r} progress={progress!r}")
        if status == "succeeded":
            return payload
        if status == "failed":
            raise RuntimeError(json.dumps(payload, ensure_ascii=False, indent=2))
        if time.time() - start > max_wait_seconds:
            raise TimeoutError(f"Timed out waiting for task {task_id}. Last payload: {json.dumps(last_payload, ensure_ascii=False)}")
        time.sleep(poll_interval)


def download_file(url: str, out_path: Path) -> Path:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "OrganoidQuant/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as resp, out_path.open("wb") as f:
        shutil.copyfileobj(resp, f)
    return out_path


def make_run_dir(output_root: Path, input_tif: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_parent = input_tif.parent.name.replace("/", "_")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", input_tif.stem)
    run_dir = output_root / f"{safe_parent}_{safe_name}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_tif = Path(args.input_tif).resolve()
    output_root = Path(args.output_root).resolve()
    env_file = Path(args.env_file).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if not input_tif.exists():
        raise FileNotFoundError(f"Input TIFF not found: {input_tif}")

    token = load_env_value(env_file, "GRSAI")
    run_dir = make_run_dir(output_root, input_tif)
    print(f"run_dir={run_dir}")

    prompt_path = run_dir / "prompt.txt"
    prompt_path.write_text(args.prompt, encoding="utf-8")

    png_path = ensure_png(input_tif, run_dir)
    request_image_path = ensure_request_image(input_tif, run_dir, args.reference_format, args.jpeg_quality, args.resize_max_dim)
    data_uri = make_data_uri(request_image_path)

    request_payload = {
        "model": args.model,
        "prompt": args.prompt,
        "urls": [data_uri],
        "webHook": "-1",
        "shutProgress": True,
    }
    request_redacted = {
        "model": args.model,
        "prompt": args.prompt,
        "urls": [f"<{request_image_path.name} data-uri length={len(data_uri)}>"],
        "webHook": "-1",
        "shutProgress": True,
    }
    write_json(run_dir / "request_payload.redacted.json", request_redacted)

    submit_url = urllib.parse.urljoin(args.host.rstrip("/") + "/", "v1/draw/nano-banana")
    status_code, submit_payload = post_json(submit_url, request_payload, token, args.request_timeout)
    write_json(run_dir / "submit_response.json", {"http_status": status_code, "payload": submit_payload})
    if status_code >= 400:
        raise RuntimeError(f"Submit failed with HTTP {status_code}: {json.dumps(submit_payload, ensure_ascii=False, indent=2)}")

    code = submit_payload.get("code")
    if code not in (0, "0", None):
        raise RuntimeError(f"Submit returned non-success code: {json.dumps(submit_payload, ensure_ascii=False, indent=2)}")

    task_id = (((submit_payload.get("data") or {}).get("id")) or submit_payload.get("id"))
    if not task_id:
        raise RuntimeError(f"No task ID found in submit response: {json.dumps(submit_payload, ensure_ascii=False, indent=2)}")

    result_payload = poll_result(args.host, str(task_id), token, args.poll_interval, args.max_wait_seconds, args.request_timeout)
    write_json(run_dir / "result_response.json", result_payload)

    result_data = result_payload.get("data") or result_payload
    results = result_data.get("results") or []
    if not results:
        raise RuntimeError(f"No results field returned: {json.dumps(result_payload, ensure_ascii=False, indent=2)}")

    first = results[0]
    result_url = first.get("url")
    if not result_url:
        raise RuntimeError(f"No result URL returned: {json.dumps(result_payload, ensure_ascii=False, indent=2)}")

    parsed = urllib.parse.urlparse(result_url)
    ext = Path(parsed.path).suffix or ".png"
    mask_path = run_dir / f"generated_mask{ext}"
    download_file(result_url, mask_path)

    manifest = {
        "input_tif": str(input_tif),
        "input_png": str(png_path),
        "request_image": str(request_image_path),
        "prompt_file": str(prompt_path),
        "host": args.host,
        "model": args.model,
        "reference_format": args.reference_format,
        "jpeg_quality": args.jpeg_quality if args.reference_format == "jpeg" else None,
        "resize_max_dim": args.resize_max_dim,
        "task_id": str(task_id),
        "generated_mask": str(mask_path),
        "result_url": result_url,
        "run_dir": str(run_dir),
    }
    write_json(run_dir / "run_manifest.json", manifest)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
