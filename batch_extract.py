"""
Batch metadata extraction for ACL Anthology volumes (dual-model + adjudication).

Given an ACL Anthology volume URL (e.g., https://aclanthology.org/volumes/2025.acl-long/
or https://aclanthology.org/volumes/D18-1/), this script:
  1. Scrapes all paper IDs from the volume page (supports both modern and old-style IDs).
  2. For each paper: downloads the PDF, renders the first N pages to images ONCE.
  3. Extracts metadata with TWO open-weight vision-language models:
        - Qwen3-VL-32B          (tag: "qwen32b")
        - gemma-4-31B-it        (tag: "gemma")
     Each model returns the languages studied and the research areas addressed,
     research areas drawn from a fixed inventory of 29 categories.
  4. Reconciles the two outputs PER FIELD (languages, research_areas):
        - Where the two models AGREE, the shared label is accepted.
        - Where they DISAGREE, the disagreement is resolved by a third model,
          Qwen3-VL-32B-Thinking. The two candidate labels are passed to the
          Thinking model ANONYMOUSLY (randomly shuffled as Option A / Option B,
          with no indication of which base model produced which), together with
          the same page images, and it selects the more accurate candidate.
  5. Saves one JSON file per paper with the reconciled fields plus full
     provenance (each model's raw answer, agreement flag, adjudication outcome).

Title and authors are also extracted (from the first model that parses) but are
NOT adjudicated; only `languages` and `research_areas` go through reconciliation,
in line with the described methodology.

PDFs are processed one at a time and deleted afterwards (use --keep_pdfs to retain).

VRAM NOTE: all three large VLMs are loaded in one process, but inference runs
sequentially (one model.generate at a time), so only one model's activations
are ever live. Three 32B models in bf16 are ~65GB of weights each (~195GB),
which fits on 2x H200 141GB (282GB). With only two GPUs you cannot pin all
three models to separate cards; the recommended layout is to pin one extractor
to each GPU and let the adjudicator shard across both:
    --qwen_device cuda:0 --gemma_device cuda:1 --thinking_device auto
The default ("auto" for all three) also works, since each sequential load
accounts for memory already taken by the previous model.

Usage:
    python batch_extract_metadata.py <volume_url> [options]

Examples:
    python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/
    python batch_extract_metadata.py https://aclanthology.org/volumes/D18-1/ \
        --qwen_device cuda:0 --gemma_device cuda:1 --thinking_device cuda:2
    python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/ \
        --start_from 2025.acl-long.50 --keep_pdfs
"""

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
import pypdfium2 as pdfium
import json
import re
import sys
import os
import argparse
import random
import hashlib
import requests
import time
from pathlib import Path
from tqdm import tqdm


# Default model identifiers. Override on the CLI if your repo names differ.
#   NOTE: "google/gemma-4-31b-it" follows the gemma-3-27b-it naming convention;
#   verify the exact HuggingFace repo id for the gemma-4 release and adjust if needed.
DEFAULT_QWEN_MODEL = "Qwen/Qwen3-VL-32B-Instruct"
DEFAULT_GEMMA_MODEL = "google/gemma-4-31b-it"
DEFAULT_THINKING_MODEL = "Qwen/Qwen3-VL-32B-Thinking"

QWEN_TAG = "qwen32b"
GEMMA_TAG = "gemma"

EXTRACTION_MAX_NEW_TOKENS = 2048
THINKING_MAX_NEW_TOKENS = 4096  # the Thinking model emits a reasoning trace first

# Fields that go through agreement / adjudication.
RECONCILED_FIELDS = ("languages", "research_areas")


# ============================================================
# Model loading
# ============================================================

def load_model(model_name, device_map="auto"):
    """Load a vision-language model and its processor.

    Uses AutoModelForImageTextToText so the same loader works across model
    families (Qwen3-VL and Gemma). `device_map` may be "auto" or a concrete
    device such as "cuda:0".
    """
    print(f"Loading model: {model_name}  (device_map={device_map})")
    model = AutoModelForImageTextToText.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map=device_map,
    )
    processor = AutoProcessor.from_pretrained(model_name)
    print(f"  -> loaded {model_name}")
    return model, processor


# ============================================================
# ACL Anthology scraping
# ============================================================

def _trailing_num(pid):
    """Extract the trailing numeric portion of a paper ID."""
    m = re.search(r'\d+$', pid)
    return m.group() if m else ""


def _is_frontmatter(pid, volume_id):
    """
    Detect volume frontmatter / proceedings-front entries.

    Conventions:
      - Modern IDs: '<volume_id>.0'           e.g. '2025.acl-long.0'
      - Old-style:  '<volume_id>000' or
                    '<volume_id>0000'         e.g. 'D18-1000', 'P19-10000'
    """
    if pid == f"{volume_id}.0":
        return True
    if re.fullmatch(rf'{re.escape(volume_id)}0+', pid):
        return True
    return False


def get_paper_ids_from_volume(volume_url):
    """
    Scrape paper IDs from an ACL Anthology volume page.

    Supports both ID formats:
      - Modern: '2025.acl-long.39'   (dot separator, no zero-padding)
      - Old:    'D18-1001'           (no separator, zero-padded)

    Returns:
        Sorted list of paper IDs.
    """
    print(f"Fetching volume page: {volume_url}")

    response = requests.get(volume_url, timeout=30)
    response.raise_for_status()
    html = response.text

    volume_match = re.search(r'/volumes/([^/?#]+)/?', volume_url)
    if not volume_match:
        raise ValueError(f"Could not extract volume ID from URL: {volume_url}")
    volume_id = volume_match.group(1)

    # Try modern format first: <volume_id>.<num>.pdf
    modern_pattern = rf'({re.escape(volume_id)}\.\d+)\.pdf'
    paper_ids = set(re.findall(modern_pattern, html))

    # Fall back to old format: <volume_id><num>.pdf (no separator)
    if not paper_ids:
        old_pattern = rf'({re.escape(volume_id)}\d+)\.pdf'
        paper_ids = set(re.findall(old_pattern, html))

    paper_ids = sorted(paper_ids, key=lambda x: int(_trailing_num(x)))
    paper_ids = [pid for pid in paper_ids if not _is_frontmatter(pid, volume_id)]

    print(f"Found {len(paper_ids)} papers in volume {volume_id}")
    return paper_ids


def download_pdf(paper_id, download_dir, max_retries=3):
    """Download a PDF from ACL Anthology with retries and backoff."""
    pdf_url = f"https://aclanthology.org/{paper_id}.pdf"
    pdf_path = os.path.join(download_dir, f"{paper_id}.pdf")

    if os.path.exists(pdf_path):
        return pdf_path

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(pdf_url, timeout=60)
            response.raise_for_status()
            with open(pdf_path, 'wb') as f:
                f.write(response.content)
            return pdf_path
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s

    print(f"  ERROR downloading {paper_id} after {max_retries} attempts: {last_err}")
    return None


# ============================================================
# PDF to images
# ============================================================

def render_paper_images(pdf_path, scale=2.0, max_pages=None):
    """Render PDF pages to PIL Images using pypdfium2 (done once per paper)."""
    pdf = pdfium.PdfDocument(pdf_path)
    images = []
    n_pages = len(pdf) if max_pages is None else min(len(pdf), max_pages)
    for page_number in range(n_pages):
        page = pdf[page_number]
        pil_image = page.render(scale=scale).to_pil()
        images.append(pil_image)
        page.close()
    pdf.close()
    return images


# ============================================================
# Shared prompt building blocks
# ============================================================

LANGUAGE_RULES = """- Only include languages where results are reported.
- Do NOT include languages that were merely mentioned, discussed as future work, or dropped/eliminated from the study.
- ONLY include natural human languages (e.g., English, French, Mandarin Chinese). NEVER include programming languages (Python, Java, C++, JavaScript, SQL, Rust, etc.), markup languages (HTML, XML), or formal languages.
- Always use the FULL English name of the language, never ISO 639 codes. For example:
  - Use "Arabic" not "ar" or "ara"
  - Use "German" not "de" or "deu"
  - Use "Swahili" not "swa"
  - Use "English" not "eng"
- Normalize language name variants to a single canonical form:
  - "Mandarin", "Mandarin Chinese", "Chinese (Mandarin)", "Simplified Chinese", "Chinese (Simplified)" -> "Chinese"
  - "Traditional Chinese", "Chinese (Traditional)" -> "Chinese"
  - "Cantonese" should remain "Cantonese" (it is distinct)
  - "Brazilian Portuguese" -> "Portuguese"
  - "Farsi" -> "Persian"
  - "Panjabi" -> "Punjabi"
  - "Uighur" -> "Uyghur"
  - "isiZulu" -> "Zulu"
  - "isiXhosa" -> "Xhosa"
  - "Bahasa Indonesian" -> "Indonesian"
- Do NOT include:
  - Language families (Indo-European, Sino-Tibetan, Polynesian)
  - Writing systems or scripts (Cyrillic, CJK, Latin)
  - Dialects listed only as labels (l2-standard, buckeye)
  - Mathematical or symbolic systems
  - Sign languages unless the paper specifically studies them"""

RESEARCH_AREA_LIST = """* T01 Bias, Guardrails, filters
* T02 Corpora, Treebanks and Annotation; Tools, Systems and Platforms
* T03 Dialogue, Conversational Systems, Chatbots, Human-Robot Interaction
* T04 Digital Humanities, Cultural Heritage and Computational Social Science
* T05 Discourse and Pragmatics
* T06 Information Retrieval and Cross-lingual Retrieval
* T07 Ethics, Research Reproducibility and Replicability, and Environmental Issues
* T08 Evaluation, Validation, Quality Assurance and Benchmarking Methodologies
* T09 Inference and Reasoning
* T10 Question Answering, Open-domain question answering, closed-domain question answering, extractive and abstractive QA, multi-hop question answering
* T11 Information Extraction, Named Entity Recognition, Relationship Extraction and Event Detection
* T12 Interpretability/explainability of language models and language and speech processing tools
* T13 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, lexicons, ontologies, etc.)
* T14 Language Modeling (including training, fine-tuning, representation learning, and generation of synthetic data)
* T15 Lexicon and Semantics
* T16 Machine Translation (including Speech-to-Speech) and Translation Aids
* T17 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities), Multimodal Applications, Grounded Language Acquisition
* T18 Text Summarization
* T19 Text Simplification, Plain Language and Assistive Technologies
* T20 Opinion & Argument Mining, Offensive Language/ Hate speech/ Toxic Language Detection, Sentiment Analysis, Emotion Recognition/Generation
* T21 Parsing, Tagging, Chunking, Grammar, Syntax, Morphosyntax, Morphology
* T22 Psycholinguistics, Cognitive Linguistics and Linguistic Theories
* T23 Social Media Processing
* T24 Speech Resources and Processing (including Phonetic Databases, Phonology, Prosody, Speech Recognition, Synthesis and Spoken Language Understanding)
* T25 Legal NLP
* T26 Clinical/biomedical NLP, NLP for Mental Health and Wellbeing
* T27 Code generation and programming languages
* T28 Authorship Attribution, AI-Generated Text Detection and Provenance
* T29 NLP for education, Automated essay scoring and feedback generation, grammatical error correction and detection, intelligent tutoring systems"""

RESEARCH_AREA_RULES = """- Select between 1 and 3 research areas that best describe the paper's core contributions. Be strict and selective.
- Only choose areas that are central to the paper, not tangential.
- If an area's description includes multiple sub-topics (e.g., "Machine Translation and Translation Aids"), the paper must genuinely fit the relevant sub-topics, not just one keyword.
- Prefer fewer, more accurate areas over more, loosely fitting ones."""


METADATA_EXTRACTION_PROMPT = f"""You are a metadata extraction assistant for academic papers in computational linguistics and NLP.

Given this research paper, extract the following metadata and return it as a JSON object:

1. **title**: The full title of the paper.

2. **authors**: A list of all authors as they appear in the paper.

3. **languages**: A list of languages the paper actually conducted experiments on or evaluated.
{LANGUAGE_RULES}

4. **research_areas**: Select research areas from the list below.
{RESEARCH_AREA_RULES}

Available research areas:
{RESEARCH_AREA_LIST}

Return ONLY a valid JSON object in the following format, with no additional text, explanation, or markdown fences:

{{
  "title": "...",
  "authors": ["...", "..."],
  "languages": ["...", "..."],
  "research_areas": ["...", "..."]
}}"""


# Per-field guidance reused by the adjudicator.
_FIELD_GUIDANCE = {
    "languages": (
        "the list of LANGUAGES the paper conducts experiments on or evaluates",
        LANGUAGE_RULES,
    ),
    "research_areas": (
        "the list of RESEARCH AREAS (from the fixed inventory below) that best "
        "describe the paper's core contributions",
        RESEARCH_AREA_RULES + "\n\nAvailable research areas:\n" + RESEARCH_AREA_LIST,
    ),
}


def build_adjudication_prompt(field, option_a, option_b):
    """Build an anonymous A/B adjudication prompt for a single field.

    The two candidate answers are presented as Option A and Option B with no
    indication of which model produced either one.
    """
    field_desc, criteria = _FIELD_GUIDANCE[field]
    return f"""You are adjudicating metadata extracted from a research paper. You are shown the first pages of the paper as images.

Two independent annotators each produced a candidate answer for {field_desc}.

The criteria both annotators were asked to follow:
{criteria}

Two candidate answers are given below. You do NOT know which annotator produced which; judge them only on the basis of the paper images and the criteria above.

Option A:
{json.dumps(option_a, ensure_ascii=False)}

Option B:
{json.dumps(option_b, ensure_ascii=False)}

Decide which single candidate is more accurate for this paper. Favour the candidate that correctly captures all and only the valid items per the criteria: penalise candidates that omit valid items or that include spurious or out-of-scope items.

Think step by step, then end your response with exactly one line:
ANSWER: A
or
ANSWER: B"""


# ============================================================
# Inference helpers
# ============================================================

def run_inference(model, processor, images, prompt, max_new_tokens):
    """Run a single VLM call over the given images + text prompt."""
    content = [{"type": "image", "image": img} for img in images]
    content.append({"type": "text", "text": prompt})
    messages = [{"role": "user", "content": content}]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = inputs.to(model.device)

    generated_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
    )

    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    return processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]


def parse_json_output(output_text):
    """Parse JSON from model output with multiple fallback strategies."""
    try:
        return json.loads(output_text.strip())
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r'\{.*\}', output_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def parse_choice(text):
    """Extract the adjudicator's 'A' / 'B' choice, ignoring any <think> trace."""
    if not text:
        return None
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    m = re.search(r'ANSWER\s*[:\-]?\s*([AB])', cleaned, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback: last standalone A/B token.
    tokens = re.findall(r'\b([AB])\b', cleaned)
    if tokens:
        return tokens[-1].upper()
    return None


# ============================================================
# Reconciliation
# ============================================================

def _norm_set(values):
    """Normalize a field value to a comparable set (order- and case-insensitive)."""
    if not values:
        return frozenset()
    out = set()
    for v in values:
        if isinstance(v, str):
            s = v.strip().casefold()
            if s:
                out.add(s)
    return frozenset(out)


def _seed_for(paper_id, field):
    """Deterministic seed so A/B shuffling is reproducible across runs."""
    h = hashlib.md5(f"{paper_id}:{field}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def adjudicate(think_model, think_processor, images, field,
               value_a, value_b, paper_id, tag_a, tag_b):
    """Resolve a disagreement on `field` using the Thinking model, anonymously.

    Returns (selected_value, selected_tag, choice, raw_output).
    """
    rng = random.Random(_seed_for(paper_id, field))
    swap = rng.random() < 0.5
    if swap:
        opt_a_val, opt_b_val, opt_a_tag, opt_b_tag = value_b, value_a, tag_b, tag_a
    else:
        opt_a_val, opt_b_val, opt_a_tag, opt_b_tag = value_a, value_b, tag_a, tag_b

    prompt = build_adjudication_prompt(field, opt_a_val, opt_b_val)
    raw = run_inference(think_model, think_processor, images, prompt,
                        max_new_tokens=THINKING_MAX_NEW_TOKENS)
    choice = parse_choice(raw)

    if choice == "A":
        return opt_a_val, opt_a_tag, choice, raw
    if choice == "B":
        return opt_b_val, opt_b_tag, choice, raw
    # Unparseable adjudication: fall back to the first model and flag it.
    return value_a, tag_a, None, raw


def reconcile_field(field, meta_a, meta_b, images,
                    think_model, think_processor, paper_id, stats):
    """Reconcile a single field across the two extraction models.

    Returns (final_value, provenance_dict).
    """
    val_a = meta_a.get(field, []) or []
    val_b = meta_b.get(field, []) or []

    if _norm_set(val_a) == _norm_set(val_b):
        stats[f"{field}_agreed"] += 1
        return val_a, {
            QWEN_TAG: val_a,
            GEMMA_TAG: val_b,
            "agreement": True,
            "source": "agreed",
            "selected_model": None,
        }

    selected_val, selected_tag, choice, _raw = adjudicate(
        think_model, think_processor, images, field,
        val_a, val_b, paper_id, QWEN_TAG, GEMMA_TAG,
    )
    stats[f"{field}_adjudicated"] += 1
    return selected_val, {
        QWEN_TAG: val_a,
        GEMMA_TAG: val_b,
        "agreement": False,
        "source": "adjudicated",
        "selected_model": selected_tag,
        "thinking_choice": choice,
        "adjudication_parse_failed": choice is None,
    }


# ============================================================
# Batch processing
# ============================================================

def process_volume(volume_url, output_dir="./output", pdf_dir="./pdfs",
                   max_pages=5, start_from=None, keep_pdfs=False,
                   qwen_model_name=DEFAULT_QWEN_MODEL,
                   gemma_model_name=DEFAULT_GEMMA_MODEL,
                   thinking_model_name=DEFAULT_THINKING_MODEL,
                   qwen_device="auto", gemma_device="auto", thinking_device="auto"):
    """Process an ACL Anthology volume one paper at a time with dual extraction
    and Thinking-model adjudication."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    # Step 1: paper IDs
    print(f"\n{'=' * 80}")
    print("STEP 1: Fetching paper IDs from ACL Anthology")
    print(f"{'=' * 80}")
    paper_ids = get_paper_ids_from_volume(volume_url)
    if not paper_ids:
        print("No papers found. Check the URL.")
        return

    if start_from:
        try:
            start_idx = paper_ids.index(start_from)
            paper_ids = paper_ids[start_idx:]
            print(f"Resuming from {start_from} ({len(paper_ids)} papers remaining)")
        except ValueError:
            print(f"WARNING: {start_from} not found in volume. Processing all papers.")

    # Step 2: load models
    print(f"\n{'=' * 80}")
    print("STEP 2: Loading models (two extractors + one adjudicator)")
    print(f"{'=' * 80}")
    print("Loading three VLMs (weights resident together; inference is sequential). "
          "On 2x H200 141GB, a balanced layout is "
          "--qwen_device cuda:0 --gemma_device cuda:1 --thinking_device auto.")
    qwen_model, qwen_proc = load_model(qwen_model_name, qwen_device)
    gemma_model, gemma_proc = load_model(gemma_model_name, gemma_device)
    think_model, think_proc = load_model(thinking_model_name, thinking_device)

    # Step 3: process
    print(f"\n{'=' * 80}")
    print(f"STEP 3: Processing {len(paper_ids)} papers (download -> extract x2 -> reconcile -> cleanup)")
    print(f"{'=' * 80}")

    results_summary = {
        'success': [],
        'failed_parse': [],
        'failed_download': [],
        'failed_error': [],
    }
    stats = {
        'languages_agreed': 0,
        'languages_adjudicated': 0,
        'research_areas_agreed': 0,
        'research_areas_adjudicated': 0,
        'single_model_fallback': 0,
    }

    pbar = tqdm(paper_ids, desc="Processing papers", unit="paper")
    for paper_id in pbar:
        pbar.set_postfix_str(paper_id, refresh=True)
        json_path = os.path.join(output_dir, f"{paper_id}.json")

        if os.path.exists(json_path):
            tqdm.write(f"    {paper_id} - already processed, skipping")
            results_summary['success'].append(paper_id)
            continue

        pdf_path = os.path.join(pdf_dir, f"{paper_id}.pdf")

        # --- Download ---
        if not os.path.exists(pdf_path):
            tqdm.write(f"    {paper_id} - downloading...")
            pdf_path = download_pdf(paper_id, pdf_dir)
            if pdf_path is None:
                results_summary['failed_download'].append(paper_id)
                continue
            time.sleep(0.5)  # Be polite to ACL servers

        try:
            # --- Render once, reuse for all models ---
            images = render_paper_images(pdf_path, max_pages=max_pages)

            # --- Extract with both models ---
            tqdm.write(f"   {paper_id} - extracting ({QWEN_TAG})...")
            meta_a = parse_json_output(
                run_inference(qwen_model, qwen_proc, images,
                              METADATA_EXTRACTION_PROMPT, EXTRACTION_MAX_NEW_TOKENS))
            tqdm.write(f"   {paper_id} - extracting ({GEMMA_TAG})...")
            meta_b = parse_json_output(
                run_inference(gemma_model, gemma_proc, images,
                              METADATA_EXTRACTION_PROMPT, EXTRACTION_MAX_NEW_TOKENS))

            if meta_a is None and meta_b is None:
                tqdm.write(f"    {paper_id} - both models failed to parse")
                results_summary['failed_parse'].append(paper_id)
                # cleanup before continuing
                if not keep_pdfs and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                continue

            metadata = {
                'paper_id': paper_id,
                'acl_url': f"https://aclanthology.org/{paper_id}/",
            }

            if meta_a is None or meta_b is None:
                # Only one model parsed: use it as-is, no adjudication possible.
                meta = meta_a if meta_a is not None else meta_b
                tag = QWEN_TAG if meta_a is not None else GEMMA_TAG
                stats['single_model_fallback'] += 1
                metadata['title'] = meta.get('title', 'N/A')
                metadata['authors'] = meta.get('authors', [])
                metadata['languages'] = meta.get('languages', []) or []
                metadata['research_areas'] = meta.get('research_areas', []) or []
                metadata['extraction_provenance'] = {
                    field: {
                        "source": f"single_model:{tag}",
                        "agreement": None,
                        "selected_model": tag,
                        tag: meta.get(field, []) or [],
                    }
                    for field in RECONCILED_FIELDS
                }
                tqdm.write(f"    {paper_id} - only {tag} parsed; used without adjudication")
            else:
                # Both parsed: reconcile each field.
                provenance = {}
                for field in RECONCILED_FIELDS:
                    value, prov = reconcile_field(
                        field, meta_a, meta_b, images,
                        think_model, think_proc, paper_id, stats)
                    metadata[field] = value
                    provenance[field] = prov
                # Title/authors are not adjudicated; take from the first model.
                metadata['title'] = meta_a.get('title', meta_b.get('title', 'N/A'))
                metadata['authors'] = meta_a.get('authors', meta_b.get('authors', []))
                metadata['extraction_provenance'] = provenance

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            title_short = (metadata.get('title') or 'N/A')[:60]
            n_langs = len(metadata.get('languages', []))
            n_areas = len(metadata.get('research_areas', []))
            tqdm.write(f"   {paper_id} - {title_short}...")
            tqdm.write(f"     Languages: {n_langs} | Areas: {n_areas}")
            results_summary['success'].append(paper_id)

        except Exception as e:
            tqdm.write(f"   {paper_id} - ERROR: {e}")
            results_summary['failed_error'].append(paper_id)

        # --- Cleanup PDF ---
        if not keep_pdfs and os.path.exists(pdf_path):
            os.remove(pdf_path)

    # Step 4: summary
    print(f"\n{'=' * 80}")
    print("PROCESSING COMPLETE")
    print(f"{'=' * 80}")
    total = len(paper_ids)
    print(f"Total papers:        {total}")
    print(f" Success:           {len(results_summary['success'])}")
    print(f" Parse failures:    {len(results_summary['failed_parse'])}")
    print(f" Download fails:    {len(results_summary['failed_download'])}")
    print(f" Other errors:      {len(results_summary['failed_error'])}")
    print(f"\nReconciliation:")
    print(f"  languages       - agreed: {stats['languages_agreed']} | "
          f"adjudicated: {stats['languages_adjudicated']}")
    print(f"  research_areas  - agreed: {stats['research_areas_agreed']} | "
          f"adjudicated: {stats['research_areas_adjudicated']}")
    print(f"  single-model fallbacks: {stats['single_model_fallback']}")

    summary_path = os.path.join(output_dir, "_processing_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({"results": results_summary, "stats": stats}, f, indent=2)
    print(f"\nSummary saved to {summary_path}")

    all_failures = (results_summary['failed_parse'] +
                    results_summary['failed_download'] +
                    results_summary['failed_error'])
    if all_failures:
        print(f"\nFailed papers ({len(all_failures)}):")
        for pid in all_failures:
            print(f"  - {pid}")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract metadata from an ACL Anthology volume with two VLMs "
                    "and a Thinking-model adjudicator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/
  python batch_extract_metadata.py https://aclanthology.org/volumes/D18-1/ \\
      --qwen_device cuda:0 --gemma_device cuda:1 --thinking_device auto
  python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/ \\
      --start_from 2025.acl-long.50 --keep_pdfs
        """
    )

    parser.add_argument("volume_url",
                        help="ACL Anthology volume URL")
    parser.add_argument("--output_dir", default="./output",
                        help="Directory for output JSON files (default: ./output)")
    parser.add_argument("--pdf_dir", default="./pdfs",
                        help="Directory for downloaded PDFs (default: ./pdfs)")
    parser.add_argument("--max_pages", type=int, default=9,
                        help="Max pages per paper to process (default: 9)")
    parser.add_argument("--start_from", default=None,
                        help="Paper ID to resume from (e.g., 2025.acl-long.50)")
    parser.add_argument("--keep_pdfs", action="store_true",
                        help="Keep PDFs after processing instead of deleting them")

    parser.add_argument("--qwen_model", default=DEFAULT_QWEN_MODEL,
                        help=f"Qwen3-VL-32B extractor (default: {DEFAULT_QWEN_MODEL})")
    parser.add_argument("--gemma_model", default=DEFAULT_GEMMA_MODEL,
                        help=f"gemma-4-31B-it extractor (default: {DEFAULT_GEMMA_MODEL})")
    parser.add_argument("--thinking_model", default=DEFAULT_THINKING_MODEL,
                        help=f"Qwen3-VL-32B-Thinking adjudicator (default: {DEFAULT_THINKING_MODEL})")

    parser.add_argument("--qwen_device", default="auto",
                        help="device_map for the Qwen extractor (e.g. 'cuda:0' or 'auto')")
    parser.add_argument("--gemma_device", default="auto",
                        help="device_map for the Gemma extractor (e.g. 'cuda:1' or 'auto')")
    parser.add_argument("--thinking_device", default="auto",
                        help="device_map for the Thinking adjudicator (e.g. 'cuda:2' or 'auto')")

    args = parser.parse_args()

    process_volume(
        volume_url=args.volume_url,
        output_dir=args.output_dir,
        pdf_dir=args.pdf_dir,
        max_pages=args.max_pages,
        start_from=args.start_from,
        keep_pdfs=args.keep_pdfs,
        qwen_model_name=args.qwen_model,
        gemma_model_name=args.gemma_model,
        thinking_model_name=args.thinking_model,
        qwen_device=args.qwen_device,
        gemma_device=args.gemma_device,
        thinking_device=args.thinking_device,
    )


if __name__ == "__main__":
    main()