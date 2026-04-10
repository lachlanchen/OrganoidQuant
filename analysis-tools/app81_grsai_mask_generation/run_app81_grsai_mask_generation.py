#!/usr/bin/env python3
"""Generate App81 organoid instance masks via GRS AI Nano Banana with resume support."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from PIL import Image


DEFAULT_HOST = "https://grsai.dakka.com.cn"
DEFAULT_MODEL = "nano-banana-fast"
PALETTE = [
    (255, 0, 0),
    (0, 220, 0),
    (0, 120, 255),
    (255, 220, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 128, 0),
    (160, 64, 255),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate App81 instance-color masks via GRS AI.")
    p.add_argument("--image", required=True, help="Path to source microscopy image")
    p.add_argument("--output-dir", required=True, help="Directory for generated outputs")
    p.add_argument("--host", default=DEFAULT_HOST, help="GRS AI API host")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Nano Banana model")
    p.add_argument("--aspect", default="auto", help="Aspect ratio")
    p.add_argument("--image-size", default="1K", help="Image size")
    p.add_argument("--max-side", type=int, default=1536, help="Resize uploaded image max side; 0 disables")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval seconds")
    p.add_argument("--poll-timeout", type=float, default=900.0, help="Polling timeout seconds")
    p.add_argument("--stalled-timeout", type=float, default=180.0, help="Polling stalled timeout seconds")
    p.add_argument("--resume", action="store_true", help="Reuse existing successful task info and outputs")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def load_grsai_key() -> str:
    api_key = os.environ.get("GRSAI", "").strip()
    if api_key:
        return api_key

    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if line.startswith("GRSAI="):
                value = line.split("=", 1)[1].strip().strip("'").strip('"')
                if value:
                    return value

    raise RuntimeError("Missing GRSAI env var and no GRSAI entry found in .env")


def image_to_data_url(path: Path) -> str:
    mime = "image/png"
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    data = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}"


def prepare_upload_image(path: Path, max_side: int) -> tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]:
    if max_side <= 0:
        return path, None

    image = Image.open(path).convert("RGB")
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return path, None

    scale = max_side / float(longest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    resized = image.resize(new_size, Image.LANCZOS)
    tmpdir = tempfile.TemporaryDirectory(prefix="app81_grsai_upload_")
    out_path = Path(tmpdir.name) / f"{path.stem}_upload.png"
    resized.save(out_path)
    return out_path, tmpdir


def request_raw(url: str, payload: Dict[str, Any], api_key: str) -> str:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        pass

    last_obj: Optional[Dict[str, Any]] = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            last_obj = obj

    if last_obj is None:
        raise RuntimeError("Failed to parse API response")
    return last_obj


def download_file(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=240) as resp:
        dest.write_bytes(resp.read())


def poll_result(
    host: str,
    task_id: str,
    api_key: str,
    interval: float,
    timeout_s: float,
    stalled_timeout_s: float,
    verbose: bool,
) -> Dict[str, Any]:
    url = host.rstrip("/") + "/v1/draw/result"
    payload = {"id": task_id}
    start = time.time()
    last_signature: Optional[tuple] = None
    last_change = start

    while True:
        raw = request_raw(url, payload, api_key)
        result = parse_json(raw)
        data = result.get("data") or {}
        status = result.get("status") or data.get("status")
        progress = result.get("progress")
        if progress is None:
            progress = data.get("progress")
        signature = (status, progress, data.get("start_time"), data.get("end_time"))
        if signature != last_signature:
            last_signature = signature
            last_change = time.time()
        if verbose:
            print(f"poll status={status} progress={progress} id={task_id}", flush=True)
        if status in {"succeeded", "failed"}:
            return result
        if time.time() - start > timeout_s:
            raise RuntimeError(f"Polling timeout after {timeout_s}s for id {task_id}")
        if time.time() - last_change > stalled_timeout_s:
            raise RuntimeError(f"Polling stalled for {stalled_timeout_s}s for id {task_id}")
        time.sleep(interval)


def build_prompt(image_name: str) -> str:
    return (
        "Task: Convert this brightfield microscopy image into a clean instance segmentation mask. "
        "Output ONLY a segmentation-style mask image, not a natural microscopy image. "
        "Background must be pure black (#000000). "
        "Every real organoid must be filled with a single solid bright color, and neighboring organoids must use different colors. "
        "Use crisp boundaries with no transparency, no gradients, no texture transfer, no shading, no highlights, and no labels. "
        "Include both small cystic organoids and large fused irregular organoids if they are true organoid tissue. "
        "Do not miss small dark-rim cysts. Do not miss large dark fused organoids. "
        "Very important: do NOT segment the outer droplet, outer circular container, well boundary, or any enclosing fluid boundary as an organoid. "
        "If there is a large droplet surrounding organoids, ignore that droplet boundary entirely and segment only the organoids inside it. "
        "Also exclude debris, speckles, blur, imaging artifacts, scratches, tiny fragments, and background haze. "
        "Do not merge separate organoids unless they are physically fused with continuous tissue in the source image. "
        "The final image should be suitable for downstream segmentation or direct quantitative mask use. "
        "Use a stable palette of saturated colors such as red, green, blue, yellow, cyan, magenta, orange, purple, but one flat color per organoid. "
        f"Source image identifier: {image_name}."
    )


def save_overlay(source_path: Path, mask_path: Path, overlay_path: Path) -> None:
    source = Image.open(source_path).convert("RGB")
    mask = Image.open(mask_path).convert("RGB")
    if mask.size != source.size:
        mask = mask.resize(source.size, Image.NEAREST)
    source_rgba = source.convert("RGBA")
    mask_rgba = mask.convert("RGBA")
    data = []
    for r, g, b, _a in mask_rgba.getdata():
        alpha = 0 if (r, g, b) == (0, 0, 0) else 140
        data.append((r, g, b, alpha))
    mask_rgba.putdata(data)
    blended = Image.alpha_composite(source_rgba, mask_rgba).convert("RGB")
    blended.save(overlay_path)


def flatten_instance_mask(raw_mask_path: Path, flat_mask_path: Path, min_area: int = 120) -> None:
    raw = np.array(Image.open(raw_mask_path).convert("RGB"))
    fg = (raw.max(axis=2) > 24).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    flat = np.zeros_like(raw)
    palette_idx = 0
    for label in range(1, num_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        mask = labels == label
        color = np.array(PALETTE[palette_idx % len(PALETTE)], dtype=np.uint8)
        flat[mask] = color
        palette_idx += 1
    Image.fromarray(flat).save(flat_mask_path)


def main() -> None:
    args = parse_args()
    api_key = load_grsai_key()

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = output_dir / "prompt.txt"
    manifest_path = output_dir / "task_manifest.json"
    mask_path = output_dir / "generated_instance_mask.png"
    flat_mask_path = output_dir / "generated_instance_mask_flat.png"
    overlay_path = output_dir / "generated_overlay.png"
    flat_overlay_path = output_dir / "generated_overlay_flat.png"
    raw_response_path = log_dir / "submit_response.raw.txt"
    poll_response_path = log_dir / "poll_response.json"

    prompt = build_prompt(image_path.name)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    if args.resume and manifest_path.exists() and mask_path.exists() and flat_mask_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "succeeded":
            print(f"Reusing existing result: {flat_mask_path}")
            return

    upload_image_path, tmpdir = prepare_upload_image(image_path, args.max_side)
    try:
        payload: Dict[str, Any] = {
            "model": args.model,
            "urls": [image_to_data_url(upload_image_path)],
            "prompt": prompt,
            "aspectRatio": args.aspect,
            "webHook": "-1",
            "shutProgress": True,
        }
        if args.image_size:
            payload["imageSize"] = args.image_size

        task_id: Optional[str] = None
        manifest: Dict[str, Any] = {}
        if args.resume and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            task_id = manifest.get("task_id")

        if not task_id:
            if args.verbose:
                print(f"Submitting image {upload_image_path.name} ({upload_image_path.stat().st_size} bytes)", flush=True)
            url = args.host.rstrip("/") + "/v1/draw/nano-banana"
            raw = request_raw(url, payload, api_key)
            raw_response_path.write_text(raw, encoding="utf-8")
            result = parse_json(raw)
            task_id = result.get("id") or (result.get("data") or {}).get("id")
            if not task_id:
                raise RuntimeError(f"Missing task id in response: {result}")
            manifest = {
                "image_path": str(image_path),
                "upload_image_path": str(upload_image_path),
                "output_dir": str(output_dir),
                "task_id": task_id,
                "status": "submitted",
                "model": args.model,
                "host": args.host,
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.verbose:
                print(f"Submitted task {task_id}", flush=True)
        else:
            if args.verbose:
                print(f"Resuming task {task_id}", flush=True)

        final = poll_result(
            args.host,
            task_id,
            api_key,
            args.poll_interval,
            args.poll_timeout,
            args.stalled_timeout,
            args.verbose,
        )
        poll_response_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

        results = final.get("results") or (final.get("data") or {}).get("results") or []
        if not results or not results[0].get("url"):
            manifest["status"] = "failed"
            manifest["final_response_path"] = str(poll_response_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            raise RuntimeError(f"No result URL in final response: {final}")

        download_file(results[0]["url"], mask_path)
        flatten_instance_mask(mask_path, flat_mask_path)
        save_overlay(image_path, mask_path, overlay_path)
        save_overlay(image_path, flat_mask_path, flat_overlay_path)

        manifest["status"] = "succeeded"
        manifest["result_url"] = results[0]["url"]
        manifest["mask_path"] = str(mask_path)
        manifest["flat_mask_path"] = str(flat_mask_path)
        manifest["overlay_path"] = str(overlay_path)
        manifest["flat_overlay_path"] = str(flat_overlay_path)
        manifest["final_response_path"] = str(poll_response_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"Saved mask: {mask_path}")
        print(f"Saved flat mask: {flat_mask_path}")
        print(f"Saved overlay: {overlay_path}")
        print(f"Saved flat overlay: {flat_overlay_path}")
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


if __name__ == "__main__":
    main()
