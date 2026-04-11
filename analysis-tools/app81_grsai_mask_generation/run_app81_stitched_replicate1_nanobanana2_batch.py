#!/usr/bin/env python3
"""Run Nano Banana on the six App81 replicate_01 stitched 3x3 collages."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from run_app81_grsai_mask_generation import (
    DEFAULT_HOST,
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


PROMPT = (
    "This is one stitched 3x3 collage of 8 separate brightfield microscopy panels plus 1 blank black tile. "
    "Treat each non-blank panel independently. "
    "Each non-blank panel is its own image and each non-blank panel contains several organoids. "
    "Search every non-blank panel carefully for multiple organoids, not just one. "
    "Generate one colored organoid instance mask aligned to the whole collage. "
    "Use pure black background everywhere outside organoids, and keep all black gutters and the blank tile black. "
    "Each true organoid must be one smooth solid filled flat-colored instance. "
    "Include all apparent real organoids. Do not miss obvious organoids. "
    "A real organoid can be a dark-rim cystic object with a lighter lumen, a dense dark compact body, or a dark fused irregular mass. "
    "Keep adjacent organoids separate when each has its own visible wall, lumen, neck, or center. "
    "Use different colors for adjacent or touching organoids. Do not give the same color to neighboring organoids that touch or nearly touch. "
    "Do not mask pale smooth translucent droplets, hollow droplet boundaries, empty pale interiors, faint circular arcs, debris, specks, or tiny detached fragments. "
    "If a large circular or oval structure is pale and translucent, keep it black. "
    "If it is dark dense real tissue, mask it. "
    "Do not draw outlines or hollow masks. "
    "Output only the colored mask image."
)

DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "app81_replicate1_stitched_prompt_overrides_v2.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Nano Banana on six replicate_01 stitched collages")
    p.add_argument(
        "--input-root",
        default="analysis-output/app81_density_stitched_inputs_v3_replicates_backfill_rep1",
        help="Root containing stitched collage inputs",
    )
    p.add_argument("--output-root", required=True, help="New output root")
    p.add_argument("--host", default=DEFAULT_HOST, help="GRS AI host")
    p.add_argument("--model", default="nano-banana-2", help="Nano Banana model")
    p.add_argument("--image-size", default="2K", help="Image size")
    p.add_argument("--max-side", type=int, default=2048, help="Resize max side for upload")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Poll interval seconds")
    p.add_argument("--poll-timeout", type=float, default=1800.0, help="Per-job poll timeout seconds")
    p.add_argument("--submit-retries", type=int, default=2, help="Submit retries")
    p.add_argument("--job-retries", type=int, default=1, help="Fresh resubmits on remote failure")
    p.add_argument("--min-kept-area-frac", type=float, default=0.0008, help="Minimum kept component area fraction")
    p.add_argument("--prompt-overrides-json", default=str(DEFAULT_OVERRIDES), help="Optional prompt overrides JSON keyed by collage label")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def find_inputs(input_root: Path) -> list[Path]:
    plain_dir = input_root / "collages" / "plain"
    images = sorted(plain_dir.glob("*_replicate_01_10x_stitched.png"))
    if len(images) != 6:
        raise RuntimeError(f"Expected 6 replicate_01 stitched inputs, found {len(images)} in {plain_dir}")
    return images


def load_override_text(label: str, override_path: Path) -> str:
    if not override_path.exists():
        return ""
    try:
        data = json.loads(override_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    value = data.get(label, "")
    return value if isinstance(value, str) else ""


def build_job(image_path: Path, output_root: Path, override_path: Path) -> dict[str, Any]:
    label = image_path.stem
    stage_dir = output_root / label
    log_dir = stage_dir / "logs"
    stage_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    override = load_override_text(label, override_path)
    prompt = PROMPT + (" " + override.strip() if override.strip() else "")
    (stage_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    write_json(stage_dir / "prompt_guidance.json", {"override": override, "base_prompt": PROMPT})
    return {
        "label": label,
        "image_path": image_path,
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
    upload_image_path, tmpdir = prepare_upload_image(job["image_path"], args.max_side)
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
                "input_collage_path": str(job["image_path"]),
                "output_dir": str(job["stage_dir"]),
                "task_id": task_id,
                "status": "submitted",
                "model": args.model,
                "host": args.host,
                "job_attempt": job["job_attempt"],
                "upload_image_path": str(upload_image_path),
            })
            return
        except Exception as exc:
            last_err = exc
            time.sleep(2.0 + attempt * 2.0)
    raise RuntimeError(f"Submit failed for {job['label']}: {last_err}")


def finalize_success(job: dict[str, Any], final: dict[str, Any], args: argparse.Namespace) -> None:
    data = final.get("data") or {}
    results = final.get("results") or data.get("results") or []
    if not results or not results[0].get("url"):
        raise RuntimeError(f"No result URL for {job['label']}: {final}")
    download_file(results[0]["url"], job["mask_path"])
    cleanup_report = clean_generated_mask_in_place(job["mask_path"], job["image_path"], min_kept_area_frac=args.min_kept_area_frac)
    write_json(job["cleanup_report_path"], cleanup_report)
    flatten_instance_mask(job["mask_path"], job["flat_mask_path"])
    save_overlay(job["image_path"], job["mask_path"], job["overlay_path"])
    save_overlay(job["image_path"], job["flat_mask_path"], job["flat_overlay_path"])
    write_json(job["manifest_path"], {
        "input_collage_path": str(job["image_path"]),
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
    })
    job["status"] = "succeeded"
    job["finished"] = True
    tmpdir = job.pop("_tmpdir", None)
    if tmpdir is not None:
        tmpdir.cleanup()


def mark_failed(job: dict[str, Any], args: argparse.Namespace, reason: str, final: dict[str, Any] | None = None, exc: Exception | None = None) -> None:
    payload = {
        "input_collage_path": str(job["image_path"]),
        "output_dir": str(job["stage_dir"]),
        "task_id": job.get("task_id"),
        "status": "failed",
        "model": args.model,
        "host": args.host,
        "job_attempt": job.get("job_attempt"),
        "failure_reason": reason,
    }
    if final is not None:
        payload["final_response_path"] = str(job["poll_response_path"])
    if exc is not None:
        payload["error"] = str(exc)
    write_json(job["manifest_path"], payload)
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
    if status == "succeeded":
        finalize_success(job, result, args)
        return
    if status == "failed":
        if job["job_attempt"] <= args.job_retries and should_resubmit_failed_result(result):
            submit_job(job, args, api_key)
            return
        mark_failed(job, args, "remote_failed", final=result)
        return
    if time.time() - job["submitted_at"] > args.poll_timeout:
        mark_failed(job, args, "poll_timeout", final=result)


def write_registry(output_root: Path, jobs: list[dict[str, Any]]) -> None:
    rows = []
    for job in jobs:
        rows.append({
            "label": job["label"],
            "input_collage_path": str(job["image_path"]),
            "task_id": job.get("task_id"),
            "status": job.get("status"),
            "job_attempt": job.get("job_attempt"),
            "last_progress": job.get("last_progress"),
            "stage_dir": str(job["stage_dir"]),
        })
    write_json(output_root / "batch_registry.json", rows)


def main() -> None:
    args = parse_args()
    api_key = load_grsai_key()
    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()
    override_path = Path(args.prompt_overrides_json)
    output_root.mkdir(parents=True, exist_ok=True)
    images = find_inputs(input_root)
    jobs = [build_job(path, output_root, override_path) for path in images]
    (output_root / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    write_json(output_root / "input_collages.json", [str(p) for p in images])

    for job in jobs:
        try:
            submit_job(job, args, api_key)
        except Exception as exc:
            mark_failed(job, args, "submit_failed", exc=exc)
        write_registry(output_root, jobs)

    pending = [job for job in jobs if not job["finished"]]
    while pending:
        for job in pending:
            try:
                poll_once(job, args, api_key)
            except Exception as exc:
                mark_failed(job, args, "poll_exception", exc=exc)
            write_registry(output_root, jobs)
        pending = [job for job in jobs if not job["finished"]]
        if pending:
            time.sleep(args.poll_interval)

    summary = {
        "input_root": str(input_root),
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
