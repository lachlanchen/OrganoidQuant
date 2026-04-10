#!/usr/bin/env python3
"""Simple single-image Nano Banana runner for cystic organoid masks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
GRSAI_RUNNER = REPO_ROOT / "analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py"
DEFAULT_OVERRIDES = REPO_ROOT / "analysis-tools/app81_grsai_mask_generation/app81_grsai_prompt_overrides_low_v1.json"


PROMPT = (
    "Segment only real medium or large organoids in this brightfield microscopy image. "
    "Use pure black background everywhere outside organoids. "
    "Each kept organoid must be one smooth solid filled flat-colored region. "
    "A true cystic organoid is a round or slightly irregular biological object with a dark continuous wall and a meaningful interior that may be lighter than the wall. "
    "If such a cystic organoid is clearly visible, segment it as one filled organoid. "
    "Also segment darker dense compact organoid tissue when it is clearly real organoid material. "
    "Do not draw hollow rings, contour-only objects, thin edge traces, or fragmental colored tails. "
    "Ignore tiny specks, tiny dots, tiny fragments, tiny isolated edge debris, and very small background objects. "
    "Prefer only medium or large real organoids, and leave small uncertain objects black. "
    "Do not segment pale transparent droplets, hollow droplet boundaries, large smooth pale circular regions, outer container arcs, fluid boundaries, or border-touching droplet arcs. "
    "If a large circular structure is pale, transparent, or mostly hollow, leave it black even if it has a visible ring. "
    "Output only the clean colored organoid mask."
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run simple cystic-organoid Nano Banana segmentation")
    p.add_argument("--image", required=True, help="Source image path")
    p.add_argument("--output-dir", required=True, help="New output root")
    p.add_argument("--host", default="https://grsaiapi.com", help="GRS AI host")
    p.add_argument("--model", default="nano-banana-fast", help="Nano Banana model")
    p.add_argument("--image-size", default="1K", help="Nano Banana image size")
    p.add_argument("--max-side", type=int, default=1024, help="Resize max side for upload")
    p.add_argument("--min-kept-area-frac", type=float, default=0.0020, help="Minimum kept component area fraction")
    p.add_argument("--prompt-overrides-json", default=str(DEFAULT_OVERRIDES), help="Optional prompt override JSON")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def convert_source_to_png(src: Path, dest: Path) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    size = img.size
    img.save(dest)
    return size


def run_cmd(cmd: list[str], verbose: bool) -> None:
    if verbose:
        print("RUN", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def main() -> None:
    args = parse_args()
    image_path = Path(args.image).resolve()
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    source_png = output_root / "source_pngs" / f"{image_path.parent.name}_{image_path.stem}_source.png"
    width, height = convert_source_to_png(image_path, source_png)

    grsai_dir = output_root / "grsai_stage"
    prompt_path = output_root / "simple_prompt.txt"
    prompt_path.write_text(PROMPT + "\n", encoding="utf-8")

    cmd = [
        sys.executable,
        str(GRSAI_RUNNER),
        "--image",
        str(source_png),
        "--output-dir",
        str(grsai_dir),
        "--host",
        args.host,
        "--model",
        args.model,
        "--image-size",
        args.image_size,
        "--max-side",
        str(args.max_side),
        "--poll-timeout",
        "1800",
        "--stalled-timeout",
        "600",
        "--extra-prompt",
        PROMPT,
        "--min-kept-area-frac",
        str(args.min_kept_area_frac),
    ]
    override_path = Path(args.prompt_overrides_json)
    if override_path.exists():
        cmd.extend(["--prompt-overrides-json", str(override_path)])
    if args.verbose:
        cmd.append("--verbose")
    run_cmd(cmd, verbose=args.verbose)

    manifest = {
        "source_image": str(image_path),
        "source_png": str(source_png),
        "source_size": [width, height],
        "prompt_path": str(prompt_path),
        "grsai_dir": str(grsai_dir),
        "mask": str(grsai_dir / "generated_instance_mask.png"),
        "flat_mask": str(grsai_dir / "generated_instance_mask_flat.png"),
        "overlay": str(grsai_dir / "generated_overlay.png"),
        "flat_overlay": str(grsai_dir / "generated_overlay_flat.png"),
    }
    (output_root / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
