#!/usr/bin/env python3
"""
Full-coverage variant of fig:rq1-heatmap.

Draws the class-assignment heatmap for every language that appears in at
least --min-areas research areas, rather than the top 40 most variable
languages. Same colour scheme and sort order as the original figure.

Designed for appendix inclusion when reviewers want to see beyond the
top-N cap.

Usage:
  python heatmap_all_multi_area.py \
      --input    area_classifications.csv \
      --output   figures/fig_heatmap_all_multi_area.pdf \
      --min-areas 5 \
      --exclude-areas T31
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

sns.set_theme(style="white", context="paper")
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.bbox": "tight",
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

CLASS_PALETTE = {
    0: "#6e0202",
    1: "#cc4c02",
    2: "#f0a202",
    3: "#a3c440",
    4: "#3d9970",
    5: "#024d33",
}
CLASS_NAMES = {
    0: "Left-Behinds",
    1: "Scraping-Bys",
    2: "Hopefuls",
    3: "Rising Stars",
    4: "Underdogs",
    5: "Winners",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True,
                   help="area_classifications.csv")
    p.add_argument("--output", type=Path, required=True,
                   help="Output figure path (.pdf or .png).")
    p.add_argument("--min-areas", type=int, default=5,
                   help="Minimum number of areas a language must appear "
                        "in (with class > 0) to be included.")
    p.add_argument("--exclude-areas", nargs="*", default=[],
                   help="Area codes to drop (e.g. T31).")
    args = p.parse_args()

    df = pd.read_csv(args.input)
    df["area_code"] = df["research_area"].str.extract(r"^(T\d+)")

    if args.exclude_areas:
        df = df[~df["area_code"].isin(args.exclude_areas)]

    # languages × areas matrix, filled with class id; absent = Left-Behind (0)
    matrix = df.pivot_table(
        index="language", columns="area_code",
        values="class", aggfunc="max",
    ).fillna(0).astype(int)

    # Keep only languages present in at least min_areas areas (class > 0).
    presence = (matrix > 0).sum(axis=1)
    matrix = matrix[presence >= args.min_areas]

    # Same sort as fig:rq1-heatmap: most variable first, tiebreak by max
    variation = matrix.max(axis=1) - matrix.min(axis=1)
    matrix = (
        matrix.assign(_var=variation, _max=matrix.max(axis=1))
        .sort_values(["_var", "_max"], ascending=[False, False])
        .drop(columns=["_var", "_max"])
    )
    matrix = matrix.reindex(sorted(matrix.columns), axis=1)

    print(f"Plotting {len(matrix)} languages × {matrix.shape[1]} areas")

    fig, ax = plt.subplots(figsize=(11, 0.14 * len(matrix) + 2))

    cmap = ListedColormap([CLASS_PALETTE[c] for c in range(6)])
    sns.heatmap(
        matrix, ax=ax, cmap=cmap, vmin=-0.5, vmax=5.5,
        cbar=False, linewidths=0.15, linecolor="white",
    )

    ax.set_title(
        "Resource-class assignment for all multi-area languages "
        f"(present in ≥{args.min_areas} areas)",
        loc="left",
    )
    ax.set_xlabel("Research area")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=90, labelsize=8)
    ax.tick_params(axis="y", labelsize=5.5)

    legend_handles = [
        Patch(facecolor=CLASS_PALETTE[c], edgecolor="white",
              label=f"{c} — {CLASS_NAMES[c]}")
        for c in range(6)
    ]
    ax.legend(
        handles=legend_handles, loc="upper left",
        bbox_to_anchor=(1.01, 1.0), title="Class",
        title_fontsize=10, fontsize=9, frameon=False,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()