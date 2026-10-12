"""
Generate high-resolution dark-mode visual benchmark charts for CustomerLens README.
Outputs:
1. assets/benchmark_accuracy.png
2. assets/benchmark_latency.png
3. assets/customer_lifecycle_matrix.png
"""

import os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Root assets directory
repo_root = Path(__file__).resolve().parent.parent.parent
assets_dir = repo_root / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)

# GitHub Dark Theme Palette
BG_COLOR = "#0d1117"
PANEL_COLOR = "#161b22"
BORDER_COLOR = "#30363d"
TEXT_COLOR = "#e6edf3"
MUTED_TEXT = "#8b949e"
ACCENT_BLUE = "#58a6ff"
ACCENT_GREEN = "#3fb950"
ACCENT_RED = "#f85149"
ACCENT_PURPLE = "#bc8cff"
ACCENT_ORANGE = "#d29922"
ACCENT_CYAN = "#39c5bb"

plt.rcParams.update({
    "figure.facecolor": BG_COLOR,
    "axes.facecolor": PANEL_COLOR,
    "axes.edgecolor": BORDER_COLOR,
    "axes.labelcolor": TEXT_COLOR,
    "text.color": TEXT_COLOR,
    "xtick.color": MUTED_TEXT,
    "ytick.color": MUTED_TEXT,
    "grid.color": BORDER_COLOR,
    "grid.linestyle": "--",
    "grid.alpha": 0.5,
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"],
})


def generate_accuracy_chart():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), facecolor=BG_COLOR)
    fig.suptitle(
        "CUSTOMERLENS BIOMETRIC ACCURACY BENCHMARK (YTF DATASET)",
        fontsize=16,
        fontweight="bold",
        color=TEXT_COLOR,
        y=0.98,
    )

    # Subplot 1: Distribution Curves (Genuine vs Impostor)
    x = np.linspace(-0.3, 1.0, 500)
    # Impostor: mean=0.006, std=0.114
    impostor_dist = np.exp(-0.5 * ((x - 0.006) / 0.114) ** 2) / (0.114 * np.sqrt(2 * np.pi))
    # Genuine: mean=0.530, std=0.193
    genuine_dist = np.exp(-0.5 * ((x - 0.530) / 0.193) ** 2) / (0.193 * np.sqrt(2 * np.pi))

    ax1.plot(x, impostor_dist, color=ACCENT_RED, lw=2.5, label="Impostor Pairs (Diff Person)\nMean: 0.006 ± 0.114")
    ax1.fill_between(x, impostor_dist, color=ACCENT_RED, alpha=0.25)

    ax1.plot(x, genuine_dist, color=ACCENT_GREEN, lw=2.5, label="Genuine Pairs (Same Person)\nMean: 0.530 ± 0.193")
    ax1.fill_between(x, genuine_dist, color=ACCENT_GREEN, alpha=0.25)

    # Threshold line
    ax1.axvline(0.55, color=ACCENT_ORANGE, lw=2, linestyle="--", label="System Threshold (θ = 0.55)\nZero False Acceptance (FAR = 0%)")
    ax1.axvline(0.166, color=ACCENT_BLUE, lw=1.5, linestyle=":", label="EER Threshold (θ* = 0.166 | EER = 7.3%)")

    ax1.set_title("Cosine Similarity Distribution & Separation Margin", fontsize=12, fontweight="bold", pad=12)
    ax1.set_xlabel("Cosine Similarity Score", fontsize=11)
    ax1.set_ylabel("Probability Density", fontsize=11)
    ax1.set_xlim(-0.3, 1.0)
    ax1.grid(True)
    ax1.legend(loc="upper right", framealpha=0.9, facecolor=PANEL_COLOR, edgecolor=BORDER_COLOR, fontsize=8.5)

    # Subplot 2: Bar Chart - Identification & Accuracy Metrics
    metrics = [
        ("Rank-1 Accuracy", 87.37, ACCENT_BLUE),
        ("Rank-5 Accuracy", 91.58, ACCENT_GREEN),
        ("TAR @ FAR=1.0%", 86.32, ACCENT_CYAN),
        ("TAR @ FAR=0.1%", 85.26, ACCENT_PURPLE),
        ("Precision (θ=0.55)", 100.0, ACCENT_ORANGE),
        ("Verification Acc", 82.18, "#79c0ff"),
    ]
    labels = [m[0] for m in metrics]
    values = [m[1] for m in metrics]
    colors = [m[2] for m in metrics]

    y_pos = np.arange(len(labels))
    bars = ax2.barh(y_pos, values, color=colors, height=0.6, edgecolor=BORDER_COLOR)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(labels, fontsize=10, fontweight="bold")
    ax2.invert_yaxis()
    ax2.set_xlim(0, 115)
    ax2.set_xlabel("Accuracy / Percentage (%)", fontsize=11)
    ax2.set_title("1:N Identification & 1:1 Verification Metrics", fontsize=12, fontweight="bold", pad=12)
    ax2.grid(True, axis="x")

    for bar, val in zip(bars, values):
        ax2.text(
            val + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}%",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
            color=TEXT_COLOR,
        )

    plt.tight_layout()
    out_file = assets_dir / "benchmark_accuracy.png"
    plt.savefig(out_file, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"[OK] Generated: {out_file}")


def generate_latency_chart():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.2), facecolor=BG_COLOR)
    fig.suptitle(
        "CUSTOMERLENS PIPELINE LATENCY BREAKDOWN & THROUGHPUT",
        fontsize=16,
        fontweight="bold",
        color=TEXT_COLOR,
        y=0.98,
    )

    # Subplot 1: Pipeline Breakdown
    stages = [
        "1. SCRFD Face Detection",
        "2. EdgeFace INT8 Embed",
        "3. Biometric Security Protect",
        "4. Kalman & IoU Tracker",
    ]
    latencies = [2.31, 29.61, 0.09, 0.27]
    p95_latencies = [2.88, 35.35, 0.14, 0.33]
    colors = [ACCENT_BLUE, ACCENT_CYAN, ACCENT_PURPLE, ACCENT_GREEN]

    y_pos = np.arange(len(stages))
    bars = ax1.barh(y_pos, latencies, color=colors, height=0.55, edgecolor=BORDER_COLOR, label="Mean Latency (ms)")
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(stages, fontsize=10, fontweight="bold")
    ax1.invert_yaxis()
    ax1.set_xlim(0, 40)
    ax1.set_xlabel("Processing Time per Frame (ms)", fontsize=11)
    ax1.set_title("End-to-End Latency Breakdown (Mean: 32.29 ms)", fontsize=12, fontweight="bold", pad=12)
    ax1.grid(True, axis="x")

    for bar, mean_val, p95_val in zip(bars, latencies, p95_latencies):
        ax1.text(
            mean_val + 0.8,
            bar.get_y() + bar.get_height() / 2,
            f"{mean_val:.2f} ms (P95: {p95_val:.2f} ms)",
            va="center",
            ha="left",
            fontsize=9.5,
            fontweight="bold",
            color=TEXT_COLOR,
        )

    # Subplot 2: Throughput FPS vs Standard Video Frequencies
    fps_labels = [
        "CustomerLens E2E\n(Measured)",
        "Standard Target\n(30 FPS Stream)",
        "RTSP Camera\n(25 FPS Stream)",
        "Minimum Realtime\n(15 FPS Target)",
    ]
    fps_values = [30.34, 30.0, 25.0, 15.0]
    fps_colors = [ACCENT_GREEN, ACCENT_BLUE, ACCENT_PURPLE, ACCENT_ORANGE]

    x_pos = np.arange(len(fps_labels))
    bars2 = ax2.bar(x_pos, fps_values, color=fps_colors, width=0.55, edgecolor=BORDER_COLOR)
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(fps_labels, fontsize=9.5, fontweight="bold")
    ax2.set_ylim(0, 38)
    ax2.set_ylabel("Throughput (Frames Per Second)", fontsize=11)
    ax2.set_title("System Frame Rate Capacity vs Real-Time Standards", fontsize=12, fontweight="bold", pad=12)
    ax2.grid(True, axis="y")

    # Add 30 FPS guideline
    ax2.axhline(30.0, color="#ffffff", linestyle=":", alpha=0.4)

    for bar, val in zip(bars2, fps_values):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            val + 1.0,
            f"{val:.2f} FPS" if val == 30.34 else f"{int(val)} FPS",
            va="bottom",
            ha="center",
            fontsize=10,
            fontweight="bold",
            color=TEXT_COLOR,
        )

    plt.tight_layout()
    out_file = assets_dir / "benchmark_latency.png"
    plt.savefig(out_file, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"[OK] Generated: {out_file}")


def generate_lifecycle_matrix_chart():
    fig, ax = plt.subplots(figsize=(11, 6.2), facecolor=BG_COLOR)
    fig.suptitle(
        "CUSTOMERLENS 2-LETTER DYNAMIC LIFECYCLE MATRIX",
        fontsize=16,
        fontweight="bold",
        color=TEXT_COLOR,
        y=0.96,
    )

    tiers_y = ["H (High / VIP)", "M (Medium / Mass)", "L (Low / Budget)"]
    stages_x = ["N (New Guest / 1 visit)", "C (Casual / 2-4 visits)", "L (Loyal / ≥5 visits)"]

    matrix_codes = [
        ["HN", "HC", "HL"],
        ["MN", "MC", "ML"],
        ["LN", "LC", "LL"],
    ]

    matrix_desc = [
        ["VIP • New\n(VIP lần đầu)", "VIP • Casual\n(VIP vãng lai)", "VIP • Loyal\n(VIP thân thiết)"],
        ["Mass • New\n(Tầm trung mới)", "Mass • Casual\n(Tầm trung vãng lai)", "Mass • Loyal\n(Tầm trung quen thuộc)"],
        ["Budget • New\n(MẶC ĐỊNH KHÁCH MỚI)", "Budget • Casual\n(Khách vãng lai)", "Budget • Loyal\n(Khách quen gắn bó)"],
    ]

    cell_colors = [
        ["#271c3b", "#362159", "#4a1b7e"],
        ["#1c2d3b", "#1c3d52", "#1c4f6b"],
        ["#133827", "#1a4d33", "#236642"],
    ]

    # Draw cells
    for row in range(3):
        for col in range(3):
            code = matrix_codes[row][col]
            desc = matrix_desc[row][col]
            c_bg = cell_colors[row][col]
            rect = patches.Rectangle(
                (col, 2 - row), 1, 1,
                facecolor=c_bg,
                edgecolor=BORDER_COLOR,
                linewidth=2,
            )
            ax.add_patch(rect)

            # Code text
            code_color = ACCENT_ORANGE if code == "LN" else (ACCENT_GREEN if code == "HL" else ACCENT_CYAN)
            ax.text(
                col + 0.5, 2 - row + 0.65,
                code,
                ha="center", va="center",
                fontsize=20, fontweight="bold",
                color=code_color,
            )
            # Desc text
            ax.text(
                col + 0.5, 2 - row + 0.30,
                desc,
                ha="center", va="center",
                fontsize=9.5, fontweight="normal",
                color=TEXT_COLOR,
            )

    # Highlight Transition Arrow: LN -> LC -> LL -> ML -> HL
    # Path 1: LN (col 0, y 0) -> LC (col 1, y 0) -> LL (col 2, y 0)
    ax.annotate("", xy=(0.88, 0.5), xytext=(0.58, 0.5),
                arrowprops=dict(arrowstyle="->", color=ACCENT_ORANGE, lw=3))
    ax.annotate("", xy=(1.88, 0.5), xytext=(1.58, 0.5),
                arrowprops=dict(arrowstyle="->", color=ACCENT_ORANGE, lw=3))
    # Path 2: LL (col 2, y 0) -> ML (col 2, y 1)
    ax.annotate("", xy=(2.5, 1.15), xytext=(2.5, 0.85),
                arrowprops=dict(arrowstyle="->", color=ACCENT_CYAN, lw=3))
    # Path 3: ML (col 2, y 1) -> HL (col 2, y 2)
    ax.annotate("", xy=(2.5, 2.15), xytext=(2.5, 1.85),
                arrowprops=dict(arrowstyle="->", color=ACCENT_GREEN, lw=3))

    # Flow Banner
    ax.text(
        1.5, -0.28,
        "Lộ trình chuyển đổi tự động: LN1 (Mới) -> LC1 (Ghé 2 lần) -> LL1 (Ghé 5 lần) -> ML1 (Chi tiêu 3.5M) -> HL1 (Hạng VIP)",
        ha="center", va="center",
        fontsize=10.5, fontweight="bold",
        color="#7ee787",
        bbox=dict(boxstyle="round,pad=0.5", facecolor=PANEL_COLOR, edgecolor="#238636", lw=1.5),
    )

    ax.set_xlim(0, 3)
    ax.set_ylim(-0.4, 3)
    ax.set_xticks([0.5, 1.5, 2.5])
    ax.set_xticklabels(stages_x, fontsize=11, fontweight="bold")
    ax.set_yticks([0.5, 1.5, 2.5])
    ax.set_yticklabels(reversed(tiers_y), fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", which="both", length=0)

    # Clean borders
    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()
    out_file = assets_dir / "customer_lifecycle_matrix.png"
    plt.savefig(out_file, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"[OK] Generated: {out_file}")


if __name__ == "__main__":
    generate_accuracy_chart()
    generate_latency_chart()
    generate_lifecycle_matrix_chart()
