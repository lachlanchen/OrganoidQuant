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
from scipy.stats import f_oneway, ttest_ind


ROOT_DEFAULT = Path(
    "/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app65_alginate_v3_direct_brightfield"
)

CONDITION_ORDER = ["No", "0.02% Alginate", "0.05% Alginate"]
CONDITION_LABEL = {
    "No": "Control",
    "0.02% Alginate": "Low Alginate",
    "0.05% Alginate": "High Alginate",
}
CONDITION_COLOR = {
    "No": "#222222",
    "0.02% Alginate": "#2C6FB7",
    "0.05% Alginate": "#C73832",
}
CONDITION_MARKER = {
    "No": "o",
    "0.02% Alginate": "s",
    "0.05% Alginate": "D",
}

PRIMARY_METRICS = [
    ("average_perimeter_px", "Growth", "Perimeter (px)"),
    ("organoid_darkness_p90", "Differentiation", "Darkness P90"),
    ("peripheral_over_central", "Fusion", "Peripheral / Central internal edge"),
]

SUPPORTIVE_METRICS = [
    ("total_area_px", "Growth Support", "Area (px)"),
    ("core_darkness_mean", "Differentiation Support", "Core darkness mean"),
    ("normalized_edge_over_count_curvature", "Fusion Support", "Normalized edge / (count * curvature)"),
    ("roundness_deviation_norm", "Differentiation Support", "Roundness deviation (norm)"),
]

FOCUSED_PANELS = [
    (6, "average_perimeter_px", "Growth D6"),
    (7, "average_perimeter_px", "Growth D7"),
    (8, "peripheral_over_central", "Fusion D8"),
    (11, "organoid_darkness_p90", "Differentiation D11"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate polished App65 v3 figures from existing metrics.")
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
        "focused": root / "figures-polished" / "focused_day_comparisons",
        "supportive": root / "figures-polished" / "supportive_timecourse",
        "tables": root / "figures-polished" / "statistics_tables",
        "supplementary": root / "figures-polished" / "supplementary_existing_metrics",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def summarize_metric(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    rows = []
    for (condition, day), sub in df.groupby(["condition", "relative_day"], observed=True):
        vals = sub[metric].dropna()
        n = int(len(vals))
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
    rows = []
    for metric, _, _ in metrics:
        for day, subday in df.groupby("relative_day", observed=True):
            groups = []
            group_ns = {}
            for cond in CONDITION_ORDER:
                vals = subday.loc[subday["condition"] == cond, metric].dropna().values
                group_ns[cond] = int(len(vals))
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


def pairwise_vs_control(df: pd.DataFrame, metric: str, day: int) -> list[dict[str, object]]:
    out = []
    control = df.loc[(df["condition"] == "No") & (df["relative_day"] == day), metric].dropna().values
    for cond in CONDITION_ORDER[1:]:
        vals = df.loc[(df["condition"] == cond) & (df["relative_day"] == day), metric].dropna().values
        p_value = math.nan
        if day > 1 and len(control) >= 2 and len(vals) >= 2:
            p_value = float(ttest_ind(control, vals, equal_var=False, nan_policy="omit").pvalue)
        out.append(
            {
                "metric": metric,
                "relative_day": day,
                "group_a": "No",
                "group_b": cond,
                "p_value": p_value,
                "stars": star_text(p_value),
                "n_control": int(len(control)),
                "n_other": int(len(vals)),
            }
        )
    return out


def add_global_stars(ax: plt.Axes, summary: pd.DataFrame, tests: pd.DataFrame, metric: str) -> None:
    y_min, y_max = ax.get_ylim()
    pad = (y_max - y_min) * 0.06 if y_max > y_min else 1.0
    for _, row in tests.loc[tests["metric"] == metric].iterrows():
        stars = row["stars"]
        day = int(row["relative_day"])
        if not stars:
            continue
        sub = summary.loc[(summary["relative_day"] == day)]
        if sub.empty:
            continue
        local_y = np.nanmax(sub["mean"].to_numpy() + np.nan_to_num(sub["sem"].to_numpy(), nan=0.0))
        ax.text(day, local_y + pad, stars, ha="center", va="bottom", color="black", fontsize=12, fontweight="bold")


def plot_timecourse(df: pd.DataFrame, metrics: list[tuple[str, str, str]], output_png: Path, output_pdf: Path, global_df: pd.DataFrame) -> pd.DataFrame:
    fig, axes = plt.subplots(1, len(metrics), figsize=(16, 4.8), sharex=False)
    summary_frames = []
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
                elinewidth=1.2,
                capsize=3,
                label=CONDITION_LABEL[cond],
            )
        add_global_stars(ax, summary, global_df, metric)
        ax.set_title(heading, fontsize=12, pad=8)
        ax.set_xlabel("Day")
        ax.set_ylabel(y_label)
        ax.set_xticks(sorted(df["relative_day"].unique()))
        ax.grid(axis="y", alpha=0.18, linewidth=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.06))
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_png, dpi=220, bbox_inches="tight")
    fig.savefig(output_pdf, bbox_inches="tight")
    plt.close(fig)
    return pd.concat(summary_frames, ignore_index=True)


def box_positions():
    return np.arange(1, len(CONDITION_ORDER) + 1)


def add_pairwise_bracket(ax: plt.Axes, x1: float, x2: float, y: float, text: str, h: float) -> None:
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], color="black", linewidth=1.1)
    ax.text((x1 + x2) / 2.0, y + h, text, ha="center", va="bottom", color="black", fontsize=11, fontweight="bold")


def plot_focused_days(df: pd.DataFrame, output_png: Path, output_pdf: Path) -> pd.DataFrame:
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    axes = axes.ravel()
    pair_rows = []
    for ax, (day, metric, title) in zip(axes, FOCUSED_PANELS):
        groups = []
        maxima = []
        for cond in CONDITION_ORDER:
            vals = df.loc[(df["condition"] == cond) & (df["relative_day"] == day), metric].dropna().to_numpy()
            groups.append(vals)
            maxima.extend(vals.tolist())
        bp = ax.boxplot(
            groups,
            positions=box_positions(),
            widths=0.55,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": "black", "linewidth": 1.2},
            whiskerprops={"color": "black", "linewidth": 1.0},
            capprops={"color": "black", "linewidth": 1.0},
            boxprops={"linewidth": 1.0, "edgecolor": "black"},
        )
        for patch, cond in zip(bp["boxes"], CONDITION_ORDER):
            patch.set_facecolor(CONDITION_COLOR[cond])
            patch.set_alpha(0.55)
        for idx, (cond, vals) in enumerate(zip(CONDITION_ORDER, groups), start=1):
            if len(vals) == 0:
                continue
            jitter = np.linspace(-0.08, 0.08, len(vals)) if len(vals) > 1 else np.array([0.0])
            ax.scatter(np.full(len(vals), idx) + jitter, vals, s=20, color=CONDITION_COLOR[cond], alpha=0.8, zorder=3)

        pair_stats = pairwise_vs_control(df, metric, day)
        pair_rows.extend(pair_stats)
        ymax = max(maxima) if maxima else 1.0
        ymin = min(maxima) if maxima else 0.0
        span = (ymax - ymin) if ymax > ymin else 1.0
        level = ymax + 0.08 * span
        step = 0.09 * span
        for row, x_other in zip(pair_stats, [2, 3]):
            if row["stars"]:
                add_pairwise_bracket(ax, 1, x_other, level, row["stars"], 0.03 * span)
                level += step

        ax.set_title(title, fontsize=11, pad=8)
        ax.set_xticks(box_positions())
        ax.set_xticklabels([CONDITION_LABEL[c] for c in CONDITION_ORDER], rotation=0)
        ax.grid(axis="y", alpha=0.18, linewidth=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_png, dpi=220, bbox_inches="tight")
    fig.savefig(output_pdf, bbox_inches="tight")
    plt.close(fig)
    return pd.DataFrame(pair_rows)


def copy_supplementary(fig_root: Path, out_root: Path) -> None:
    mapping = {
        "overview_segmentation_metrics": out_root / "standard_metric_panels" / "overview_segmentation_metrics",
        "fusion_proxy_metrics": out_root / "standard_metric_panels" / "fusion_proxy_metrics",
        "differentiation_roundness": out_root / "standard_metric_panels" / "differentiation_roundness",
        "differentiation_darkness": out_root / "standard_metric_panels" / "differentiation_darkness",
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
        dirs["main"] / "app65_v3_primary_metrics_timecourse_polished.png",
        dirs["main"] / "app65_v3_primary_metrics_timecourse_polished.pdf",
        global_primary,
    )
    supportive_summary = plot_timecourse(
        df,
        SUPPORTIVE_METRICS,
        dirs["supportive"] / "app65_v3_supportive_metrics_timecourse_polished.png",
        dirs["supportive"] / "app65_v3_supportive_metrics_timecourse_polished.pdf",
        global_supportive,
    )
    focused_pairs = plot_focused_days(
        df,
        dirs["focused"] / "app65_v3_focused_day_comparisons_polished.png",
        dirs["focused"] / "app65_v3_focused_day_comparisons_polished.pdf",
    )

    primary_summary.to_csv(dirs["tables"] / "primary_metric_summary.csv", index=False)
    supportive_summary.to_csv(dirs["tables"] / "supportive_metric_summary.csv", index=False)
    global_primary.to_csv(dirs["tables"] / "primary_same_day_global_tests.csv", index=False)
    global_supportive.to_csv(dirs["tables"] / "supportive_same_day_global_tests.csv", index=False)
    focused_pairs.to_csv(dirs["tables"] / "focused_day_pairwise_vs_control.csv", index=False)

    copy_supplementary(root / "figures", dirs["supplementary"])

    manifest = {
        "out_dir": str(root),
        "source_csv": str(per_csv),
        "primary_metrics": [m for m, _, _ in PRIMARY_METRICS],
        "supportive_metrics": [m for m, _, _ in SUPPORTIVE_METRICS],
        "focused_panels": [
            {"relative_day": day, "metric": metric, "title": title}
            for day, metric, title in FOCUSED_PANELS
        ],
        "rule_notes": {
            "no_stars_first_two_days": True,
            "longitudinal_stars_are_global_only": True,
            "focused_pairwise_is_vs_control_only": True,
        },
    }
    with open(dirs["root"] / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(dirs["root"])


if __name__ == "__main__":
    main()
