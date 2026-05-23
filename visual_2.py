#!/usr/bin/env python3
"""
RQ2: Which NLP research areas are most and least linguistically inclusive,
     and how has this changed over the last ten years?

This script produces three figures designed to compress both dimensions
of RQ2 into legible images, matching the density of the RQ1 heatmap.

  Figure 1 — Inclusivity ranking, current snapshot.
             A horizontal lollipop chart of research areas ranked by the
             number of languages with non-zero presence. Each lollipop is
             coloured by the share of Winners-and-Underdogs vs the long
             tail, exposing both volume and concentration in a single view.

  Figure 2 — Temporal heatmap of inclusivity.
             A research-area × year matrix, coloured by the number of
             distinct languages with at least one paper in that area-year.
             Reveals which areas have grown, stalled, or contracted in
             linguistic coverage over the last decade.

  Figure 3 — Per-area trajectory of class composition over time.
             Small-multiples of stacked bars (one panel per selected area)
             showing how the class distribution evolved year by year.
             Surfaces qualitative shifts that a coverage count alone hides.

Inputs:
  --current  area_classifications.csv          (from classify_languages_by_area.py)
  --temporal area_classifications_by_year.csv  (from classify_languages_by_area_years.py)
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
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
    1: "#cc4c02",
    2: "#f0a202",
    3: "#a3c440",
    4: "#3d9970",
    5: "#024d33",
}
CLASS_NAMES = {1: "Scraping-Bys", 2: "Hopefuls", 3: "Rising Stars",
               4: "Underdogs", 5: "Winners"}


def load_current(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["area_code"] = df["research_area"].str.extract(r"^(T\d+)")
    df["area_short"] = df["research_area"].str.replace(
        r"^T\d+\s+", "", regex=True)
    return df[df["class"] > 0]


def load_temporal(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["area_code"] = df["research_area"].str.extract(r"^(T\d+)")
    df["area_short"] = df["research_area"].str.replace(
        r"^T\d+\s+", "", regex=True)
    return df


# ---------------------------------------------------------------------------
# Figure 1: Inclusivity ranking (current snapshot)
# ---------------------------------------------------------------------------
def fig1_inclusivity_ranking(df: pd.DataFrame, out_path: Path):
    """
    For each area, two summary numbers:
      - total distinct languages with ≥1 paper (lollipop length)
      - share of those that sit in Classes 4-5 (lollipop colour)

    The colour signals concentration: a darker-green lollipop means the
    area's coverage is more concentrated in top-tier languages, while an
    orange-red lollipop indicates that the area is dominated by the long
    tail.
    """
    agg = (
        df.groupby(["area_code", "area_short"])
        .agg(n_languages=("language", "nunique"),
             n_top=("class", lambda s: int((s >= 4).sum())))
        .reset_index()
    )
    agg["top_share"] = 100 * agg["n_top"] / agg["n_languages"]

    # Sort by language count, MOST inclusive at top of plot (= last in
    # ascending sort, since matplotlib plots low-y at bottom).
    agg = agg.sort_values("n_languages", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 0.34 * len(agg) + 1.5))

    # Calibrate colour scale to the actual data range so the gradient is
    # informative rather than collapsing everything to one end of the scale.
    cmap = LinearSegmentedColormap.from_list(
        "concentration", ["#cc4c02", "#f0a202", "#a3c440", "#024d33"])
    vmax = max(agg["top_share"].max(), 5.0)  # at least 5% so tiny values
                                              # still get distinct colours
    colors = cmap(agg["top_share"] / vmax)

    y = np.arange(len(agg))
    ax.hlines(y, 0, agg["n_languages"], color="#cccccc", lw=1.6, zorder=1)
    ax.scatter(agg["n_languages"], y, s=180, color=colors,
               edgecolor="white", linewidth=1.4, zorder=3)

    # Annotate the count at each lollipop tip for precise reading
    for yi, (n, t) in enumerate(zip(agg["n_languages"], agg["top_share"])):
        ax.text(n + max(agg["n_languages"]) * 0.012, yi, f"{n}",
                va="center", fontsize=8.5, color="#444")

    ax.set_yticks(y)
    ax.set_yticklabels(
        [s[:55] for s in agg["area_short"]], fontsize=8.5)
    ax.set_xlabel("Number of languages with ≥1 paper")
    ax.set_xlim(0, max(agg["n_languages"]) * 1.10)
    ax.set_title(
        "Linguistic inclusivity by research area\n"
        "Lollipop length = languages covered; "
        "colour = share concentrated in Winners and Underdogs",
        loc="left",
    )
    ax.grid(axis="x", linestyle=":", alpha=0.4)

    # Inset colour legend for the concentration scale
    cbar_ax = fig.add_axes([0.93, 0.20, 0.018, 0.30])
    sm = plt.cm.ScalarMappable(cmap=cmap,
                               norm=plt.Normalize(vmin=0, vmax=vmax))
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label("% in Winners + Underdogs", fontsize=8)
    cbar.ax.tick_params(labelsize=8)

    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Figure 2: Temporal heatmap of inclusivity
# ---------------------------------------------------------------------------
def fig2_temporal_heatmap(df: pd.DataFrame, out_path: Path):
    """
    Area × year matrix. Cell value = distinct-language count in that
    area-year. Areas sorted by total coverage. Year columns chronological.
    """
    coverage = (
        df.groupby(["area_code", "area_short", "bin"])["language"]
        .nunique()
        .reset_index()
    )
    pivot = coverage.pivot_table(
        index=["area_code", "area_short"],
        columns="bin", values="language", aggfunc="sum", fill_value=0,
    )
    # Sort areas by total coverage across all bins (most covered at top)
    pivot["_total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("_total", ascending=False)
    pivot = pivot.drop(columns="_total")


    # Use only the area code for row labels (e.g. T01 instead of "T01 Bias...")
    pivot.index = [c for c, _ in pivot.index]

    fig, ax = plt.subplots(figsize=(8.5, 0.32 * len(pivot) + 1.5))

    sns.heatmap(
        pivot, ax=ax, cmap="YlGnBu", cbar_kws={"label": "Languages covered"},
        linewidths=0.4, linecolor="white", square=False,
        annot=False,
    )

    ax.set_title(
        "Linguistic coverage per research area over time\n"
        "Number of distinct languages with ≥1 paper in each (area, year-bin)",
        loc="left",
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=0, labelsize=9)
    ax.tick_params(axis="y", rotation=0, labelsize=8.5)

    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Figure 3: Class composition trajectories for selected areas
# ---------------------------------------------------------------------------
def fig3_class_trajectories(df: pd.DataFrame, out_path: Path,
                            selected_areas: list = None,
                            n_cols: int = 3):
    """
    Small multiples: one panel per selected research area, showing the
    distribution of languages across classes 1-5 year by year as stacked
    bars. Surfaces *qualitative* shifts (e.g. an area whose total coverage
    grew but whose top-class share collapsed).

    Defaults to a curated mix: two consistently inclusive areas, two that
    appear less inclusive, two showing the most temporal change.
    """
    if selected_areas is None:
        selected_areas = _select_areas_by_change(df, k=6)

    sub = df[df["area_code"].isin(selected_areas)].copy()
    area_to_short = (
        sub.drop_duplicates("area_code")
        .set_index("area_code")["area_short"]
        .to_dict()
    )

    bins = sorted(sub["bin"].unique())
    n_rows = (len(selected_areas) + n_cols - 1) // n_cols
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(4.0 * n_cols, 2.6 * n_rows),
        sharey=False,
    )
    axes = np.array(axes).reshape(-1)

    for idx, code in enumerate(selected_areas):
        ax = axes[idx]
        area_df = sub[sub["area_code"] == code]
        counts = (
            area_df.groupby(["bin", "class"])["language"]
            .nunique()
            .unstack(fill_value=0)
            .reindex(columns=[1, 2, 3, 4, 5], fill_value=0)
            .reindex(bins, fill_value=0)
        )

        bottom = np.zeros(len(counts))
        x = np.arange(len(counts))
        for cls in [1, 2, 3, 4, 5]:
            vals = counts[cls].values
            ax.bar(x, vals, bottom=bottom, color=CLASS_PALETTE[cls],
                   width=0.78, edgecolor="white", linewidth=0.4,
                   label=CLASS_NAMES[cls] if idx == 0 else None)
            bottom += vals

        ax.set_title(f"{code}  {area_to_short[code][:35]}",
                     fontsize=10, loc="left")
        ax.set_xticks(x)
        ax.set_xticklabels(counts.index, rotation=45, fontsize=8,
                           ha="right")
        ax.tick_params(axis="y", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    # Hide unused panels
    for j in range(len(selected_areas), len(axes)):
        axes[j].axis("off")

    # Single shared legend below the panels (avoids overlapping the
    # rightmost plot in the top row).
    legend_handles = [
        Patch(facecolor=CLASS_PALETTE[c], label=f"{c} — {CLASS_NAMES[c]}")
        for c in [5, 4, 3, 2, 1]
    ]
    fig.legend(handles=legend_handles, loc="lower center",
               bbox_to_anchor=(0.5, -0.06), frameon=False, ncol=5,
               title_fontsize=10, fontsize=9)

    fig.suptitle(
        "How the class composition of selected areas has shifted over time",
        fontsize=12, fontweight="bold", x=0.02, y=1.02, ha="left",
    )
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def _select_areas_by_change(df: pd.DataFrame, k: int = 6) -> list:
    """
    Select k research areas that show the most interesting temporal pattern.
    Heuristic: rank areas by (coverage in latest bin - coverage in earliest
    bin), and take the top k/2 gainers + top k/2 losers.
    """
    coverage = (
        df.groupby(["area_code", "bin"])["language"].nunique().unstack()
    )
    if coverage.shape[1] < 2:
        return list(coverage.index[:k])

    first, last = coverage.columns[0], coverage.columns[-1]
    delta = (coverage[last].fillna(0) - coverage[first].fillna(0))
    delta = delta.sort_values()
    losers = delta.head(k // 2).index.tolist()
    gainers = delta.tail(k - len(losers)).index.tolist()
    return losers + gainers


# ---------------------------------------------------------------------------
# Summary statistics for the paper text
# ---------------------------------------------------------------------------
def print_rq2_summary(current_df, temporal_df):
    print()
    print("=" * 70)
    print("RQ2 summary statistics")
    print("=" * 70)

    # Most / least inclusive areas right now
    coverage_now = (
        current_df.groupby(["area_code", "area_short"])["language"]
        .nunique()
        .reset_index()
        .sort_values("language", ascending=False)
    )
    print("\nMost inclusive areas (by # languages covered, current snapshot):")
    print(coverage_now.head(5).to_string(index=False))
    print("\nLeast inclusive areas:")
    print(coverage_now.tail(5).to_string(index=False))

    # Temporal change
    cov = (
        temporal_df.groupby(["area_code", "bin"])["language"].nunique()
        .unstack(fill_value=0)
    )
    first, last = cov.columns[0], cov.columns[-1]
    delta = (cov[last] - cov[first]).sort_values()
    print(f"\nLargest coverage gains ({first} -> {last}):")
    print(delta.tail(5).to_string())
    print(f"\nLargest coverage losses ({first} -> {last}):")
    print(delta.head(5).to_string())
    print("=" * 70)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description="RQ2 visualisations: per-area inclusivity and "
                    "its evolution over time.")
    p.add_argument("--current", type=Path, required=True,
                   help="area_classifications.csv")
    p.add_argument("--temporal", type=Path, required=True,
                   help="area_classifications_by_year.csv")
    p.add_argument("--outdir", type=Path, default=Path("figures_rq2"))
    p.add_argument("--exclude-areas", nargs="*", default=[])
    p.add_argument("--format", choices=["pdf", "png", "both"],
                   default="both")
    args = p.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    cur = load_current(args.current)
    tmp = load_temporal(args.temporal)

    if args.exclude_areas:
        cur = cur[~cur["area_code"].isin(args.exclude_areas)]
        tmp = tmp[~tmp["area_code"].isin(args.exclude_areas)]
        print(f"Excluded areas {args.exclude_areas}")

    exts = ["pdf", "png"] if args.format == "both" else [args.format]
    for ext in exts:
        fig1_inclusivity_ranking(
            cur, args.outdir / f"fig_rq2_ranking.{ext}")
        fig2_temporal_heatmap(
            tmp, args.outdir / f"fig_rq2_temporal_heatmap.{ext}")
        fig3_class_trajectories(
            tmp, args.outdir / f"fig_rq2_class_trajectories.{ext}")

    print_rq2_summary(cur, tmp)


if __name__ == "__main__":
    main()