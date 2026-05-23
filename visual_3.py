#!/usr/bin/env python3
"""
RQ3: To what extent do global resource classifications agree with
     area-specific classifications?

Compares a single global class per language (from global_classifier.py,
area-agnostic) against the distribution of that language's area-specific
classes (from classify_languages_by_area.py).

Three figures:

  Figure 1 — Agreement matrix (confusion-style heatmap).
             Rows = global class, columns = area-specific class. Cell value
             = number of (language, area) assignments. A purely diagonal
             matrix would mean global and area-specific labels always agree.
             Off-diagonal mass is the disagreement RQ3 is about.

  Figure 2 — Per-language divergence strip.
             For each language, its global class (marker) against the spread
             of its area-specific classes (range bar). Languages sorted by
             how far their area-specific classes stray from the global label.
             Shows which languages are most mis-described by a global label.

  Figure 3 — Direction-of-disagreement bars.
             For each global class, the share of area-specific assignments
             that fall BELOW, AT, or ABOVE the global class. Reveals whether
             global labels systematically over- or under-state area-specific
             status.

Usage:
  python rq3_visualisations.py \
      --global   global_classification.csv \
      --area     area_classifications.csv \
      --outdir   figures_rq3/ \
      --exclude-areas T31
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
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
    1: "#cc4c02", 2: "#f0a202", 3: "#a3c440", 4: "#3d9970", 5: "#024d33",
}
CLASS_NAMES = {1: "Scraping-Bys", 2: "Hopefuls", 3: "Rising Stars",
               4: "Underdogs", 5: "Winners"}


def load_data(global_path, area_path, exclude_areas):
    g = pd.read_csv(global_path)[["language", "class"]]
    g = g.rename(columns={"class": "global_class"})

    a = pd.read_csv(area_path)
    a["area_code"] = a["research_area"].str.extract(r"^(T\d+)")
    if exclude_areas:
        a = a[~a["area_code"].isin(exclude_areas)]
    a = a[a["class"] > 0][["language", "area_code", "class"]]
    a = a.rename(columns={"class": "area_class"})

    merged = a.merge(g, on="language", how="inner")
    return merged, g


# ---------------------------------------------------------------------------
# Figure 1: Agreement matrix
# ---------------------------------------------------------------------------
def fig1_agreement_matrix(merged: pd.DataFrame, out_path: Path):
    mat = (
        merged.groupby(["global_class", "area_class"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=[5, 4, 3, 2, 1], columns=[1, 2, 3, 4, 5],
                 fill_value=0)
    )
    # Row-normalise to show, for each global class, where its area-specific
    # assignments land.
    mat_norm = mat.div(mat.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    sns.heatmap(
        mat_norm, ax=ax, cmap="rocket_r", annot=mat.values, fmt="d",
        cbar_kws={"label": "% of global-class assignments"},
        linewidths=0.5, linecolor="white", annot_kws={"fontsize": 9},
    )
    ax.set_xlabel("Area-specific class")
    ax.set_ylabel("Global class")
    ax.set_xticklabels([f"{c}\n{CLASS_NAMES[c]}" for c in [1, 2, 3, 4, 5]],
                       fontsize=8.5, rotation=0)
    ax.set_yticklabels([f"{c} {CLASS_NAMES[c]}" for c in [5, 4, 3, 2, 1]],
                       fontsize=8.5, rotation=0)
    ax.set_title(
        "Global vs area-specific class assignments\n"
        "Cell = count of (language, area) pairs; colour = row %",
        loc="left",
    )
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Figure 2: Per-language divergence strip
# ---------------------------------------------------------------------------
def fig2_divergence_strip(merged: pd.DataFrame, out_path: Path,
                          min_areas: int = 5, top_n: int = 40):
    stats = (
        merged.groupby("language")
        .agg(global_class=("global_class", "first"),
             min_area=("area_class", "min"),
             max_area=("area_class", "max"),
             median_area=("area_class", "median"),
             n_areas=("area_class", "size"))
        .reset_index()
    )
    stats = stats[stats["n_areas"] >= min_areas]
    # Divergence = how far the area range extends from the global label
    stats["divergence"] = (
        (stats["global_class"] - stats["min_area"]).abs()
        + (stats["max_area"] - stats["global_class"]).abs()
    )
    stats = stats.sort_values(
        ["divergence", "global_class"], ascending=[False, False]
    ).head(top_n)
    stats = stats.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(9, 0.30 * len(stats) + 2))
    y = np.arange(len(stats))

    for i, row in stats.iterrows():
        # Area-specific range
        ax.hlines(i, row["min_area"], row["max_area"],
                  color="#bbbbbb", lw=3, alpha=0.7, zorder=1)
        ax.scatter(row["min_area"], i, s=70,
                   color=CLASS_PALETTE[int(row["min_area"])],
                   edgecolor="white", lw=1, zorder=3)
        ax.scatter(row["max_area"], i, s=70,
                   color=CLASS_PALETTE[int(row["max_area"])],
                   edgecolor="white", lw=1, zorder=3)
        # Global class as a black ring
        ax.scatter(row["global_class"], i, s=150, facecolor="none",
                   edgecolor="black", lw=1.8, zorder=4)

    ax.set_yticks(y)
    ax.set_yticklabels(stats["language"], fontsize=8.5)
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.set_xticklabels([f"{c}\n{CLASS_NAMES[c]}" for c in [1, 2, 3, 4, 5]],
                       fontsize=8.5)
    ax.set_xlim(0.5, 5.5)
    ax.set_xlabel("Class")
    ax.set_title(
        "Global label vs area-specific range, per language\n"
        f"Languages in ≥{min_areas} areas, sorted by divergence from global label",
        loc="left",
    )
    ax.grid(axis="x", linestyle=":", alpha=0.4)

    legend = [
        Line2D([0], [0], marker="o", color="#bbbbbb", lw=3,
               markerfacecolor="#ccc", markeredgecolor="white",
               markersize=8, label="Area-specific class range"),
        Line2D([0], [0], marker="o", color="white", markerfacecolor="none",
               markeredgecolor="black", markeredgewidth=1.8, markersize=11,
               label="Global class"),
    ]
    ax.legend(handles=legend, loc="lower right", frameon=False, fontsize=9)

    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Figure 3: Direction of disagreement
# ---------------------------------------------------------------------------
def fig3_direction_of_disagreement(merged: pd.DataFrame, out_path: Path):
    merged = merged.copy()
    merged["direction"] = np.select(
        [merged["area_class"] < merged["global_class"],
         merged["area_class"] == merged["global_class"],
         merged["area_class"] > merged["global_class"]],
        ["below", "equal", "above"],
        default="equal",
    )
    comp = (
        merged.groupby(["global_class", "direction"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=[5, 4, 3, 2, 1])
        .reindex(columns=["below", "equal", "above"], fill_value=0)
    )
    comp_pct = comp.div(comp.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = {"below": "#cc4c02", "equal": "#bdbdbd", "above": "#024d33"}
    left = np.zeros(len(comp_pct))
    labels = [f"{c} — {CLASS_NAMES[c]}" for c in comp_pct.index]
    for direction in ["below", "equal", "above"]:
        vals = comp_pct[direction].values
        ax.barh(labels, vals, left=left, color=colors[direction],
                edgecolor="white", label=direction.capitalize())
        left += vals

    ax.set_xlabel("% of (language, area) assignments")
    ax.set_ylabel("Global class")
    ax.set_xlim(0, 100)
    ax.set_title(
        "Direction of disagreement between global and area-specific labels\n"
        "For each global class, where do the area-specific labels fall?",
        loc="left",
    )
    handles = [
        Patch(facecolor=colors["below"], label="Area class below global"),
        Patch(facecolor=colors["equal"], label="Area class equals global"),
        Patch(facecolor=colors["above"], label="Area class above global"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9)

    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def print_rq3_summary(merged: pd.DataFrame):
    total = len(merged)
    agree = (merged["area_class"] == merged["global_class"]).sum()
    below = (merged["area_class"] < merged["global_class"]).sum()
    above = (merged["area_class"] > merged["global_class"]).sum()
    print()
    print("=" * 60)
    print("RQ3 summary statistics")
    print("=" * 60)
    print(f"Total (language, area) assignments: {total}")
    print(f"Agree with global label : {agree} ({100*agree/total:.1f}%)")
    print(f"Area class BELOW global : {below} ({100*below/total:.1f}%)")
    print(f"Area class ABOVE global : {above} ({100*above/total:.1f}%)")

    # Languages whose global label never matches any area
    per_lang = merged.groupby("language").apply(
        lambda d: (d["area_class"] == d["global_class"]).mean(),
        include_groups=False,
    )
    never_match = (per_lang == 0).sum()
    print(f"\nLanguages whose global label matches NO area: {never_match}")
    print("=" * 60)


def main():
    p = argparse.ArgumentParser(description="RQ3 visualisations.")
    p.add_argument("--global", dest="global_path", type=Path, required=True)
    p.add_argument("--area", type=Path, required=True)
    p.add_argument("--outdir", type=Path, default=Path("figures_rq3"))
    p.add_argument("--exclude-areas", nargs="*", default=[])
    p.add_argument("--min-areas", type=int, default=5)
    p.add_argument("--top-n", type=int, default=40)
    p.add_argument("--format", choices=["pdf", "png", "both"], default="both")
    args = p.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    merged, _ = load_data(args.global_path, args.area, args.exclude_areas)

    exts = ["pdf", "png"] if args.format == "both" else [args.format]
    for ext in exts:
        fig1_agreement_matrix(
            merged, args.outdir / f"fig_rq3_agreement_matrix.{ext}")
        fig2_divergence_strip(
            merged, args.outdir / f"fig_rq3_divergence_strip.{ext}",
            min_areas=args.min_areas, top_n=args.top_n)
        fig3_direction_of_disagreement(
            merged, args.outdir / f"fig_rq3_direction.{ext}")

    print_rq3_summary(merged)


if __name__ == "__main__":
    main()