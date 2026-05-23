#!/usr/bin/env python3
"""
Global language classification (area-agnostic).

Reconstructs a Joshi et al. (2020)-style global classification by pooling
ALL papers regardless of research area, then applying the same six-class
cumulative-share taxonomy used per-area. Each paper is counted once per
language it covers (NOT once per area-language pair), so a paper tagged
with multiple areas does not inflate the global count.

This is the baseline against which RQ3 compares the area-specific labels.

Class cutoffs (cumulative share of all papers, languages sorted desc):
  Class 5 (Winners)      : top 50%
  Class 4 (Underdogs)    : next 20%
  Class 3 (Rising Stars) : next 15%
  Class 2 (Hopefuls)     : next 10%
  Class 1 (Scraping-Bys) : remaining 5%
  Class 0 (Left-Behinds) : 0 papers globally (cannot occur here, since a
                           language with 0 papers never appears in the data)

Usage:
  python global_classifier.py \
      --input-dir   ../ACL-Data/ \
      --output-csv  global_classification.csv
"""
from __future__ import annotations

import argparse
import csv
import json
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


def load_papers(input_dir: Path):
    for path in sorted(input_dir.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                yield json.load(f)
        except json.JSONDecodeError as e:
            print(f"WARN: skipping {path}: {e}", file=sys.stderr)


def class_for(cum_share: float):
    for cls_id, cls_name, upper in CLASS_CUTOFFS:
        if cum_share <= upper + 1e-9:
            return cls_id, cls_name
    return 1, "Scraping-Bys"


def main():
    p = argparse.ArgumentParser(
        description="Area-agnostic global language classification.")
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-csv", type=Path,
                   default=Path("global_classification.csv"))
    args = p.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"Not a directory: {args.input_dir}")

    # Each paper counts once per language, regardless of how many areas
    # it is tagged with.
    lang_counts = defaultdict(int)
    n_papers = 0
    for paper in load_papers(args.input_dir):
        langs = paper.get("languages") or []
        if not langs:
            continue
        n_papers += 1
        for lang in set(langs):  # set() guards against duplicate tags
            lang_counts[lang] += 1

    total = sum(lang_counts.values())
    print(f"Papers with languages: {n_papers}")
    print(f"Languages: {len(lang_counts)}")
    print(f"Total language mentions: {total}")

    sorted_langs = sorted(lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))

    rows = []
    cumulative = 0
    for lang, count in sorted_langs:
        cumulative += count
        cum_share = cumulative / total
        cls_id, cls_name = class_for(cum_share)
        rows.append({
            "language": lang,
            "paper_count": count,
            "cumulative_share": round(cum_share, 6),
            "class": cls_id,
            "class_name": cls_name,
        })

    with args.output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "language", "paper_count", "cumulative_share",
            "class", "class_name",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.output_csv}")

    # Quick class-size summary
    from collections import Counter
    sizes = Counter(r["class"] for r in rows)
    print("\nGlobal class sizes:")
    for c in [5, 4, 3, 2, 1]:
        print(f"  Class {c}: {sizes.get(c, 0)} languages")


if __name__ == "__main__":
    main()