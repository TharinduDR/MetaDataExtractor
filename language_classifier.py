#!/usr/bin/env python3
"""
Area-Specific Language Classification for NLP Research

For each research area, classify languages into six tiers based on the
cumulative share of papers in that area, following the Joshi et al. (2020)
taxonomy applied per-area:

  Class 5 (Winners)        : top 50% of papers in the area
  Class 4 (Underdogs)      : next 20% (cumulative 50-70%)
  Class 3 (Rising Stars)   : next 15% (cumulative 70-85%)
  Class 2 (Hopefuls)       : next 10% (cumulative 85-95%)
  Class 1 (Scraping-Bys)   : remaining 5% (cumulative 95-100%)
  Class 0 (Left-Behinds)   : 0 papers in the area

Input  : directory of per-paper JSON files (one paper per file).
Output : a JSON file with per-area classifications, plus a CSV summary.

Usage:
  python classify_languages_by_area.py \
      --input-dir   ./papers_json \
      --output-json ./area_classifications.json \
      --output-csv  ./area_classifications.csv \
      [--all-languages ./all_languages.txt]

The optional --all-languages file (one language name per line) lets you
identify Left-Behinds — languages that exist globally but have 0 papers in
a given area. Without it, Class 0 is only computed implicitly (languages
that appear in some areas but not others).
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Cumulative-share cutoffs for classes 5 down to 1.
# A language belongs to class C if its cumulative share (after sorting
# languages by paper count in descending order) first exceeds the lower
# bound of class C.
CLASS_CUTOFFS = [
    (5, "Winners",       0.00, 0.50),  # top 50% of papers
    (4, "Underdogs",     0.50, 0.70),  # next 20%
    (3, "Rising Stars",  0.70, 0.85),  # next 15%
    (2, "Hopefuls",      0.85, 0.95),  # next 10%
    (1, "Scraping-Bys",  0.95, 1.00),  # remaining 5%
]
LEFT_BEHIND = (0, "Left-Behinds")


def load_papers(input_dir: Path):
    """Yield (paper_dict, source_filename) for every JSON file in input_dir."""
    json_files = sorted(input_dir.rglob("*.json"))
    if not json_files:
        sys.exit(f"No JSON files found under {input_dir}")
    for path in json_files:
        try:
            with path.open("r", encoding="utf-8") as f:
                yield json.load(f), path.name
        except json.JSONDecodeError as e:
            print(f"WARNING: skipping malformed JSON {path}: {e}", file=sys.stderr)


def count_papers_per_area_language(papers):
    """
    Return:
      area_lang_counts : dict[area] -> dict[language] -> paper count
      all_languages    : set of every language seen anywhere
      all_areas        : set of every research area seen anywhere
    """
    area_lang_counts = defaultdict(lambda: defaultdict(int))
    all_languages = set()
    all_areas = set()

    for paper, _ in papers:
        langs = paper.get("languages") or []
        areas = paper.get("research_areas") or []
        if not langs or not areas:
            continue
        # Each paper counts once per (area, language) pair it touches.
        # Multi-language, multi-area papers contribute to all combinations.
        for area in areas:
            all_areas.add(area)
            for lang in langs:
                all_languages.add(lang)
                area_lang_counts[area][lang] += 1

    return area_lang_counts, all_languages, all_areas


def classify_area(lang_counts: dict, all_languages: set):
    """
    Given per-language paper counts for one research area and the global
    language vocabulary, return a list of records:

        {language, paper_count, share, cumulative_share, class, class_name}

    sorted from most-resourced to least-resourced. Languages with 0 papers
    in this area are assigned to class 0 (Left-Behinds).
    """
    total = sum(lang_counts.values())
    records = []

    if total == 0:
        # No papers in this area at all — everyone is a Left-Behind.
        for lang in sorted(all_languages):
            records.append({
                "language": lang,
                "paper_count": 0,
                "share": 0.0,
                "cumulative_share": 0.0,
                "class": LEFT_BEHIND[0],
                "class_name": LEFT_BEHIND[1],
            })
        return records

    # Sort languages with >=1 paper, descending by count.
    # Tie-break alphabetically for determinism.
    sorted_langs = sorted(
        lang_counts.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )

    cumulative = 0
    for lang, count in sorted_langs:
        cumulative += count
        cum_share = cumulative / total
        share = count / total

        # Find the class whose [lower, upper) interval contains
        # the cumulative share that this language's bucket lands in.
        # The convention: a language belongs to the highest class
        # whose lower bound it has not yet crossed past.
        # Specifically, the class is determined by where the cumulative
        # share lies AFTER adding this language.
        cls_id, cls_name = _class_from_cumulative(cum_share)

        records.append({
            "language": lang,
            "paper_count": count,
            "share": round(share, 6),
            "cumulative_share": round(cum_share, 6),
            "class": cls_id,
            "class_name": cls_name,
        })

    # Languages with 0 papers in this area but present in the global list:
    seen = {r["language"] for r in records}
    for lang in sorted(all_languages - seen):
        records.append({
            "language": lang,
            "paper_count": 0,
            "share": 0.0,
            "cumulative_share": 0.0,
            "class": LEFT_BEHIND[0],
            "class_name": LEFT_BEHIND[1],
        })

    return records


def _class_from_cumulative(cum_share: float):
    """
    Map a cumulative share value (0 < s <= 1) to a class id and name.

    Boundaries are inclusive on the upper side so that, e.g., a language
    landing exactly at cumulative share 0.50 is still a Winner.
    """
    for cls_id, cls_name, lower, upper in CLASS_CUTOFFS:
        if cum_share <= upper + 1e-9:
            return cls_id, cls_name
    # Floating-point safety net: anything beyond 1.0 is Scraping-Bys.
    return 1, "Scraping-Bys"


def write_json(out_path: Path, area_records: dict):
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(area_records, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path}")


def write_csv(out_path: Path, area_records: dict):
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "research_area", "language", "paper_count",
            "share", "cumulative_share", "class", "class_name",
        ])
        for area, records in sorted(area_records.items()):
            for r in records:
                writer.writerow([
                    area, r["language"], r["paper_count"],
                    r["share"], r["cumulative_share"],
                    r["class"], r["class_name"],
                ])
    print(f"Wrote {out_path}")


def print_summary(area_records: dict):
    """Print a compact per-area class-size table for quick inspection."""
    print()
    print(f"{'Research area':<80} {'W':>4} {'U':>4} {'R':>4} {'H':>4} {'S':>4} {'L':>5}")
    print("-" * 110)
    for area in sorted(area_records):
        counts = defaultdict(int)
        for r in area_records[area]:
            counts[r["class"]] += 1
        print(f"{area[:80]:<80} "
              f"{counts[5]:>4} {counts[4]:>4} {counts[3]:>4} "
              f"{counts[2]:>4} {counts[1]:>4} {counts[0]:>5}")
    print("\nLegend: W=Winners U=Underdogs R=Rising Stars "
          "H=Hopefuls S=Scraping-Bys L=Left-Behinds")


def main():
    parser = argparse.ArgumentParser(
        description="Classify languages into the six-class Joshi-style "
                    "taxonomy independently for each research area.",
    )
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Directory containing per-paper JSON files.")
    parser.add_argument("--output-json", type=Path,
                        default=Path("area_classifications.json"),
                        help="Where to write the full per-area JSON output.")
    parser.add_argument("--output-csv", type=Path,
                        default=Path("area_classifications.csv"),
                        help="Where to write a flat CSV version.")
    parser.add_argument("--all-languages", type=Path,
                        help="Optional file listing every language to "
                             "consider (one per line). Used to identify "
                             "Left-Behinds. If omitted, the global language "
                             "set is derived from the input papers.")
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"Input directory does not exist: {args.input_dir}")

    print(f"Loading papers from {args.input_dir} ...")
    papers = list(load_papers(args.input_dir))
    print(f"Loaded {len(papers)} papers")

    area_lang_counts, derived_languages, all_areas = \
        count_papers_per_area_language(papers)
    print(f"Found {len(all_areas)} research areas and "
          f"{len(derived_languages)} languages")

    if args.all_languages and args.all_languages.exists():
        with args.all_languages.open("r", encoding="utf-8") as f:
            all_languages = {line.strip() for line in f if line.strip()}
        print(f"Using {len(all_languages)} languages from "
              f"{args.all_languages}")
    else:
        all_languages = derived_languages

    area_records = {}
    for area in sorted(all_areas):
        area_records[area] = classify_area(
            area_lang_counts[area], all_languages,
        )

    write_json(args.output_json, area_records)
    write_csv(args.output_csv, area_records)
    print_summary(area_records)


if __name__ == "__main__":
    main()