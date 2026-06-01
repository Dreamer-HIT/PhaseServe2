#!/usr/bin/env python3
"""Plot Background/Motivation evidence for runtime pressure propagation.

Figure contract:
1. Core conclusion: runtime pressure in a phase-disaggregated baseline is
   multi-component, and the same traces expose hard-feasibility counters that
   justify a typed pressure interface.
2. Evidence chain: baseline TTFT/TPOT tails show symptoms; baseline queue
   stacks show where waiting accumulates; instrumented pressure counters show
   that hard feasibility and budget movement are distinct from queue latency.
3. Archetype: quantitative grid.
4. Backend: Python / matplotlib.
5. Export: editable SVG/PDF, high-DPI PNG, and CSV source data.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "results/stage4o_stage4p_plot_data/stage4o_e2e_full_matrix_20260531_234957"
OUT_DIR = ROOT / "results/figures/motivation"
SOURCE_OUT = OUT_DIR / "background_pressure_motivation_source.csv"

COMBOS = [
    ("opt13b_sharegpt", "OPT-13B + ShareGPT", "opt13b_sharegpt/sweep_summary.csv"),
    ("llama13b_sharegpt", "LLaMA2-13B + ShareGPT", "llama13b_sharegpt/sweep_summary.csv"),
    ("llama13b_longbench4k", "LLaMA2-13B + LongBench 4K", "llama13b_longbench4k/sweep_summary.csv"),
]

COLORS = {
    "OPT-13B + ShareGPT": "#2f6fbb",
    "LLaMA2-13B + ShareGPT": "#c45a2d",
    "LLaMA2-13B + LongBench 4K": "#2f8f6b",
}

QUEUE_COLORS = {
    "Context queue": "#4c78a8",
    "Bridge queue": "#f58518",
    "Decode queue": "#54a24b",
}

DIAG_COLORS = {
    "Bridge/first-token debt": "#cc5a43",
    "Hard KV/swap pressure": "#7b4fb2",
    "Prefill budget ratio": "#4c78a8",
    "Decode utility intensity": "#2f8f6b",
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
        -0.16,
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


def load_baseline() -> pd.DataFrame:
    frames = []
    for combo, label, relpath in COMBOS:
        df = pd.read_csv(DATA_ROOT / relpath).copy()
        df["combo"] = combo
        df["workload"] = label
        df["per_gpu_rate"] = df["request_rate"].astype(float) / df["num_gpus"].astype(float)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    return raw


def summarize(raw: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "policy",
        "ttft_s_p90",
        "tpot_s_p90",
        "context_queue_s_median",
        "bridge_queue_s_median",
        "decode_queue_s_median",
        "context_exec_s_median",
        "decode_exec_s_median",
        "phase_decode_handoff_debt_pressure_mean",
        "phase_decode_rho_hard_mean",
        "phase_decode_infeasible_rounds",
        "phase_context_prefill_budget_ratio_mean",
        "phase_decode_kas_intensity_mean",
    ]
    fields = [field for field in fields if field in raw.columns]
    grouped = (
        raw.groupby(["combo", "workload", "policy", "per_gpu_rate"], as_index=False)[
            [f for f in fields if f != "policy"]
        ]
        .mean(numeric_only=True)
        .sort_values(["combo", "policy", "per_gpu_rate"])
    )
    return grouped


def plot(summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(
        nrows=2,
        ncols=3,
        figsize=(7.2, 4.7),
        constrained_layout=True,
    )
    axes_flat = axes.ravel()

    rate_hi = 3.0
    baseline = summary[(summary["policy"] == "fcfs") & (summary["per_gpu_rate"] <= rate_hi)].copy()
    phase = summary[(summary["policy"] == "phase") & (summary["per_gpu_rate"] <= rate_hi)].copy()

    for panel_idx, (ax, metric, ylabel, title) in enumerate([
        (axes_flat[0], "ttft_s_p90", "P90 TTFT (s)", "First-token pressure"),
        (axes_flat[1], "tpot_s_p90", "P90 TPOT (s/token)", "Decode-token pressure"),
    ]):
        add_panel_label(ax, "abcdef"[panel_idx])
        ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.8)
        ax.set_xlabel("Per-GPU rate (req/s)")
        ax.set_ylabel(ylabel)
        ax.set_title(title, pad=5)
        ax.set_xlim(0.2, rate_hi + 0.05)
        ax.set_xticks([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
        for _, label, _ in COMBOS:
            curve = baseline[baseline["workload"] == label].sort_values("per_gpu_rate")
            ax.plot(
                curve["per_gpu_rate"],
                curve[metric],
                color=COLORS[label],
                marker="o",
                markersize=2.8,
                linewidth=1.35,
                label=label,
            )
        ymax = baseline[metric].max()
        ax.set_ylim(0, ymax * 1.12)

    queue_fields = [
        ("Context queue", "context_queue_s_median"),
        ("Bridge queue", "bridge_queue_s_median"),
        ("Decode queue", "decode_queue_s_median"),
    ]
    for panel_idx, (combo, title) in enumerate(
        [
            ("opt13b_sharegpt", "Queue mix: OPT-13B + ShareGPT"),
            ("llama13b_longbench4k", "Queue mix: LLaMA2 LongBench 4K"),
        ],
        start=3,
    ):
        ax = axes_flat[panel_idx]
        add_panel_label(ax, "abcdef"[panel_idx])
        q = baseline[
            (baseline["combo"] == combo)
            & (baseline["per_gpu_rate"].isin([0.5, 1.0, 1.5, 2.0, 2.5, 3.0]))
        ].sort_values("per_gpu_rate")
        x = np.arange(len(q))
        bottom = np.zeros(len(q))
        for label, field in queue_fields:
            vals = q[field].to_numpy(dtype=float)
            ax.bar(
                x,
                vals,
                bottom=bottom,
                color=QUEUE_COLORS[label],
                edgecolor="white",
                linewidth=0.4,
                width=0.72,
                label=label,
            )
            bottom += vals
        ax.set_xticks(x)
        ax.set_xticklabels([f"{r:.1f}" for r in q["per_gpu_rate"]])
        ax.set_xlabel("Per-GPU rate (req/s)")
        ax.set_ylabel("Median queue time (s)")
        ax.set_title(title, pad=5)
        ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.8)
        ax.set_ylim(0, max(bottom) * 1.15)

    # Panel (c): instrumented hard-feasibility pressure on the same traces.
    ax = axes_flat[2]
    add_panel_label(ax, "c")
    ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.8)
    ax.set_xlabel("Per-GPU rate (req/s)")
    ax.set_ylabel("Normalized pressure")
    ax.set_title("Hard-feasibility pressure", pad=5)
    ax.set_xlim(0.2, rate_hi + 0.05)
    ax.set_xticks([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    for _, label, _ in COMBOS:
        curve = phase[phase["workload"] == label].sort_values("per_gpu_rate")
        ax.plot(
            curve["per_gpu_rate"],
            curve["phase_decode_rho_hard_mean"],
            color=COLORS[label],
            marker="o",
            markersize=2.6,
            linewidth=1.25,
        )
    ax.set_ylim(0, 1.02)

    # Panel (f): budget movement under the strongest long-context pressure.
    ax = axes_flat[5]
    add_panel_label(ax, "f")
    q = phase[phase["combo"] == "llama13b_longbench4k"].sort_values("per_gpu_rate")
    ax.grid(True, axis="y", color="#d9dee7", linewidth=0.5, alpha=0.8)
    ax.set_xlabel("Per-GPU rate (req/s)")
    ax.set_ylabel("Budget value")
    ax.set_title("Budget response: LongBench 4K", pad=5)
    ax.set_xlim(0.2, rate_hi + 0.05)
    ax.set_xticks([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    ax.plot(
        q["per_gpu_rate"],
        q["phase_context_prefill_budget_ratio_mean"],
        color=DIAG_COLORS["Prefill budget ratio"],
        marker="s",
        markersize=2.5,
        linewidth=1.25,
        label="Prefill budget ratio",
    )
    ax.plot(
        q["per_gpu_rate"],
        q["phase_decode_kas_intensity_mean"],
        color=DIAG_COLORS["Decode utility intensity"],
        marker="^",
        markersize=2.5,
        linewidth=1.25,
        label="Decode utility intensity",
    )
    ax.set_ylim(0, 1.08)
    ax.legend(loc="lower right", handlelength=1.5)

    line_handles = [
        mlines.Line2D([], [], color=COLORS[label], marker="o", linewidth=1.4, markersize=3, label=label)
        for _, label, _ in COMBOS
    ]
    queue_handles = [
        mpl.patches.Patch(facecolor=QUEUE_COLORS[label], edgecolor="white", label=label)
        for label, _ in queue_fields
    ]
    fig.legend(
        handles=line_handles,
        loc="upper center",
        ncol=3,
        bbox_to_anchor=(0.5, 1.06),
        columnspacing=1.2,
        handlelength=1.7,
    )
    fig.legend(
        handles=queue_handles,
        loc="lower center",
        ncol=3,
        bbox_to_anchor=(0.34, -0.055),
        columnspacing=1.2,
        handlelength=1.4,
    )
    save_all(fig, OUT_DIR / "background_pressure_motivation")
    plt.close(fig)


def main() -> None:
    configure_matplotlib()
    raw = load_baseline()
    summary = summarize(raw)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SOURCE_OUT, index=False)
    plot(summary)


if __name__ == "__main__":
    main()
