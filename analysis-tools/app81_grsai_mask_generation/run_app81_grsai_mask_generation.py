#!/usr/bin/env python3
"""Generate App81 organoid instance masks via GRS AI Nano Banana with resume support."""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from PIL import Image


DEFAULT_HOST = "https://grsaiapi.com"
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

TRANSIENT_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate App81 instance-color masks via GRS AI.")
    p.add_argument("--image", required=True, help="Path to source microscopy image")
    p.add_argument("--output-dir", required=True, help="Directory for generated outputs")
    p.add_argument("--host", default=DEFAULT_HOST, help="GRS AI API host")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Nano Banana model")
    p.add_argument("--aspect", default="auto", help="Aspect ratio")
    p.add_argument("--image-size", default="1K", help="Image size")
    p.add_argument("--max-side", type=int, default=1024, help="Resize uploaded image max side; 0 disables")
    p.add_argument("--request-timeout", type=float, default=300.0, help="HTTP request timeout seconds")
    p.add_argument("--submit-retries", type=int, default=2, help="Retries for initial submit")
    p.add_argument("--job-retries", type=int, default=2, help="Fresh task resubmissions when the remote job fails")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval seconds")
    p.add_argument("--poll-timeout", type=float, default=900.0, help="Polling timeout seconds")
    p.add_argument("--stalled-timeout", type=float, default=180.0, help="Polling stalled timeout seconds")
    p.add_argument("--resume", action="store_true", help="Reuse existing successful task info and outputs")
    p.add_argument("--prompt-overrides-json", default="", help="Optional JSON file mapping image names to extra prompt guidance")
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


def request_raw(
    url: str,
    payload: Dict[str, Any],
    api_key: str,
    timeout_s: float = 120.0,
    retries: int = 0,
    verbose: bool = False,
    context: str = "request",
) -> str:
    body = json.dumps(payload).encode("utf-8")
    last_err: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code not in TRANSIENT_HTTP_CODES or attempt >= retries:
                raise
            if verbose:
                print(f"{context} transient HTTP {exc.code}; retry {attempt+1}/{retries}", flush=True)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_err = exc
            if attempt >= retries:
                raise
            if verbose:
                print(f"{context} transient {type(exc).__name__}; retry {attempt+1}/{retries}", flush=True)
        time.sleep(2.0 + attempt * 2.0)
    raise RuntimeError(f"{context} failed after retries: {last_err}")


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
        raw = request_raw(url, payload, api_key, timeout_s=timeout_s, retries=4, verbose=verbose, context="poll")
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


def analyze_prompt_guidance(image_path: Path) -> Dict[str, Any]:
    rgb = np.array(Image.open(image_path).convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    mean = cv2.GaussianBlur(gray, (0, 0), 21)
    sq_mean = cv2.GaussianBlur(gray * gray, (0, 0), 21)
    std = np.sqrt(np.maximum(sq_mean - mean * mean, 0.0))

    bright_thr = float(np.quantile(gray, 0.45))
    std_thr = float(np.quantile(std, 0.35))
    smooth = np.logical_and(gray > bright_thr, std < std_thr).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    smooth = cv2.morphologyEx(smooth, cv2.MORPH_CLOSE, kernel, iterations=1)
    smooth = cv2.morphologyEx(smooth, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)), iterations=1)
    smooth = cv2.dilate(smooth, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)), iterations=1)
    smooth = cv2.erode(smooth, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)), iterations=1)
    smooth = smooth.astype(bool)

    h, w = gray.shape
    total = float(h * w)
    num, cc, stats, _ = cv2.connectedComponentsWithStats(smooth.astype(np.uint8), connectivity=8)
    big_regions = []
    for lid in range(1, num):
        area = int(stats[lid, cv2.CC_STAT_AREA])
        frac = area / total
        if frac < 0.08:
            continue
        x = int(stats[lid, cv2.CC_STAT_LEFT])
        y = int(stats[lid, cv2.CC_STAT_TOP])
        ww = int(stats[lid, cv2.CC_STAT_WIDTH])
        hh = int(stats[lid, cv2.CC_STAT_HEIGHT])
        border = x <= 8 or y <= 8 or (x + ww) >= (w - 8) or (y + hh) >= (h - 8)
        big_regions.append(
            {
                "area_fraction": round(frac, 6),
                "bbox": [x, y, ww, hh],
                "touches_border": border,
            }
        )

    has_large_smooth_region = bool(big_regions)
    touches_border = any(r["touches_border"] for r in big_regions)
    has_multiple_regions = len(big_regions) >= 2
    return {
        "image_shape": [int(h), int(w)],
        "gray_bright_threshold": round(bright_thr, 6),
        "gray_std_threshold": round(std_thr, 6),
        "has_large_smooth_region": has_large_smooth_region,
        "touches_border": touches_border,
        "has_multiple_large_smooth_regions": has_multiple_regions,
        "large_smooth_regions": big_regions,
    }


def load_prompt_override(image_name: str, override_path: str) -> str:
    if not override_path:
        return ""
    path = Path(override_path)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    value = data.get(image_name, "")
    return value if isinstance(value, str) else ""


def build_prompt(image_name: str, guidance: Dict[str, Any] | None = None, extra_prompt: str = "") -> str:
    guidance = guidance or {}
    extra = []
    if guidance.get("has_large_smooth_region"):
        extra.append(
            "This image contains one or more large pale smooth translucent droplet regions. "
            "These are not organoids. Leave every such large smooth pale droplet interior completely black."
        )
    if guidance.get("touches_border"):
        extra.append(
            "Ignore any large circular or elliptical boundary touching the image border; border-touching droplet arcs are not organoids."
        )
    if guidance.get("has_multiple_large_smooth_regions"):
        extra.append("There may be several partial droplets at the image edges; do not segment them.")
    if extra_prompt:
        extra.append(extra_prompt.strip())
    extra_text = " ".join(extra)
    return (
        "Generate only a clean organoid instance mask for this brightfield microscopy image. "
        "Use pure black background (#000000) everywhere outside organoids. "
        "Each true organoid must be one smooth filled solid region with one bright flat color. "
        "Use different colors for neighboring organoids when possible. "
        "Include both small organoids and large fused irregular organoids if they are real organoid tissue. "
        "Real organoids are darker denser compact tissue bodies or dark-rim cystic structures, not large pale smooth translucent regions. "
        "If a very large object occupies much of the image, only segment it when it is visibly dark, dense, and non-transparent like real tissue. "
        "If a very large circular or elliptical region is pale, smooth, almost transparent, or looks like a droplet interior, do not segment it at all. "
        "Match the visible organoid body accurately and compactly; do not over-expand into surrounding droplet or background, and do not under-fill the real organoid body. "
        "Do not segment the outer droplet, outer circular container, surrounding fluid boundary, well boundary, debris, speckles, halos, scratches, or thin edge fragments. "
        "Ignore tiny isolated dots unless they are clearly real compact dark organoids. "
        "Ignore partially clipped edge objects unless most of a real dark organoid body is visible. "
        "Do not draw outlines, rings, texture, shading, gradients, labels, arrows, or text. "
        "Do not create stray islands, narrow colored tails, or tiny background fragments. "
        "Keep separate organoids separate with black gaps unless they are visibly fused into one continuous tissue mass. "
        "Output only the colored mask image, suitable for downstream instance processing. "
        "Preferred colors are bright flat red, green, blue, yellow, cyan, magenta, orange, and purple. "
        f"{extra_text} "
        f"Source image identifier: {image_name}."
    )


def should_resubmit_failed_result(final: Dict[str, Any]) -> bool:
    data = final.get("data") or {}
    status = final.get("status") or data.get("status")
    if status != "failed":
        return False
    failure_reason = (final.get("failure_reason") or data.get("failure_reason") or "").strip().lower()
    error_text = (final.get("error") or data.get("error") or "").strip().lower()
    if "timeout" in error_text:
        return True
    if failure_reason == "error":
        return True
    return False


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


def source_feature_maps(source_rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    mean = cv2.GaussianBlur(gray, (0, 0), 11)
    sq_mean = cv2.GaussianBlur(gray * gray, (0, 0), 11)
    local_std = np.sqrt(np.maximum(sq_mean - mean * mean, 0.0))
    dark = 1.0 - gray
    return dark, local_std, grad


def clean_generated_mask_in_place(mask_path: Path, source_path: Path, min_area: int = 120) -> dict[str, Any]:
    raw = np.array(Image.open(mask_path).convert("RGB"))
    source_rgb = np.array(Image.open(source_path).convert("RGB"))
    if source_rgb.shape[:2] != raw.shape[:2]:
        source_rgb = cv2.resize(source_rgb, (raw.shape[1], raw.shape[0]), interpolation=cv2.INTER_LINEAR)
    hsv = cv2.cvtColor(raw, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    fg = np.logical_and(val > 32, sat > 60).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    keep = np.zeros(fg.shape, dtype=np.uint8)
    dark, local_std, grad = source_feature_maps(source_rgb)
    total = float(fg.shape[0] * fg.shape[1])
    grad_thr = float(np.quantile(grad, 0.55))
    std_thr = float(np.quantile(local_std, 0.45))
    dropped_components: list[dict[str, Any]] = []
    kept_component_count = 0
    for label in range(1, num):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        mask = labels == label
        frac = area / total
        ys, xs = np.where(mask)
        border_touch = bool((ys == 0).any() or (ys == fg.shape[0] - 1).any() or (xs == 0).any() or (xs == fg.shape[1] - 1).any())
        dark_mean = float(dark[mask].mean())
        std_mean = float(local_std[mask].mean())
        boundary = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
        boundary_grad = float(grad[boundary].mean()) if boundary.any() else 0.0
        frac = area / total
        pale_blob_like = (
            (area < 2500 and dark_mean < 0.55 and std_mean < 0.02 and boundary_grad < 0.06)
            or (border_touch and area < 2600 and std_mean < 0.02 and boundary_grad < 0.06)
            or (frac < 0.003 and dark_mean < 0.55 and std_mean < 0.02 and boundary_grad < 0.04)
            or (border_touch and frac < 0.004 and std_mean < 0.015 and boundary_grad < 0.035)
        )
        small_fragment_like = (
            (area < 180 and (dark_mean < 0.56 or std_mean < max(std_thr, 0.04)))
            or (area < 240 and dark_mean < 0.52 and boundary_grad < max(grad_thr, 0.14))
            or (border_touch and area < 500 and dark_mean < 0.60 and boundary_grad < 0.18)
            or (frac < 0.00025 and dark_mean < 0.54 and (std_mean < 0.06 or boundary_grad < 0.11))
        )
        droplet_like = (
            (frac > 0.10 and dark_mean < 0.34 and std_mean < std_thr and boundary_grad < grad_thr)
            or (frac > 0.22 and dark_mean < 0.40 and std_mean < max(std_thr, 0.045))
            or (border_touch and frac > 0.08 and dark_mean < 0.34 and std_mean < std_thr)
        )
        if droplet_like or small_fragment_like or pale_blob_like:
            dropped_components.append(
                {
                    "label": int(label),
                    "area_fraction": round(frac, 6),
                    "area_px": area,
                    "touches_border": border_touch,
                    "mean_darkness": round(dark_mean, 6),
                    "mean_local_std": round(std_mean, 6),
                    "mean_boundary_grad": round(boundary_grad, 6),
                    "reason": "droplet_like" if droplet_like else ("pale_blob_like" if pale_blob_like else "small_fragment_like"),
                }
            )
            continue
        keep[mask] = 1
        kept_component_count += 1

    cleaned = np.zeros_like(raw)
    cleaned[keep > 0] = raw[keep > 0]
    Image.fromarray(cleaned).save(mask_path)
    return {
        "kept_component_count": kept_component_count,
        "dropped_component_count": len(dropped_components),
        "dropped_components": dropped_components,
        "grad_threshold": round(grad_thr, 6),
        "std_threshold": round(std_thr, 6),
    }


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
    guidance_path = output_dir / "prompt_guidance.json"
    clean_report_path = output_dir / "mask_cleanup_report.json"
    manifest_path = output_dir / "task_manifest.json"
    mask_path = output_dir / "generated_instance_mask.png"
    flat_mask_path = output_dir / "generated_instance_mask_flat.png"
    overlay_path = output_dir / "generated_overlay.png"
    flat_overlay_path = output_dir / "generated_overlay_flat.png"
    raw_response_path = log_dir / "submit_response.raw.txt"
    poll_response_path = log_dir / "poll_response.json"

    guidance = analyze_prompt_guidance(image_path)
    extra_prompt = load_prompt_override(image_path.name, args.prompt_overrides_json)
    if extra_prompt:
        guidance["manual_prompt_override"] = extra_prompt
    guidance_path.write_text(json.dumps(guidance, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt = build_prompt(image_path.name, guidance, extra_prompt=extra_prompt)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    existing_manifest: Dict[str, Any] = {}
    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.resume and existing_manifest and mask_path.exists() and flat_mask_path.exists():
        if existing_manifest.get("status") == "succeeded":
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

        manifest: Dict[str, Any] = dict(existing_manifest) if existing_manifest else {}
        task_id: Optional[str] = None
        if args.resume and manifest:
            if manifest.get("status") in {"submitted", "running"}:
                task_id = manifest.get("task_id")

        final: Optional[Dict[str, Any]] = None
        for job_attempt in range(args.job_retries + 1):
            if not task_id:
                if args.verbose:
                    print(
                        f"Submitting image {upload_image_path.name} ({upload_image_path.stat().st_size} bytes) "
                        f"[job attempt {job_attempt+1}/{args.job_retries+1}]",
                        flush=True,
                    )
                url = args.host.rstrip("/") + "/v1/draw/nano-banana"
                result: Optional[Dict[str, Any]] = None
                last_err: Optional[Exception] = None
                for attempt in range(args.submit_retries + 1):
                    try:
                        raw = request_raw(
                            url,
                            payload,
                            api_key,
                            timeout_s=args.request_timeout,
                            retries=2,
                            verbose=args.verbose,
                            context="submit",
                        )
                        raw_response_path.write_text(raw, encoding="utf-8")
                        result = parse_json(raw)
                        break
                    except Exception as exc:
                        last_err = exc
                        if args.verbose:
                            print(f"submit attempt {attempt+1} failed: {type(exc).__name__}: {exc}", flush=True)
                        time.sleep(2.0 + attempt * 2.0)
                if result is None:
                    raise RuntimeError(f"Submission failed after retries: {last_err}")
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
                    "prompt_guidance_path": str(guidance_path),
                    "job_attempt": job_attempt + 1,
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
            if results and results[0].get("url"):
                break

            manifest["status"] = "failed"
            manifest["final_response_path"] = str(poll_response_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            if job_attempt < args.job_retries and should_resubmit_failed_result(final):
                if args.verbose:
                    print(
                        f"Remote job {task_id} failed without result URL; resubmitting fresh task "
                        f"({job_attempt+2}/{args.job_retries+1})",
                        flush=True,
                    )
                task_id = None
                continue
            raise RuntimeError(f"No result URL in final response: {final}")

        assert final is not None
        results = final.get("results") or (final.get("data") or {}).get("results") or []

        download_file(results[0]["url"], mask_path)
        cleanup_report = clean_generated_mask_in_place(mask_path, image_path)
        clean_report_path.write_text(json.dumps(cleanup_report, ensure_ascii=False, indent=2), encoding="utf-8")
        flatten_instance_mask(mask_path, flat_mask_path)
        save_overlay(image_path, mask_path, overlay_path)
        save_overlay(image_path, flat_mask_path, flat_overlay_path)

        manifest["status"] = "succeeded"
        manifest["result_url"] = results[0]["url"]
        manifest["mask_path"] = str(mask_path)
        manifest["flat_mask_path"] = str(flat_mask_path)
        manifest["overlay_path"] = str(overlay_path)
        manifest["flat_overlay_path"] = str(flat_overlay_path)
        manifest["mask_cleanup_report_path"] = str(clean_report_path)
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
