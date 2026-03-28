#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def parse_args():
    root = Path(__file__).resolve().parents[2]
    default_output_dir = root / "analysis-output/app80_10uM_first_replicate_prompted_watershed"
    p = argparse.ArgumentParser()
    p.add_argument(
        "--manifest",
        default=str(default_output_dir / "batch_manifest.csv"),
        help="Path to the existing prompted watershed batch manifest.",
    )
    p.add_argument(
        "--output-dir",
        default=str(default_output_dir),
        help="Directory where the existing signal.png files already live.",
    )
    return p.parse_args()


def load_rows(manifest_path: Path):
    with manifest_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: int(r["day_rank"]))
    return rows


def compute_signal_metrics(rows):
    metrics = []
    for row in rows:
        run_dir = Path(row["run_dir"])
        signal_path = run_dir / "signal.png"
        arr = np.array(Image.open(signal_path).convert("L"), dtype=np.uint64)
        sum_intensity = int(arr.sum())
        reciprocal_sum_intensity = 1.0 / float(sum_intensity) if sum_intensity > 0 else float("nan")
        metrics.append(
            {
                "date_label": row["date_label"],
                "day_rank": int(row["day_rank"]),
                "stage_label": row["stage_label"],
                "run_dir": str(run_dir),
                "signal_path": str(signal_path),
                "sum_intensity": sum_intensity,
                "reciprocal_sum_intensity": reciprocal_sum_intensity,
            }
        )
    return metrics


def write_csv(metrics, out_csv: Path):
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "date_label",
                "day_rank",
                "stage_label",
                "run_dir",
                "signal_path",
                "sum_intensity",
                "reciprocal_sum_intensity",
            ],
        )
        writer.writeheader()
        writer.writerows(metrics)


def build_plot(metrics, out_png: Path, out_pdf: Path):
    x = [m["day_rank"] for m in metrics]
    x_labels = [f"D{m['day_rank']}" for m in metrics]
    sum_vals = [m["sum_intensity"] for m in metrics]
    recip_vals = [m["reciprocal_sum_intensity"] for m in metrics]

    fig, axes = plt.subplots(2, 1, figsize=(9.5, 7.2), sharex=True)

    axes[0].plot(x, sum_vals, color="#1f5aa6", marker="o", linewidth=2.2, markersize=6)
    axes[0].set_ylabel("Sum Intensity")
    axes[0].set_title("Signal Brightness Sum From Gallery Column 2")
    axes[0].grid(True, alpha=0.25)
    axes[0].ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))

    axes[1].plot(x, recip_vals, color="#c44e1a", marker="o", linewidth=2.2, markersize=6)
    axes[1].set_ylabel("1 / Sum Intensity")
    axes[1].set_xlabel("Day")
    axes[1].grid(True, alpha=0.25)
    axes[1].ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))

    axes[1].set_xticks(x)
    axes[1].set_xticklabels(x_labels)

    for ax, vals in ((axes[0], sum_vals), (axes[1], recip_vals)):
        for xi, yi in zip(x, vals):
            ax.annotate(f"{yi:.3e}" if yi < 1 else f"{yi:.0f}", (xi, yi), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_png, dpi=220, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(manifest_path)
    metrics = compute_signal_metrics(rows)

    csv_path = output_dir / "signal_intensity_sum_by_day.csv"
    png_path = output_dir / "signal_intensity_sum_by_day.png"
    pdf_path = output_dir / "signal_intensity_sum_by_day.pdf"

    write_csv(metrics, csv_path)
    build_plot(metrics, png_path, pdf_path)
    print(csv_path)
    print(png_path)
    print(pdf_path)


if __name__ == "__main__":
    raise SystemExit(main())
