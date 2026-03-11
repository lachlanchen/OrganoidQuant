#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
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
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


VISUAL_NOTES = [
    "There is one circular droplet centered in the frame.",
    "A dominant irregular fused dark organoid mass occupies the upper-central region.",
    "A second elongated fused organoid mass occupies the lower-central region.",
    "Several medium round organoids cluster along the right arc of the droplet.",
    "Many small round organoids are scattered in the left and lower regions inside the droplet.",
    "Do not over-segment tiny background speckles or halo artifacts as organoids.",
    "Preserve overlap and fusion in the dense central regions instead of flattening them into one blob.",
]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_input = repo_root / "DEO/App80 DEO/10uM/05-十二月-2025/10x00.tif"
    default_env = repo_root / ".env"
    default_output = repo_root / "api-tests/grsai_nano_banana_mask_with_prior_test/output"
    default_coarse = repo_root / "api-tests/grsai_nano_banana_mask_test/output/05-十二月-2025_10x00_20260311_212149/generated_mask.png"
    p = argparse.ArgumentParser(description="Prior-assisted GRSAI mask refinement test for organoid overlap segmentation.")
    p.add_argument("--input-tif", default=str(default_input))
    p.add_argument("--coarse-mask", default=str(default_coarse))
    p.add_argument("--env-file", default=str(default_env))
    p.add_argument("--output-root", default=str(default_output))
    p.add_argument("--host", default="https://grsaiapi.com")
    p.add_argument("--model", default="nano-banana-pro")
    p.add_argument("--jpeg-quality", type=int, default=88)
    p.add_argument("--resize-max-dim", type=int, default=1024)
    p.add_argument("--request-timeout", type=float, default=600.0)
    p.add_argument("--poll-interval", type=float, default=10.0)
    p.add_argument("--max-wait-seconds", type=float, default=1800.0)
    return p.parse_args()


def load_env_value(env_path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        return value
    raise KeyError(f"{key} not found in {env_path}")


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_run_dir(output_root: Path, input_tif: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_parent = input_tif.parent.name.replace("/", "_")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", input_tif.stem)
    out = output_root / f"{safe_parent}_{safe_name}_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    return out


def resize_keep_aspect(im: Image.Image, max_dim: int) -> Image.Image:
    if max(im.size) <= max_dim:
        return im.copy()
    scale = max_dim / float(max(im.size))
    new_size = (max(1, int(im.size[0] * scale)), max(1, int(im.size[1] * scale)))
    return im.resize(new_size, Image.Resampling.LANCZOS)


def save_source_and_request_images(src_tif: Path, out_dir: Path, resize_max_dim: int, jpeg_quality: int) -> Tuple[Path, Path]:
    with Image.open(src_tif) as im:
        source_png = out_dir / f"{src_tif.stem}.png"
        im.save(source_png, format="PNG")

        req = resize_keep_aspect(im.convert("RGB"), resize_max_dim)
        request_jpg = out_dir / f"{src_tif.stem}_request.jpg"
        req.save(request_jpg, format="JPEG", quality=jpeg_quality, optimize=True)
    return source_png, request_jpg


def load_rgb_np(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def detect_droplet(gray: np.ndarray) -> Tuple[int, int, int]:
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min(gray.shape[:2]) // 2,
        param1=80,
        param2=30,
        minRadius=min(gray.shape[:2]) // 5,
        maxRadius=min(gray.shape[:2]) // 2,
    )
    h, w = gray.shape[:2]
    if circles is not None:
        circles = np.round(circles[0]).astype(int)
        cx0, cy0 = w / 2.0, h / 2.0
        best = min(circles, key=lambda c: (c[0] - cx0) ** 2 + (c[1] - cy0) ** 2)
        return int(best[0]), int(best[1]), int(best[2])
    return w // 2, h // 2, int(min(h, w) * 0.38)


def circle_mask(shape: Tuple[int, int], cx: int, cy: int, r: int) -> np.ndarray:
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return ((xx - cx) ** 2 + (yy - cy) ** 2) <= r ** 2


def find_large_regions(gray: np.ndarray, droplet_mask: np.ndarray) -> List[Dict[str, Any]]:
    inside = gray[droplet_mask]
    thr = np.percentile(inside, 36)
    dark = np.zeros_like(gray, dtype=np.uint8)
    dark[(gray < thr) & droplet_mask] = 255
    kernel = np.ones((7, 7), np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: List[Dict[str, Any]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 2200:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        regions.append(
            {
                "kind": "large_region",
                "area": float(area),
                "bbox": [int(x), int(y), int(w), int(h)],
                "contour": cnt.squeeze(1).tolist(),
            }
        )
    regions.sort(key=lambda r: r["area"], reverse=True)
    return regions[:8]


def find_small_candidates(gray: np.ndarray, droplet_mask: np.ndarray, large_regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    adaptive = cv2.adaptiveThreshold(255 - blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, -5)
    adaptive = cv2.bitwise_and(adaptive, adaptive, mask=droplet_mask.astype(np.uint8) * 255)
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(adaptive, connectivity=8)

    large_boxes = [tuple(r["bbox"]) for r in large_regions]
    candidates: List[Dict[str, Any]] = []
    for i in range(1, num_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 40 or area > 1800:
            continue
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        cx, cy = centroids[i]
        radius = int(max(w, h) / 2)
        if radius < 4 or radius > 38:
            continue
        if any((bx <= cx <= bx + bw and by <= cy <= by + bh) for bx, by, bw, bh in large_boxes):
            continue
        aspect = w / float(h) if h else 99
        if aspect < 0.35 or aspect > 2.8:
            continue
        candidates.append(
            {
                "kind": "small_candidate",
                "area": area,
                "center": [float(cx), float(cy)],
                "radius": radius,
                "bbox": [x, y, w, h],
            }
        )
    candidates.sort(key=lambda c: (c["radius"], c["area"]), reverse=True)
    deduped: List[Dict[str, Any]] = []
    for cand in candidates:
        cx, cy = cand["center"]
        keep = True
        for prev in deduped:
            px, py = prev["center"]
            if (cx - px) ** 2 + (cy - py) ** 2 < (0.65 * max(cand["radius"], prev["radius"])) ** 2:
                keep = False
                break
        if keep:
            deduped.append(cand)
        if len(deduped) >= 28:
            break
    return deduped


def render_prior_overlay(request_image: Path, out_path: Path) -> Dict[str, Any]:
    rgb = load_rgb_np(request_image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cx, cy, r = detect_droplet(gray)
    droplet = circle_mask(gray.shape, cx, cy, r)
    large_regions = find_large_regions(gray, droplet)
    small_candidates = find_small_candidates(gray, droplet, large_regions)

    base = rgb.copy()
    base = (0.7 * base + 15).clip(0, 255).astype(np.uint8)
    overlay = base.copy()

    large_colors = [
        (255, 80, 80),
        (255, 160, 80),
        (255, 210, 90),
        (255, 120, 180),
        (220, 120, 255),
        (255, 100, 120),
    ]
    small_colors = [
        (80, 220, 255),
        (120, 255, 160),
        (120, 180, 255),
        (180, 255, 120),
        (150, 220, 255),
        (180, 200, 255),
    ]

    for i, region in enumerate(large_regions):
        color = large_colors[i % len(large_colors)]
        cnt = np.array(region["contour"], dtype=np.int32).reshape((-1, 1, 2))
        fill = overlay.copy()
        cv2.drawContours(fill, [cnt], -1, color, thickness=cv2.FILLED)
        overlay = cv2.addWeighted(fill, 0.22, overlay, 0.78, 0)
        cv2.drawContours(overlay, [cnt], -1, color, thickness=3)

    for i, cand in enumerate(small_candidates):
        color = small_colors[i % len(small_colors)]
        cx_i, cy_i = [int(round(v)) for v in cand["center"]]
        rad = int(cand["radius"])
        cv2.circle(overlay, (cx_i, cy_i), rad, color, 2)
        cv2.circle(overlay, (cx_i, cy_i), max(2, rad // 4), color, -1)

    cv2.circle(overlay, (cx, cy), r, (240, 240, 240), 2)
    cv2.putText(overlay, "droplet boundary", (max(10, cx - r // 2), max(30, cy - r - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 2, cv2.LINE_AA)

    Image.fromarray(overlay).save(out_path)
    return {
        "droplet_circle": {"center_x": cx, "center_y": cy, "radius": r},
        "large_regions": large_regions,
        "small_candidates": small_candidates,
        "visual_notes": VISUAL_NOTES,
    }


def make_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def build_prompt(prior: Dict[str, Any]) -> str:
    n_large = len(prior["large_regions"])
    n_small = len(prior["small_candidates"])
    notes = "\n".join(f"- {note}" for note in prior["visual_notes"])
    return f"""You are given three reference images of the same specimen.

Reference image 1: the original microscopy image.
Reference image 2: a prior guidance overlay created from local inspection. Warm colored irregular regions indicate likely fused organoid masses. Cool colored circles indicate likely medium/small organoid candidates. The white circle shows the droplet boundary.
Reference image 3: a coarse segmentation mask from an earlier run. Treat it only as an initial guess. Correct it using references 1 and 2.

Observed scene summary:
- Approximate large fused regions highlighted: {n_large}
- Approximate medium/small organoid candidates highlighted: {n_small}
{notes}

Task:
Generate an improved RGB instance segmentation mask for all real organoids in the droplet.

Rules:
- Output only the segmentation mask on a black background.
- Preserve overlap identity using additive RGB composition in overlap regions.
- Do not merge overlapping organoids into one object.
- Correctly separate touching and partially fused organoids where real morphological boundaries exist.
- Keep fused areas explicit and readable.
- Respect the candidate positions and coarse organoid extents shown in the prior overlay unless the source image clearly contradicts them.
- Use the coarse mask only as a rough starting point; remove its mistakes.
- Ignore background speckles, halos, and tiny debris that are not real organoids.
- Stay inside the droplet.
- Preserve true shape, size, and topology as much as possible.
- Do not hallucinate additional organoids.
- Do not remove real organoids.

Return only the final RGB segmentation mask image."""


def post_json(url: str, payload: Dict[str, Any], token: str, timeout: float) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
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


def download_file(url: str, out_path: Path) -> None:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "OrganoidQuant/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as resp, out_path.open("wb") as f:
        shutil.copyfileobj(resp, f)


def main() -> int:
    args = parse_args()
    input_tif = Path(args.input_tif).resolve()
    coarse_mask = Path(args.coarse_mask).resolve()
    env_file = Path(args.env_file).resolve()
    out_root = Path(args.output_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    token = load_env_value(env_file, "GRSAI")
    run_dir = make_run_dir(out_root, input_tif)
    print(f"run_dir={run_dir}")

    source_png, request_jpg = save_source_and_request_images(input_tif, run_dir, args.resize_max_dim, args.jpeg_quality)
    resized_coarse = run_dir / "coarse_mask_reference.png"
    with Image.open(coarse_mask) as im:
        resize_keep_aspect(im.convert("RGBA"), args.resize_max_dim).save(resized_coarse, format="PNG")

    prior_overlay = run_dir / "prior_overlay.png"
    prior = render_prior_overlay(request_jpg, prior_overlay)
    write_json(run_dir / "prior_summary.json", prior)

    prompt = build_prompt(prior)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    payload = {
        "model": args.model,
        "prompt": prompt,
        "urls": [
            make_data_uri(request_jpg),
            make_data_uri(prior_overlay),
            make_data_uri(resized_coarse),
        ],
        "webHook": "-1",
        "shutProgress": True,
    }
    write_json(
        run_dir / "request_payload.redacted.json",
        {
            "model": args.model,
            "prompt_preview": prompt[:500] + "...",
            "urls": [
                f"<{request_jpg.name}>",
                f"<{prior_overlay.name}>",
                f"<{resized_coarse.name}>",
            ],
            "webHook": "-1",
            "shutProgress": True,
        },
    )

    submit_url = urllib.parse.urljoin(args.host.rstrip("/") + "/", "v1/draw/nano-banana")
    http_status, submit_payload = post_json(submit_url, payload, token, args.request_timeout)
    write_json(run_dir / "submit_response.json", {"http_status": http_status, "payload": submit_payload})
    if http_status >= 400:
        raise RuntimeError(json.dumps(submit_payload, ensure_ascii=False, indent=2))

    task_id = (((submit_payload.get("data") or {}).get("id")) or submit_payload.get("id"))
    if not task_id:
        raise RuntimeError(f"No task id returned: {json.dumps(submit_payload, ensure_ascii=False, indent=2)}")

    result_payload = poll_result(args.host, str(task_id), token, args.poll_interval, args.max_wait_seconds, args.request_timeout)
    write_json(run_dir / "result_response.json", result_payload)

    result_data = result_payload.get("data") or result_payload
    first = (result_data.get("results") or [None])[0]
    if not first or not first.get("url"):
        raise RuntimeError(f"No result URL found: {json.dumps(result_payload, ensure_ascii=False, indent=2)}")

    result_url = first["url"]
    ext = Path(urllib.parse.urlparse(result_url).path).suffix or ".png"
    generated = run_dir / f"generated_mask_refined{ext}"
    download_file(result_url, generated)

    manifest = {
        "input_tif": str(input_tif),
        "source_png": str(source_png),
        "request_image": str(request_jpg),
        "prior_overlay": str(prior_overlay),
        "prior_summary": str(run_dir / "prior_summary.json"),
        "coarse_mask_reference": str(resized_coarse),
        "prompt_file": str(run_dir / "prompt.txt"),
        "host": args.host,
        "model": args.model,
        "task_id": str(task_id),
        "generated_mask": str(generated),
        "result_url": result_url,
        "run_dir": str(run_dir),
    }
    write_json(run_dir / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
