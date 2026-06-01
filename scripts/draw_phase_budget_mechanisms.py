#!/usr/bin/env python3
"""Draw the detailed PhaseServe budgeted-mechanism figure.

Figure contract:
1. Core conclusion: PBC, BPS, and KAS are one typed action-space control
   system, not three independent heuristics.
2. Evidence chain: panel (a) maps pressure types to budget knobs and owners;
   panel (b) shows BPS changing the feasible prefill batch under those budgets;
   panel (c) shows KAS applying hard KV/swap gates before soft decode utility.
3. Archetype: schematic-led composite.
4. Backend: Python / matplotlib.
5. Export: editable SVG/PDF and high-DPI PNG.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


OUT_DIR = Path("results/figures/mechanism")
OUT_PREFIX = OUT_DIR / "phaseserve_budget_mechanisms"

COLORS = {
    "ink": "#172033",
    "muted": "#5b677a",
    "border": "#aab5c6",
    "panel": "#f8fafc",
    "pbc": "#fff2da",
    "pbc_edge": "#d98a16",
    "bps": "#eaf3ff",
    "bps_edge": "#4f8ee8",
    "kas": "#e9f8f1",
    "kas_edge": "#219e7a",
    "hard": "#f9e9ee",
    "hard_edge": "#cc3d5a",
    "soft": "#eef2f7",
    "arrow": "#2d5fd7",
    "budget": "#d98a16",
}


def configure() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "figure.facecolor": "white",
        }
    )


def box(ax, x, y, w, h, text, *, fc="white", ec=None, lw=0.9, size=7, weight="normal",
        color=None, radius=0.018, z=2):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        linewidth=lw,
        edgecolor=ec or COLORS["border"],
        facecolor=fc,
        zorder=z,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=size,
        fontweight=weight,
        color=color or COLORS["ink"],
        linespacing=1.2,
        zorder=z + 1,
    )
    return patch


def label(ax, x, y, s, *, size=8, weight="normal", color=None, ha="left", va="center"):
    ax.text(
        x,
        y,
        s,
        ha=ha,
        va=va,
        fontsize=size,
        fontweight=weight,
        color=color or COLORS["ink"],
        zorder=4,
    )


def arrow(ax, start, end, *, color=None, lw=1.4, style="-", rad=0.0, z=3):
    arr = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=lw,
        linestyle=style,
        color=color or COLORS["arrow"],
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=2,
        shrinkB=2,
        zorder=z,
    )
    ax.add_patch(arr)
    return arr


def panel_frame(ax, x, y, w, h, title, tag):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.016,rounding_size=0.02",
            linewidth=0.9,
            edgecolor=COLORS["border"],
            facecolor=COLORS["panel"],
            zorder=0,
        )
    )
    label(ax, x + 0.016, y + h - 0.045, f"({tag}) {title}", size=8.6, weight="bold")


def draw_pbc(ax):
    panel_frame(ax, 0.03, 0.09, 0.29, 0.82, "pressure-budget graph", "a")

    pressures = [
        ("Context\nqueue", 0.15),
        ("Bridge /\nfirst debt", 0.29),
        ("Decode\nbacklog", 0.43),
        ("Hard KV /\nswap", 0.57),
        ("Age /\nskip debt", 0.71),
    ]
    budgets = [
        ("B_pre\nM_pre", 0.18),
        ("R_bridge\nfirst slot", 0.34),
        ("I_dec\nL_scan", 0.50),
        ("B_swap\nhard gate", 0.66),
    ]
    owners = [
        ("BPS\ncontext owner", 0.22),
        ("KAS\nfirst-decode owner", 0.42),
        ("KAS\ndecode owner", 0.62),
    ]

    label(ax, 0.055, 0.80, "Pressure", size=7.5, weight="bold", color=COLORS["muted"])
    label(ax, 0.145, 0.80, "Budget", size=7.5, weight="bold", color=COLORS["muted"])
    label(ax, 0.235, 0.80, "Owner", size=7.5, weight="bold", color=COLORS["muted"])

    for text, y in pressures:
        fc = COLORS["hard"] if "Hard" in text else "white"
        ec = COLORS["hard_edge"] if "Hard" in text else COLORS["border"]
        box(ax, 0.05, y, 0.065, 0.075, text, fc=fc, ec=ec, size=6.2, weight="bold")
    for text, y in budgets:
        box(ax, 0.145, y, 0.07, 0.08, text, fc=COLORS["pbc"], ec=COLORS["pbc_edge"], size=6.2, weight="bold")
    for text, y in owners:
        box(ax, 0.24, y, 0.06, 0.09, text, fc="white", ec=COLORS["border"], size=6.2, weight="bold")

    # Main dependencies.
    arrow(ax, (0.115, 0.187), (0.145, 0.207), color=COLORS["budget"])
    arrow(ax, (0.115, 0.327), (0.145, 0.377), color=COLORS["budget"])
    arrow(ax, (0.115, 0.467), (0.145, 0.535), color=COLORS["budget"])
    arrow(ax, (0.115, 0.607), (0.145, 0.695), color=COLORS["hard_edge"])
    arrow(ax, (0.115, 0.747), (0.145, 0.705), color=COLORS["budget"], rad=-0.12)
    arrow(ax, (0.215, 0.22), (0.24, 0.26), color=COLORS["budget"])
    arrow(ax, (0.215, 0.38), (0.24, 0.46), color=COLORS["budget"])
    arrow(ax, (0.215, 0.54), (0.24, 0.66), color=COLORS["budget"])
    arrow(ax, (0.215, 0.70), (0.24, 0.66), color=COLORS["hard_edge"], rad=0.12)

    box(
        ax,
        0.055,
        0.10,
        0.235,
        0.035,
        "priority: hard gates -> safety\n-> progress -> regime utility",
        fc="white",
        ec=COLORS["border"],
        size=5.4,
        color=COLORS["muted"],
    )


def draw_bps(ax):
    panel_frame(ax, 0.355, 0.09, 0.29, 0.82, "BPS executor", "b")

    label(ax, 0.38, 0.79, "waiting prefill queue", size=7.5, weight="bold", color=COLORS["muted"])
    x0 = 0.385
    widths = [0.035, 0.065, 0.03, 0.09, 0.045, 0.075]
    colors = ["#9cc6ef", "#4f8ee8", "#9cc6ef", "#2d5fd7", "#9cc6ef", "#4f8ee8"]
    for i, (w, c) in enumerate(zip(widths, colors)):
        ax.add_patch(Rectangle((x0 + i * 0.04, 0.72), w, 0.018, facecolor=c, edgecolor="none", zorder=3))
    box(ax, 0.385, 0.64, 0.095, 0.06, "bounded\nwindow", fc="white", size=6.4, weight="bold")
    box(ax, 0.505, 0.64, 0.095, 0.06, "oldest\nprotected", fc="white", size=6.4, weight="bold")
    arrow(ax, (0.43, 0.72), (0.43, 0.70), color=COLORS["arrow"])
    arrow(ax, (0.55, 0.72), (0.55, 0.70), color=COLORS["arrow"])

    box(ax, 0.385, 0.52, 0.22, 0.065, "length buckets -> compatible candidates", fc=COLORS["bps"], ec=COLORS["bps_edge"], size=6.4, weight="bold")
    arrow(ax, (0.43, 0.64), (0.47, 0.59), color=COLORS["arrow"])
    arrow(ax, (0.55, 0.64), (0.53, 0.59), color=COLORS["arrow"])

    box(ax, 0.385, 0.39, 0.095, 0.075, "hard gates\nB_pre / M_pre\nGPU blocks", fc=COLORS["hard"], ec=COLORS["hard_edge"], size=5.8, weight="bold")
    box(ax, 0.51, 0.39, 0.095, 0.075, "soft score\nfill / pad\nrisk / age", fc=COLORS["soft"], ec=COLORS["border"], size=5.8, weight="bold")
    arrow(ax, (0.495, 0.52), (0.435, 0.47), color=COLORS["hard_edge"])
    arrow(ax, (0.495, 0.52), (0.555, 0.47), color=COLORS["budget"])

    box(ax, 0.41, 0.25, 0.165, 0.065, "prefill batch\nbounded KV injection", fc="white", ec=COLORS["bps_edge"], size=6.3, weight="bold")
    arrow(ax, (0.435, 0.39), (0.47, 0.315), color=COLORS["hard_edge"])
    arrow(ax, (0.555, 0.39), (0.52, 0.315), color=COLORS["budget"])

    box(ax, 0.39, 0.12, 0.205, 0.045, "ablation hook: w/o BPS", fc="white", ec=COLORS["border"], size=6.0, color=COLORS["muted"])


def draw_kas(ax):
    panel_frame(ax, 0.68, 0.09, 0.29, 0.82, "KAS executor", "c")

    label(ax, 0.705, 0.79, "ready decode candidates", size=7.5, weight="bold", color=COLORS["muted"])
    for i, c in enumerate(["#dbeafe", "#bbf7d0", "#fde68a", "#f8c7d3", "#dbeafe", "#bbf7d0"]):
        ax.add_patch(Rectangle((0.705 + i * 0.035, 0.72), 0.024, 0.024, facecolor=c, edgecolor=COLORS["border"], linewidth=0.4, zorder=3))

    box(ax, 0.705, 0.60, 0.22, 0.07, "hard feasibility gates\nslot + append block + swap budget", fc=COLORS["hard"], ec=COLORS["hard_edge"], size=5.9, weight="bold")
    arrow(ax, (0.81, 0.72), (0.81, 0.67), color=COLORS["hard_edge"])

    box(ax, 0.705, 0.47, 0.095, 0.075, "first-decode\nreserve", fc="white", ec=COLORS["kas_edge"], size=6.2, weight="bold")
    box(ax, 0.83, 0.47, 0.095, 0.075, "completion\ndrain", fc="white", ec=COLORS["kas_edge"], size=6.2, weight="bold")
    arrow(ax, (0.77, 0.60), (0.755, 0.545), color=COLORS["kas_edge"])
    arrow(ax, (0.86, 0.60), (0.88, 0.545), color=COLORS["kas_edge"])

    box(ax, 0.705, 0.34, 0.22, 0.07, "rank feasible set\nattained + age + residency + KV cost", fc=COLORS["soft"], ec=COLORS["border"], size=5.9, weight="bold")
    arrow(ax, (0.755, 0.47), (0.775, 0.41), color=COLORS["budget"])
    arrow(ax, (0.88, 0.47), (0.855, 0.41), color=COLORS["budget"])

    box(ax, 0.735, 0.22, 0.16, 0.065, "decode active set\nKV-safe iteration", fc="white", ec=COLORS["kas_edge"], size=6.3, weight="bold")
    arrow(ax, (0.815, 0.34), (0.815, 0.285), color=COLORS["kas_edge"])

    box(
        ax,
        0.705,
        0.105,
        0.22,
        0.045,
        "empty feasible set: record stall\nrather than bypass hard gates",
        fc="white",
        ec=COLORS["border"],
        size=6.0,
        color=COLORS["muted"],
    )
    box(ax, 0.705, 0.155, 0.22, 0.04, "ablation hook: w/o KAS", fc="white", ec=COLORS["border"], size=6.0, color=COLORS["muted"])


def draw() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    configure()
    fig = plt.figure(figsize=(7.2, 3.7), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    draw_pbc(ax)
    draw_bps(ax)
    draw_kas(ax)

    fig.savefig(OUT_PREFIX.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.04)
    fig.savefig(OUT_PREFIX.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.04)
    fig.savefig(OUT_PREFIX.with_suffix(".png"), dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)

    print(OUT_PREFIX.with_suffix(".pdf"))


if __name__ == "__main__":
    draw()
