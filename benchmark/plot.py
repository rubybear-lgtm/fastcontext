#!/usr/bin/env python3
"""Plot FastContext quantization benchmark results."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

RESULTS_DIR = Path(__file__).parent / "results"


def load_results():
    with open(RESULTS_DIR / "comparison.json") as f:
        return json.load(f)


def plot_comparison(data):
    agg = data["aggregate"]

    models = list(agg.keys())
    bits_per_weight = {
        "4bit-mattrobenolt": 4.5,
        "affine4-g64": 4.5,
        "affine4-g32": 5.0,
        "affine8": 8.5,
        "affine3": 3.5,
    }
    model_sizes = {
        "4bit-mattrobenolt": 2.1,
        "affine4-g64": 2.1,
        "affine4-g32": 2.4,
        "affine8": 4.0,
        "affine3": 1.7,
    }
    labels = [
        "3-bit\n(1.7G)",
        "4-bit g64\nmattrobenolt\n(2.1G)",
        "4-bit g64\nours\n(2.1G)",
        "4-bit g32\nours\n(2.4G)",
        "8-bit\nours\n(4.0G)",
    ]
    order = ["affine3", "4bit-mattrobenolt", "affine4-g64", "affine4-g32", "affine8"]

    file_f1 = [agg[m]["file_f1_mean"] for m in order]
    line_f1 = [agg[m]["line_f1_mean"] for m in order]
    avg_time = [agg[m]["elapsed_mean"] for m in order]
    bpw = [bits_per_weight[m] for m in order]

    colors = ["#e74c3c", "#95a5a6", "#3498db", "#2ecc71", "#9b59b6"]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    fig.suptitle("FastContext Quantization Benchmark\n(10 SWE-bench Multilingual instances)",
                 fontsize=14, fontweight="bold", y=1.02)

    # Plot 1: File F1
    ax = axes[0]
    bars = ax.bar(range(len(order)), file_f1, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("File F1 (higher = better)")
    ax.set_title("File-Level F1")
    ax.set_ylim(0, 0.65)
    for bar, val in zip(bars, file_f1):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{val:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    # Plot 2: Line F1
    ax = axes[1]
    bars = ax.bar(range(len(order)), line_f1, color=colors, edgecolor="white", linewidth=0.5)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Line F1 (higher = better)")
    ax.set_title("Line-Level F1")
    ax.set_ylim(0, 0.20)
    for bar, val in zip(bars, line_f1):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                f"{val:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    # Plot 3: Quality vs Size scatter
    ax = axes[2]
    for i, m in enumerate(order):
        ax.scatter(bpw[i], file_f1[i], s=150, c=colors[i], edgecolors="black",
                   linewidth=0.5, zorder=5)
        ax.annotate(order[i].replace("4bit-mattrobenolt", "matt-4bit"),
                    (bpw[i], file_f1[i]),
                    textcoords="offset points", xytext=(8, 5), fontsize=8)
    ax.set_xlabel("Bits per Weight")
    ax.set_ylabel("File F1")
    ax.set_title("Quality vs Model Size")
    ax.set_xlim(2.5, 9.5)
    ax.set_ylim(-0.02, 0.60)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = RESULTS_DIR / "benchmark_comparison.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {out_path}")

    # Also create a per-instance heatmap
    plot_heatmap(data)


def plot_heatmap(data):
    per_instance = data["per_instance"]
    order = ["affine3", "4bit-mattrobenolt", "affine4-g64", "affine4-g32", "affine8"]
    available = [m for m in order if m in per_instance]

    instance_ids = [r["instance_id"] for r in per_instance[available[0]]]
    short_ids = [iid.split("__")[-1] for iid in instance_ids]

    matrix = []
    for m in available:
        row = []
        for r in per_instance[m]:
            fs = r.get("file_scores", {})
            row.append(fs.get("f1", 0.0))
        matrix.append(row)

    fig, ax = plt.subplots(figsize=(12, 4))
    im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(range(len(short_ids)))
    ax.set_xticklabels(short_ids, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(available)))
    ax.set_yticklabels(available, fontsize=9)

    for i in range(len(available)):
        for j in range(len(short_ids)):
            val = matrix[i][j]
            color = "white" if val > 0.5 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

    ax.set_title("File F1 per Instance (green = better)", fontsize=12, fontweight="bold")
    plt.colorbar(im, ax=ax, label="File F1", shrink=0.8)
    plt.tight_layout()

    out_path = RESULTS_DIR / "benchmark_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved heatmap to {out_path}")


if __name__ == "__main__":
    data = load_results()
    plot_comparison(data)
