#!/usr/bin/env python3
"""Plot Stage 4R SLO comparison with vLLM."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGE4O = (
    ROOT
    / "results/stage4o_stage4p_plot_data"
    / "stage4o_e2e_full_matrix_20260531_234957"
    / "opt13b_sharegpt"
    / "sweep_summary.csv"
)

POLICY_LABELS = {
    "fcfs": "DistServe",
    "phase": "PhaseServe",
    "vllm": "vLLM",
}

COLORS = {
    "fcfs": "#6f7681",
    "phase": "#2b6cb0",
    "vllm": "#c2410c",
}

MARKERS = {
    "fcfs": "o",
    "phase": "s",
    "vllm": "^",
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
        -0.10,
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
    fig.savefig(path_prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")


def load_stage4o(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["policy"].isin(["fcfs", "phase"])].copy()
    df["per_gpu_rate"] = df["request_rate"].astype(float) / df["num_gpus"].astype(float)
    return df


def load_vllm(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    df = df[df["policy"].eq("vllm")]
    df["per_gpu_rate"] = df["request_rate"].astype(float) / df["num_gpus"].astype(float)
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "slo_attainment_completed",
        "throughput_per_gpu_goodput_req_s",
        "throughput_per_gpu_completed_req_s",
        "ttft_s_p90",
        "tpot_s_p90",
    ]
    return (
        df.groupby(["policy", "per_gpu_rate"], as_index=False)[metrics]
        .mean()
        .sort_values(["policy", "per_gpu_rate"])
    )


def plot_slo(df: pd.DataFrame, out_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.55), constrained_layout=True)
    panels = [
        (
            "slo_attainment_completed",
            "SLO attainment (%)",
            "SLO attainment",
            lambda s: s * 100,
            (0, 104),
        ),
        (
            "throughput_per_gpu_goodput_req_s",
            "Per-GPU SLO goodput (req/s/GPU)",
            "SLO goodput",
            lambda s: s,
            None,
        ),
    ]
    for ax, (metric, ylabel, title, transform, ylim), label in zip(axes, panels, "ab"):
        add_panel_label(ax, label)
        ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.8)
        for policy in ["fcfs", "vllm", "phase"]:
            sub = df[df["policy"].eq(policy)]
            if sub.empty:
                continue
            ax.plot(
                sub["per_gpu_rate"],
                transform(sub[metric]),
                color=COLORS[policy],
                marker=MARKERS[policy],
                markersize=3.0,
                linewidth=1.55,
                label=POLICY_LABELS[policy],
            )
        ax.set_title(title, pad=4)
        ax.set_xlabel("Per-GPU rate (req/s)")
        ax.set_ylabel(ylabel)
        ax.set_xticks([0.75, 1.0, 1.5, 2.0, 2.5, 3.0])
        ax.set_xlim(0.70, 3.05)
        if ylim:
            ax.set_ylim(*ylim)
    axes[0].legend(loc="lower left")
    save_all(fig, out_dir / "stage4r_slo_vllm_opt13b_sharegpt")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage4o", type=Path, default=DEFAULT_STAGE4O)
    parser.add_argument("--vllm", type=Path, required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "results/figures/stage4r_slo_vllm",
    )
    args = parser.parse_args()
    configure_matplotlib()
    combined = pd.concat([load_stage4o(args.stage4o), load_vllm(args.vllm)], ignore_index=True)
    combined = aggregate(combined)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.out_dir / "stage4r_slo_vllm_opt13b_sharegpt_source.csv", index=False)
    plot_slo(combined, args.out_dir)
    print(f"Wrote SLO vLLM figure to {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
