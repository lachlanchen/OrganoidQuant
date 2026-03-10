#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from PIL import Image


def circle_edge_score(grad: np.ndarray, cx: float, cy: float, r: float, min_visible: float = 0.7) -> float:
    if r < 5:
        return -1.0
    h, w = grad.shape
    n = 120
    t = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False, dtype=np.float32)
    xs = np.rint(cx + r * np.cos(t)).astype(np.int32)
    ys = np.rint(cy + r * np.sin(t)).astype(np.int32)
    inside_mask = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    inside = int(np.count_nonzero(inside_mask))
    visible = inside / float(n)
    if visible < min_visible or inside == 0:
        return -1.0
    values = grad[ys[inside_mask], xs[inside_mask]]
    return float(np.mean(values) * (0.5 + 0.5 * visible))


def optimize_circle(grad: np.ndarray, cx: float, cy: float, r: float) -> Tuple[Tuple[float, float, float], float, float]:
    base_score = circle_edge_score(grad, cx, cy, r)
    best = (cx, cy, r)
    best_score = base_score
    max_shift = max(4, min(28, int(r * 0.08)))
    max_dr = max(4, min(26, int(r * 0.10)))

    for dx in range(-max_shift, max_shift + 1, 2):
        for dy in range(-max_shift, max_shift + 1, 2):
            for dr in range(-max_dr, max_dr + 1, 2):
                rr = max(5.0, r + dr)
                score = circle_edge_score(grad, cx + dx, cy + dy, rr)
                if score > best_score:
                    best_score = score
                    best = (cx + dx, cy + dy, rr)
    return best, base_score, best_score


def main() -> None:
    p = argparse.ArgumentParser(description="Refine one single-droplet circle by local edge optimization.")
    p.add_argument("--summary-json", required=True)
    p.add_argument("--source-png", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--report-json", required=True)
    args = p.parse_args()

    summary_path = Path(args.summary_json).resolve()
    source_png = Path(args.source_png).resolve()
    out_json = Path(args.out_json).resolve()
    report_json = Path(args.report_json).resolve()

    summary: Dict = json.loads(summary_path.read_text(encoding="utf-8"))
    gray = np.array(Image.open(source_png).convert("L")).astype(np.float32)
    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx * gx + gy * gy)

    cx = float(summary["droplet_center_x_px"])
    cy = float(summary["droplet_center_y_px"])
    r = float(summary["droplet_radius_px"])
    (nx, ny, nr), base_score, best_score = optimize_circle(grad, cx, cy, r)
    improved = best_score > base_score * 1.03 if base_score > 0 else best_score > base_score

    if improved:
        summary["droplet_center_x_px"] = round(nx, 2)
        summary["droplet_center_y_px"] = round(ny, 2)
        summary["droplet_radius_px"] = round(nr, 2)
        note = str(summary.get("droplet_note", "")).strip()
        extra = "edge_refined_single_circle"
        summary["droplet_note"] = f"{note}; {extra}" if note else extra

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "source_summary_json": str(summary_path),
        "output_summary_json": str(out_json),
        "improved": improved,
        "base_score": round(float(base_score), 6),
        "best_score": round(float(best_score), 6),
        "old_circle": {"cx": cx, "cy": cy, "r": r},
        "new_circle": {
            "cx": float(summary["droplet_center_x_px"]),
            "cy": float(summary["droplet_center_y_px"]),
            "r": float(summary["droplet_radius_px"]),
        },
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
