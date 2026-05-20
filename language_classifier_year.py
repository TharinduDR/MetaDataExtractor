#!/usr/bin/env python3
"""
Year-stratified area-specific language classification.

Extends classify_languages_by_area.py with a `--bin-years` option that
splits papers into year bins and emits one classification per (bin, area).
The bin column lets downstream RQ2 analyses see how each area's
inclusivity has changed over time.

Year is extracted from the ACL Anthology paper_id:
  - "P19-1001"            -> 2019
  - "2023.acl-long.42"    -> 2023
  - "W14-3504"            -> 2014
  - "L18-1234"            -> 2018

Falls back to a `year` field in the JSON if paper_id is malformed.

Usage:
  python classify_languages_by_area_years.py \
      --input-dir   ./papers_json \
      --output-csv  ./area_classifications_by_year.csv \
      --bin-size    2          # 2-year bins (default 1 = per-year)
      --start-year  2015 \
      --end-year    2024
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CLASS_CUTOFFS = [
    (5, "Winners",       0.50),
    (4, "Underdogs",     0.70),
    (3, "Rising Stars",  0.85),
    (2, "Hopefuls",      0.95),
    (1, "Scraping-Bys",  1.00),
]

# Two ACL Anthology paper-id formats:
#   Pre-2020:  L<id>, P<id>, W<id>, etc. with 2-digit year (e.g. P19-1001)
#   Post-2020: 4-digit year prefix (e.g. 2023.acl-long.42)
RE_NEW = re.compile(r"^(\d{4})\.")
RE_OLD = re.compile(r"^[A-Za-z](\d{2})-")


def parse_year(paper: dict) -> int | None:
    """Return the 4-digit publication year for a paper, or None."""
    if "year" in paper and isinstance(paper["year"], int):
        return paper["year"]

    pid = paper.get("paper_id", "")
    m = RE_NEW.match(pid)
    if m:
        return int(m.group(1))

    m = RE_OLD.match(pid)
    if m:
        yy = int(m.group(1))
        # ACL Anthology old-style IDs start in 1965; treat 65-99 as 1900s,
        # 00-24 as 2000s. Adjust upper bound if needed.
        return 1900 + yy if yy >= 65 else 2000 + yy

    return None


def load_papers(input_dir: Path):
    for path in sorted(input_dir.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                yield json.load(f)
        except json.JSONDecodeError as e:
            print(f"WARN: skipping {path}: {e}", file=sys.stderr)


def bin_label(year: int, bin_size: int) -> str:
    """Return a label like '2015-2016' (size 2) or '2019' (size 1)."""
    if bin_size == 1:
        return str(year)
    start = year - ((year - 1) % bin_size)  # round down to bin start
    return f"{start}-{start + bin_size - 1}"


def class_for(cum_share: float) -> tuple[int, str]:
    for cls_id, cls_name, upper in CLASS_CUTOFFS:
        if cum_share <= upper + 1e-9:
            return cls_id, cls_name
    return 1, "Scraping-Bys"


def classify(bin_area_lang_counts: dict) -> list[dict]:
    """
    Yield records of the form:
      {bin, research_area, language, paper_count, cumulative_share,
       class, class_name}
    one per (bin, area, non-zero language).
    """
    out = []
    for bin_label_, area_map in bin_area_lang_counts.items():
        for area, lang_counts in area_map.items():
            total = sum(lang_counts.values())
            if total == 0:
                continue
            sorted_langs = sorted(
                lang_counts.items(),
                key=lambda kv: (-kv[1], kv[0]),
            )
            cumulative = 0
            for lang, count in sorted_langs:
                cumulative += count
                cum_share = cumulative / total
                cls_id, cls_name = class_for(cum_share)
                out.append({
                    "bin": bin_label_,
                    "research_area": area,
                    "language": lang,
                    "paper_count": count,
                    "cumulative_share": round(cum_share, 6),
                    "class": cls_id,
                    "class_name": cls_name,
                })
    return out


def main():
    p = argparse.ArgumentParser(
        description="Year-stratified per-area language classification.")
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-csv", type=Path,
                   default=Path("area_classifications_by_year.csv"))
    p.add_argument("--bin-size", type=int, default=1,
                   help="Year bin size; 1 = per-year, 2 = biennial, etc.")
    p.add_argument("--start-year", type=int, default=None,
                   help="Drop papers before this year.")
    p.add_argument("--end-year", type=int, default=None,
                   help="Drop papers after this year.")
    p.add_argument("--exclude-areas", nargs="*", default=[])
    args = p.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"Not a directory: {args.input_dir}")

    # bin -> area -> lang -> count
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    no_year = 0
    total = 0

    for paper in load_papers(args.input_dir):
        total += 1
        year = parse_year(paper)
        if year is None:
            no_year += 1
            continue
        if args.start_year and year < args.start_year:
            continue
        if args.end_year and year > args.end_year:
            continue

        b = bin_label(year, args.bin_size)
        langs = paper.get("languages") or []
        areas = paper.get("research_areas") or []
        if not langs or not areas:
            continue
        for area in areas:
            code = area.split()[0] if area else ""
            if code in args.exclude_areas:
                continue
            for lang in langs:
                counts[b][area][lang] += 1

    print(f"Total papers: {total}")
    print(f"Papers with no parsable year: {no_year}")
    print(f"Year bins: {sorted(counts)}")

    records = classify(counts)

    with args.output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bin", "research_area", "language", "paper_count",
            "cumulative_share", "class", "class_name",
        ])
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} rows to {args.output_csv}")


if __name__ == "__main__":
    main()