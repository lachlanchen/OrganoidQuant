#!/usr/bin/env python3
"""Batch-run GRS-AI Nano Banana on stitched multi-view images of the same field."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from run_app81_grsai_mask_generation import (
    DEFAULT_HOST,
    analyze_prompt_guidance,
    clean_generated_mask_in_place,
    download_file,
    image_to_data_url,
    load_grsai_key,
    parse_json,
    prepare_upload_image,
    request_raw,
    save_overlay,
    should_resubmit_failed_result,
)


DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "app81_grsai_prompt_overrides_five_examples_v1.json"

PROMPT = (
    "This is a stitched three-view image of the same brightfield microscopy field. "
    "The large left panel is the raw brightfield image. "
    "The upper-right panel is a contrast-enhanced view of the same field. "
    "The lower-right panel is a boundary-enhanced view of the same field. "
    "Use all three panels together to identify true organoids accurately, but draw colored mask only inside the large left raw panel. "
    "Leave both right reference panels pure black. "
    "Inside the left raw panel, use pure black background everywhere outside organoids. "
    "Each true organoid must be one smooth solid filled flat-colored instance. "
    "Mask true organoids only: dark-rim cystic organoids with a closed biological wall and lighter lumen, dense dark compact organoids, and dark fused irregular tissue masses. "
    "Include true small, moderate, and large organoids when they are real tissue. "
    "Do not mask pale smooth transparent droplets, hollow droplet boundaries, empty pale interiors, faint circular arcs, debris, specks, or tiny detached fragments. "
    "If a large circular structure is pale and translucent, keep it black. "
    "If a large structure is dark dense real tissue, mask it. "
    "Keep adjacent organoids separate when each has its own visible wall, lumen, or center. "
    "Do not draw outlines or hollow masks. "
    "Output only the colored organoid mask."
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch submit stitched-view GRS-AI example masks")
    p.add_argument("--output-root", required=True, help="New output root")
    p.add_argument("--image", action="append", required=True, help="Image path; pass multiple times")
    p.add_argument("--host", default=DEFAULT_HOST, help="GRS AI host")
    p.add_argument("--model", default="nano-banana-2", help="Nano Banana model")
    p.add_argument("--image-size", default="2K", help="Image size")
    p.add_argument("--max-side", type=int, default=2048, help="Resize max side for upload")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Poll interval seconds")
    p.add_argument("--poll-timeout", type=float, default=1800.0, help="Per-job poll timeout seconds")
    p.add_argument("--submit-retries", type=int, default=2, help="Submit retries")
    p.add_argument("--job-retries", type=int, default=1, help="Fresh resubmits on remote failure")
    p.add_argument("--min-kept-area-frac", type=float, default=0.0020, help="Minimum kept component area fraction")
    p.add_argument("--prompt-overrides-json", default=str(DEFAULT_OVERRIDES), help="Optional prompt overrides JSON")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def derive_label(image_path: Path) -> str:
    stem = image_path.stem.replace(" ", "_")
    return f"{image_path.parent.name}_{stem}"


def convert_source_to_png(src: Path, dest: Path) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    size = img.size
    img.save(dest)
    return size


def load_override_text(image_name: str, override_path: Path) -> str:
    if not override_path.exists():
        return ""
    try:
        data = json.loads(override_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    value = data.get(image_name, "")
    return value if isinstance(value, str) else ""


def make_clahe_view(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)


def make_boundary_view(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    blackhat = cv2.morphologyEx(clahe, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    gx = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    grad = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    combo = cv2.addWeighted(blackhat, 0.55, grad, 0.45, 0)
    combo = cv2.GaussianBlur(combo, (0, 0), 1.0)
    return cv2.cvtColor(combo, cv2.COLOR_GRAY2RGB)


def build_stitched_views(source_png: Path, stitched_png: Path) -> dict[str, Any]:
    source = np.array(Image.open(source_png).convert("RGB"))
    h, w = source.shape[:2]
    side_w = max(1, w // 3)
    side_h = h // 2

    clahe = make_clahe_view(source)
    boundary = make_boundary_view(source)

    clahe_small = cv2.resize(clahe, (side_w, side_h), interpolation=cv2.INTER_AREA)
    boundary_small = cv2.resize(boundary, (side_w, h - side_h), interpolation=cv2.INTER_AREA)

    canvas = np.zeros((h, w + side_w, 3), dtype=np.uint8)
    canvas[:, :w] = source
    canvas[:side_h, w:] = clahe_small
    canvas[side_h:, w:] = boundary_small

    stitched_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(canvas).save(stitched_png)

    return {
        "source_size": [int(w), int(h)],
        "stitched_size": [int(w + side_w), int(h)],
        "raw_panel_fraction": round(w / float(w + side_w), 8),
        "raw_panel_box_source_px": [0, 0, int(w), int(h)],
        "contrast_panel_box_source_px": [int(w), 0, int(w + side_w), int(side_h)],
        "boundary_panel_box_source_px": [int(w), int(side_h), int(w + side_w), int(h)],
    }


def build_job(image_str: str, output_root: Path, overrides_path: Path) -> dict[str, Any]:
    image_path = Path(image_str).resolve()
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    label = derive_label(image_path)
    job_root = output_root / label
    source_png = job_root / "source_pngs" / f"{image_path.parent.name}_{image_path.stem}_source.png"
    width, height = convert_source_to_png(image_path, source_png)
    stage_dir = job_root / "grsai_stage"
    log_dir = stage_dir / "logs"
    stage_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    stitched_png = stage_dir / "stitched_input.png"
    layout = build_stitched_views(source_png, stitched_png)
    guidance = analyze_prompt_guidance(source_png)
    override = load_override_text(source_png.name, overrides_path)
    prompt = PROMPT + (" " + override.strip() if override.strip() else "")

    (job_root / "optimized_prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    (stage_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    stitched_guidance = dict(guidance)
    stitched_guidance["stitched_layout"] = layout
    if override:
        stitched_guidance["manual_prompt_override"] = override
    write_json(stage_dir / "prompt_guidance.json", stitched_guidance)

    return {
        "label": label,
        "image_path": image_path,
        "source_png": source_png,
        "source_size": [width, height],
        "stitched_png": stitched_png,
        "stitched_layout": layout,
        "stage_dir": stage_dir,
        "log_dir": log_dir,
        "manifest_path": stage_dir / "task_manifest.json",
        "submit_response_path": log_dir / "submit_response.raw.txt",
        "poll_response_path": log_dir / "poll_response.json",
        "cleanup_report_path": stage_dir / "mask_cleanup_report.json",
        "stitched_mask_path": stage_dir / "generated_stitched_full.png",
        "mask_path": stage_dir / "generated_instance_mask.png",
        "flat_mask_path": stage_dir / "generated_instance_mask_flat.png",
        "overlay_path": stage_dir / "generated_overlay.png",
        "flat_overlay_path": stage_dir / "generated_overlay_flat.png",
        "prompt": prompt,
        "job_attempt": 0,
        "task_id": None,
        "status": "prepared",
        "submitted_at": None,
        "last_progress": None,
        "finished": False,
    }


def crop_left_panel_to_source(stitched_mask_path: Path, source_mask_path: Path, layout: dict[str, Any], source_size: list[int]) -> None:
    stitched = Image.open(stitched_mask_path).convert("RGB")
    crop_w = max(1, int(round(stitched.width * float(layout["raw_panel_fraction"]))))
    left_panel = stitched.crop((0, 0, crop_w, stitched.height))
    left_panel = left_panel.resize((int(source_size[0]), int(source_size[1])), Image.NEAREST)
    left_panel.save(source_mask_path)


def submit_job(job: dict[str, Any], args: argparse.Namespace, api_key: str) -> None:
    upload_image_path, tmpdir = prepare_upload_image(job["stitched_png"], args.max_side)
    job["_tmpdir"] = tmpdir
    job["upload_image_path"] = str(upload_image_path)
    payload: dict[str, Any] = {
        "model": args.model,
        "urls": [image_to_data_url(upload_image_path)],
        "prompt": job["prompt"],
        "aspectRatio": "auto",
        "webHook": "-1",
        "shutProgress": True,
    }
    if args.image_size:
        payload["imageSize"] = args.image_size
    url = args.host.rstrip("/") + "/v1/draw/nano-banana"
    last_err: Exception | None = None
    for attempt in range(args.submit_retries + 1):
        try:
            raw = request_raw(url, payload, api_key, timeout_s=300.0, retries=2, verbose=args.verbose, context=f"submit:{job['label']}")
            job["submit_response_path"].write_text(raw, encoding="utf-8")
            result = parse_json(raw)
            task_id = result.get("id") or (result.get("data") or {}).get("id")
            if not task_id:
                raise RuntimeError(f"Missing task id in response: {result}")
            job["task_id"] = task_id
            job["status"] = "submitted"
            job["submitted_at"] = time.time()
            job["job_attempt"] += 1
            write_json(job["manifest_path"], {
                "image_path": str(job["image_path"]),
                "source_png": str(job["source_png"]),
                "stitched_png": str(job["stitched_png"]),
                "upload_image_path": str(upload_image_path),
                "output_dir": str(job["stage_dir"]),
                "task_id": task_id,
                "status": "submitted",
                "model": args.model,
                "host": args.host,
                "job_attempt": job["job_attempt"],
                "stitched_layout": job["stitched_layout"],
            })
            if args.verbose:
                print(f"submitted {job['label']} -> {task_id}", flush=True)
            return
        except Exception as exc:
            last_err = exc
            if args.verbose:
                print(f"submit failed for {job['label']} attempt {attempt+1}: {exc}", flush=True)
            time.sleep(2.0 + attempt * 2.0)
    raise RuntimeError(f"Submit failed for {job['label']}: {last_err}")


def finalize_success(job: dict[str, Any], final: dict[str, Any], args: argparse.Namespace) -> None:
    data = final.get("data") or {}
    results = final.get("results") or data.get("results") or []
    if not results or not results[0].get("url"):
        raise RuntimeError(f"No result URL for {job['label']}: {final}")
    download_file(results[0]["url"], job["stitched_mask_path"])
    crop_left_panel_to_source(job["stitched_mask_path"], job["mask_path"], job["stitched_layout"], job["source_size"])
    cleanup_report = clean_generated_mask_in_place(job["mask_path"], job["source_png"], min_kept_area_frac=args.min_kept_area_frac)
    write_json(job["cleanup_report_path"], cleanup_report)
    from run_app81_grsai_mask_generation import flatten_instance_mask  # lazy import to keep source-of-truth implementation
    flatten_instance_mask(job["mask_path"], job["flat_mask_path"])
    save_overlay(job["source_png"], job["mask_path"], job["overlay_path"])
    save_overlay(job["source_png"], job["flat_mask_path"], job["flat_overlay_path"])
    manifest = {
        "image_path": str(job["image_path"]),
        "source_png": str(job["source_png"]),
        "stitched_png": str(job["stitched_png"]),
        "upload_image_path": job.get("upload_image_path", ""),
        "output_dir": str(job["stage_dir"]),
        "task_id": job["task_id"],
        "status": "succeeded",
        "model": args.model,
        "host": args.host,
        "job_attempt": job["job_attempt"],
        "result_url": results[0]["url"],
        "stitched_mask_path": str(job["stitched_mask_path"]),
        "mask_path": str(job["mask_path"]),
        "flat_mask_path": str(job["flat_mask_path"]),
        "overlay_path": str(job["overlay_path"]),
        "flat_overlay_path": str(job["flat_overlay_path"]),
        "mask_cleanup_report_path": str(job["cleanup_report_path"]),
        "final_response_path": str(job["poll_response_path"]),
        "stitched_layout": job["stitched_layout"],
    }
    write_json(job["manifest_path"], manifest)
    job["status"] = "succeeded"
    job["finished"] = True
    tmpdir = job.pop("_tmpdir", None)
    if tmpdir is not None:
        tmpdir.cleanup()


def mark_failed(job: dict[str, Any], final: dict[str, Any], args: argparse.Namespace, reason: str) -> None:
    manifest = {
        "image_path": str(job["image_path"]),
        "source_png": str(job["source_png"]),
        "stitched_png": str(job["stitched_png"]),
        "upload_image_path": job.get("upload_image_path", ""),
        "output_dir": str(job["stage_dir"]),
        "task_id": job["task_id"],
        "status": "failed",
        "model": args.model,
        "host": args.host,
        "job_attempt": job["job_attempt"],
        "failure_reason": reason,
        "final_response_path": str(job["poll_response_path"]),
        "stitched_layout": job["stitched_layout"],
    }
    write_json(job["manifest_path"], manifest)
    job["status"] = "failed"
    job["finished"] = True
    tmpdir = job.pop("_tmpdir", None)
    if tmpdir is not None:
        tmpdir.cleanup()


def mark_exception(job: dict[str, Any], args: argparse.Namespace, reason: str, exc: Exception) -> None:
    manifest = {
        "image_path": str(job["image_path"]),
        "source_png": str(job["source_png"]),
        "stitched_png": str(job["stitched_png"]),
        "upload_image_path": job.get("upload_image_path", ""),
        "output_dir": str(job["stage_dir"]),
        "task_id": job.get("task_id"),
        "status": "failed",
        "model": args.model,
        "host": args.host,
        "job_attempt": job.get("job_attempt"),
        "failure_reason": reason,
        "error": str(exc),
        "stitched_layout": job["stitched_layout"],
    }
    write_json(job["manifest_path"], manifest)
    job["status"] = "failed"
    job["finished"] = True
    tmpdir = job.pop("_tmpdir", None)
    if tmpdir is not None:
        tmpdir.cleanup()


def poll_once(job: dict[str, Any], args: argparse.Namespace, api_key: str) -> None:
    url = args.host.rstrip("/") + "/v1/draw/result"
    raw = request_raw(url, {"id": job["task_id"]}, api_key, timeout_s=300.0, retries=2, verbose=args.verbose, context=f"poll:{job['label']}")
    result = parse_json(raw)
    write_json(job["poll_response_path"], result)
    data = result.get("data") or {}
    status = result.get("status") or data.get("status")
    progress = result.get("progress")
    if progress is None:
        progress = data.get("progress")
    job["last_progress"] = progress
    if args.verbose:
        print(f"poll {job['label']} status={status} progress={progress}", flush=True)
    if status == "succeeded":
        finalize_success(job, result, args)
        return
    if status == "failed":
        if job["job_attempt"] <= args.job_retries and should_resubmit_failed_result(result):
            if args.verbose:
                print(f"resubmitting {job['label']} after remote failure", flush=True)
            submit_job(job, args, api_key)
            return
        mark_failed(job, result, args, reason="remote_failed")
        return
    if time.time() - job["submitted_at"] > args.poll_timeout:
        mark_failed(job, result, args, reason="poll_timeout")


def write_registry(output_root: Path, jobs: list[dict[str, Any]]) -> None:
    registry = []
    for job in jobs:
        registry.append({
            "label": job["label"],
            "image_path": str(job["image_path"]),
            "task_id": job.get("task_id"),
            "status": job.get("status"),
            "job_attempt": job.get("job_attempt"),
            "last_progress": job.get("last_progress"),
            "stage_dir": str(job["stage_dir"]),
            "stitched_png": str(job["stitched_png"]),
        })
    write_json(output_root / "batch_registry.json", registry)


def main() -> None:
    args = parse_args()
    api_key = load_grsai_key()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    overrides_path = Path(args.prompt_overrides_json)
    jobs = [build_job(img, output_root, overrides_path) for img in args.image]
    (output_root / "optimized_prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")

    for job in jobs:
        try:
            submit_job(job, args, api_key)
        except Exception as exc:
            mark_exception(job, args, "submit_failed", exc)
    write_registry(output_root, jobs)

    pending = [job for job in jobs if not job["finished"]]
    while pending:
        for job in pending:
            try:
                poll_once(job, args, api_key)
            except Exception as exc:
                mark_exception(job, args, "poll_exception", exc)
            write_registry(output_root, jobs)
        pending = [job for job in jobs if not job["finished"]]
        if pending:
            time.sleep(args.poll_interval)

    summary = {
        "output_root": str(output_root),
        "model": args.model,
        "count": len(jobs),
        "succeeded": sum(1 for j in jobs if j["status"] == "succeeded"),
        "failed": sum(1 for j in jobs if j["status"] == "failed"),
    }
    write_json(output_root / "batch_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
