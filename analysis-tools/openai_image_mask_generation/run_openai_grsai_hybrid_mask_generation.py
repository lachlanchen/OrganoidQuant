#!/usr/bin/env python3
"""Two-stage organoid mask generation: OpenAI rough localization followed by GRS AI refinement."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAI_RUNNER = REPO_ROOT / "analysis-tools/openai_image_mask_generation/run_openai_image_mask_generation.py"
GRSAI_RUNNER = REPO_ROOT / "analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py"
DEFAULT_OVERRIDES = REPO_ROOT / "analysis-tools/app81_grsai_mask_generation/app81_grsai_prompt_overrides_low_v1.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run hybrid OpenAI + GRS-AI organoid mask generation")
    p.add_argument("--image", required=True, help="Source microscopy image path")
    p.add_argument("--output-dir", required=True, help="New output root")
    p.add_argument("--openai-host", default="https://api.openai.com", help="OpenAI API host")
    p.add_argument("--grsai-host", default="https://grsaiapi.com", help="GRS AI host")
    p.add_argument("--grsai-model", default="nano-banana-fast", help="Nano Banana model")
    p.add_argument("--grsai-image-size", default="1K", help="Nano Banana image size")
    p.add_argument("--grsai-max-side", type=int, default=1024, help="Resize max side for Nano Banana upload")
    p.add_argument("--grsai-poll-timeout", type=float, default=1800.0, help="Nano Banana poll timeout seconds")
    p.add_argument("--grsai-stalled-timeout", type=float, default=600.0, help="Nano Banana stalled timeout seconds")
    p.add_argument("--prompt-overrides-json", default=str(DEFAULT_OVERRIDES), help="Optional prompt override JSON for the GRS-AI stage")
    p.add_argument("--resume", action="store_true", help="Reuse existing stage outputs and task ids when present")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def ensure_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def image_label_from_path(path: Path) -> str:
    date_label = path.parent.name
    stem = path.stem.replace("/", "_")
    return f"{date_label}_{stem}_source"


def convert_source_to_png(src: Path, dest: Path) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    size = img.size
    img.save(dest)
    return size


def choose_openai_size(width: int, height: int) -> str:
    ratio = width / float(height)
    if 0.92 <= ratio <= 1.08:
        return "1024x1024"
    if ratio > 1.08:
        return "1536x1024"
    return "1024x1536"


def run_cmd(cmd: list[str], verbose: bool) -> None:
    if verbose:
        print("RUN", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def main() -> None:
    args = parse_args()
    image_path = Path(args.image).resolve()
    ensure_exists(image_path)

    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    source_png = output_root / "source_pngs" / f"{image_label_from_path(image_path)}.png"
    width, height = convert_source_to_png(image_path, source_png)
    openai_size = choose_openai_size(width, height)

    openai_dir = output_root / "openai_stage"
    grsai_dir = output_root / "grsai_stage"

    openai_prompt_extra = (
        "Keep the same full image canvas, orientation, and approximate spatial registration as the source image. "
        "Do not crop, zoom, recenter, rotate, or rearrange objects. "
        "This mask is only a rough localization hint of likely organoids. "
        "Mark only likely organoid tissue positions and leave uncertain background black. "
        "Do not create any large colored region in an area that does not show a real dark dense organoid or a real cystic organoid with a dark continuous wall."
    )

    openai_mask = openai_dir / "generated_instance_mask.png"
    if not (args.resume and openai_mask.exists()):
        run_cmd(
            [
                sys.executable,
                str(OPENAI_RUNNER),
                "--image",
                str(source_png),
                "--output-dir",
                str(openai_dir),
                "--host",
                args.openai_host,
                "--size",
                openai_size,
                "--quality",
                "high",
                "--background",
                "opaque",
                "--prompt-extra",
                openai_prompt_extra,
                *(["--verbose"] if args.verbose else []),
            ],
            verbose=args.verbose,
        )
    ensure_exists(openai_mask)

    grsai_prompt_extra = (
        "Reference image order: the first reference image is the original microscopy image; the second reference image is only a rough heuristic mask. "
        "Use the second image only as a hint for likely organoid count and approximate location. "
        "Final organoid positions, sizes, and boundaries must match the first original microscopy image, not the rough mask, whenever they disagree. "
        "Preserve the same full canvas and spatial registration as the first image. "
        "Use the rough mask to avoid missing likely organoids, but do not copy its inaccurate geometry or false positives. "
        "Exclude any large pale smooth translucent droplet or hollow droplet ring even if the rough mask suggests it."
    )

    grsai_cmd = [
        sys.executable,
        str(GRSAI_RUNNER),
        "--image",
        str(source_png),
        "--reference-image",
        str(openai_mask),
        "--output-dir",
        str(grsai_dir),
        "--host",
        args.grsai_host,
        "--model",
        args.grsai_model,
        "--image-size",
        args.grsai_image_size,
        "--max-side",
        str(args.grsai_max_side),
        "--poll-timeout",
        str(args.grsai_poll_timeout),
        "--stalled-timeout",
        str(args.grsai_stalled_timeout),
        "--extra-prompt",
        grsai_prompt_extra,
    ]
    override_path = Path(args.prompt_overrides_json)
    if override_path.exists():
        grsai_cmd.extend(["--prompt-overrides-json", str(override_path)])
    if args.resume:
        grsai_cmd.append("--resume")
    if args.verbose:
        grsai_cmd.append("--verbose")
    run_cmd(grsai_cmd, verbose=args.verbose)

    final_manifest = {
        "source_image": str(image_path),
        "source_png": str(source_png),
        "source_size": [width, height],
        "openai_size": openai_size,
        "openai_dir": str(openai_dir),
        "openai_mask": str(openai_mask),
        "grsai_dir": str(grsai_dir),
        "grsai_mask": str(grsai_dir / "generated_instance_mask.png"),
        "grsai_flat_mask": str(grsai_dir / "generated_instance_mask_flat.png"),
        "grsai_overlay": str(grsai_dir / "generated_overlay.png"),
        "grsai_flat_overlay": str(grsai_dir / "generated_overlay_flat.png"),
    }
    (output_root / "hybrid_manifest.json").write_text(json.dumps(final_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(final_manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
