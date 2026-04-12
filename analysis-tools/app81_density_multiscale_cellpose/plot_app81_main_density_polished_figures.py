#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import f_oneway


ROOT_DEFAULT = Path(
    "/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app81_density_stitched_cellpose_v5_final_metrics_v1"
)

CONDITION_ORDER = ["low", "middle", "high"]
CONDITION_LABEL = {
    "low": "Low density",
    "middle": "Middle density",
    "high": "High density",
}
CONDITION_COLOR = {
    "low": "#2C6FB7",
    "middle": "#3FA7A3",
    "high": "#C73832",
}
CONDITION_MARKER = {
    "low": "o",
    "middle": "s",
    "high": "D",
}

PRIMARY_METRICS = [
    ("average_perimeter_px", "Growth", "Average perimeter (px)"),
    ("roundness_deviation_norm", "Differentiation", "Roundness deviation (norm)"),
    (
        "normalized_edge_over_count_curvature",
        "Fusion",
        "Normalized edge / (count * curvature)",
    ),
]

SUPPORTIVE_METRICS = [
    ("total_area_px", "Growth Support", "Total area (px)"),
    ("roundness", "Differentiation Support", "Roundness"),
    ("curvature", "Fusion Support", "Curvature"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate polished App81 density figures from final stitched single-image metrics."
    )
    p.add_argument("--out-dir", type=Path, default=ROOT_DEFAULT)
    return p.parse_args()


def star_text(p_value: float | None) -> str:
    if p_value is None or pd.isna(p_value):
        return ""
    if p_value < 1e-4:
        return "****"
    if p_value < 1e-3:
        return "***"
    if p_value < 1e-2:
        return "**"
    if p_value < 5e-2:
        return "*"
    return ""


def ensure_dirs(root: Path) -> dict[str, Path]:
    dirs = {
        "root": root / "figures-polished",
        "main": root / "figures-polished" / "main_primary_metrics",
        "supportive": root / "figures-polished" / "supportive_timecourse",
        "tables": root / "figures-polished" / "statistics_tables",
        "supplementary": root / "figures-polished" / "supplementary_existing_metrics",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def summarize_metric(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (condition, day), sub in df.groupby(["condition", "relative_day"], observed=True):
        vals = sub[metric].dropna().to_numpy(dtype=float)
        n = int(vals.size)
        mean = float(vals.mean()) if n else math.nan
        std = float(vals.std(ddof=1)) if n > 1 else math.nan
        sem = float(std / math.sqrt(n)) if n > 1 else math.nan
        rows.append(
            {
                "condition": condition,
                "relative_day": int(day),
                "n": n,
                "mean": mean,
                "std": std,
                "sem": sem,
            }
        )
    return pd.DataFrame(rows)


def global_tests(df: pd.DataFrame, metrics: list[tuple[str, str, str]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric, _, _ in metrics:
        for day, subday in df.groupby("relative_day", observed=True):
            groups = []
            group_ns: dict[str, int] = {}
            for cond in CONDITION_ORDER:
                vals = subday.loc[subday["condition"] == cond, metric].dropna().to_numpy(dtype=float)
                group_ns[cond] = int(vals.size)
                groups.append(vals)
            p_value = math.nan
            method = ""
            if int(day) > 1 and all(len(g) >= 2 for g in groups):
                method = "anova"
                p_value = float(f_oneway(*groups).pvalue)
            rows.append(
                {
                    "metric": metric,
                    "relative_day": int(day),
                    "method": method,
                    "p_value": p_value,
                    "stars": star_text(p_value),
                    "group_ns": json.dumps(group_ns, ensure_ascii=False),
                }
            )
    return pd.DataFrame(rows)


def add_global_stars(ax: plt.Axes, summary: pd.DataFrame, tests: pd.DataFrame, metric: str) -> None:
    y_min, y_max = ax.get_ylim()
    span = (y_max - y_min) if y_max > y_min else 1.0
    pad = 0.06 * span
    for _, row in tests.loc[tests["metric"] == metric].iterrows():
        stars = row["stars"]
        if not stars:
            continue
        day = int(row["relative_day"])
        sub = summary.loc[summary["relative_day"] == day]
        if sub.empty:
            continue
        local_y = np.nanmax(sub["mean"].to_numpy() + np.nan_to_num(sub["sem"].to_numpy(), nan=0.0))
        ax.text(
            day,
            local_y + pad,
            stars,
            ha="center",
            va="bottom",
            color="black",
            fontsize=12,
            fontweight="bold",
        )


def style_axis(ax: plt.Axes, xticks: list[int], xticklabels: list[str], title: str, ylabel: str, mean_col: str) -> None:
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xlabel("Day")
    ax.set_ylabel(ylabel)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels)
    ax.grid(axis="y", alpha=0.18, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if "area" in mean_col or "perimeter" in mean_col:
        ax.ticklabel_format(style="scientific", axis="y", scilimits=(0, 0))


def plot_timecourse(
    df: pd.DataFrame,
    metrics: list[tuple[str, str, str]],
    output_png: Path,
    output_pdf: Path,
    global_df: pd.DataFrame,
) -> pd.DataFrame:
    fig, axes = plt.subplots(1, len(metrics), figsize=(16.2, 4.8))
    summary_frames: list[pd.DataFrame] = []
    xticks = sorted(int(v) for v in df["relative_day"].unique())
    xticklabels = [f"D{d}" for d in xticks]
    for ax, (metric, heading, y_label) in zip(axes, metrics):
        summary = summarize_metric(df, metric)
        summary["metric"] = metric
        summary_frames.append(summary)
        for cond in CONDITION_ORDER:
            sub = summary.loc[summary["condition"] == cond].sort_values("relative_day")
            if sub.empty:
                continue
            ax.errorbar(
                sub["relative_day"],
                sub["mean"],
                yerr=sub["sem"].fillna(0.0),
                color=CONDITION_COLOR[cond],
                marker=CONDITION_MARKER[cond],
                markersize=5.5,
                linewidth=2.0,
                elinewidth=1.1,
                capsize=3,
                label=CONDITION_LABEL[cond],
            )
        add_global_stars(ax, summary, global_df, metric)
        style_axis(ax, xticks, xticklabels, heading, y_label, metric)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(output_png, dpi=240, bbox_inches="tight")
    fig.savefig(output_pdf, bbox_inches="tight")
    plt.close(fig)
    return pd.concat(summary_frames, ignore_index=True)


def copy_supplementary(fig_root: Path, out_root: Path) -> None:
    mapping = {
        "overview_segmentation_metrics": out_root / "standard_metric_panels" / "overview_segmentation_metrics",
        "fusion_proxy_metrics": out_root / "standard_metric_panels" / "fusion_proxy_metrics",
        "differentiation_roundness": out_root / "standard_metric_panels" / "differentiation_roundness",
        "metric_group_panels": out_root / "standard_metric_panels" / "metric_group_panels",
        "full_metric_panels": out_root / "full_metric_panels",
    }
    for src_name, dst in mapping.items():
        src = fig_root / src_name
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for file_path in src.iterdir():
            if file_path.is_file():
                shutil.copy2(file_path, dst / file_path.name)


def main() -> None:
    args = parse_args()
    root = args.out_dir.resolve()
    per_csv = root / "profiling" / "quantification" / "per_image_metrics.csv"
    df = pd.read_csv(per_csv)
    df = df.loc[df["condition"].isin(CONDITION_ORDER)].copy()

    dirs = ensure_dirs(root)
    global_primary = global_tests(df, PRIMARY_METRICS)
    global_supportive = global_tests(df, SUPPORTIVE_METRICS)

    primary_summary = plot_timecourse(
        df,
        PRIMARY_METRICS,
        dirs["main"] / "app81_main_density_primary_metrics_timecourse_polished.png",
        dirs["main"] / "app81_main_density_primary_metrics_timecourse_polished.pdf",
        global_primary,
    )
    supportive_summary = plot_timecourse(
        df,
        SUPPORTIVE_METRICS,
        dirs["supportive"] / "app81_main_density_supportive_metrics_timecourse_polished.png",
        dirs["supportive"] / "app81_main_density_supportive_metrics_timecourse_polished.pdf",
        global_supportive,
    )

    primary_summary.to_csv(dirs["tables"] / "primary_metric_summary.csv", index=False)
    supportive_summary.to_csv(dirs["tables"] / "supportive_metric_summary.csv", index=False)
    global_primary.to_csv(dirs["tables"] / "primary_same_day_global_tests.csv", index=False)
    global_supportive.to_csv(dirs["tables"] / "supportive_same_day_global_tests.csv", index=False)

    copy_supplementary(root / "figures", dirs["supplementary"])

    manifest = {
        "out_dir": str(root),
        "source_csv": str(per_csv),
        "primary_metrics": [m for m, _, _ in PRIMARY_METRICS],
        "supportive_metrics": [m for m, _, _ in SUPPORTIVE_METRICS],
        "rule_notes": {
            "no_stars_first_two_days": True,
            "longitudinal_stars_are_global_only": True,
            "palette": CONDITION_COLOR,
            "labels": CONDITION_LABEL,
        },
    }
    with open(dirs["root"] / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(dirs["root"])


if __name__ == "__main__":
    main()
