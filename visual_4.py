#!/usr/bin/env python3
"""
Corpus exploration over the raw per-paper JSONs.

Produces four figures, all from unique-paper counts (each paper counted
once, unlike the classification CSVs which count per language-area):

  1. Papers per year                       (bar)
  2. Papers per research area              (bar)
  3. Papers per conference venue           (pie)
  4. Language diversity per conference     (bar: distinct languages/venue)

Venue and year are parsed from the ACL Anthology paper_id, which comes in
two formats:
  old:  D19-1001          (letter = venue, 2-digit year)
  new:  2021.emnlp-main.5 (4-digit year, venue slug)

Usage:
  python eda_repo.py --input-dir ../ACL-Data/ --outdir figures_eda/ \
      --exclude-areas T31
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns

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

ACCENT = "#3d6fb4"
ACCENT2 = "#cc4c02"

# Conferences we report individually; everything else is bucketed.
MAIN_VENUES = ["ACL", "EMNLP", "NAACL", "COLING", "LREC"]
PIE_ORDER = MAIN_VENUES + ["Other conferences", "Workshops"]

# Pie palette
PIE_COLORS = ["#024d33", "#3d9970", "#3d6fb4", "#f0a202", "#cc4c02",
              "#9467bd", "#bdbdbd"]

# Folder-name (venue) -> reporting bucket. The directory layout is
# ACL-Data/<year>/<venue>/..., so the venue is the folder name. Matching is
# case-insensitive. Every venue folder in the repo is listed explicitly so
# the bucketing is deterministic; edit a line here to move a venue.
VENUE_TO_BUCKET = {
    # --- Five main conferences (reported individually) ---
    "ACL": "ACL",
    "EMNLP": "EMNLP",
    "NAACL": "NAACL",
    "COLING": "COLING",
    "LREC": "LREC",

    # --- Workshops / shared-task / co-located events ---
    "WS": "Workshops",
    "WMT": "Workshops",
    "SEMEVAL": "Workshops",
    "CONLL": "Workshops",
    "STARSEM": "Workshops",
    "IWSLT": "Workshops",
    "INLG": "Workshops",
    "SIGDIAL": "Workshops",
    "ARABICNLP": "Workshops",

    # --- Other conferences ---
    "AACL": "Other conferences",
    "EACL": "Other conferences",
    "IJCNLP": "Other conferences",
    "FINDINGS": "Other conferences",
    "ALTA": "Other conferences",
    "AMTA": "Other conferences",
    "CCL": "Other conferences",
    "CLICIT": "Other conferences",
    "EAMT": "Other conferences",
    "IWSDS": "Other conferences",
    "KONVENS": "Other conferences",
    "LILT": "Other conferences",
    "MTSUMMIT": "Other conferences",
    "NODALIDA": "Other conferences",
    "PACLIC": "Other conferences",
    "PROPOR": "Other conferences",
    "RANLP": "Other conferences",
    "ROCLING": "Other conferences",
    "SCIL": "Other conferences",
}


def classify_venue(folder: str) -> str:
    """Map a venue folder name to one of the PIE_ORDER buckets."""
    if not folder:
        return "Other conferences"
    return VENUE_TO_BUCKET.get(folder.strip().upper(), "Other conferences")


def parse_path(path: Path, input_dir: Path):
    """
    Extract (year:int|None, venue:str) from the file path, assuming the
    layout  <input_dir>/<year>/<venue>/.../paper.json

    Falls back gracefully if the structure is shallower or deeper.
    """
    try:
        rel = path.relative_to(input_dir)
    except ValueError:
        rel = path
    parts = rel.parts

    year = None
    venue_folder = None
    for part in parts:
        # First 4-digit number we see is the year.
        if year is None and re.fullmatch(r"(19|20)\d{2}", part):
            year = int(part)
            continue
        # The folder immediately after the year is the venue.
        if year is not None and venue_folder is None and not part.endswith(
                ".json"):
            venue_folder = part
            break

    return year, classify_venue(venue_folder or "")


def load_papers(input_dir: Path):
    for path in sorted(input_dir.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                yield json.load(f), path
        except json.JSONDecodeError:
            continue


def fig_bar(labels, values, out, xlabel, title, color=ACCENT,
            horizontal=False, annotate=True, rotation=0):
    if horizontal:
        fig, ax = plt.subplots(figsize=(8.5, 0.34 * len(labels) + 1))
        ax.barh(labels, values, color=color, edgecolor="white")
        if annotate:
            for i, v in enumerate(values):
                ax.text(v + max(values) * 0.01, i, f"{int(v):,}",
                        va="center", fontsize=7.5, color="#444")
        ax.set_xlabel(xlabel)
        ax.set_xlim(0, max(values) * 1.12)
        ax.tick_params(axis="y", labelsize=8)
    else:
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        ax.bar(labels, values, color=color, edgecolor="white")
        if annotate:
            for i, v in enumerate(values):
                ax.text(i, v + max(values) * 0.01, f"{int(v):,}",
                        ha="center", fontsize=8, color="#444")
        ax.set_ylabel(xlabel)
        ax.set_ylim(0, max(values) * 1.12)
        ax.tick_params(axis="x", rotation=rotation, labelsize=9)
    ax.set_title(title, loc="left")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def fig_pie(counts: dict, out):
    labels = [v for v in PIE_ORDER if counts.get(v, 0) > 0]
    sizes = [counts[v] for v in labels]
    colors = [PIE_COLORS[PIE_ORDER.index(v)] for v in labels]

    fig, ax = plt.subplots(figsize=(7, 5.5))
    wedges, _texts, autotexts = ax.pie(
        sizes, colors=colors, startangle=90, counterclock=False,
        autopct=lambda p: f"{p:.1f}%", pctdistance=0.78,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
        textprops={"fontsize": 9},
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontweight("bold")
    ax.legend(wedges, [f"{l} ({s:,})" for l, s in zip(labels, sizes)],
              loc="center left", bbox_to_anchor=(1.0, 0.5),
              frameon=False, fontsize=9)
    ax.set_title("Papers by venue", loc="left")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--outdir", type=Path, default=Path("figures_eda"))
    p.add_argument("--exclude-areas", nargs="*", default=[])
    p.add_argument("--start-year", type=int, default=None)
    p.add_argument("--end-year", type=int, default=None)
    p.add_argument("--format", choices=["pdf", "png", "both"], default="both")
    args = p.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    year_counts = Counter()
    area_counts = Counter()
    venue_counts = Counter()
    venue_languages = defaultdict(set)   # venue -> set of languages
    n = 0

    for paper, path in load_papers(args.input_dir):
        year, venue = parse_path(path, args.input_dir)
        if args.start_year and year and year < args.start_year:
            continue
        if args.end_year and year and year > args.end_year:
            continue

        n += 1
        if year:
            year_counts[year] += 1
        venue_counts[venue] += 1

        # research areas (count each paper once per area)
        for area in (paper.get("research_areas") or []):
            code = area.split()[0] if area else ""
            if code in args.exclude_areas:
                continue
            area_counts[code] += 1

        # languages per venue (for diversity)
        for lang in set(paper.get("languages") or []):
            venue_languages[venue].add(lang)

    print(f"Total papers parsed: {n:,}")
    print(f"Year range: {min(year_counts)}-{max(year_counts)}")
    print(f"Venues: {dict(venue_counts)}")

    exts = ["pdf", "png"] if args.format == "both" else [args.format]
    for ext in exts:
        # 1. Papers per year
        years = sorted(year_counts)
        fig_bar([str(y) for y in years], [year_counts[y] for y in years],
                args.outdir / f"eda_papers_per_year.{ext}",
                xlabel="Number of papers", title="Papers per year",
                rotation=45)

        # 2. Papers per area
        areas_sorted = sorted(area_counts.items(), key=lambda kv: kv[1])
        fig_bar([k for k, _ in areas_sorted], [v for _, v in areas_sorted],
                args.outdir / f"eda_papers_per_area.{ext}",
                xlabel="Number of papers", title="Papers per research area",
                color=ACCENT, horizontal=True)

        # 3. Pie of venues
        fig_pie(venue_counts, args.outdir / f"eda_venues_pie.{ext}")

        # 4. Language diversity per venue
        div = {v: len(venue_languages[v]) for v in PIE_ORDER
               if v in venue_languages}
        div_sorted = sorted(div.items(), key=lambda kv: kv[1])
        fig_bar([k for k, _ in div_sorted], [v for _, v in div_sorted],
                args.outdir / f"eda_language_diversity.{ext}",
                xlabel="Number of distinct languages",
                title="Language diversity by venue",
                color=ACCENT2, horizontal=True)

    # Summary
    print("\nLanguage diversity per venue:")
    for v in PIE_ORDER:
        if v in venue_languages:
            print(f"  {v:20s}: {len(venue_languages[v])} languages, "
                  f"{venue_counts[v]:,} papers")


if __name__ == "__main__":
    main()