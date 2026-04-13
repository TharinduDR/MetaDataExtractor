#!/usr/bin/env python3
"""
Post-processing script to clean up language fields in metadata JSON files.
Fixes: programming languages, ISO codes, duplicates, normalization,
       non-languages, typos, language families, modalities, language pairs,
       romanized variants, Arabic dialects, Italian dialects, writing systems,
       nationality/region labels, etc.

Usage:
    python cleanup_languages.py /path/to/json/files
    python cleanup_languages.py /path/to/json/files --dry-run --verbose
    python cleanup_languages.py combined.json --combined
    python cleanup_languages.py /path/to/json/files --outdir cleaned/
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

# =============================================================================
# 1. NORMALIZATION MAP: Map variant names to canonical form
# =============================================================================
NORMALIZE_MAP = {
    # =========================================================================
    # Chinese variants
    # =========================================================================
    "Mandarin": "Chinese",
    "Mandarin Chinese": "Chinese",
    "Chinese (Mandarin)": "Chinese",
    "Chinese (Simplified)": "Chinese",
    "Simplified Chinese": "Chinese",
    "Chinese (Traditional)": "Chinese",
    "Traditional Chinese": "Chinese",
    "Classical Chinese": "Chinese",
    "cmn": "Chinese",
    "chn": "Chinese",

    # =========================================================================
    # Arabic variants & dialects → Arabic
    # =========================================================================
    "Modern Standard Arabic": "Arabic",
    "Moroccan Arabic": "Arabic",
    "Egyptian Arabic": "Arabic",
    "Tunisian Arabic": "Arabic",
    "Chadian Arabic": "Arabic",
    "ar": "Arabic",
    "arq": "Arabic",
    "ary": "Arabic",

    # =========================================================================
    # German variants
    # =========================================================================
    "Standard German": "German",
    "Austrian German": "German",
    "de": "German",
    "deu": "German",
    "ger": "German",

    # =========================================================================
    # Portuguese variants
    # =========================================================================
    "Brazilian Portuguese": "Portuguese",
    "Portuguese (African)": "Portuguese",
    "ptbr": "Portuguese",
    "ptmz": "Portuguese",
    "pt": "Portuguese",
    "por": "Portuguese",

    # =========================================================================
    # French variants
    # =========================================================================
    "French (African)": "French",
    "fr": "French",
    "fre": "French",

    # =========================================================================
    # Spanish variants
    # =========================================================================
    "es": "Spanish",
    "esp": "Spanish",
    "spa": "Spanish",

    # =========================================================================
    # Persian variants
    # =========================================================================
    "Farsi": "Persian",
    "Western Persian": "Persian",

    # =========================================================================
    # Hindi variants
    # =========================================================================
    "hi": "Hindi",
    "hin": "Hindi",

    # =========================================================================
    # Italian variants
    # =========================================================================
    "it": "Italian",
    "ita": "Italian",

    # =========================================================================
    # Russian ISO codes
    # =========================================================================
    "ru": "Russian",

    # =========================================================================
    # Dutch variants
    # =========================================================================
    "Flemish": "Dutch",
    "dut": "Dutch",

    # =========================================================================
    # Romanian variants
    # =========================================================================
    "Moldavian": "Romanian",
    "ron": "Romanian",

    # =========================================================================
    # Bengali variants
    # =========================================================================
    "Bangla": "Bengali",
    "Bengla": "Bengali",
    "Bengali Romanized": "Bengali",

    # =========================================================================
    # Telugu variants
    # =========================================================================
    "Telugu Romanized": "Telugu",

    # =========================================================================
    # Punjabi variants
    # =========================================================================
    "Panjabi": "Punjabi",
    "Eastern Panjabi": "Punjabi",

    # =========================================================================
    # Uyghur variants
    # =========================================================================
    "Uighur": "Uyghur",

    # =========================================================================
    # Zulu variants
    # =========================================================================
    "isiZulu": "Zulu",
    "zul": "Zulu",

    # =========================================================================
    # Xhosa variants
    # =========================================================================
    "isiXhosa": "Xhosa",
    "xho": "Xhosa",

    # =========================================================================
    # Indonesian variants
    # =========================================================================
    "Bahasa Indonesian": "Indonesian",
    "ind": "Indonesian",

    # =========================================================================
    # Sesotho / Sotho variants
    # =========================================================================
    "Sotho": "Sesotho",
    "Southern Sotho": "Sesotho",

    # =========================================================================
    # English variants
    # =========================================================================
    "Standard English": "English",
    "eng": "English",

    # =========================================================================
    # Azerbaijani variants
    # =========================================================================
    "North Azerbaijani": "Azerbaijani",
    "Azeri": "Azerbaijani",

    # =========================================================================
    # Armenian variants
    # =========================================================================
    "Western Armenian": "Armenian",

    # =========================================================================
    # Burmese variants
    # =========================================================================
    "Myanmar": "Burmese",

    # =========================================================================
    # Lao variants
    # =========================================================================
    "Laos": "Lao",

    # =========================================================================
    # Pashto variants
    # =========================================================================
    "Southern Pashto": "Pashto",
    "Pushto": "Pashto",

    # =========================================================================
    # Shona variants
    # =========================================================================
    "ChiShona": "Shona",

    # =========================================================================
    # Swahili variants
    # =========================================================================
    "Kiswahili": "Swahili",
    "SwaHili": "Swahili",
    "swa": "Swahili",

    # =========================================================================
    # Luganda variants
    # =========================================================================
    "Ganda": "Luganda",

    # =========================================================================
    # Setswana variants
    # =========================================================================
    "Tswana": "Setswana",

    # =========================================================================
    # Chichewa / Nyanja variants
    # =========================================================================
    "Chewa": "Chichewa",
    "Nyanja": "Chichewa",

    # =========================================================================
    # Latvian variants
    # =========================================================================
    "Standard Latvian": "Latvian",

    # =========================================================================
    # Malay variants
    # =========================================================================
    "Standard Malay": "Malay",

    # =========================================================================
    # Norwegian variants
    # =========================================================================
    "Norwegian Bokmål": "Norwegian",

    # =========================================================================
    # Malagasy variants
    # =========================================================================
    "Plateau Malagasy": "Malagasy",

    # =========================================================================
    # Uzbek variants
    # =========================================================================
    "Northern Uzbek": "Uzbek",

    # =========================================================================
    # Bambara variants
    # =========================================================================
    "Bamanankan": "Bambara",

    # =========================================================================
    # Nigerian Pidgin variants
    # =========================================================================
    "Nigerian-Pidgin": "Nigerian Pidgin",

    # =========================================================================
    # Slovenian variants
    # =========================================================================
    "Slovene": "Slovenian",

    # =========================================================================
    # Sinhala variants
    # =========================================================================
    "Sinhalese": "Sinhala",

    # =========================================================================
    # Greek variants
    # =========================================================================
    "Modern Greek": "Greek",

    # =========================================================================
    # Ilocano variants
    # =========================================================================
    "Ilokano": "Ilocano",

    # =========================================================================
    # Urdu variants
    # =========================================================================
    "Roman Urdu": "Urdu",

    # =========================================================================
    # Quechua variants
    # =========================================================================
    "Eastern Apurímac Quechua": "Quechua",
    "Cusco Quechua": "Quechua",

    # =========================================================================
    # Mongolian variants
    # =========================================================================
    "Halh Mongolian": "Mongolian",

    # =========================================================================
    # Navajo variants
    # =========================================================================
    "Navaho": "Navajo",

    # =========================================================================
    # Odia variants
    # =========================================================================
    "Oriya": "Odia",

    # =========================================================================
    # Oromo variants
    # =========================================================================
    "Oromo (West Central)": "Oromo",
    "Afaan Oromo": "Oromo",

    # =========================================================================
    # Haitian Creole variants
    # =========================================================================
    "Haitian": "Haitian Creole",

    # =========================================================================
    # Maori variants (diacritic normalization)
    # =========================================================================
    "Māori": "Maori",
    "C.I. Māori": "Cook Islands Maori",
    "Cook Islands Māori": "Cook Islands Maori",

    # =========================================================================
    # Sami variants (diacritic normalization)
    # =========================================================================
    "Sámi": "Sami",

    # =========================================================================
    # Upper Sorbian variants
    # =========================================================================
    "Sorbian (Upper)": "Upper Sorbian",

    # =========================================================================
    # Manipuri variants
    # =========================================================================
    "Meitei": "Manipuri",

    # =========================================================================
    # Frisian variants
    # =========================================================================
    "West Frisian": "Frisian",

    # =========================================================================
    # Fulfulde / Fula variants
    # =========================================================================
    "Fulfulde (Nigerian)": "Fulfulde",

    # =========================================================================
    # Kurdish variants (keep Kurdish as canonical)
    # =========================================================================
    "Kurmanji Kurdish": "Kurdish",

    # =========================================================================
    # Italian dialect labels → standalone dialect names
    # =========================================================================
    "Italian (Sicilian)": "Sicilian",
    "Italian (Neapolitan)": "Neapolitan",
    "Italian (Tuscan)": "Tuscan",
    "Italian (Venetian)": "Venetian",
    "Italian (Emilian)": "Emilian",
    "Italian (Lombard)": "Lombard",
    "Italian (Friulian)": "Friulian",
    "Italian (Sardinian)": "Sardinian",

    # =========================================================================
    # Diacritic / accent variants
    # =========================================================================
    "Yorùbá": "Yoruba",
    "Éwé": "Ewe",
    "Gà": "Ga",
    "Asháninka": "Ashaninka",

    # =========================================================================
    # Typos
    # =========================================================================
    "Malayam": "Malayalam",
    "Urdi": "Urdu",
    "Galacian": "Galician",
    "Glacian": "Galician",
    "Komi-Ziran": "Komi-Zyrian",
    "Alsacian": "Alsatian",

    # =========================================================================
    # Sign language normalization
    # =========================================================================
    "Sign Language": "Sign Language (unspecified)",

    # =========================================================================
    # African American English
    # =========================================================================
    "African American Vernacular English": "African American English",

    # =========================================================================
    # Other ISO codes
    # =========================================================================
    "afr": "Afrikaans",
    "hau": "Hausa",
    "jav": "Javanese",
    "kin": "Kinyarwanda",
    "mar": "Marathi",
    "pcm": "Nigerian Pidgin",
    "sun": "Sundanese",
    "swe": "Swedish",
    "tat": "Tatar",
    "ukr": "Ukrainian",
    "vmw": "Makhuwa",
    "yor": "Yoruba",
}

# =============================================================================
# 2. PROGRAMMING LANGUAGES: To be excluded
# =============================================================================
PROGRAMMING_LANGUAGES = {
    "Python", "Java", "C++", "C", "C#", "JavaScript", "TypeScript",
    "Go", "Ruby", "Rust", "PHP", "Scala", "Kotlin", "Swift", "Perl",
    "Lua", "R", "Julia", "Haskell", "Bash", "Shell", "HTML", "CSS",
    "SQL", "MATLAB", "Racket", "Objective-C", "Dart", "Groovy",
    "Assembly", "Fortran", "COBOL", "Prolog", "Lisp", "Erlang",
    "Clojure", "F#", "OCaml", "Scheme", "Smalltalk", "VHDL",
    "Verilog", "PowerShell", "Awk", "Sed",
}

# =============================================================================
# 3. EXCLUDE LIST: Non-languages to remove
# =============================================================================
EXCLUDE_SET = {
    # ---- Writing systems / scripts ----
    "Cyrillic", "CJK", "Latin script", "Latin", "Devanagari",
    "Arabic Script", "Baybayin", "Lontara", "Thaana", "Takri",
    "Prachalit", "Sylheti Nagri",

    # ---- Language families ----
    "Indo-European", "Sino-Tibetan", "Polynesian", "Uto-Aztecan",
    "Afro-Asiatic", "Austronesian", "Niger-Congo", "Dravidian",
    "Turkic", "Uralic", "Malayo-Polynesian", "Hokan",
    "Mixe-Zoque", "Pama-Nyungan", "Trans-New Guinea",
    "Araucanian", "Oto-Manguean", "Mande",
    "Nilo-Saharan", "Edoid",
    "Romance languages", "Polynesian languages",

    # ---- Dataset / corpus names that leaked in ----
    "l2-standard", "l2-perceived", "buckeye", "doreco", "voxangeles",

    # ---- Modalities (not languages) ----
    "Audio", "Video", "Acoustic", "Visual",

    # ---- Nationalities / regions (not languages) ----
    "British", "East Asian", "Indian",

    # ---- Other non-language entries ----
    "Mathematical Symbols", "Formal Languages",
    "Other Languages", "Other",
    "Unassigned", "Artificial",

    # ---- Language pairs (not individual languages) ----
    "English-Macedonian", "English-Albanian",
    "English-Spanish", "English-French",
    "English-German", "English-Chinese",
    "English-Arabic", "English-Hindi",
    "English-Japanese", "English-Korean",
    "English-Russian", "English-Portuguese",
    "English-Turkish", "English-Vietnamese",
    "English-Thai", "English-Indonesian",
    "Spanish-English", "French-English",
    "German-English", "Chinese-English",
    "Arabic-English", "Hindi-English",
    "Japanese-English", "Korean-English",
}

# =============================================================================
# 4. Case-insensitive lookup helpers
# =============================================================================

def _build_case_insensitive_map(mapping):
    """Build a case-insensitive version of the normalization map."""
    ci_map = {}
    for k, v in mapping.items():
        ci_map[k.lower()] = v
    return ci_map


def _build_case_insensitive_set(s):
    """Build a case-insensitive version of a set."""
    return {item.lower() for item in s}


NORMALIZE_MAP_CI = _build_case_insensitive_map(NORMALIZE_MAP)
PROGRAMMING_CI = _build_case_insensitive_set(PROGRAMMING_LANGUAGES)
EXCLUDE_CI = _build_case_insensitive_set(EXCLUDE_SET)

# Known non-pairs: hyphenated names that are NOT language pairs
KNOWN_NON_PAIRS = {
    "komi-zyrian", "komi-ziran", "min dong", "shipibo-konibo",
    "serbo-croatian", "kazakh-russian sign language",
    "guinea kpelle", "kok borok", "hiri motu",
    "cook islands maori", "cook islands māori",
    "sri lankan malay", "hawaiian pidgin",
    "haitian creole", "reunionese creole",
    "seychellois creole", "louisiana creole",
    "early new high german", "old church slavonic",
    "central bikol",
}


# =============================================================================
# 5. Core cleanup logic
# =============================================================================

def is_language_pair(lang):
    """Check if a string looks like a language pair (e.g., 'English-French')."""
    if "-" not in lang:
        return False

    # Check against known non-pairs first
    if lang.lower() in KNOWN_NON_PAIRS:
        return False

    parts = lang.split("-")
    if len(parts) == 2:
        p1, p2 = parts[0].strip(), parts[1].strip()
        # Both parts start with uppercase and are multi-char → likely a pair
        if (len(p1) > 1 and p1[0].isupper() and
            len(p2) > 1 and p2[0].isupper()):
            return True

    return False


def clean_language(lang):
    """
    Clean a single language string.
    Returns the cleaned language name, or None if it should be excluded.
    """
    lang = lang.strip()
    lang_lower = lang.lower()

    # Exclude programming languages
    if lang_lower in PROGRAMMING_CI:
        return None

    # Exclude non-language entries
    if lang_lower in EXCLUDE_CI:
        return None

    # Exclude language pairs
    if is_language_pair(lang):
        return None

    # Normalize known variants (case-insensitive)
    if lang_lower in NORMALIZE_MAP_CI:
        return NORMALIZE_MAP_CI[lang_lower]

    # If it looks like a short ISO code (2-4 lowercase letters), try to resolve
    if len(lang) <= 4 and lang.isalpha() and lang == lang.lower():
        if lang_lower in NORMALIZE_MAP_CI:
            return NORMALIZE_MAP_CI[lang_lower]
        else:
            return None  # Unresolved ISO code

    return lang


def clean_languages(languages):
    """
    Clean a list of languages.
    Returns deduplicated list of cleaned language names and removed items.
    """
    cleaned = []
    removed = []

    for lang in languages:
        result = clean_language(lang)
        if result is not None:
            cleaned.append(result)
        else:
            removed.append(lang)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for lang in cleaned:
        if lang not in seen:
            seen.add(lang)
            deduped.append(lang)

    return deduped, removed


def clean_record(record):
    """
    Clean the languages field of a single record.
    Returns the cleaned record and a change log dict.
    """
    original = record.get("languages", [])
    if not original:
        return record, None

    cleaned, removed = clean_languages(original)

    changes = None
    if cleaned != original:
        # Build normalized pairs for reporting
        normalized = []
        for lang in original:
            result = clean_language(lang)
            if result is not None and result != lang:
                normalized.append(f"{lang} → {result}")

        changes = {
            "title": record.get("title", "Unknown"),
            "original": original,
            "cleaned": cleaned,
            "removed": removed,
            "normalized": normalized,
        }

    record["languages"] = cleaned
    return record, changes


# =============================================================================
# 6. File I/O
# =============================================================================

def load_json_files(directory):
    """Load all JSON files from a directory, returning (filepath, data) pairs."""
    results = []
    json_files = sorted(Path(directory).glob("*.json"))

    for filepath in json_files:
        # Skip summary/meta files
        if filepath.name.startswith("_"):
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append((filepath, data))
        except (json.JSONDecodeError, Exception) as e:
            print(f"  [WARN] Skipping {filepath.name}: {e}")

    return results


def save_json(filepath, data):
    """Save data to a JSON file with nice formatting."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# 7. Reporting
# =============================================================================

def print_change_log(all_changes):
    """Print a detailed log of all changes made."""
    if not all_changes:
        print("\nNo changes were needed.")
        return

    print(f"\n{'=' * 70}")
    print(f" CHANGE LOG ({len(all_changes)} records modified)")
    print(f"{'=' * 70}")

    for i, change in enumerate(all_changes, 1):
        print(f"\n  [{i}] {change['title'][:80]}")
        print(f"      Before:     {change['original']}")
        print(f"      After:      {change['cleaned']}")
        if change["removed"]:
            print(f"      Removed:    {change['removed']}")
        if change["normalized"]:
            print(f"      Normalized: {change['normalized']}")


def print_before_after_counts(before_counter, after_counter):
    """Print side-by-side before/after language counts."""
    print(f"\n{'=' * 70}")
    print(f" BEFORE vs AFTER: Language Counts")
    print(f"{'=' * 70}")

    print(f"\n  Unique languages BEFORE: {len(before_counter)}")
    print(f"  Unique languages AFTER:  {len(after_counter)}")
    print(f"  Reduction: {len(before_counter) - len(after_counter)} entries consolidated\n")

    # Items removed entirely
    removed_langs = set(before_counter.keys()) - set(after_counter.keys())
    if removed_langs:
        print(f"  Languages/entries REMOVED ({len(removed_langs)}):")
        for lang in sorted(removed_langs):
            print(f"    ✗ {lang} (was {before_counter[lang]})")

    # Items added by normalization
    new_langs = set(after_counter.keys()) - set(before_counter.keys())
    if new_langs:
        print(f"\n  Languages ADDED via normalization ({len(new_langs)}):")
        for lang in sorted(new_langs):
            print(f"    + {lang} ({after_counter[lang]})")

    # Items whose counts changed
    changed = []
    for lang in sorted(after_counter.keys()):
        before = before_counter.get(lang, 0)
        after = after_counter[lang]
        if before != after and lang not in new_langs:
            changed.append((lang, before, after))

    if changed:
        print(f"\n  Languages with CHANGED counts ({len(changed)}):")
        for lang, before, after in changed:
            print(f"    ~ {lang}: {before} → {after} ({after - before:+d})")

    # Top languages after cleanup
    print(f"\n  Top 50 languages AFTER cleanup:")
    for i, (lang, count) in enumerate(after_counter.most_common(50), 1):
        print(f"    {i:3d}. {lang:<45} {count:4d}")

    # Show full list if more than 50
    remaining = after_counter.most_common()[50:]
    if remaining:
        print(f"\n  Remaining {len(remaining)} languages:")
        for i, (lang, count) in enumerate(remaining, 51):
            print(f"    {i:3d}. {lang:<45} {count:4d}")

    total_before = sum(before_counter.values())
    total_after = sum(after_counter.values())
    print(f"\n  Total occurrences BEFORE: {total_before}")
    print(f"  Total occurrences AFTER:  {total_after}")
    print(f"  Removed: {total_before - total_after}")


def export_csv(counter, output_path, field_name="item"):
    """Export counts to CSV."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"{field_name},count\n")
        for item, count in counter.most_common():
            item_escaped = f'"{item}"' if "," in item else item
            f.write(f"{item_escaped},{count}\n")
    print(f"  Exported to {output_path}")


# =============================================================================
# 8. Main
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up language fields in metadata JSON files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (recommended first step)
  python cleanup_languages.py /path/to/json/files --dry-run --verbose

  # Apply changes in place
  python cleanup_languages.py /path/to/json/files

  # Apply changes to a separate directory
  python cleanup_languages.py /path/to/json/files --outdir cleaned/

  # Combined JSON file
  python cleanup_languages.py combined.json --combined --dry-run --verbose

  # Export CSV reports
  python cleanup_languages.py /path/to/json/files --export-csv --outdir results/
        """
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
        "--dry-run", action="store_true",
        help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--outdir", default=None,
        help="Write cleaned files to a separate directory (default: overwrite in place)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed change log"
    )
    parser.add_argument(
        "--export-csv", action="store_true",
        help="Export before/after counts to CSV"
    )

    args = parser.parse_args()

    all_changes = []
    before_counter = Counter()
    after_counter = Counter()

    # ---- Combined JSON file ----
    if args.combined or os.path.isfile(args.path):
        with open(args.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = data if isinstance(data, list) else [data]
        print(f"Loaded {len(records)} records from {args.path}")

        for record in records:
            for lang in record.get("languages", []):
                before_counter[lang] += 1

            _, changes = clean_record(record)
            if changes:
                all_changes.append(changes)

            for lang in record.get("languages", []):
                after_counter[lang] += 1

        if not args.dry_run:
            outpath = args.path
            if args.outdir:
                os.makedirs(args.outdir, exist_ok=True)
                outpath = os.path.join(args.outdir, Path(args.path).name)

            save_json(outpath, data if isinstance(data, list) else records[0])
            print(f"Saved cleaned data to {outpath}")

    # ---- Directory of JSON files ----
    else:
        file_data = load_json_files(args.path)
        print(f"Loaded {len(file_data)} files from {args.path}")

        for filepath, data in file_data:
            records = data if isinstance(data, list) else [data]

            for record in records:
                for lang in record.get("languages", []):
                    before_counter[lang] += 1

                _, changes = clean_record(record)
                if changes:
                    all_changes.append(changes)

                for lang in record.get("languages", []):
                    after_counter[lang] += 1

            if not args.dry_run:
                if args.outdir:
                    os.makedirs(args.outdir, exist_ok=True)
                    outpath = Path(args.outdir) / filepath.name
                else:
                    outpath = filepath

                save_json(outpath, data)

        if not args.dry_run:
            dest = args.outdir or args.path
            print(f"Saved cleaned files to {dest}")

    # ---- Reporting ----
    if args.verbose:
        print_change_log(all_changes)

    print_before_after_counts(before_counter, after_counter)

    print(f"\n  Total records modified: {len(all_changes)}")

    if args.dry_run:
        print("\n  *** DRY RUN — No files were modified ***")

    # ---- Export CSV ----
    if args.export_csv:
        csv_dir = args.outdir or "."
        os.makedirs(csv_dir, exist_ok=True)
        export_csv(
            before_counter,
            os.path.join(csv_dir, "languages_before.csv"),
            "language"
        )
        export_csv(
            after_counter,
            os.path.join(csv_dir, "languages_after.csv"),
            "language"
        )


if __name__ == "__main__":
    main()