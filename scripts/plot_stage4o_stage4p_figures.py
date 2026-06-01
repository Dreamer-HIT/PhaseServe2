#!/usr/bin/env python3
"""Plot Stage 4O end-to-end and Stage 4P ablation figures."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COMBOS = [
    (
        "OPT-13B + ShareGPT",
        "opt13b_sharegpt",
        "stage4o_e2e_full_matrix_20260531_234957/opt13b_sharegpt/sweep_summary.csv",
    ),
    (
        "LLaMA2-13B + ShareGPT",
        "llama13b_sharegpt",
        "stage4o_e2e_full_matrix_20260531_234957/llama13b_sharegpt/sweep_summary.csv",
    ),
    (
        "LLaMA2-13B + LongBench 4K",
        "llama13b_longbench4k",
        "stage4o_e2e_full_matrix_20260531_234957/llama13b_longbench4k/sweep_summary.csv",
    ),
]

POLICY_LABELS = {
    "fcfs": "DistServe",
    "phase": "PhaseServe",
    "bps_kas": "w/o PBC",
    "kas_pbc": "w/o BPS",
    "bps_pbc": "w/o KAS",
}

COLORS = {
    "fcfs": "#6f7681",
    "phase": "#2b6cb0",
    "bps_kas": "#d97706",
    "kas_pbc": "#7c3aed",
    "bps_pbc": "#059669",
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


def save_all(fig: mpl.figure.Figure, path_prefix: Path) -> None:
    path_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_prefix.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(path_prefix.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(path_prefix.with_suffix(".png"), dpi=300, bbox_inches="tight")


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


def load_e2e(data_root: Path) -> pd.DataFrame:
    frames = []
    for title, combo, relpath in COMBOS:
        df = pd.read_csv(data_root / relpath).copy()
        df["combo_title"] = title
        df["combo"] = combo
        df["per_gpu_rate"] = df["request_rate"].astype(float) / df["num_gpus"].astype(float)
        df["policy_label"] = df["policy"].map(POLICY_LABELS)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    metrics = [
        "slo_attainment_completed",
        "goodput_req_s",
        "throughput_completed_req_s",
        "ttft_s_median",
        "ttft_s_p90",
        "ttft_s_p99",
        "tpot_s_median",
        "tpot_s_p90",
        "tpot_s_p99",
    ]
    grouped = (
        raw.groupby(["combo", "combo_title", "policy", "policy_label", "per_gpu_rate"], as_index=False)[
            metrics
        ]
        .mean()
        .sort_values(["combo", "policy", "per_gpu_rate"])
    )
    return grouped


def plot_e2e(e2e: pd.DataFrame, out_dir: Path) -> None:
    fig, axes = plt.subplots(
        nrows=3,
        ncols=3,
        figsize=(7.2, 6.6),
        sharex=False,
        constrained_layout=True,
    )
    panel_labels = iter("abcdefghi")
    for row, (title, combo, _) in enumerate(COMBOS):
        sub = e2e[e2e["combo"] == combo]
        for col in range(3):
            ax = axes[row, col]
            add_panel_label(ax, next(panel_labels))
            ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.7)
            ax.set_xlim(0.2, 5.05)
            ax.set_xticks([0.25, 1, 2, 3, 4, 5])
            ax.set_xlabel("Per-GPU rate (req/s)")
            if col == 0:
                ax.set_title(f"{title}\nSLO attainment", pad=5)
                ax.set_ylabel("SLO attainment (%)")
                ax.set_ylim(-2, 102)
                for policy in ["fcfs", "phase"]:
                    s = sub[sub["policy"] == policy]
                    ax.plot(
                        s["per_gpu_rate"],
                        s["slo_attainment_completed"] * 100,
                        marker="o",
                        markersize=2.6,
                        linewidth=1.5,
                        color=COLORS[policy],
                        label=POLICY_LABELS[policy],
                    )
            elif col == 1:
                ax.set_title(f"{title}\nTTFT tail", pad=5)
                ax.set_ylabel("TTFT (s, log)")
                ax.set_yscale("log")
                for policy in ["fcfs", "phase"]:
                    s = sub[sub["policy"] == policy]
                    for metric, style, pct in [
                        ("ttft_s_p90", "-", "p90"),
                        ("ttft_s_p99", "--", "p99"),
                    ]:
                        ax.plot(
                            s["per_gpu_rate"],
                            s[metric],
                            marker="o",
                            markersize=2.4,
                            linewidth=1.35,
                            linestyle=style,
                            color=COLORS[policy],
                            label=f"{POLICY_LABELS[policy]} {pct}",
                        )
            else:
                ax.set_title(f"{title}\nTPOT tail", pad=5)
                ax.set_ylabel("TPOT (s/token, log)")
                ax.set_yscale("log")
                for policy in ["fcfs", "phase"]:
                    s = sub[sub["policy"] == policy]
                    for metric, style, pct in [
                        ("tpot_s_p90", "-", "p90"),
                        ("tpot_s_p99", "--", "p99"),
                    ]:
                        ax.plot(
                            s["per_gpu_rate"],
                            s[metric],
                            marker="o",
                            markersize=2.4,
                            linewidth=1.35,
                            linestyle=style,
                            color=COLORS[policy],
                            label=f"{POLICY_LABELS[policy]} {pct}",
                        )
            if row == 0:
                ax.legend(loc="best", handlelength=2.2)
    save_all(fig, out_dir / "stage4o_end_to_end_full_matrix")
    plt.close(fig)


def plot_ablation_lines(data_root: Path, out_dir: Path) -> pd.DataFrame:
    mean_path = (
        data_root
        / "stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.mean.csv"
    )
    df = pd.read_csv(mean_path).sort_values(["policy", "per_gpu_rate"])
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.7), constrained_layout=True)
    panels = [
        ("slo_attainment_completed_mean", "SLO attainment (%)", False, "a"),
        ("ttft_p90_mean", "TTFT p90 (s, log)", True, "b"),
        ("tpot_p90_mean", "TPOT p90 (s/token, log)", True, "c"),
        ("tpot_p99_mean", "TPOT p99 (s/token, log)", True, "d"),
    ]
    for ax, (metric, ylabel, logy, panel) in zip(axes.flat, panels):
        add_panel_label(ax, panel)
        ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.7)
        for policy in ["fcfs", "phase", "bps_kas", "kas_pbc", "bps_pbc"]:
            s = df[df["policy"] == policy]
            y = s[metric] * 100 if metric.startswith("slo_") else s[metric]
            ax.plot(
                s["per_gpu_rate"],
                y,
                marker="o",
                markersize=2.8,
                linewidth=1.45,
                color=COLORS[policy],
                label=POLICY_LABELS[policy],
            )
        ax.set_xlabel("Per-GPU rate (req/s)")
        ax.set_ylabel(ylabel)
        ax.set_xticks([0.75, 1, 1.5, 2, 2.5])
        if logy:
            ax.set_yscale("log")
        if metric.startswith("slo_"):
            ax.set_ylim(0, 100)
    axes[0, 0].legend(ncol=2, loc="best")
    fig.suptitle("OPT-13B + ShareGPT targeted component ablation", fontsize=9)
    save_all(fig, out_dir / "stage4p_ablation_raw_curves")
    plt.close(fig)
    return df


def plot_ablation_heatmap(data_root: Path, out_dir: Path) -> None:
    comp_path = (
        data_root
        / "stage4p_targeted_ablation_20260601_101528/opt13b_sharegpt_ablation/stage4p_merged_ablation.comparisons.csv"
    )
    df = pd.read_csv(comp_path)
    df = df[~df["policy"].isin(["fcfs", "phase"])].copy()
    metrics = [
        ("slo_attainment_completed_full_vs_ablation_pp", "SLO +pp"),
        ("ttft_p90_full_vs_ablation_pct", "TTFT p90 %"),
        ("ttft_p99_full_vs_ablation_pct", "TTFT p99 %"),
        ("tpot_p90_full_vs_ablation_pct", "TPOT p90 %"),
        ("tpot_p99_full_vs_ablation_pct", "TPOT p99 %"),
    ]
    fig, axes = plt.subplots(
        nrows=1,
        ncols=len(metrics),
        figsize=(7.2, 2.6),
        constrained_layout=True,
        sharey=False,
    )
    rates = sorted(df["per_gpu_rate"].unique())
    labels = ["w/o PBC", "w/o BPS", "w/o KAS"]
    policies = ["bps_kas", "kas_pbc", "bps_pbc"]
    for idx, (ax, (metric, title)) in enumerate(zip(axes, metrics)):
        matrix = []
        for policy in policies:
            s = df[df["policy"] == policy].set_index("per_gpu_rate").reindex(rates)
            matrix.append(s[metric].to_numpy(dtype=float))
        matrix = np.asarray(matrix)
        vmax = max(25, np.nanmax(np.abs(matrix)))
        im = ax.imshow(matrix, aspect="auto", cmap="RdBu", vmin=-vmax, vmax=vmax)
        add_panel_label(ax, chr(ord("a") + idx))
        ax.set_title(title, pad=5)
        ax.set_xticks(range(len(rates)))
        ax.set_xticklabels([f"{r:g}" for r in rates], rotation=45, ha="right")
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels if idx == 0 else [])
        ax.tick_params(axis="y", labelleft=(idx == 0))
        if idx == 0:
            ax.set_ylabel("Ablation")
        ax.set_xlabel("Per-GPU rate")
        for y in range(matrix.shape[0]):
            for x in range(matrix.shape[1]):
                value = matrix[y, x]
                color = "white" if abs(value) > vmax * 0.55 else "#1f2933"
                ax.text(x, y, f"{value:.0f}", ha="center", va="center", fontsize=5.6, color=color)
        cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.02)
        cbar.ax.tick_params(labelsize=5.5, length=2)
    fig.suptitle("Full PhaseServe improvement over component ablations", fontsize=9)
    save_all(fig, out_dir / "stage4p_ablation_improvement_heatmap")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("results/stage4o_stage4p_plot_data"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/figures/stage4o_stage4p"),
    )
    args = parser.parse_args()
    configure_matplotlib()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    e2e = load_e2e(args.data_root)
    e2e.to_csv(args.out_dir / "stage4o_end_to_end_seed_mean_source.csv", index=False)
    plot_e2e(e2e, args.out_dir)
    ablation = plot_ablation_lines(args.data_root, args.out_dir)
    ablation.to_csv(args.out_dir / "stage4p_ablation_seed_mean_source.csv", index=False)
    plot_ablation_heatmap(args.data_root, args.out_dir)
    print(f"Wrote figures to {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
