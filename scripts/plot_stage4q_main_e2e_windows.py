#!/usr/bin/env python3
"""Plot draft main end-to-end latency figures with explicit pressure windows."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "results/stage4o_stage4p_plot_data/stage4o_e2e_full_matrix_20260531_234957"
OUT_DIR = ROOT / "results/figures/stage4q_main_e2e_windows"
PER_SEED_SOURCE_OUT = OUT_DIR / "stage4q_main_latency_windows_per_seed_source.csv"
SUMMARY_SOURCE_OUT = OUT_DIR / "stage4q_main_latency_windows_summary_source.csv"

COMBOS = [
    ("opt13b_sharegpt", "OPT-13B\nShareGPT", "opt13b_sharegpt/sweep_summary.csv"),
    ("llama13b_sharegpt", "LLaMA2-13B\nShareGPT", "llama13b_sharegpt/sweep_summary.csv"),
    ("llama13b_longbench4k", "LLaMA2-13B\nLongBench 4K", "llama13b_longbench4k/sweep_summary.csv"),
]

WINDOWS = {
    ("opt13b_sharegpt", "ttft"): (1.0, 2.75),
    ("opt13b_sharegpt", "tpot"): (1.0, 2.75),
    ("llama13b_sharegpt", "ttft"): (1.0, 2.25),
    ("llama13b_sharegpt", "tpot"): (0.75, 2.0),
    ("llama13b_longbench4k", "ttft"): (1.0, 3.0),
    ("llama13b_longbench4k", "tpot"): (1.0, 3.0),
}

POLICY_LABELS = {
    "fcfs": "DistServe",
    "phase": "PhaseServe",
}

COLORS = {
    "fcfs": "#6f7681",
    "phase": "#2b6cb0",
}

METRICS = {
    "ttft": [
        ("ttft_s_median", "p50", "-"),
        ("ttft_s_p90", "p90", "--"),
    ],
    "tpot": [
        ("tpot_s_p90", "p90", "--"),
        ("tpot_s_p95", "p95", ":"),
    ],
}

FIGURE_META = {
    "combined": {
        "prefix": "stage4q_main_latency_windows_combined",
        "title": "End-to-end latency under selected pressure windows",
    },
    "ttft": {
        "prefix": "stage4q_main_ttft_latency_windows",
        "ylabel": "TTFT (s)",
        "title": "TTFT latency under selected pressure windows",
    },
    "tpot": {
        "prefix": "stage4q_main_tpot_latency_windows",
        "ylabel": "TPOT (s/token)",
        "title": "TPOT latency under selected pressure windows",
    },
}


def configure_matplotlib() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "axes.labelsize": 7,
            "axes.titlesize": 8,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def add_panel_label(ax: mpl.axes.Axes, label: str) -> None:
    ax.text(
        -0.12,
        1.08,
        label,
        transform=ax.transAxes,
        fontsize=8,
        fontweight="bold",
        va="top",
        ha="left",
    )


def save_all(fig: mpl.figure.Figure, path_prefix: Path) -> None:
    path_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_prefix.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(path_prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(path_prefix.with_suffix(".png"), dpi=600, bbox_inches="tight")


def load_raw() -> pd.DataFrame:
    frames = []
    for combo, combo_title, relpath in COMBOS:
        df = pd.read_csv(DATA_ROOT / relpath).copy()
        df["combo"] = combo
        df["combo_title"] = combo_title.replace("\n", " + ")
        df["policy_label"] = df["policy"].map(POLICY_LABELS)
        df["per_gpu_rate"] = df["request_rate"].astype(float) / df["num_gpus"].astype(float)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    return raw[raw["policy"].isin(POLICY_LABELS)].copy()


def windowed(df: pd.DataFrame, combo: str, family: str) -> pd.DataFrame:
    lo, hi = WINDOWS[(combo, family)]
    return df[
        (df["combo"] == combo)
        & (df["per_gpu_rate"] >= lo)
        & (df["per_gpu_rate"] <= hi)
    ].copy()


def make_long_sources(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    per_seed_rows = []
    summary_rows = []
    for combo, combo_title, _ in COMBOS:
        for family, metrics in METRICS.items():
            sub = windowed(raw, combo, family)
            lo, hi = WINDOWS[(combo, family)]
            for metric, percentile, _ in metrics:
                for _, row in sub.iterrows():
                    per_seed_rows.append(
                        {
                            "combo": combo,
                            "combo_title": combo_title.replace("\n", " + "),
                            "metric_family": family,
                            "metric": metric,
                            "percentile": percentile,
                            "policy": row["policy"],
                            "policy_label": row["policy_label"],
                            "seed": int(row["seed"]),
                            "per_gpu_rate": float(row["per_gpu_rate"]),
                            "value": float(row[metric]),
                            "unit": "s" if family == "ttft" else "s/token",
                            "window_low": lo,
                            "window_high": hi,
                        }
                    )

                grouped = (
                    sub.groupby(["policy", "policy_label", "per_gpu_rate"], as_index=False)[metric]
                    .agg(["mean", "min", "max"])
                    .reset_index()
                )
                for _, row in grouped.iterrows():
                    summary_rows.append(
                        {
                            "combo": combo,
                            "combo_title": combo_title.replace("\n", " + "),
                            "metric_family": family,
                            "metric": metric,
                            "percentile": percentile,
                            "policy": row["policy"],
                            "policy_label": row["policy_label"],
                            "per_gpu_rate": float(row["per_gpu_rate"]),
                            "mean": float(row["mean"]),
                            "min": float(row["min"]),
                            "max": float(row["max"]),
                            "unit": "s" if family == "ttft" else "s/token",
                            "window_low": lo,
                            "window_high": hi,
                        }
                    )
    return pd.DataFrame(per_seed_rows), pd.DataFrame(summary_rows)


def apply_linear_limits(ax: mpl.axes.Axes, values: list[np.ndarray]) -> None:
    ymax = max(float(np.nanmax(v)) for v in values if len(v))
    if ymax <= 0:
        ymax = 1.0
    ax.set_ylim(0, ymax * 1.10)


def plot_family(summary: pd.DataFrame, family: str) -> None:
    fig, axes = plt.subplots(
        nrows=1,
        ncols=3,
        figsize=(7.2, 2.35),
        constrained_layout=True,
        sharex=False,
    )
    meta = FIGURE_META[family]
    for col, (combo, combo_title, _) in enumerate(COMBOS):
        ax = axes[col]
        add_panel_label(ax, chr(ord("a") + col))
        sub = summary[(summary["combo"] == combo) & (summary["metric_family"] == family)]
        lo, hi = WINDOWS[(combo, family)]
        x_pad = (hi - lo) * 0.08
        ax.set_xlim(lo - 0.04, hi + 0.04)
        ax.set_xticks(sorted(sub["per_gpu_rate"].unique()))
        ax.tick_params(axis="x", rotation=45)
        ax.set_xlabel("Per-GPU rate (req/s)")
        ax.set_ylabel(meta["ylabel"])
        ax.set_title(combo_title, pad=5)
        ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.7)
        y_values = []
        for policy in ["fcfs", "phase"]:
            for metric, percentile, linestyle in METRICS[family]:
                curve = sub[(sub["policy"] == policy) & (sub["metric"] == metric)].sort_values("per_gpu_rate")
                x = curve["per_gpu_rate"].to_numpy(dtype=float)
                y = curve["mean"].to_numpy(dtype=float)
                y_values.append(y)
                ax.plot(
                    x,
                    y,
                    color=COLORS[policy],
                    linestyle=linestyle,
                    marker="o",
                    markersize=3.0,
                    linewidth=1.45,
                    label=f"{POLICY_LABELS[policy]} {percentile}",
                )
        apply_linear_limits(ax, y_values)

    method_handles = [
        mlines.Line2D([], [], color=COLORS["fcfs"], linewidth=1.7, label="DistServe"),
        mlines.Line2D([], [], color=COLORS["phase"], linewidth=1.7, label="PhaseServe"),
    ]
    metric_handles = [
        mlines.Line2D([], [], color="#1f2937", linestyle=style, linewidth=1.6, label=percentile)
        for _, percentile, style in METRICS[family]
    ]
    fig.legend(
        handles=method_handles + metric_handles,
        loc="upper center",
        ncol=4,
        bbox_to_anchor=(0.5, 1.08),
        columnspacing=1.25,
        handlelength=2.2,
    )
    fig.suptitle(meta["title"], fontsize=9, y=1.18)
    save_all(fig, OUT_DIR / meta["prefix"])
    plt.close(fig)


def plot_combined(summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(
        nrows=2,
        ncols=3,
        figsize=(7.2, 3.55),
        constrained_layout=True,
        sharex=False,
    )
    for col, (combo, combo_title, _) in enumerate(COMBOS):
        for row, family in enumerate(["ttft", "tpot"]):
            ax = axes[row, col]
            add_panel_label(ax, chr(ord("a") + row * len(COMBOS) + col))
            sub = summary[(summary["combo"] == combo) & (summary["metric_family"] == family)]
            lo, hi = WINDOWS[(combo, family)]
            ax.set_xlim(lo - 0.04, hi + 0.04)
            ax.set_xticks(sorted(sub["per_gpu_rate"].unique()))
            ax.tick_params(axis="x", rotation=45, length=2.5)
            ax.set_xlabel("Per-GPU rate (req/s)")
            ax.grid(True, axis="y", color="#d9dee7", linewidth=0.45, alpha=0.65)
            if row == 0:
                ax.set_title(combo_title, pad=4)
                ax.set_ylabel("TTFT (s)")
            else:
                ax.set_ylabel("TPOT (s/token)")

            y_values = []
            for policy in ["fcfs", "phase"]:
                for metric, percentile, linestyle in METRICS[family]:
                    curve = sub[(sub["policy"] == policy) & (sub["metric"] == metric)].sort_values("per_gpu_rate")
                    x = curve["per_gpu_rate"].to_numpy(dtype=float)
                    y = curve["mean"].to_numpy(dtype=float)
                    y_values.append(y)
                    ax.plot(
                        x,
                        y,
                        color=COLORS[policy],
                        linestyle=linestyle,
                        marker="o",
                        markersize=2.4,
                        linewidth=1.15,
                    )
            apply_linear_limits(ax, y_values)

    method_handles = [
        mlines.Line2D([], [], color=COLORS["fcfs"], linewidth=1.6, label="DistServe"),
        mlines.Line2D([], [], color=COLORS["phase"], linewidth=1.6, label="PhaseServe"),
    ]
    ttft_handles = [
        mlines.Line2D([], [], color="#1f2937", linestyle=style, linewidth=1.45, label=f"TTFT {percentile}")
        for _, percentile, style in METRICS["ttft"]
    ]
    tpot_handles = [
        mlines.Line2D([], [], color="#1f2937", linestyle=style, linewidth=1.45, label=f"TPOT {percentile}")
        for _, percentile, style in METRICS["tpot"]
    ]
    fig.legend(
        handles=method_handles + ttft_handles + tpot_handles,
        loc="upper center",
        ncol=6,
        bbox_to_anchor=(0.5, 1.04),
        columnspacing=1.05,
        handlelength=1.9,
    )
    save_all(fig, OUT_DIR / FIGURE_META["combined"]["prefix"])
    plt.close(fig)


def main() -> None:
    configure_matplotlib()
    raw = load_raw()
    per_seed, summary = make_long_sources(raw)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_seed.to_csv(PER_SEED_SOURCE_OUT, index=False)
    summary.to_csv(SUMMARY_SOURCE_OUT, index=False)
    plot_combined(summary)
    plot_family(summary, "ttft")
    plot_family(summary, "tpot")
    print(f"Wrote {OUT_DIR / 'stage4q_main_latency_windows_combined.png'}")
    print(f"Wrote {OUT_DIR / 'stage4q_main_ttft_latency_windows.png'}")
    print(f"Wrote {OUT_DIR / 'stage4q_main_tpot_latency_windows.png'}")
    print(f"Wrote {PER_SEED_SOURCE_OUT}")
    print(f"Wrote {SUMMARY_SOURCE_OUT}")


if __name__ == "__main__":
    main()
