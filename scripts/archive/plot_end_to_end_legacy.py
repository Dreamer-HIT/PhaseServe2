#!/usr/bin/env python3
"""Generate PhaseServe end-to-end paper figures.

Inputs live under docs/figures/data:
  - opt13b_sweep_summary.csv
  - llama13b_s0_sweep_summary.csv
  - llama13b_s1_sweep_summary.csv
  - opt13b_tpot_highrate_pilot_summary.csv
  - opt13b_tpot_highrate_confirm_seed1_summary.csv
  - llama13b_tpot_highrate_confirm_summary.csv
  - stage4d_slo_attainment.csv

Outputs:
  - docs/figures/end_to_end_latency_rate_sweep.{pdf,png,svg}
  - docs/figures/slo_scale_sensitivity.{pdf,png,svg}
  - paper/end_to_end_latency_rate_sweep.pdf
  - paper/slo_scale_sensitivity.pdf
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "figures" / "data"
FIG_DIR = ROOT / "docs" / "figures"
PAPER_DIR = ROOT / "paper"

MODEL_SOURCES = {
    "OPT-13B": [
        DATA_DIR / "opt13b_sweep_summary.csv",
        DATA_DIR / "opt13b_tpot_highrate_pilot_summary.csv",
        DATA_DIR / "opt13b_tpot_highrate_confirm_seed1_summary.csv",
    ],
    "LLaMA-13B": [
        DATA_DIR / "llama13b_s0_sweep_summary.csv",
        DATA_DIR / "llama13b_s1_sweep_summary.csv",
        DATA_DIR / "llama13b_tpot_highrate_confirm_summary.csv",
    ],
}

POLICY_LABEL = {"fcfs": "DistServe", "phase": "PhaseServe"}
POLICY_COLOR = {"fcfs": "#ff8c00", "phase": "#0072B2"}
POLICY_MARKER = {"fcfs": "o", "phase": "s"}


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.titlesize": 8.0,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.linewidth": 0.7,
            "lines.linewidth": 1.65,
            "lines.markersize": 4.3,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )


def read_sweep_data() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for model, paths in MODEL_SOURCES.items():
        for path in paths:
            df = pd.read_csv(path).copy()
            df["model_label"] = model
            frames.append(df)
    data = pd.concat(frames, ignore_index=True).copy()
    data = data[data["policy"].isin(POLICY_LABEL)]
    data["per_gpu_rate"] = data["request_rate"] / data["num_gpus"]
    return data


def read_slo_data() -> pd.DataFrame:
    path = DATA_DIR / "stage4d_slo_attainment.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Recompute it from raw JSONL before plotting."
        )
    data = pd.read_csv(path)
    data = data[data["policy"].isin(POLICY_LABEL)]
    return data


def mean_by(
    data: pd.DataFrame,
    group_cols: list[str],
    value_cols: list[str],
) -> pd.DataFrame:
    return (
        data.groupby(group_cols, as_index=False)[value_cols]
        .mean(numeric_only=True)
        .sort_values(group_cols)
    )


def axis_polish(ax: plt.Axes) -> None:
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.45, alpha=0.85)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(width=0.7, length=3)


def plot_line(
    ax: plt.Axes,
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    policy: str,
    linestyle: str,
    marker: str | None = None,
    label: str | None = None,
) -> None:
    sub = df[df["policy"] == policy].sort_values(x_col)
    ax.plot(
        sub[x_col],
        sub[y_col],
        color=POLICY_COLOR[policy],
        linestyle=linestyle,
        marker=marker or POLICY_MARKER[policy],
        markerfacecolor="white",
        markeredgewidth=0.9,
        label=label,
    )


def plot_rate_sweep(
    sweep: pd.DataFrame,
    slo: pd.DataFrame,
    output_prefix: Path,
    rate_points: list[float],
) -> None:
    metrics = [
        "ttft_s_p90",
        "ttft_s_p99",
        "tpot_s_median",
        "tpot_s_p90",
    ]
    agg = mean_by(
        sweep[sweep["per_gpu_rate"].isin(rate_points)],
        ["model_label", "per_gpu_rate", "policy"],
        metrics,
    )
    slo_agg = mean_by(
        slo[(slo["scale"] == 1.0) & (slo["per_gpu_rate"].isin(rate_points))],
        ["model", "per_gpu_rate", "policy"],
        ["attainment_submitted"],
    ).rename(columns={"model": "model_label"})
    slo_agg["attainment_pct"] = 100.0 * slo_agg["attainment_submitted"]

    fig, axes = plt.subplots(2, 3, figsize=(7.15, 3.75), sharex=True)
    models = ["OPT-13B", "LLaMA-13B"]
    titles = [
        ("SLO", "SLO Attainment (%)"),
        ("TTFT", "TTFT (s)"),
        ("TPOT", "TPOT (s)"),
    ]
    panel = 0
    for row, model in enumerate(models):
        for col, (title, ylabel) in enumerate(titles):
            ax = axes[row, col]
            axis_polish(ax)
            panel += 1
            ax.set_title(
                f"({chr(96 + panel)}) {model} {title}",
                pad=2,
                fontweight="bold",
            )
            ax.set_xlim(min(rate_points) - 0.25, max(rate_points) + 0.25)
            ax.set_xticks(rate_points)
            if row == 1:
                ax.set_xlabel("Per-GPU Rates (req/s)")
            if col == 0:
                ax.set_ylabel(ylabel)
            else:
                ax.set_ylabel(ylabel)

            if col == 0:
                data = slo_agg[slo_agg["model_label"] == model]
                for policy in ["fcfs", "phase"]:
                    plot_line(
                        ax,
                        data,
                        "per_gpu_rate",
                        "attainment_pct",
                        policy,
                        "-",
                        label=POLICY_LABEL[policy],
                    )
                ax.set_ylim(25, 72)
            elif col == 1:
                data = agg[agg["model_label"] == model]
                for policy in ["fcfs", "phase"]:
                    plot_line(
                        ax,
                        data,
                        "per_gpu_rate",
                        "ttft_s_p90",
                        policy,
                        "-",
                        "o",
                        f"{POLICY_LABEL[policy]} p90",
                    )
                    plot_line(
                        ax,
                        data,
                        "per_gpu_rate",
                        "ttft_s_p99",
                        policy,
                        "--",
                        "s",
                        f"{POLICY_LABEL[policy]} p99",
                    )
            else:
                data = agg[agg["model_label"] == model]
                for policy in ["fcfs", "phase"]:
                    plot_line(
                        ax,
                        data,
                        "per_gpu_rate",
                        "tpot_s_median",
                        policy,
                        "-",
                        "o",
                        f"{POLICY_LABEL[policy]} p50",
                    )
                    plot_line(
                        ax,
                        data,
                        "per_gpu_rate",
                        "tpot_s_p90",
                        policy,
                        "--",
                        "s",
                        f"{POLICY_LABEL[policy]} p90",
                    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            color=POLICY_COLOR["fcfs"],
            marker=POLICY_MARKER["fcfs"],
            markerfacecolor="white",
            markeredgewidth=0.9,
            linewidth=1.65,
            label=POLICY_LABEL["fcfs"],
        ),
        Line2D(
            [0],
            [0],
            color=POLICY_COLOR["phase"],
            marker=POLICY_MARKER["phase"],
            markerfacecolor="white",
            markeredgewidth=0.9,
            linewidth=1.65,
            label=POLICY_LABEL["phase"],
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 1.03),
        handlelength=2.0,
        columnspacing=1.8,
    )
    fig.tight_layout(pad=0.5, w_pad=0.8, h_pad=0.9, rect=(0, 0, 1, 0.98))
    save_figure(fig, output_prefix)


def plot_latency_rate_sweep(
    sweep: pd.DataFrame,
    output_prefix: Path,
    ttft_rates: list[float],
    tpot_rates: list[float],
) -> None:
    metrics = [
        "ttft_s_p90",
        "ttft_s_p99",
        "tpot_s_median",
        "tpot_s_p90",
    ]
    agg = mean_by(
        sweep[sweep["per_gpu_rate"].isin(sorted(set(ttft_rates + tpot_rates)))],
        ["model_label", "per_gpu_rate", "policy"],
        metrics,
    )

    fig, axes = plt.subplots(2, 2, figsize=(6.4, 3.35))
    panels = [
        ("OPT-13B", "TTFT", ttft_rates),
        ("OPT-13B", "TPOT", tpot_rates),
        ("LLaMA-13B", "TTFT", ttft_rates),
        ("LLaMA-13B", "TPOT", tpot_rates),
    ]
    for idx, (ax, (model, metric, rates)) in enumerate(zip(axes.flat, panels), start=1):
        axis_polish(ax)
        ax.set_title(f"({chr(96 + idx)}) {model} {metric}", pad=2, fontweight="bold")
        ax.set_xlim(min(rates) - 0.25, max(rates) + 0.25)
        ax.set_xticks(rates)
        if idx > 2:
            ax.set_xlabel("Per-GPU Rates (req/s)")
        ax.set_ylabel(f"{metric} (s)")
        data = agg[
            (agg["model_label"] == model) & (agg["per_gpu_rate"].isin(rates))
        ]
        if metric == "TTFT":
            for policy in ["fcfs", "phase"]:
                plot_line(
                    ax,
                    data,
                    "per_gpu_rate",
                    "ttft_s_p90",
                    policy,
                    "-",
                    "o",
                    f"{POLICY_LABEL[policy]} p90",
                )
                plot_line(
                    ax,
                    data,
                    "per_gpu_rate",
                    "ttft_s_p99",
                    policy,
                    "--",
                    "s",
                    f"{POLICY_LABEL[policy]} p99",
                )
        else:
            for policy in ["fcfs", "phase"]:
                plot_line(
                    ax,
                    data,
                    "per_gpu_rate",
                    "tpot_s_median",
                    policy,
                    "-",
                    "o",
                    f"{POLICY_LABEL[policy]} p50",
                )
                plot_line(
                    ax,
                    data,
                    "per_gpu_rate",
                    "tpot_s_p90",
                    policy,
                    "--",
                    "s",
                    f"{POLICY_LABEL[policy]} p90",
                )

    system_handles = [
        Line2D(
            [0],
            [0],
            color=POLICY_COLOR["fcfs"],
            marker=POLICY_MARKER["fcfs"],
            markerfacecolor="white",
            markeredgewidth=0.9,
            linewidth=1.65,
            label=POLICY_LABEL["fcfs"],
        ),
        Line2D(
            [0],
            [0],
            color=POLICY_COLOR["phase"],
            marker=POLICY_MARKER["phase"],
            markerfacecolor="white",
            markeredgewidth=0.9,
            linewidth=1.65,
            label=POLICY_LABEL["phase"],
        ),
    ]
    style_handles = [
        Line2D(
            [0],
            [0],
            color="#333333",
            linestyle="-",
            linewidth=1.65,
            label="solid: p90 / p50",
        ),
        Line2D(
            [0],
            [0],
            color="#333333",
            linestyle="--",
            linewidth=1.65,
            label="dashed: p99 / p90",
        ),
    ]
    fig.legend(
        handles=system_handles + style_handles,
        loc="upper center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 1.04),
        handlelength=2.0,
        columnspacing=1.3,
    )
    fig.tight_layout(pad=0.5, w_pad=0.9, h_pad=0.85, rect=(0, 0, 1, 0.97))
    save_figure(fig, output_prefix)


def plot_slo_scale(
    slo: pd.DataFrame,
    output_prefix: Path,
    fixed_per_gpu_rate: float,
) -> None:
    data = slo[slo["per_gpu_rate"] == fixed_per_gpu_rate]
    agg = mean_by(
        data,
        ["model", "scale", "policy"],
        ["attainment_submitted"],
    )
    agg["attainment_pct"] = 100.0 * agg["attainment_submitted"]

    fig, axes = plt.subplots(1, 2, figsize=(4.9, 1.95), sharey=True)
    for i, model in enumerate(["OPT-13B", "LLaMA-13B"]):
        ax = axes[i]
        axis_polish(ax)
        ax.set_title(f"({chr(97 + i)}) {model}", pad=2, fontweight="bold")
        ax.set_xlabel("SLO Scale")
        if i == 0:
            ax.set_ylabel("SLO Attainment (%)")
        ax.set_ylim(0.0, 102)
        ax.set_xticks(sorted(agg["scale"].unique()))
        sub = agg[agg["model"] == model]
        for policy in ["fcfs", "phase"]:
            plot_line(
                ax,
                sub,
                "scale",
                "attainment_pct",
                policy,
                "-",
                label=POLICY_LABEL[policy],
            )
        if i == 0:
            ax.legend(frameon=False, loc="lower right", handlelength=1.8)
    fig.tight_layout(pad=0.45, w_pad=0.8)
    save_figure(fig, output_prefix)


def save_figure(fig: plt.Figure, output_prefix: Path) -> None:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        path = output_prefix.with_suffix(f".{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300)
    plt.close(fig)


def copy_to_paper(*pdfs: Path) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        shutil.copyfile(pdf, PAPER_DIR / pdf.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rate-points",
        default="1,2,3,4,5,6,8",
        help="Comma-separated per-GPU rates for the legacy 2x3 rate-sweep figure.",
    )
    parser.add_argument(
        "--ttft-rate-points",
        default="2,3,4,5,6,8",
        help="Comma-separated per-GPU rates for TTFT in the main latency figure.",
    )
    parser.add_argument(
        "--tpot-rate-points",
        default="2,3,4,5,6,8,10,12,14,16",
        help="Comma-separated per-GPU rates for TPOT in the main latency figure.",
    )
    parser.add_argument(
        "--slo-scale-rate",
        type=float,
        default=6.0,
        help="Fixed per-GPU rate for the SLO scale sensitivity figure.",
    )
    args = parser.parse_args()

    configure_matplotlib()
    rate_points = [float(x) for x in args.rate_points.split(",") if x.strip()]
    ttft_rates = [float(x) for x in args.ttft_rate_points.split(",") if x.strip()]
    tpot_rates = [float(x) for x in args.tpot_rate_points.split(",") if x.strip()]
    sweep = read_sweep_data()
    slo = read_slo_data()

    latency_prefix = FIG_DIR / "end_to_end_latency_rate_sweep"
    legacy_rate_prefix = FIG_DIR / "end_to_end_rate_sweep"
    scale_prefix = FIG_DIR / "slo_scale_sensitivity"
    plot_latency_rate_sweep(sweep, latency_prefix, ttft_rates, tpot_rates)
    plot_rate_sweep(sweep, slo, legacy_rate_prefix, rate_points)
    plot_slo_scale(slo, scale_prefix, args.slo_scale_rate)
    copy_to_paper(latency_prefix.with_suffix(".pdf"), scale_prefix.with_suffix(".pdf"))

    print(f"Wrote {latency_prefix.with_suffix('.pdf')}")
    print(f"Wrote {latency_prefix.with_suffix('.png')}")
    print(f"Wrote {latency_prefix.with_suffix('.svg')}")
    print(f"Wrote {legacy_rate_prefix.with_suffix('.pdf')} [legacy/exploratory]")
    print(f"Wrote {legacy_rate_prefix.with_suffix('.png')} [legacy/exploratory]")
    print(f"Wrote {legacy_rate_prefix.with_suffix('.svg')} [legacy/exploratory]")
    print(f"Wrote {scale_prefix.with_suffix('.pdf')}")
    print(f"Wrote {scale_prefix.with_suffix('.png')}")
    print(f"Wrote {scale_prefix.with_suffix('.svg')}")
    print(f"Copied PDFs to {PAPER_DIR}")


if __name__ == "__main__":
    main()
