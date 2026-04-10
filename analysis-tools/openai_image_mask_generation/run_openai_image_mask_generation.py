#!/usr/bin/env python3
"""Generate an organoid mask from a microscopy image using OpenAI Images Edit API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


DEFAULT_HOST = "https://api.openai.com"
DEFAULT_MODELS = ["gpt-image-1.5", "gpt-image-1"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run OpenAI image edit for organoid mask generation.")
    p.add_argument("--image", required=True, help="Source image path (png/jpg/webp)")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--host", default=DEFAULT_HOST, help="OpenAI API host")
    p.add_argument("--size", default="auto", help="Output size")
    p.add_argument("--quality", default="high", help="Output quality")
    p.add_argument("--background", default="opaque", help="Background option")
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="Models to try in order")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def load_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if line.startswith("OPENAI_API_KEY="):
                value = line.split("=", 1)[1].strip().strip("'").strip('"')
                if value:
                    return value
    raise RuntimeError("Missing OPENAI_API_KEY")


def build_prompt(image_name: str) -> str:
    return (
        "Edit this brightfield microscopy image into only an instance segmentation mask. "
        "Use pure black background everywhere outside organoids. "
        "Segment only true organoids. "
        "Each organoid must be one smooth solid filled flat-colored region with clean boundaries. "
        "Use different bright colors for separate neighboring organoids when possible. "
        "Include both compact dense organoids and cystic organoids with a dark continuous wall and lighter interior, treating each such cystic structure as one organoid. "
        "Do not omit a real cystic organoid just because its center is lighter than its wall. "
        "Exclude large pale smooth transparent droplet interiors, hollow droplet rings, outer circular container boundaries, border arcs, fluid boundaries, halos, speckles, scratches, debris, and tiny fragments. "
        "If a large circular or elliptical structure is mostly pale or transparent, leave it black. "
        "If a ring-like boundary surrounds a pale empty interior, leave both the boundary and the interior black unless the enclosed region is clearly filled with dark dense tissue. "
        "Keep separate organoids separate with black gaps unless they are visibly fused into one real continuous tissue mass. "
        "Output only the colored mask image and nothing else. "
        f"Source image identifier: {image_name}."
    )


def save_overlay(source_path: Path, mask_path: Path, overlay_path: Path) -> None:
    source = Image.open(source_path).convert("RGB")
    mask = Image.open(mask_path).convert("RGB")
    if mask.size != source.size:
        mask = mask.resize(source.size, Image.NEAREST)
    source_rgba = source.convert("RGBA")
    mask_rgba = mask.convert("RGBA")
    alpha_data = []
    for r, g, b, _a in mask_rgba.getdata():
        alpha = 0 if (r, g, b) == (0, 0, 0) else 140
        alpha_data.append((r, g, b, alpha))
    mask_rgba.putdata(alpha_data)
    blended = Image.alpha_composite(source_rgba, mask_rgba).convert("RGB")
    blended.save(overlay_path)


def solid_fill_mask(mask_rgb: np.ndarray, min_area: int = 120) -> np.ndarray:
    fg = (mask_rgb.max(axis=2) > 24).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    out = np.zeros_like(mask_rgb)
    for lid in range(1, num):
        area = int(stats[lid, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        comp = (labels == lid).astype(np.uint8)
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        filled = np.zeros_like(comp)
        cv2.drawContours(filled, contours, -1, 1, thickness=-1)
        pixels = mask_rgb[comp > 0]
        nonblack = pixels[np.max(pixels, axis=1) > 24]
        work = nonblack if nonblack.size else pixels
        unique, counts = np.unique(work, axis=0, return_counts=True)
        color = unique[int(np.argmax(counts))].astype(np.uint8)
        out[filled > 0] = color
    return out


def run_model(host: str, api_key: str, model: str, image_path: Path, prompt: str, size: str, quality: str, background: str) -> tuple[int, str]:
    cmd = [
        "curl",
        "-sS",
        "-X",
        "POST",
        f"{host.rstrip('/')}/v1/images/edits",
        "-H",
        f"Authorization: Bearer {api_key}",
        "-F",
        f"model={model}",
        "-F",
        f"prompt={prompt}",
        "-F",
        f"size={size}",
        "-F",
        f"quality={quality}",
        "-F",
        f"background={background}",
        "-F",
        "output_format=png",
        "-F",
        f"image=@{str(image_path)};type=image/png",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout if proc.stdout else proc.stderr


def main() -> None:
    args = parse_args()
    api_key = load_openai_key()

    image_path = Path(args.image)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = output_dir / "prompt.txt"
    response_path = output_dir / "response.json"
    solid_mask_path = output_dir / "generated_instance_mask.png"
    raw_mask_path = output_dir / "generated_instance_mask_raw.png"
    overlay_path = output_dir / "generated_overlay.png"
    meta_path = output_dir / "run_manifest.json"

    prompt = build_prompt(image_path.name)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    last_error = None
    used_model = None
    parsed = None
    for model in args.models:
        if args.verbose:
            print(f"Trying model {model}", flush=True)
        code, raw = run_model(args.host, api_key, model, image_path, prompt, args.size, args.quality, args.background)
        response_path.write_text(raw, encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if code == 0 and isinstance(parsed, dict) and "data" in parsed and parsed["data"]:
            used_model = model
            break
        last_error = raw
    if used_model is None or parsed is None:
        raise RuntimeError(f"OpenAI image edit failed: {last_error}")

    item = parsed["data"][0]
    b64 = item.get("b64_json")
    if not b64:
        raise RuntimeError(f"No b64_json returned: {json.dumps(parsed, ensure_ascii=False)[:1000]}")

    raw_bytes = base64.b64decode(b64)
    raw_mask_path.write_bytes(raw_bytes)

    raw_mask = np.array(Image.open(raw_mask_path).convert("RGB"))
    solid_mask = solid_fill_mask(raw_mask)
    Image.fromarray(solid_mask).save(solid_mask_path)
    save_overlay(image_path, solid_mask_path, overlay_path)

    meta = {
        "source_path": str(image_path),
        "host": args.host,
        "used_model": used_model,
        "size": args.size,
        "quality": args.quality,
        "background": args.background,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"used_model": used_model, "mask": str(solid_mask_path), "overlay": str(overlay_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
