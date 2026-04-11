#!/usr/bin/env python3
"""
Post-processing script to clean up research_areas fields in metadata JSON files.
Normalizes variant/truncated/partial research area labels to canonical forms.

Canonical areas (from batch_extract.py):
  T01-T29, where T10=QA, T11=IE, T12=Interpretability, T13=Knowledge,
  T14=LM, T15=Lexicon, T16=MT, T17=Multimodality, T18=Summarization,
  T19=Simplification, T20=Opinion/Sentiment, T21=Parsing, T22=Psycholing,
  T23=Social Media, T24=Speech, T25=Legal, T26=Clinical, T27=Code,
  T28=Authorship/AI Detection, T29=Education

Usage:
    python cleanup_research_areas.py /path/to/json/files --dry-run --verbose
    python cleanup_research_areas.py combined.json --combined --dry-run --verbose
    python cleanup_research_areas.py /path/to/json/files --outdir cleaned/
    python cleanup_research_areas.py /path/to/json/files  # in-place
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

# =============================================================================
# 1. CANONICAL RESEARCH AREAS
# =============================================================================
CANONICAL_AREAS = {
    "T01": "T01 Bias, Guardrails, filters",
    "T02": "T02 Corpora, Treebanks and Annotation; Tools, Systems and Platforms",
    "T03": "T03 Dialogue, Conversational Systems, Chatbots, Human-Robot Interaction",
    "T04": "T04 Digital Humanities, Cultural Heritage and Computational Social Science",
    "T05": "T05 Discourse and Pragmatics",
    "T06": "T06 Information Retrieval and Cross-lingual Retrieval",
    "T07": "T07 Ethics, Research Reproducibility and Replicability, and Environmental Issues",
    "T08": "T08 Evaluation, Validation, Quality Assurance and Benchmarking Methodologies",
    "T09": "T09 Inference and Reasoning",
    "T10": "T10 Question Answering, Open-domain question answering, closed-domain question answering, extractive and abstractive QA, multi-hop question answering",
    "T11": "T11 Information Extraction, Named Entity Recognition, Relationship Extraction and Event Detection",
    "T12": "T12 Interpretability/explainability of language models and language and speech processing tools",
    "T13": "T13 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, lexicons, ontologies, etc.)",
    "T14": "T14 Language Modeling (including training, fine-tuning, representation learning, and generation of synthetic data)",
    "T15": "T15 Lexicon and Semantics",
    "T16": "T16 Machine Translation (including Speech-to-Speech) and Translation Aids",
    "T17": "T17 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities), Multimodal Applications, Grounded Language Acquisition",
    "T18": "T18 Text Summarization",
    "T19": "T19 Text Simplification, Plain Language and Assistive Technologies",
    "T20": "T20 Opinion & Argument Mining, Offensive Language/ Hate speech/ Toxic Language Detection, Sentiment Analysis, Emotion Recognition/Generation",
    "T21": "T21 Parsing, Tagging, Chunking, Grammar, Syntax, Morphosyntax, Morphology",
    "T22": "T22 Psycholinguistics, Cognitive Linguistics and Linguistic Theories",
    "T23": "T23 Social Media Processing",
    "T24": "T24 Speech Resources and Processing (including Phonetic Databases, Phonology, Prosody, Speech Recognition, Synthesis and Spoken Language Understanding)",
    "T25": "T25 Legal NLP",
    "T26": "T26 Clinical/biomedical NLP, NLP for Mental Health and Wellbeing",
    "T27": "T27 Code generation and programming languages",
    "T28": "T28 Authorship Attribution, AI-Generated Text Detection and Provenance",
    "T29": "T29 NLP for education, Automated essay scoring and feedback generation, grammatical error correction and detection, intelligent tutoring systems",
}

# =============================================================================
# 2. EXPLICIT OVERRIDE MAP
#    Maps known variant strings (exact match) to their canonical key.
#    Covers: bare codes, truncated labels, partial labels, old numbering,
#    misassignments, and all variants seen in production data.
# =============================================================================
EXPLICIT_OVERRIDES = {
    # =======================================================================
    # T01 Bias
    # =======================================================================
    "T01": "T01",
    "T01 Bias, Guardrails, filters": "T01",
    "T01 Bias": "T01",

    # =======================================================================
    # T02 Corpora
    # =======================================================================
    "T02": "T02",
    "T02 Corpora, Treebanks and Annotation; Tools, Systems and Platforms": "T02",
    "T02 Corpora": "T02",
    # Old schema (was T03)
    "T03 Corpora, Treebanks and Annotation; Tools, Systems and Platforms": "T02",

    # =======================================================================
    # T03 Dialogue
    # =======================================================================
    "T03": "T03",
    "T03 Dialogue, Conversational Systems, Chatbots, Human-Robot Interaction": "T03",
    "T03 Dialogue": "T03",
    # Old schema (was T04)
    "T04 Dialogue, Conversational Systems, Chatbots, Human-Robot Interaction": "T03",

    # =======================================================================
    # T04 Digital Humanities
    # =======================================================================
    "T04": "T04",
    "T04 Digital Humanities": "T04",
    "T04 Digital Humanities, Cultural Heritage and Computational Social Science": "T04",
    # Old schema (was T05)
    "T05 Digital Humanities, Cultural Heritage and Computational Social Science": "T04",
    "T05 Digital Humanities": "T04",

    # =======================================================================
    # T05 Discourse
    # =======================================================================
    "T05": "T05",
    "T05 Discourse and Pragmatics": "T05",
    "T05 Discourse": "T05",
    # Old schema (was T06)
    "T06 Discourse and Pragmatics": "T05",

    # =======================================================================
    # T06 Information Retrieval
    # =======================================================================
    "T06": "T06",
    "T06 Information Retrieval and Cross-lingual Retrieval": "T06",
    "T06 Information Retrieval": "T06",
    # Old schema (was T07)
    "T07 Information Retrieval and Cross-lingual Retrieval": "T06",
    "T07 Document Classification, Information Retrieval and Cross-lingual Retrieval": "T06",

    # =======================================================================
    # T07 Ethics
    # =======================================================================
    "T07": "T07",
    "T07 Ethics, Research Reproducibility and Replicability, and Environmental Issues": "T07",
    "T07 Ethics": "T07",
    # Old schema (was T08)
    "T08 Ethics, Research Reproducibility and Replicability, and Environmental Issues": "T07",

    # =======================================================================
    # T08 Evaluation
    # =======================================================================
    "T08": "T08",
    "T08 Evaluation, Validation, Quality Assurance and Benchmarking Methodologies": "T08",
    "T08 Evaluation": "T08",
    # Old schema (was T09)
    "T09 Evaluation, Validation, Quality Assurance and Benchmarking Methodologies": "T08",

    # =======================================================================
    # T09 Inference and Reasoning
    # =======================================================================
    "T09": "T09",
    "T09 Inference and Reasoning": "T09",
    "T09 Inference": "T09",
    # Old schema (was T10)
    "T10 Inference and Reasoning": "T09",
    "T10 Inference, Reasoning, Question Answering": "T09",

    # =======================================================================
    # T10 Question Answering
    # =======================================================================
    "T10": "T10",
    "T10 Question Answering": "T10",
    "T10 Question Answering, Open-domain question answering": "T10",
    "T10 Question Answering, Open-domain question answering, closed-domain question answering, multi-hop question answering": "T10",
    "T10 Question Answering, Open-domain question answering, closed-domain question answering, extractive and abstractive QA, multi-hop question answering": "T10",
    "T10 Question Answering, Open-domain question answering, extractive and abstractive QA, multi-hop question answering": "T10",

    # =======================================================================
    # T11 Information Extraction
    # =======================================================================
    "T11": "T11",
    "T11 Information Extraction": "T11",
    "T11 Information Extraction, Named Entity Recognition, Relationship Extraction and Event Detection": "T11",
    # Old schema (T10 was shared for QA and IE)
    "T10 Information Extraction": "T11",
    "T10 Information Extraction, Named Entity Recognition, Relationship Extraction and Event Detection": "T11",

    # =======================================================================
    # T12 Interpretability
    # =======================================================================
    "T12": "T12",
    "T12 Interpretability/explainability of language models and language and speech processing tools": "T12",
    "T12 Interpretability/explainability": "T12",
    "T12 Interpretability": "T12",
    # Old schema (was T11)
    "T11 Interpretability/explainability of language models": "T12",
    "T11 Interpretability/explainability of language models and language and speech processing tools": "T12",

    # =======================================================================
    # T13 Knowledge discovery
    # =======================================================================
    "T13": "T13",
    "T13 Knowledge discovery/representation": "T13",
    "T13 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, lexicons, ontologies, etc.)": "T13",
    "T13 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, ontologies, etc.)": "T13",
    # Old schema (was T12)
    "T12 Knowledge discovery/representation": "T13",
    "T12 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, ontologies, etc.)": "T13",
    "T12 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, lexicons, ontologies, etc.)": "T13",

    # =======================================================================
    # T14 Language Modeling
    # =======================================================================
    "T14": "T14",
    "T14 Language Modeling": "T14",
    "T14 Language Modeling (including training, fine-tuning, representation learning, and generation of synthetic data)": "T14",
    # Old schema (was T13)
    "T13 Language Modeling": "T14",
    "T13 Language Modeling (including training, fine-tuning, representation learning, and generation of synthetic data)": "T14",
    # Older schema variant
    "T14 Language Modeling and LRs (including training, fine-tuning, representation learning, and generation of synthetic data)": "T14",

    # =======================================================================
    # T15 Lexicon and Semantics
    # =======================================================================
    "T15": "T15",
    "T15 Lexicon and Semantics": "T15",
    # Old schema (was T14)
    "T14 Lexicon and Semantics": "T15",
    # Even older (was T16)
    "T16 Lexicon and Semantics": "T15",

    # =======================================================================
    # T16 Machine Translation
    # =======================================================================
    "T16": "T16",
    "T16 Machine Translation": "T16",
    "T16 Machine Translation and Translation Aids": "T16",
    "T16 Machine Translation (including Speech-to-Speech) and Translation Aids": "T16",
    # Old schema (was T15)
    "T15 Machine Translation": "T16",
    "T15 Machine Translation and Translation Aids": "T16",
    "T15 Machine Translation (including Speech-to-Speech) and Translation Aids": "T16",
    # Even older (was T18)
    "T18 Multilinguality, Machine Translation (including Speech-to-Speech) and Translation Aids": "T16",

    # =======================================================================
    # T17 Multimodality
    # =======================================================================
    "T17": "T17",
    "T17 Multimodality": "T17",
    "T17 Multimodality, Cross-modality": "T17",
    "T17 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities)": "T17",
    "T17 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities), Multimodal Applications, Grounded Language Acquisition": "T17",
    # Old schema (was T16)
    "T16 Multimodality": "T17",
    "T16 Multimodality, Cross-modality": "T17",
    "T16 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities)": "T17",
    "T16 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities), Multimodal Applications, Grounded Language Acquisition": "T17",
    # Even older (was T19)
    "T19 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities), Multimodal Applications, Grounded Language Acquisition": "T17",

    # =======================================================================
    # T18 Text Summarization
    # =======================================================================
    "T18": "T18",
    "T18 Text Summarization": "T18",
    # Old schema (was T17)
    "T17 Text Summarization": "T18",
    # Even older (was T20)
    "T20 Natural Language Generation and Summarization": "T18",

    # =======================================================================
    # T19 Text Simplification
    # =======================================================================
    "T19": "T19",
    "T19 Text Simplification": "T19",
    "T19 Text Simplification, Plain Language and Assistive Technologies": "T19",
    # Old schema (was T18)
    "T18 Text Simplification, Plain Language and Assistive Technologies": "T19",
    "T18 Text Simplification": "T19",
    # Even older (was T21)
    "T21 Simplification, Plain Language and Assistive Technologies": "T19",

    # =======================================================================
    # T20 Opinion & Argument Mining / Sentiment
    # =======================================================================
    "T20": "T20",
    "T20 Opinion & Argument Mining": "T20",
    "T20 Opinion & Argument Mining, Sentiment Analysis": "T20",
    "T20 Sentiment Analysis": "T20",
    "T20 Sentiment Analysis, Emotion Recognition/Generation": "T20",
    "T20 Opinion & Argument Mining, Sentiment Analysis, Emotion Recognition/Generation": "T20",
    "T20 Opinion & Argument Mining, Offensive Language/ Hate speech/ Toxic Language Detection, Sentiment Analysis, Emotion Recognition/Generation": "T20",
    # Old schema (was T19)
    "T19 Opinion & Argument Mining": "T20",
    "T19 Opinion & Argument Mining, Sentiment Analysis": "T20",
    "T19 Sentiment Analysis": "T20",
    "T19 Opinion & Argument Mining, Sentiment Analysis, Emotion Recognition/Generation": "T20",
    "T19 Opinion & Argument Mining, Offensive Language/ Hate speech/ Toxic Language Detection, Sentiment Analysis, Emotion Recognition/Generation": "T20",
    # Even older (was T22)
    "T22 Opinion & Argument Mining, Sentiment Analysis, Emotion Recognition/Generation": "T20",

    # =======================================================================
    # T21 Parsing
    # =======================================================================
    "T21": "T21",
    "T21 Parsing": "T21",
    "T21 Parsing, Tagging, Chunking, Grammar, Syntax, Morphosyntax, Morphology": "T21",
    # Old schema (was T20)
    "T20 Parsing, Tagging, Chunking, Grammar, Syntax, Morphosyntax, Morphology": "T21",
    # Even older (was T23)
    "T23 Parsing, Tagging, Chunking, Grammar, Syntax, Morphosyntax, Morphology": "T21",

    # =======================================================================
    # T22 Psycholinguistics
    # =======================================================================
    "T22": "T22",
    "T22 Psycholinguistics": "T22",
    "T22 Psycholinguistics, Cognitive Linguistics and Linguistic Theories": "T22",
    # Old schema (was T21)
    "T21 Psycholinguistics": "T22",
    "T21 Psycholinguistics, Cognitive Linguistics and Linguistic Theories": "T22",
    # Even older (was T25)
    "T25 Psycholinguistics, Cognitive Linguistics and Linguistic Theories": "T22",

    # =======================================================================
    # T23 Social Media Processing
    # =======================================================================
    "T23": "T23",
    "T23 Social Media Processing": "T23",
    # Old schema (was T22)
    "T22 Social Media Processing": "T23",
    # Even older (was T26)
    "T26 Social Media Processing": "T23",
    # MISASSIGNMENT: T24 Social Media → T23
    "T24 Social Media Processing": "T23",

    # =======================================================================
    # T24 Speech
    # =======================================================================
    "T24": "T24",
    "T24 Speech Resources and Processing": "T24",
    "T24 Speech Resources and Processing (including Phonetic Databases, Phonology, Prosody, Speech Recognition, Synthesis and Spoken Language Understanding)": "T24",
    # Old schema (was T23)
    "T23 Speech Resources and Processing": "T24",
    "T23 Speech Resources and Processing (including Phonetic Databases, Phonology, Prosody, Speech Recognition, Synthesis and Spoken Language Understanding)": "T24",
    # Even older (was T27)
    "T27 Speech Resources and Processing (including Phonetic Databases, Phonology, Prosody, Speech Recognition, Synthesis and Spoken Language Understanding)": "T24",

    # =======================================================================
    # T25 Legal NLP
    # =======================================================================
    "T25": "T25",
    "T25 Legal NLP": "T25",
    # Old schema (was T24)
    "T24 Legal NLP": "T25",

    # =======================================================================
    # T26 Clinical/biomedical NLP
    # =======================================================================
    "T26": "T26",
    "T26 Clinical/biomedical NLP": "T26",
    "T26 Clinical/biomedical NLP, NLP for Mental Health and Wellbeing": "T26",
    # Old schema (was T25)
    "T25 Clinical/biomedical NLP": "T26",
    "T25 Clinical/biomedical NLP, NLP for Mental Health and Wellbeing": "T26",

    # =======================================================================
    # T27 Code generation
    # =======================================================================
    "T27": "T27",
    "T27 Code generation and programming languages": "T27",
    # Old schema (was T26)
    "T26 Code generation and programming languages": "T27",

    # =======================================================================
    # T28 Authorship Attribution / AI-Generated Text Detection
    # =======================================================================
    "T28": "T28",
    "T28 Authorship Attribution": "T28",
    "T28 AI-Generated Text Detection and Provenance": "T28",
    "T28 AI-Generated Text Detection": "T28",
    "T28 Authorship Attribution, AI-Generated Text Detection and Provenance": "T28",
    # Old schema (was T27)
    "T27 Authorship Attribution": "T28",
    "T27 AI-Generated Text Detection and Provenance": "T28",
    "T27 Authorship Attribution, AI-Generated Text Detection and Provenance": "T28",

    # =======================================================================
    # T29 NLP for education
    # =======================================================================
    "T29": "T29",
    "T29 NLP for education": "T29",
    "T29 NLP for education, Automated essay scoring and feedback generation, grammatical error correction and detection, intelligent tutoring systems": "T29",
    # Old schema (was T28)
    "T28 NLP for education": "T29",
    "T28 NLP for education, Automated essay scoring and feedback generation, grammatical error correction and detection, intelligent tutoring systems": "T29",

    # =======================================================================
    # VERY OLD SCHEMA mappings (LREC-style T-codes)
    # These come from an older numbering where codes were different
    # =======================================================================
    "T01 Applications Involving LRs and Evaluation for any area/domain of language and speech processing": "T08",
}


# =============================================================================
# 3. KEYWORD-BASED FALLBACK RESOLUTION
#    When exact match fails but we have a T-code, use keywords to disambiguate
# =============================================================================

KEYWORD_RULES = {
    "T10": {
        "keywords": {"QUESTION ANSWERING", "QA", "OPEN-DOMAIN", "CLOSED-DOMAIN", "MULTI-HOP"},
        "target": "T10",
    },
    "T11": {
        "keywords": {"INFORMATION EXTRACTION", "NAMED ENTITY", "NER", "RELATIONSHIP EXTRACTION", "EVENT DETECTION"},
        "target": "T11",
    },
}

# For bare T10 with no keywords, we need to check content
T11_KEYWORDS = {"INFORMATION EXTRACTION", "NAMED ENTITY", "NER", "RELATIONSHIP EXTRACTION", "EVENT DETECTION"}
T10_KEYWORDS = {"QUESTION ANSWERING", "QA", "OPEN-DOMAIN", "CLOSED-DOMAIN", "MULTI-HOP"}


# =============================================================================
# 4. Core cleanup logic
# =============================================================================

def extract_code(area_string):
    """Extract the T-code from a research area string."""
    match = re.match(r"^(T\d+)", area_string.strip())
    if match:
        return match.group(1)
    return None


def clean_research_area(area):
    """
    Normalize a research area string to its canonical form.
    Returns the canonical string, or the original if unrecognized.
    """
    area = area.strip()

    # 1. Try explicit override (exact match)
    if area in EXPLICIT_OVERRIDES:
        key = EXPLICIT_OVERRIDES[area]
        return CANONICAL_AREAS[key]

    # 2. Case-insensitive explicit override
    area_lower = area.lower()
    for override_key, canonical_key in EXPLICIT_OVERRIDES.items():
        if override_key.lower() == area_lower:
            return CANONICAL_AREAS[canonical_key]

    # 3. Extract T-code and try keyword-based resolution
    code = extract_code(area)
    if code:
        area_upper = area.upper()

        # Special: disambiguate T10 (old shared code for QA + IE)
        if code == "T10":
            if any(kw in area_upper for kw in T11_KEYWORDS):
                return CANONICAL_AREAS["T11"]
            elif any(kw in area_upper for kw in T10_KEYWORDS):
                return CANONICAL_AREAS["T10"]
            else:
                # Bare T10 defaults to QA (more common)
                return CANONICAL_AREAS["T10"]

        # Direct code lookup for valid codes
        if code in CANONICAL_AREAS:
            return CANONICAL_AREAS[code]

    # 4. Return original if nothing matched (will be flagged in report)
    return area


def clean_research_areas(areas):
    """Clean a list of research areas. Returns deduplicated list and details."""
    cleaned = []
    changes = []

    for area in areas:
        canonical = clean_research_area(area)
        if canonical != area:
            changes.append(f"'{area}' → '{canonical}'")
        cleaned.append(canonical)

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for area in cleaned:
        if area not in seen:
            seen.add(area)
            deduped.append(area)

    duplicates_removed = len(cleaned) - len(deduped)
    return deduped, changes, duplicates_removed


def clean_record(record):
    """Clean the research_areas field of a single record."""
    original = record.get("research_areas", [])
    if not original:
        return record, None

    cleaned, changes, duplicates_removed = clean_research_areas(original)

    change_log = None
    if cleaned != original:
        change_log = {
            "title": record.get("title", "Unknown"),
            "original": original,
            "cleaned": cleaned,
            "changes": changes,
            "duplicates_removed": duplicates_removed,
        }

    record["research_areas"] = cleaned
    return record, change_log


# =============================================================================
# 5. File I/O
# =============================================================================

def load_json_files(directory):
    """Load all JSON files from a directory, skipping non-data files."""
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
    """Save data to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# 6. Reporting
# =============================================================================

def print_change_log(all_changes):
    """Print detailed change log."""
    if not all_changes:
        print("\nNo changes were needed.")
        return

    print(f"\n{'=' * 70}")
    print(f" CHANGE LOG ({len(all_changes)} records modified)")
    print(f"{'=' * 70}")

    for i, change in enumerate(all_changes, 1):
        print(f"\n  [{i}] {change['title'][:80]}")
        print(f"      Before: {change['original']}")
        print(f"      After:  {change['cleaned']}")
        for c in change["changes"]:
            print(f"        → {c}")
        if change["duplicates_removed"] > 0:
            print(f"        ({change['duplicates_removed']} duplicate(s) removed after normalization)")


def print_before_after_counts(before_counter, after_counter):
    """Print before/after comparison and validation."""
    print(f"\n{'=' * 70}")
    print(f" BEFORE vs AFTER: Research Area Counts")
    print(f"{'=' * 70}")

    print(f"\n  Unique labels BEFORE: {len(before_counter)}")
    print(f"  Unique labels AFTER:  {len(after_counter)}")
    print(f"  Reduction: {len(before_counter) - len(after_counter)} variants consolidated\n")

    # Removed labels
    removed = set(before_counter.keys()) - set(after_counter.keys())
    if removed:
        print(f"  Labels REMOVED / merged ({len(removed)}):")
        for label in sorted(removed):
            print(f"    ✗ {label[:90]} (was {before_counter[label]})")

    # Changed counts
    changed = []
    for label in sorted(after_counter.keys()):
        before = before_counter.get(label, 0)
        after = after_counter[label]
        if before != after:
            changed.append((label, before, after))

    if changed:
        print(f"\n  Labels with CHANGED counts ({len(changed)}):")
        for label, before, after in changed:
            short = label[:80]
            print(f"    ~ {short}: {before} → {after} ({after - before:+d})")

    # Final distribution
    print(f"\n  FINAL Research Area Distribution:")
    print(f"  {'-' * 110}")
    for i, (label, count) in enumerate(after_counter.most_common(), 1):
        print(f"    {i:3d}. {label:<100} {count:4d}")

    total = sum(after_counter.values())
    print(f"\n  Total assignments: {total}")

    # Validate all labels are canonical
    canonical_set = set(CANONICAL_AREAS.values())
    non_canonical = set(after_counter.keys()) - canonical_set
    if non_canonical:
        print(f"\n  ⚠ WARNING: {len(non_canonical)} non-canonical labels remain:")
        for label in sorted(non_canonical):
            print(f"    ? \"{label}\" ({after_counter[label]})")
        print(f"\n  → Add these to EXPLICIT_OVERRIDES to resolve them.")
    else:
        print(f"\n  ✓ All {len(after_counter)} labels match the {len(CANONICAL_AREAS)} canonical research areas.")


def export_csv(counter, output_path):
    """Export counts to CSV."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("research_area,count\n")
        for item, count in counter.most_common():
            item_escaped = f'"{item}"' if "," in item else item
            f.write(f"{item_escaped},{count}\n")
    print(f"  Exported to {output_path}")


# =============================================================================
# 7. Main
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up research_areas in metadata JSON files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (recommended first step)
  python cleanup_research_areas.py /path/to/json/files --dry-run --verbose

  # Apply changes in place
  python cleanup_research_areas.py /path/to/json/files

  # Apply changes to a separate directory
  python cleanup_research_areas.py /path/to/json/files --outdir cleaned/

  # Combined JSON file
  python cleanup_research_areas.py combined.json --combined --dry-run --verbose

  # Export CSV reports
  python cleanup_research_areas.py /path/to/json/files --export-csv --outdir results/
        """
    )
    parser.add_argument("path", help="Directory of JSON files or a single combined JSON file")
    parser.add_argument("--combined", action="store_true", help="Treat path as a single combined JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    parser.add_argument("--outdir", default=None, help="Write cleaned files to a separate directory (default: overwrite in place)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed change log")
    parser.add_argument("--export-csv", action="store_true", help="Export before/after counts to CSV")

    args = parser.parse_args()

    all_changes = []
    before_counter = Counter()
    after_counter = Counter()

    # ---- Load and process ----
    if args.combined or os.path.isfile(args.path):
        with open(args.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data if isinstance(data, list) else [data]
        print(f"Loaded {len(records)} records from {args.path}")

        for record in records:
            for area in record.get("research_areas", []):
                before_counter[area] += 1
            _, changes = clean_record(record)
            if changes:
                all_changes.append(changes)
            for area in record.get("research_areas", []):
                after_counter[area] += 1

        if not args.dry_run:
            outpath = args.path
            if args.outdir:
                os.makedirs(args.outdir, exist_ok=True)
                outpath = os.path.join(args.outdir, Path(args.path).name)
            save_json(outpath, data if isinstance(data, list) else records[0])
            print(f"Saved cleaned data to {outpath}")

    else:
        file_data = load_json_files(args.path)
        print(f"Loaded {len(file_data)} files from {args.path}")

        for filepath, data in file_data:
            records = data if isinstance(data, list) else [data]
            for record in records:
                for area in record.get("research_areas", []):
                    before_counter[area] += 1
                _, changes = clean_record(record)
                if changes:
                    all_changes.append(changes)
                for area in record.get("research_areas", []):
                    after_counter[area] += 1

            if not args.dry_run:
                if args.outdir:
                    os.makedirs(args.outdir, exist_ok=True)
                    outpath = Path(args.outdir) / filepath.name
                else:
                    outpath = filepath
                save_json(outpath, data)

        if not args.dry_run:
            print(f"Saved cleaned files to {args.outdir or args.path}")

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
        export_csv(before_counter, os.path.join(csv_dir, "research_areas_before.csv"))
        export_csv(after_counter, os.path.join(csv_dir, "research_areas_after.csv"))


if __name__ == "__main__":
    main()