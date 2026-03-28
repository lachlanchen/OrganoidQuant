#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


APP80_ROOT = Path("/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO")
DEFAULT_OUTPUT_DIR = Path("/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum")
CONCENTRATION_ORDER = ["No", "10uM", "20uM", "50uM", "100uM"]
COLORS = {
    "No": "#4c4c4c",
    "10uM": "#1f77b4",
    "20uM": "#2ca02c",
    "50uM": "#ff7f0e",
    "100uM": "#d62728",
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--app80-root", default=str(APP80_ROOT))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return p.parse_args()


def load_rgb(path: Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if arr is None:
        with Image.open(path) as im:
            return np.array(im.convert("RGB").copy())
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def compute_signal_sum(source_tif: Path) -> tuple[int, float]:
    rgb = load_rgb(source_tif)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (3, 3), 0)
    bg = cv2.GaussianBlur(clahe, (31, 31), 0)
    residual = cv2.subtract(bg, blur)
    inv = 255 - blur
    residual_norm = cv2.normalize(residual, None, 0, 255, cv2.NORM_MINMAX)
    inv_norm = cv2.normalize(inv, None, 0, 255, cv2.NORM_MINMAX)
    signal = cv2.addWeighted(inv_norm, 0.45, residual_norm, 0.55, 0)
    sum_intensity = int(np.array(signal, dtype=np.uint64).sum())
    reciprocal = 1.0 / float(sum_intensity) if sum_intensity > 0 else float("nan")
    return sum_intensity, reciprocal


def extract_day_number(date_label: str) -> int:
    token = date_label.split("-", 1)[0]
    try:
        return int(token)
    except ValueError:
        return 10**9


def collect_image_rows(app80_root: Path):
    rows = []
    for tif in sorted(app80_root.rglob("*")):
        if not tif.is_file():
            continue
        if tif.suffix.lower() not in {".tif", ".tiff"}:
            continue
        if "10x" not in tif.stem.lower():
            continue
        rel = tif.relative_to(app80_root)
        if len(rel.parts) < 3:
            continue
        concentration = rel.parts[0]
        date_label = rel.parts[1]
        sum_intensity, reciprocal = compute_signal_sum(tif)
        rows.append(
            {
                "source_tif": str(tif),
                "concentration_label": concentration,
                "date_label": date_label,
                "day_number": extract_day_number(date_label),
                "image_stem": tif.stem,
                "sum_intensity": sum_intensity,
                "reciprocal_sum_intensity": reciprocal,
            }
        )
    rows.sort(key=lambda r: (CONCENTRATION_ORDER.index(r["concentration_label"]) if r["concentration_label"] in CONCENTRATION_ORDER else 999, r["day_number"], r["image_stem"].lower()))
    return rows


def mean(vals: list[float]) -> float:
    return float(sum(vals) / len(vals)) if vals else float("nan")


def std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = mean(vals)
    return float((sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5)


def sem(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return std(vals) / math.sqrt(len(vals))


def build_summary_rows(image_rows):
    grouped = defaultdict(list)
    for row in image_rows:
        grouped[(row["concentration_label"], row["date_label"], row["day_number"])].append(row)

    summary = []
    for concentration_label in CONCENTRATION_ORDER:
        keys = sorted([k for k in grouped if k[0] == concentration_label], key=lambda k: k[2])
        for key in keys:
            rows = grouped[key]
            sum_vals = [float(r["sum_intensity"]) for r in rows]
            recip_vals = [float(r["reciprocal_sum_intensity"]) for r in rows]
            summary.append(
                {
                    "concentration_label": key[0],
                    "date_label": key[1],
                    "day_number": key[2],
                    "n_replicates": len(rows),
                    "sum_intensity_mean": mean(sum_vals),
                    "sum_intensity_std": std(sum_vals),
                    "sum_intensity_sem": sem(sum_vals),
                    "reciprocal_mean": mean(recip_vals),
                    "reciprocal_std": std(recip_vals),
                    "reciprocal_sem": sem(recip_vals),
                }
            )
    return summary


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def plot_metric(summary_rows, output_dir: Path):
    fig, axes = plt.subplots(2, 1, figsize=(13.2, 8.2), sharex=True, constrained_layout=True)
    for concentration in CONCENTRATION_ORDER:
        rows = [r for r in summary_rows if r["concentration_label"] == concentration]
        if not rows:
            continue
        x = [r["day_number"] for r in rows]
        x_labels = [r["date_label"] for r in rows]
        sum_mean = np.array([r["sum_intensity_mean"] for r in rows], dtype=float)
        sum_sem = np.array([r["sum_intensity_sem"] for r in rows], dtype=float)
        recip_mean = np.array([r["reciprocal_mean"] for r in rows], dtype=float)
        recip_sem = np.array([r["reciprocal_sem"] for r in rows], dtype=float)
        color = COLORS.get(concentration, None)

        axes[0].plot(x, sum_mean, marker="o", linewidth=2.2, markersize=5.5, label=concentration, color=color)
        axes[0].fill_between(x, sum_mean - sum_sem, sum_mean + sum_sem, color=color, alpha=0.16)

        axes[1].plot(x, recip_mean, marker="o", linewidth=2.2, markersize=5.5, label=concentration, color=color)
        axes[1].fill_between(x, recip_mean - recip_sem, recip_mean + recip_sem, color=color, alpha=0.16)

    axes[0].set_title("Hybrid Signal Sum By Day", fontsize=15, pad=10)
    axes[0].set_ylabel("Mean Sum Intensity")
    axes[0].grid(True, alpha=0.25)
    axes[0].ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))

    axes[1].set_title("Reciprocal Of Hybrid Signal Sum By Day", fontsize=15, pad=10)
    axes[1].set_ylabel("Mean 1 / Sum Intensity")
    axes[1].set_xlabel("Date")
    axes[1].grid(True, alpha=0.25)
    axes[1].ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))

    x_ticks = sorted({r["day_number"] for r in summary_rows})
    x_labels = []
    day_to_label = {r["day_number"]: r["date_label"] for r in summary_rows}
    for tick in x_ticks:
        x_labels.append(day_to_label[tick].split("-", 1)[0])
    axes[1].set_xticks(x_ticks)
    axes[1].set_xticklabels(x_labels)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        ncol=1,
        frameon=False,
        title="Concentration",
    )

    png_path = output_dir / "app80_all_concentration_signal_sum_and_reciprocal.png"
    pdf_path = output_dir / "app80_all_concentration_signal_sum_and_reciprocal.pdf"
    fig.savefig(png_path, dpi=220, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)


def write_readme(output_dir: Path):
    text = (
        "# App80 10x Hybrid Signal Intensity Summary\n\n"
        "- Metric uses the same hybrid second-column signal family as the prompted watershed gallery.\n"
        "- For cross-image comparability, the signal generation is fixed across all images:\n"
        "  - CLAHE clip limit `2.4`\n"
        "  - foreground blur kernel `3`\n"
        "  - background blur kernel `31`\n"
        "  - signal = `0.45 * inv_norm + 0.55 * residual_norm`\n"
        "- The figure shows mean across all 10x replicates for each date and concentration.\n"
        "- Shaded bands are mean +/- SEM.\n"
    )
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main():
    args = parse_args()
    app80_root = Path(args.app80_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    image_rows = collect_image_rows(app80_root)
    summary_rows = build_summary_rows(image_rows)

    write_csv(
        output_dir / "app80_all_concentration_signal_sum_per_image.csv",
        image_rows,
        [
            "source_tif",
            "concentration_label",
            "date_label",
            "day_number",
            "image_stem",
            "sum_intensity",
            "reciprocal_sum_intensity",
        ],
    )
    write_csv(
        output_dir / "app80_all_concentration_signal_sum_daily_summary.csv",
        summary_rows,
        [
            "concentration_label",
            "date_label",
            "day_number",
            "n_replicates",
            "sum_intensity_mean",
            "sum_intensity_std",
            "sum_intensity_sem",
            "reciprocal_mean",
            "reciprocal_std",
            "reciprocal_sem",
        ],
    )
    plot_metric(summary_rows, output_dir)
    write_readme(output_dir)
    print(output_dir / "app80_all_concentration_signal_sum_per_image.csv")
    print(output_dir / "app80_all_concentration_signal_sum_daily_summary.csv")
    print(output_dir / "app80_all_concentration_signal_sum_and_reciprocal.png")


if __name__ == "__main__":
    raise SystemExit(main())
