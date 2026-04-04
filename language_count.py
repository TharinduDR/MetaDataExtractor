#!/usr/bin/env python3
"""
Count languages and research areas across metadata JSON files.
Usage: python count_metadata.py /path/to/json/files
       python count_metadata.py --combined combined.json
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path


def load_json_files(directory):
    """Load all JSON files from a directory."""
    records = []
    json_files = sorted(Path(directory).glob("*.json"))

    for filepath in json_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Handle both single objects and lists
                if isinstance(data, list):
                    records.extend(data)
                else:
                    records.append(data)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  [WARN] Skipping {filepath.name}: {e}")

    print(f"Loaded {len(records)} records from {len(json_files)} files\n")
    return records


def load_combined_file(filepath):
    """Load a single combined JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data if isinstance(data, list) else [data]
    print(f"Loaded {len(records)} records from {filepath}\n")
    return records


def count_field(records, field):
    """Count occurrences of values in a list field across records."""
    counter = Counter()
    missing = 0

    for record in records:
        values = record.get(field, [])
        if not values:
            missing += 1
            continue
        if isinstance(values, str):
            values = [values]
        for value in values:
            counter[value.strip()] += 1

    return counter, missing


def print_counts(counter, label, top_n=None):
    """Print a frequency table."""
    print(f"{'=' * 60}")
    print(f" {label}")
    print(f"{'=' * 60}")

    items = counter.most_common(top_n)
    max_label_len = max(len(item) for item, _ in items) if items else 0

    for i, (item, count) in enumerate(items, 1):
        print(f"  {i:3d}. {item:<{max_label_len}}  {count:4d}")

    print(f"\n  Total unique: {len(counter)}")
    print(f"  Total occurrences: {sum(counter.values())}")
    print()


def export_csv(counter, output_path, field_name="item"):
    """Export counts to CSV."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"{field_name},count\n")
        for item, count in counter.most_common():
            # Escape commas in values
            item_escaped = f'"{item}"' if "," in item else item
            f.write(f"{item_escaped},{count}\n")
    print(f"  Exported to {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Count languages and research areas in metadata JSON files."
    )
    parser.add_argument(
        "path",
        help="Directory of JSON files or a single combined JSON file"
    )
    parser.add_argument(
        "--combined", action="store_true",
        help="Treat path as a single combined JSON file"
    )
    parser.add_argument(
        "--top", type=int, default=None,
        help="Show only top N results"
    )
    parser.add_argument(
        "--export-csv", action="store_true",
        help="Export results to CSV files"
    )
    parser.add_argument(
        "--outdir", default=".",
        help="Output directory for CSV files (default: current dir)"
    )

    args = parser.parse_args()

    # Load records
    if args.combined or os.path.isfile(args.path):
        records = load_combined_file(args.path)
    else:
        records = load_json_files(args.path)

    if not records:
        print("No records found.")
        sys.exit(1)

    # Count languages
    lang_counter, lang_missing = count_field(records, "languages")
    print_counts(lang_counter, "Language Frequency", top_n=args.top)
    if lang_missing:
        print(f"  ({lang_missing} records had no languages)\n")

    # Count research areas
    area_counter, area_missing = count_field(records, "research_areas")
    print_counts(area_counter, "Research Area Frequency", top_n=args.top)
    if area_missing:
        print(f"  ({area_missing} records had no research areas)\n")

    # Export CSV if requested
    if args.export_csv:
        os.makedirs(args.outdir, exist_ok=True)
        export_csv(
            lang_counter,
            os.path.join(args.outdir, "language_counts.csv"),
            "language"
        )
        export_csv(
            area_counter,
            os.path.join(args.outdir, "research_area_counts.csv"),
            "research_area"
        )


if __name__ == "__main__":
    main()