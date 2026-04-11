#!/usr/bin/env python3
"""Generate one Nano Banana mask over a stitched collage of multiple example images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from run_app81_grsai_mask_generation import (
    clean_generated_mask_in_place,
    flatten_instance_mask,
    image_to_data_url,
    load_grsai_key,
    parse_json,
    prepare_upload_image,
    request_raw,
    download_file,
    poll_result,
    save_overlay,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "https://grsaiapi.com"
DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "app81_grsai_prompt_overrides_five_examples_v1.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one stitched-collage GRS-AI Nano Banana experiment")
    p.add_argument("--output-root", required=True, help="New output root")
    p.add_argument("--image", action="append", required=True, help="Source image path; pass five times")
    p.add_argument("--host", default=DEFAULT_HOST, help="GRS AI host")
    p.add_argument("--model", default="nano-banana-2", help="Nano Banana model")
    p.add_argument("--image-size", default="2K", help="Nano Banana image size")
    p.add_argument("--max-side", type=int, default=2048, help="Resize uploaded collage max side")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval seconds")
    p.add_argument("--poll-timeout", type=float, default=1800.0, help="Polling timeout seconds")
    p.add_argument("--stalled-timeout", type=float, default=600.0, help="Polling stalled timeout seconds")
    p.add_argument("--min-kept-area-frac", type=float, default=0.0008, help="Minimum kept component area fraction")
    p.add_argument("--prompt-overrides-json", default=str(DEFAULT_OVERRIDES), help="Optional prompt override JSON")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


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


def convert_source_to_png(src: Path, dest: Path) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    size = img.size
    img.save(dest)
    return size


def panel_position_name(index: int) -> str:
    mapping = {
        0: "top-left",
        1: "top-middle",
        2: "top-right",
        3: "bottom-left",
        4: "bottom-middle",
        5: "bottom-right",
    }
    return mapping.get(index, f"panel-{index+1}")


def build_collage(source_pngs: list[Path], collage_path: Path, gap: int = 48) -> dict[str, Any]:
    images = [Image.open(p).convert("RGB") for p in source_pngs]
    widths = {img.size[0] for img in images}
    heights = {img.size[1] for img in images}
    if len(widths) != 1 or len(heights) != 1:
        raise RuntimeError("All stitched example images must have the same size")
    w = widths.pop()
    h = heights.pop()
    cols = 3
    rows = 2
    canvas_w = cols * w + (cols + 1) * gap
    canvas_h = rows * h + (rows + 1) * gap
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    panels = []
    for idx in range(6):
        row = idx // cols
        col = idx % cols
        x0 = gap + col * (w + gap)
        y0 = gap + row * (h + gap)
        x1 = x0 + w
        y1 = y0 + h
        if idx < len(images):
            canvas[y0:y1, x0:x1] = np.array(images[idx], dtype=np.uint8)
        panels.append({
            "index": idx,
            "position": panel_position_name(idx),
            "bbox": [x0, y0, x1, y1],
            "blank": idx >= len(images),
        })
    collage_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(canvas).save(collage_path)
    return {
        "canvas_size": [canvas_w, canvas_h],
        "panel_size": [w, h],
        "gap_px": gap,
        "panels": panels,
    }


def build_prompt(source_pngs: list[Path], override_path: Path) -> str:
    intro = (
        "This is one stitched collage containing five separate brightfield microscopy panels, with thick black gutters between panels and one blank black panel. "
        "Treat each panel independently. "
        "Generate one colored organoid instance mask aligned to the collage. "
        "Use pure black background everywhere outside organoids and keep the gutters and blank panel black. "
        "Each true organoid must be one smooth solid filled flat-colored instance. "
        "Mask true organoids only: dark-rim cystic organoids with a closed biological wall and lighter lumen, dense dark compact organoids, and dark fused irregular tissue masses. "
        "Do not mask pale smooth transparent droplets, hollow droplet boundaries, empty pale interiors, faint circular arcs, debris, specks, or tiny detached fragments. "
        "If a large circular structure is pale and translucent, keep it black. "
        "If a large structure is dark dense real tissue, mask it. "
        "Keep adjacent organoids separate when each has its own visible wall, lumen, or center. "
        "Do not draw outlines or hollow masks. "
        "Panel-specific guidance follows."
    )
    panel_lines = []
    for idx, png in enumerate(source_pngs):
        extra = load_override_text(png.name, override_path)
        line = f"{panel_position_name(idx)} panel: {extra}" if extra else f"{panel_position_name(idx)} panel: segment only real organoids and ignore pale droplet structures."
        panel_lines.append(line)
    panel_lines.append("bottom-right panel: this panel is blank black and must remain completely black.")
    return intro + " " + " ".join(panel_lines) + " Output only the colored mask image."


def save_panel_crops(layout: dict[str, Any], collage_source: Path, mask_path: Path, overlay_path: Path, out_dir: Path) -> None:
    src = Image.open(collage_source).convert("RGB")
    mask = Image.open(mask_path).convert("RGB")
    overlay = Image.open(overlay_path).convert("RGB")
    out_dir.mkdir(parents=True, exist_ok=True)
    for panel in layout["panels"]:
        if panel["blank"]:
            continue
        x0, y0, x1, y1 = panel["bbox"]
        stem = f"{panel['index']+1:02d}_{panel['position'].replace('-', '_')}"
        src.crop((x0, y0, x1, y1)).save(out_dir / f"{stem}_source.png")
        mask.crop((x0, y0, x1, y1)).save(out_dir / f"{stem}_mask.png")
        overlay.crop((x0, y0, x1, y1)).save(out_dir / f"{stem}_overlay.png")


def main() -> None:
    args = parse_args()
    if len(args.image) != 5:
        raise RuntimeError("Pass exactly five --image values for this stitched collage experiment")
    api_key = load_grsai_key()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    source_pngs: list[Path] = []
    source_manifest = []
    for image_str in args.image:
        src = Path(image_str).resolve()
        if not src.exists():
            raise FileNotFoundError(src)
        source_png = output_root / "source_pngs" / src.parent.name / f"{src.parent.name}_{src.stem}_source.png"
        size = convert_source_to_png(src, source_png)
        source_pngs.append(source_png)
        source_manifest.append({
            "image_path": str(src),
            "source_png": str(source_png),
            "size": list(size),
        })
    write_json(output_root / "source_manifest.json", source_manifest)

    collage_path = output_root / "stitched_collage.png"
    layout = build_collage(source_pngs, collage_path)
    write_json(output_root / "panel_layout.json", layout)

    overrides_path = Path(args.prompt_overrides_json)
    prompt = build_prompt(source_pngs, overrides_path)
    (output_root / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")

    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "task_manifest.json"
    raw_submit_path = log_dir / "submit_response.raw.txt"
    poll_response_path = log_dir / "poll_response.json"
    raw_mask_path = output_root / "generated_instance_mask.png"
    flat_mask_path = output_root / "generated_instance_mask_flat.png"
    overlay_path = output_root / "generated_overlay.png"
    flat_overlay_path = output_root / "generated_overlay_flat.png"
    cleanup_path = output_root / "mask_cleanup_report.json"

    upload_image_path, tmpdir = prepare_upload_image(collage_path, args.max_side)
    try:
        payload = {
            "model": args.model,
            "urls": [image_to_data_url(upload_image_path)],
            "prompt": prompt,
            "aspectRatio": "auto",
            "imageSize": args.image_size,
            "webHook": "-1",
            "shutProgress": True,
        }
        url = args.host.rstrip("/") + "/v1/draw/nano-banana"
        raw = request_raw(url, payload, api_key, timeout_s=300.0, retries=2, verbose=args.verbose, context="submit:collage")
        raw_submit_path.write_text(raw, encoding="utf-8")
        result = parse_json(raw)
        task_id = result.get("id") or (result.get("data") or {}).get("id")
        if not task_id:
            raise RuntimeError(f"Missing task id in response: {result}")

        write_json(manifest_path, {
            "status": "submitted",
            "task_id": task_id,
            "host": args.host,
            "model": args.model,
            "collage_path": str(collage_path),
            "panel_layout_path": str(output_root / "panel_layout.json"),
            "source_manifest_path": str(output_root / "source_manifest.json"),
            "upload_image_path": str(upload_image_path),
        })

        final = poll_result(
            args.host,
            task_id,
            api_key,
            args.poll_interval,
            args.poll_timeout,
            args.stalled_timeout,
            args.verbose,
        )
        write_json(poll_response_path, final)
        data = final.get("data") or {}
        results = final.get("results") or data.get("results") or []
        if not results or not results[0].get("url"):
            raise RuntimeError(f"No result URL in final response: {final}")

        download_file(results[0]["url"], raw_mask_path)
        cleanup = clean_generated_mask_in_place(raw_mask_path, collage_path, min_kept_area_frac=args.min_kept_area_frac)
        write_json(cleanup_path, cleanup)
        flatten_instance_mask(raw_mask_path, flat_mask_path)
        save_overlay(collage_path, raw_mask_path, overlay_path)
        save_overlay(collage_path, flat_mask_path, flat_overlay_path)
        save_panel_crops(layout, collage_path, raw_mask_path, overlay_path, output_root / "panel_crops")

        write_json(manifest_path, {
            "status": "succeeded",
            "task_id": task_id,
            "host": args.host,
            "model": args.model,
            "collage_path": str(collage_path),
            "panel_layout_path": str(output_root / "panel_layout.json"),
            "source_manifest_path": str(output_root / "source_manifest.json"),
            "upload_image_path": str(upload_image_path),
            "result_url": results[0]["url"],
            "mask_path": str(raw_mask_path),
            "flat_mask_path": str(flat_mask_path),
            "overlay_path": str(overlay_path),
            "flat_overlay_path": str(flat_overlay_path),
            "cleanup_report_path": str(cleanup_path),
            "panel_crops_dir": str(output_root / "panel_crops"),
            "final_response_path": str(poll_response_path),
        })
        print(json.dumps({
            "output_root": str(output_root),
            "task_id": task_id,
            "mask_path": str(raw_mask_path),
            "overlay_path": str(overlay_path),
            "panel_crops_dir": str(output_root / "panel_crops"),
        }, ensure_ascii=False))
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


if __name__ == "__main__":
    main()
