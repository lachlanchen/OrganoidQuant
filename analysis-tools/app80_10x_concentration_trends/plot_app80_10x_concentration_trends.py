#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


MONTH_MAP = {
    "一月": 1,
    "二月": 2,
    "三月": 3,
    "四月": 4,
    "五月": 5,
    "六月": 6,
    "七月": 7,
    "八月": 8,
    "九月": 9,
    "十月": 10,
    "十一月": 11,
    "十二月": 12,
}

CONCENTRATION_ORDER = ["No", "10uM", "20uM", "50uM", "100uM"]
COLOR_MAP = {
    "No": "#2F2F2F",
    "10uM": "#1B9E77",
    "20uM": "#2C7FB8",
    "50uM": "#D95F02",
    "100uM": "#C0392B",
}
SKIP_TIFS = {
    "/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/No/10-十二月-2025/10x02.tif",
}


@dataclass(frozen=True)
class DateToken:
    year: int
    month: int
    day: int
    label: str

    @property
    def sort_key(self) -> Tuple[int, int, int]:
        return (self.year, self.month, self.day)

    @property
    def axis_label(self) -> str:
        return f"Day {self.day}\n{self.month:02d}-{self.day:02d}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot App80 10x fusion and growth trends from 3 selected replicates per date.")
    p.add_argument("--app80-root", default="/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO")
    p.add_argument("--results-csv", default="/home/lachlan/ProjectsLFS/Zhengyu/DEO-DATABASE/app80_10x_single_droplet_results.csv")
    p.add_argument("--output-dir", default="/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10x_concentration_trends")
    return p.parse_args()


def natural_sample_key(path: Path) -> Tuple[int, str]:
    m = re.search(r"(?i)10x(\d+)$", path.stem)
    sample_idx = int(m.group(1)) if m else 10**9
    return (sample_idx, path.stem.lower())


def parse_date_label(label: str) -> DateToken:
    m = re.match(r"^(\d{2})-([^-]+)-(\d{4})$", label)
    if not m:
        raise ValueError(f"Unsupported date label: {label}")
    day = int(m.group(1))
    month_text = m.group(2)
    year = int(m.group(3))
    month = MONTH_MAP[month_text]
    return DateToken(year=year, month=month, day=day, label=label)


def concentration_sort_key(label: str) -> Tuple[int, str]:
    if label in CONCENTRATION_ORDER:
        return (CONCENTRATION_ORDER.index(label), label)
    return (len(CONCENTRATION_ORDER), label)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#333333",
            "axes.labelcolor": "#222222",
            "axes.titleweight": "bold",
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "xtick.color": "#333333",
            "ytick.color": "#333333",
            "grid.color": "#D8D8D8",
            "grid.linewidth": 0.7,
            "grid.alpha": 0.55,
            "font.family": "DejaVu Serif",
            "legend.frameon": False,
            "savefig.dpi": 300,
        }
    )


def build_selected_subset(app80_root: Path, results_csv: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    results = pd.read_csv(results_csv)
    results["source_tif"] = results["source_tif"].astype(str)
    result_by_tif: Dict[str, Dict] = {
        str(Path(row["source_tif"]).resolve()): row.to_dict() for _, row in results.iterrows()
    }

    selected_rows: List[Dict] = []
    missing_rows: List[Dict] = []

    for concentration_dir in sorted([p for p in app80_root.iterdir() if p.is_dir()], key=lambda p: concentration_sort_key(p.name)):
        for date_dir in sorted([p for p in concentration_dir.iterdir() if p.is_dir()], key=lambda p: parse_date_label(p.name).sort_key):
            tifs = sorted(
                [
                    p.resolve()
                    for p in date_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == ".tif" and re.search(r"(?i)10x\d+$", p.stem)
                ],
                key=natural_sample_key,
            )
            chosen: List[Path] = []
            for tif in tifs:
                if str(tif) in SKIP_TIFS:
                    continue
                chosen.append(tif)
                if len(chosen) == 3:
                    break

            for rank, tif in enumerate(chosen, start=1):
                key = str(tif)
                if key not in result_by_tif:
                    missing_rows.append(
                        {
                            "concentration_label": concentration_dir.name,
                            "date_label": date_dir.name,
                            "source_tif": key,
                            "selection_rank": rank,
                            "status": "missing_from_results_csv",
                        }
                    )
                    continue
                row = dict(result_by_tif[key])
                row["selection_rank"] = rank
                row["selection_policy"] = "first_3_sorted_10x_per_date_except_known_skip"
                selected_rows.append(row)

    selected_df = pd.DataFrame(selected_rows)
    missing_df = pd.DataFrame(missing_rows)
    return selected_df, missing_df


def add_ordering_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date_token"] = out["date_label"].map(parse_date_label)
    out["day_index"] = out["date_token"].map(lambda x: x.day)
    out["axis_label"] = out["date_token"].map(lambda x: x.axis_label)
    out["concentration_order"] = out["concentration_label"].map(lambda x: concentration_sort_key(x)[0])
    return out


def build_daily_summary(selected_df: pd.DataFrame) -> pd.DataFrame:
    metrics = {
        "fusion_score_combined_0_to_5": "fusion",
        "droplet_area_px": "droplet_area_px",
        "droplet_circumference_px": "droplet_circumference_px",
        "organoid_count_combined": "organoid_count",
    }

    work = selected_df.copy()
    for col in metrics:
        work[col] = pd.to_numeric(work[col], errors="coerce")

    grouped = (
        work.groupby(
            [
                "concentration_label",
                "concentration_order",
                "date_label",
                "day_index",
                "axis_label",
            ],
            as_index=False,
        )
        .agg(
            n=("source_tif", "count"),
            fusion_mean=("fusion_score_combined_0_to_5", "mean"),
            fusion_std=("fusion_score_combined_0_to_5", "std"),
            droplet_area_mean_px=("droplet_area_px", "mean"),
            droplet_area_std_px=("droplet_area_px", "std"),
            droplet_circumference_mean_px=("droplet_circumference_px", "mean"),
            droplet_circumference_std_px=("droplet_circumference_px", "std"),
            organoid_count_mean=("organoid_count_combined", "mean"),
            organoid_count_std=("organoid_count_combined", "std"),
        )
        .sort_values(["concentration_order", "day_index"])
        .reset_index(drop=True)
    )

    std_cols = [c for c in grouped.columns if c.endswith("_std") or c.endswith("_std_px")]
    for col in std_cols:
        grouped[col] = grouped[col].fillna(0.0)

    grouped["droplet_area_mean_million_px"] = grouped["droplet_area_mean_px"] / 1_000_000.0
    grouped["droplet_area_std_million_px"] = grouped["droplet_area_std_px"] / 1_000_000.0
    grouped["droplet_circumference_mean_kpx"] = grouped["droplet_circumference_mean_px"] / 1_000.0
    grouped["droplet_circumference_std_kpx"] = grouped["droplet_circumference_std_px"] / 1_000.0
    return grouped


def plot_metric_lines(
    ax: plt.Axes,
    daily: pd.DataFrame,
    y_mean_col: str,
    y_std_col: str,
    ylabel: str,
    title: str,
) -> None:
    for concentration in CONCENTRATION_ORDER:
        sub = daily[daily["concentration_label"] == concentration].sort_values("day_index")
        if sub.empty:
            continue
        x = sub["day_index"].to_numpy(dtype=float)
        y = sub[y_mean_col].to_numpy(dtype=float)
        y_std = sub[y_std_col].to_numpy(dtype=float)
        color = COLOR_MAP[concentration]
        ax.plot(
            x,
            y,
            color=color,
            linewidth=2.6,
            marker="o",
            markersize=6.5,
            markerfacecolor="white",
            markeredgewidth=1.6,
            label=concentration,
        )
        ax.fill_between(x, y - y_std, y + y_std, color=color, alpha=0.12, linewidth=0)

    ax.set_title(title, loc="left")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y")
    ax.grid(axis="x", alpha=0.15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save_figure(fig: plt.Figure, base_path: Path) -> None:
    for suffix in (".png", ".svg", ".pdf"):
        fig.savefig(base_path.with_suffix(suffix), bbox_inches="tight")


def write_readme(output_dir: Path, daily: pd.DataFrame, missing: pd.DataFrame) -> None:
    readme = output_dir / "README.md"
    concentrations = ", ".join([c for c in CONCENTRATION_ORDER if c in set(daily["concentration_label"])])
    days = ", ".join(str(x) for x in sorted(daily["day_index"].unique()))
    lines = [
        "# App80 10x Concentration Trend Outputs",
        "",
        "- Source CSV: `DEO-DATABASE/app80_10x_single_droplet_results.csv`",
        "- Selection policy: first 3 sorted `10x` TIFFs per concentration/date folder.",
        "- Known skipped image: `No/10-十二月-2025/10x02.tif`.",
        f"- Concentrations included: {concentrations}",
        f"- Day labels included: {days}",
        "",
        "## Files",
        "- `app80_10x_publication_subset.csv`: exact rows used for plotting.",
        "- `app80_10x_daily_summary.csv`: per-day mean/std summary.",
        "- `app80_10x_fusion_trends_publication.*`: fusion line plots.",
        "- `app80_10x_growth_trends_publication.*`: area and circumference line plots.",
        "- `app80_10x_combined_trends_publication.*`: combined publication figure.",
        "",
        f"- Missing selected rows: {len(missing)}",
    ]
    readme.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    app80_root = Path(args.app80_root).resolve()
    results_csv = Path(args.results_csv).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    configure_style()

    selected_df, missing_df = build_selected_subset(app80_root, results_csv)
    if selected_df.empty:
        raise SystemExit("No selected rows found for plotting.")

    selected_df = add_ordering_columns(selected_df)
    daily = build_daily_summary(selected_df)

    selected_path = output_dir / "app80_10x_publication_subset.csv"
    missing_path = output_dir / "app80_10x_missing_selected_rows.csv"
    daily_path = output_dir / "app80_10x_daily_summary.csv"
    selected_df.drop(columns=["date_token"]).to_csv(selected_path, index=False)
    daily.to_csv(daily_path, index=False)
    if not missing_df.empty:
        missing_df.to_csv(missing_path, index=False)

    x_days = sorted(daily["day_index"].unique())
    x_labels = [parse_date_label(f"{day:02d}-十二月-2025").axis_label for day in x_days]

    fusion_fig, fusion_ax = plt.subplots(figsize=(10.8, 5.8))
    plot_metric_lines(
        fusion_ax,
        daily,
        y_mean_col="fusion_mean",
        y_std_col="fusion_std",
        ylabel="Fusion Score (0-5)",
        title="Fusion Progression Across Y-27632 Concentrations",
    )
    fusion_ax.set_xticks(x_days, x_labels)
    fusion_ax.set_xlabel("Culture Day")
    fusion_ax.set_ylim(0, 5.2)
    fusion_ax.legend(ncols=len(CONCENTRATION_ORDER), loc="upper center", bbox_to_anchor=(0.5, 1.16))
    save_figure(fusion_fig, output_dir / "app80_10x_fusion_trends_publication")
    plt.close(fusion_fig)

    growth_fig, growth_axes = plt.subplots(1, 2, figsize=(13.5, 5.6), sharex=True)
    plot_metric_lines(
        growth_axes[0],
        daily,
        y_mean_col="droplet_area_mean_million_px",
        y_std_col="droplet_area_std_million_px",
        ylabel="Droplet Area (million px$^2$)",
        title="Growth by Droplet Area",
    )
    plot_metric_lines(
        growth_axes[1],
        daily,
        y_mean_col="droplet_circumference_mean_kpx",
        y_std_col="droplet_circumference_std_kpx",
        ylabel="Circumference (kpx)",
        title="Growth by Droplet Circumference",
    )
    for ax in growth_axes:
        ax.set_xticks(x_days, x_labels)
        ax.set_xlabel("Culture Day")
    growth_axes[1].legend(ncols=1, loc="upper left")
    save_figure(growth_fig, output_dir / "app80_10x_growth_trends_publication")
    plt.close(growth_fig)

    combined_fig, axes = plt.subplots(3, 1, figsize=(11.4, 13.4), sharex=True, constrained_layout=True)
    plot_metric_lines(
        axes[0],
        daily,
        y_mean_col="fusion_mean",
        y_std_col="fusion_std",
        ylabel="Fusion Score (0-5)",
        title="Fusion Progression",
    )
    axes[0].set_ylim(0, 5.2)
    plot_metric_lines(
        axes[1],
        daily,
        y_mean_col="droplet_area_mean_million_px",
        y_std_col="droplet_area_std_million_px",
        ylabel="Area (million px$^2$)",
        title="Growth by Area",
    )
    plot_metric_lines(
        axes[2],
        daily,
        y_mean_col="droplet_circumference_mean_kpx",
        y_std_col="droplet_circumference_std_kpx",
        ylabel="Circumference (kpx)",
        title="Growth by Circumference",
    )
    axes[2].set_xticks(x_days, x_labels)
    axes[2].set_xlabel("Culture Day")
    handles, labels = axes[0].get_legend_handles_labels()
    combined_fig.legend(handles, labels, ncols=len(labels), loc="upper center", bbox_to_anchor=(0.5, 1.01))
    save_figure(combined_fig, output_dir / "app80_10x_combined_trends_publication")
    plt.close(combined_fig)

    write_readme(output_dir, daily, missing_df)

    print(f"selected_subset_csv={selected_path}")
    print(f"daily_summary_csv={daily_path}")
    print(f"output_dir={output_dir}")
    print(f"missing_selected_rows={len(missing_df)}")


if __name__ == "__main__":
    main()
