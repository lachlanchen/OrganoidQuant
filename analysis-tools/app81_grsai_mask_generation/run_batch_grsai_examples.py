#!/usr/bin/env python3
"""Batch-submit multiple GRS-AI Nano Banana jobs, then poll and finalize in parallel."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

from run_app81_grsai_mask_generation import (
    DEFAULT_HOST,
    analyze_prompt_guidance,
    clean_generated_mask_in_place,
    download_file,
    flatten_instance_mask,
    image_to_data_url,
    load_grsai_key,
    parse_json,
    prepare_upload_image,
    request_raw,
    save_overlay,
    should_resubmit_failed_result,
)
from run_single_grsai_cystic_organoid_mask import PROMPT


DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "app81_grsai_prompt_overrides_five_examples_v1.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch submit and poll GRS-AI example masks")
    p.add_argument("--output-root", required=True, help="New output root")
    p.add_argument("--image", action="append", required=True, help="Image path; pass multiple times")
    p.add_argument("--host", default=DEFAULT_HOST, help="GRS AI host")
    p.add_argument("--model", default="nano-banana-2", help="Nano Banana model")
    p.add_argument("--image-size", default="1K", help="Image size")
    p.add_argument("--max-side", type=int, default=1024, help="Resize max side for upload")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Poll interval seconds")
    p.add_argument("--poll-timeout", type=float, default=1800.0, help="Per-job poll timeout seconds")
    p.add_argument("--submit-retries", type=int, default=2, help="Submit retries")
    p.add_argument("--job-retries", type=int, default=1, help="Fresh resubmits on remote failure")
    p.add_argument("--min-kept-area-frac", type=float, default=0.0020, help="Minimum kept component area fraction")
    p.add_argument("--prompt-overrides-json", default=str(DEFAULT_OVERRIDES), help="Optional prompt overrides JSON")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def convert_source_to_png(src: Path, dest: Path) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    size = img.size
    img.save(dest)
    return size


def derive_label(image_path: Path) -> str:
    stem = image_path.stem.replace(" ", "_")
    return f"{image_path.parent.name}_{stem}"


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


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


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
    guidance = analyze_prompt_guidance(source_png)
    override = load_override_text(source_png.name, overrides_path)
    prompt = PROMPT + (" " + override.strip() if override.strip() else "")
    (job_root / "simple_prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    (stage_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    if override:
        guidance["manual_prompt_override"] = override
    write_json(stage_dir / "prompt_guidance.json", guidance)
    return {
        "label": label,
        "image_path": image_path,
        "source_png": source_png,
        "source_size": [width, height],
        "stage_dir": stage_dir,
        "log_dir": log_dir,
        "manifest_path": stage_dir / "task_manifest.json",
        "submit_response_path": log_dir / "submit_response.raw.txt",
        "poll_response_path": log_dir / "poll_response.json",
        "cleanup_report_path": stage_dir / "mask_cleanup_report.json",
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


def submit_job(job: dict[str, Any], args: argparse.Namespace, api_key: str) -> None:
    upload_image_path, tmpdir = prepare_upload_image(job["source_png"], args.max_side)
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
                "upload_image_path": str(upload_image_path),
                "output_dir": str(job["stage_dir"]),
                "task_id": task_id,
                "status": "submitted",
                "model": args.model,
                "host": args.host,
                "job_attempt": job["job_attempt"],
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
    download_file(results[0]["url"], job["mask_path"])
    cleanup_report = clean_generated_mask_in_place(job["mask_path"], job["source_png"], min_kept_area_frac=args.min_kept_area_frac)
    write_json(job["cleanup_report_path"], cleanup_report)
    flatten_instance_mask(job["mask_path"], job["flat_mask_path"])
    save_overlay(job["source_png"], job["mask_path"], job["overlay_path"])
    save_overlay(job["source_png"], job["flat_mask_path"], job["flat_overlay_path"])
    manifest = {
        "image_path": str(job["image_path"]),
        "source_png": str(job["source_png"]),
        "upload_image_path": job.get("upload_image_path", ""),
        "output_dir": str(job["stage_dir"]),
        "task_id": job["task_id"],
        "status": "succeeded",
        "model": args.model,
        "host": args.host,
        "job_attempt": job["job_attempt"],
        "result_url": results[0]["url"],
        "mask_path": str(job["mask_path"]),
        "flat_mask_path": str(job["flat_mask_path"]),
        "overlay_path": str(job["overlay_path"]),
        "flat_overlay_path": str(job["flat_overlay_path"]),
        "mask_cleanup_report_path": str(job["cleanup_report_path"]),
        "final_response_path": str(job["poll_response_path"]),
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
        "upload_image_path": job.get("upload_image_path", ""),
        "output_dir": str(job["stage_dir"]),
        "task_id": job["task_id"],
        "status": "failed",
        "model": args.model,
        "host": args.host,
        "job_attempt": job["job_attempt"],
        "failure_reason": reason,
        "final_response_path": str(job["poll_response_path"]),
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
        "upload_image_path": job.get("upload_image_path", ""),
        "output_dir": str(job["stage_dir"]),
        "task_id": job.get("task_id"),
        "status": "failed",
        "model": args.model,
        "host": args.host,
        "job_attempt": job.get("job_attempt"),
        "failure_reason": reason,
        "error": str(exc),
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
