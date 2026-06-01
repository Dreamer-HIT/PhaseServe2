#!/usr/bin/env python3
"""Draw a clean paper-style PhaseServe overview figure.

This intentionally avoids SVG authoring. Matplotlib exports a publication
preview PNG and a vector PDF while keeping all text deterministic.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


OUT_DIR = Path("results/figures/mechanism")
PNG_OUT = OUT_DIR / "phaseserve_overview_best.png"
PDF_OUT = OUT_DIR / "phaseserve_overview_best.pdf"


COLORS = {
    "ink": "#172033",
    "muted": "#5B677A",
    "border": "#AAB5C6",
    "prefill": "#EAF3FF",
    "prefill_edge": "#4F8EE8",
    "decode": "#E9F8F1",
    "decode_edge": "#219E7A",
    "bridge": "#F7F8FA",
    "control": "#FFF2DA",
    "control_edge": "#D98A16",
    "problem": "#FFF1F3",
    "pressure": "#D62F4B",
    "path": "#2D5FD7",
    "kv": "#087F74",
}


def rounded_box(
    ax,
    x,
    y,
    w,
    h,
    *,
    fc="white",
    ec=None,
    lw=1.2,
    radius=0.08,
    z=1,
):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.018,rounding_size={radius}",
        linewidth=lw,
        edgecolor=ec or COLORS["border"],
        facecolor=fc,
        zorder=z,
    )
    ax.add_patch(patch)
    return patch


def arrow(ax, start, end, *, color, lw=2.2, style="-", rad=0.0, z=3):
    arr = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=16,
        linewidth=lw,
        linestyle=style,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=0,
        shrinkB=0,
        zorder=z,
    )
    ax.add_patch(arr)
    return arr


def text(ax, x, y, s, *, size=10, weight="normal", color=None, ha="left", va="center"):
    ax.text(
        x,
        y,
        s,
        fontsize=size,
        fontweight=weight,
        color=color or COLORS["ink"],
        ha=ha,
        va=va,
        family="DejaVu Sans",
    )


def small_bar(ax, x, y, w, color):
    ax.add_patch(Rectangle((x, y), w, 0.012, linewidth=0, facecolor=color, zorder=3))


def draw_problem_panel(ax):
    rounded_box(ax, 0.03, 0.08, 0.23, 0.84, fc="white", lw=1.0, radius=0.035)
    text(ax, 0.055, 0.875, "(a) pressure after split", size=12, weight="bold")

    rounded_box(ax, 0.06, 0.67, 0.075, 0.105, fc="#FFF4CD", ec="#A88F39", lw=0.9, radius=0.018)
    rounded_box(ax, 0.165, 0.67, 0.075, 0.105, fc="#E8F2FF", ec="#6186AF", lw=0.9, radius=0.018)
    text(ax, 0.0975, 0.735, "Prefill", size=8, weight="bold", ha="center")
    text(ax, 0.0975, 0.705, "FCFS", size=7, weight="bold", color=COLORS["muted"], ha="center")
    text(ax, 0.2025, 0.735, "Decode", size=8, weight="bold", ha="center")
    text(ax, 0.2025, 0.705, "FCFS", size=7, weight="bold", color=COLORS["muted"], ha="center")
    small_bar(ax, 0.078, 0.683, 0.04, "#9CC6EF")
    small_bar(ax, 0.183, 0.683, 0.04, "#71BE76")
    arrow(ax, (0.138, 0.722), (0.162, 0.722), color=COLORS["ink"], lw=1.2)
    text(ax, 0.15, 0.745, "KV", size=6.5, weight="bold", color=COLORS["muted"], ha="center")

    rounded_box(ax, 0.065, 0.43, 0.17, 0.135, fc=COLORS["problem"], ec=COLORS["pressure"], lw=0.9, radius=0.02)
    text(ax, 0.081, 0.53, "Downstream pressure", size=8, weight="bold")
    text(ax, 0.081, 0.495, "bridge / first-token wait", size=7, color=COLORS["muted"])
    text(ax, 0.081, 0.462, "decode backlog / KV / swap", size=7, color=COLORS["muted"])
    arrow(ax, (0.202, 0.67), (0.202, 0.57), color=COLORS["pressure"], lw=1.4, style=(0, (3, 3)))
    arrow(ax, (0.098, 0.67), (0.123, 0.57), color=COLORS["pressure"], lw=1.4, style=(0, (3, 3)), rad=0.25)

    text(ax, 0.065, 0.315, "Observation", size=8, weight="bold")
    text(ax, 0.065, 0.275, "Disaggregation removes co-location,", size=7, color=COLORS["muted"])
    text(ax, 0.065, 0.242, "but pressure still crosses phases.", size=7, color=COLORS["muted"])


def draw_main_panel(ax):
    rounded_box(ax, 0.285, 0.08, 0.685, 0.84, fc="white", lw=1.0, radius=0.035)
    text(ax, 0.31, 0.875, "(b) PhaseServe overview", size=12, weight="bold")

    # PBC control plane.
    rounded_box(
        ax,
        0.46,
        0.69,
        0.325,
        0.15,
        fc=COLORS["control"],
        ec=COLORS["control_edge"],
        lw=1.15,
        radius=0.025,
        z=2,
    )
    text(ax, 0.485, 0.795, "PBC", size=12, weight="bold")
    text(ax, 0.545, 0.795, "pressure-budget controller", size=9, weight="bold")
    text(ax, 0.485, 0.75, "pressure  ->  regime/conflict owner  ->  typed budgets", size=8, color=COLORS["muted"])
    rounded_box(ax, 0.49, 0.705, 0.08, 0.035, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01, z=3)
    rounded_box(ax, 0.595, 0.705, 0.08, 0.035, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01, z=3)
    rounded_box(ax, 0.70, 0.705, 0.07, 0.035, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01, z=3)
    text(ax, 0.53, 0.722, "monitor", size=6.8, weight="bold", color=COLORS["muted"], ha="center")
    text(ax, 0.635, 0.722, "owner", size=6.8, weight="bold", color=COLORS["muted"], ha="center")
    text(ax, 0.735, 0.722, "mapper", size=6.8, weight="bold", color=COLORS["muted"], ha="center")

    # Runtime blocks.
    text(ax, 0.315, 0.565, "Requests", size=10, weight="bold")
    text(ax, 0.315, 0.525, "known prompt", size=7.5, color=COLORS["muted"])
    text(ax, 0.315, 0.495, "unknown output", size=7.5, color=COLORS["muted"])
    small_bar(ax, 0.315, 0.438, 0.075, "#A7CDED")
    small_bar(ax, 0.315, 0.392, 0.055, "#63AE5A")

    rounded_box(ax, 0.445, 0.34, 0.16, 0.25, fc=COLORS["prefill"], ec=COLORS["prefill_edge"], lw=1.05, radius=0.025)
    text(ax, 0.463, 0.555, "Prefill instance", size=10, weight="bold")
    text(ax, 0.463, 0.515, "BPS", size=8, weight="bold", color=COLORS["muted"])
    rounded_box(ax, 0.463, 0.455, 0.124, 0.04, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01)
    text(ax, 0.525, 0.475, "known-size buckets", size=7, weight="bold", color=COLORS["muted"], ha="center")
    rounded_box(ax, 0.463, 0.40, 0.124, 0.04, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01)
    text(ax, 0.525, 0.42, "token + block gates", size=7, weight="bold", color=COLORS["muted"], ha="center")
    text(ax, 0.525, 0.36, "protected oldest", size=7, color=COLORS["muted"], ha="center")

    rounded_box(ax, 0.635, 0.34, 0.12, 0.25, fc=COLORS["bridge"], ec=COLORS["border"], lw=1.05, radius=0.025)
    text(ax, 0.655, 0.555, "Bridge", size=10, weight="bold")
    text(ax, 0.655, 0.515, "KV handoff", size=7.5, color=COLORS["muted"])
    text(ax, 0.655, 0.485, "first-decode admission", size=7.5, color=COLORS["muted"])
    for i, c in enumerate(["#06B768", "#35C98F", "#9BE7C0", "#DDE5F0"]):
        ax.add_patch(Rectangle((0.655 + i * 0.024, 0.385), 0.017, 0.025, linewidth=0, facecolor=c, zorder=3))

    rounded_box(ax, 0.785, 0.34, 0.16, 0.25, fc=COLORS["decode"], ec=COLORS["decode_edge"], lw=1.05, radius=0.025)
    text(ax, 0.803, 0.555, "Decode instance", size=10, weight="bold")
    text(ax, 0.803, 0.515, "KAS", size=8, weight="bold", color=COLORS["muted"])
    rounded_box(ax, 0.803, 0.455, 0.124, 0.04, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01)
    text(ax, 0.865, 0.475, "hard gates before utility", size=7, weight="bold", color=COLORS["muted"], ha="center")
    rounded_box(ax, 0.803, 0.40, 0.124, 0.04, fc="white", ec=COLORS["border"], lw=0.8, radius=0.01)
    text(ax, 0.865, 0.42, "tail eligibility + drain", size=7, weight="bold", color=COLORS["muted"], ha="center")
    text(ax, 0.865, 0.36, "first-decode reserved", size=7, color=COLORS["muted"], ha="center")

    # Request/KV path.
    arrow(ax, (0.395, 0.465), (0.44, 0.465), color=COLORS["path"], lw=2.2)
    arrow(ax, (0.605, 0.465), (0.63, 0.465), color=COLORS["path"], lw=2.2)
    arrow(ax, (0.755, 0.465), (0.78, 0.465), color=COLORS["kv"], lw=2.2)
    arrow(ax, (0.945, 0.465), (0.965, 0.465), color=COLORS["kv"], lw=2.2)
    text(ax, 0.952, 0.498, "tokens", size=7, color=COLORS["muted"])

    # Pressure feedback into PBC.
    arrow(ax, (0.695, 0.595), (0.56, 0.685), color=COLORS["pressure"], lw=1.7, style=(0, (4, 3)), rad=0.12)
    arrow(ax, (0.865, 0.595), (0.705, 0.685), color=COLORS["pressure"], lw=1.7, style=(0, (4, 3)), rad=-0.12)

    # Budgets from PBC into action points.
    arrow(ax, (0.525, 0.69), (0.525, 0.595), color=COLORS["control_edge"], lw=2.0)
    arrow(ax, (0.635, 0.69), (0.695, 0.595), color=COLORS["control_edge"], lw=2.0, rad=0.05)
    arrow(ax, (0.735, 0.69), (0.865, 0.595), color=COLORS["control_edge"], lw=2.0, rad=0.05)

    # Legend.
    y = 0.17
    arrow(ax, (0.32, y), (0.36, y), color=COLORS["path"], lw=1.8)
    text(ax, 0.372, y, "request / KV path", size=6.8, color=COLORS["muted"])
    arrow(ax, (0.49, y), (0.53, y), color=COLORS["pressure"], lw=1.5, style=(0, (4, 3)))
    text(ax, 0.542, y, "pressure", size=6.8, color=COLORS["muted"])
    arrow(ax, (0.62, y), (0.66, y), color=COLORS["control_edge"], lw=1.8)
    text(ax, 0.672, y, "typed budget", size=6.8, color=COLORS["muted"])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(13.2, 6.0), dpi=260)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    draw_problem_panel(ax)
    draw_main_panel(ax)

    fig.savefig(PNG_OUT, dpi=260, bbox_inches="tight", pad_inches=0.08)
    fig.savefig(PDF_OUT, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)

    print(PNG_OUT)
    print(PDF_OUT)


if __name__ == "__main__":
    main()
