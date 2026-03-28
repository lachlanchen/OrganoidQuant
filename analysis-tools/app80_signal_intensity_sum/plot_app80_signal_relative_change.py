#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DEFAULT_INPUT = Path("/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum/app80_all_concentration_signal_sum_daily_summary.csv")
DEFAULT_OUTPUT_DIR = Path("/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentration_signal_intensity_sum")
CONCENTRATION_ORDER = ["No", "10uM", "20uM", "50uM", "100uM"]
COLORS = {
    "No": "#4c4c4c",
    "10uM": "#1f77b4",
    "20uM": "#2ca02c",
    "50uM": "#ff7f0e",
    "100uM": "#d62728",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return p.parse_args()


def load_summary_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                {
                    "concentration_label": row["concentration_label"],
                    "date_label": row["date_label"],
                    "day_number": int(row["day_number"]),
                    "n_replicates": int(row["n_replicates"]),
                    "sum_intensity_mean": float(row["sum_intensity_mean"]),
                    "sum_intensity_sem": float(row["sum_intensity_sem"]),
                    "reciprocal_mean": float(row["reciprocal_mean"]),
                    "reciprocal_sem": float(row["reciprocal_sem"]),
                }
            )
    rows.sort(key=lambda r: (CONCENTRATION_ORDER.index(r["concentration_label"]) if r["concentration_label"] in CONCENTRATION_ORDER else 999, r["day_number"]))
    return rows


def build_relative_change_rows(summary_rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for concentration in CONCENTRATION_ORDER:
        rows = [r for r in summary_rows if r["concentration_label"] == concentration]
        rows.sort(key=lambda r: r["day_number"])
        for prev, curr in zip(rows, rows[1:]):
            prev_sum = prev["sum_intensity_mean"]
            prev_recip = prev["reciprocal_mean"]
            sum_rel_change = (curr["sum_intensity_mean"] - prev_sum) / prev_sum if prev_sum else float("nan")
            reciprocal_rel_change = (curr["reciprocal_mean"] - prev_recip) / prev_recip if prev_recip else float("nan")
            out.append(
                {
                    "concentration_label": concentration,
                    "prev_date_label": prev["date_label"],
                    "date_label": curr["date_label"],
                    "prev_day_number": prev["day_number"],
                    "day_number": curr["day_number"],
                    "n_replicates": curr["n_replicates"],
                    "sum_intensity_mean": curr["sum_intensity_mean"],
                    "sum_intensity_relative_change": sum_rel_change,
                    "reciprocal_mean": curr["reciprocal_mean"],
                    "reciprocal_relative_change": reciprocal_rel_change,
                }
            )
    return out


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def plot_relative_change(rows: list[dict], output_dir: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13.2, 8.2), sharex=True, constrained_layout=True)

    for concentration in CONCENTRATION_ORDER:
        group = [r for r in rows if r["concentration_label"] == concentration]
        if not group:
            continue
        x = [r["day_number"] for r in group]
        sum_delta = np.array([r["sum_intensity_relative_change"] for r in group], dtype=float)
        reciprocal_delta = np.array([r["reciprocal_relative_change"] for r in group], dtype=float)
        color = COLORS.get(concentration)

        axes[0].plot(x, sum_delta, marker="o", linewidth=2.2, markersize=5.5, label=concentration, color=color)
        axes[1].plot(x, reciprocal_delta, marker="o", linewidth=2.2, markersize=5.5, label=concentration, color=color)

    axes[0].axhline(0.0, color="#888888", linewidth=1.0, alpha=0.7)
    axes[1].axhline(0.0, color="#888888", linewidth=1.0, alpha=0.7)

    axes[0].set_title("Relative Change In Hybrid Signal Sum Vs Previous Date", fontsize=15, pad=10)
    axes[0].set_ylabel("(Current - Previous) / Previous")
    axes[0].grid(True, alpha=0.25)

    axes[1].set_title("Relative Change In Reciprocal Signal Sum Vs Previous Date", fontsize=15, pad=10)
    axes[1].set_ylabel("(Current - Previous) / Previous")
    axes[1].set_xlabel("Date")
    axes[1].grid(True, alpha=0.25)

    tick_map = {}
    for row in rows:
        tick_map[row["day_number"]] = row["date_label"].split("-", 1)[0]
    x_ticks = sorted(tick_map)
    axes[1].set_xticks(x_ticks)
    axes[1].set_xticklabels([tick_map[t] for t in x_ticks])

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

    png_path = output_dir / "app80_all_concentration_signal_sum_relative_change.png"
    pdf_path = output_dir / "app80_all_concentration_signal_sum_relative_change.pdf"
    fig.savefig(png_path, dpi=220, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = load_summary_rows(input_csv)
    relative_change_rows = build_relative_change_rows(summary_rows)

    write_csv(
        output_dir / "app80_all_concentration_signal_sum_relative_change.csv",
        relative_change_rows,
        [
            "concentration_label",
            "prev_date_label",
            "date_label",
            "prev_day_number",
            "day_number",
            "n_replicates",
            "sum_intensity_mean",
            "sum_intensity_relative_change",
            "reciprocal_mean",
            "reciprocal_relative_change",
        ],
    )
    plot_relative_change(relative_change_rows, output_dir)
    print(output_dir / "app80_all_concentration_signal_sum_relative_change.csv")
    print(output_dir / "app80_all_concentration_signal_sum_relative_change.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
