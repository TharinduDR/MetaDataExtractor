"""
Batch metadata extraction for ACL Anthology volumes.

Given an ACL Anthology volume URL (e.g., https://aclanthology.org/volumes/2025.acl-long/),
this script:
1. Scrapes all paper IDs from the volume page
2. For each paper: downloads PDF -> extracts metadata -> deletes PDF
3. Saves a JSON file per paper (e.g., 2025.acl-long.39.json)

This processes one paper at a time to minimise disk usage.
Use --keep_pdfs to retain downloaded PDFs.

Usage:
    python batch_extract_metadata.py <volume_url> [--output_dir OUTPUT_DIR] [--max_pages 5] [--start_from PAPER_ID] [--keep_pdfs]

Examples:
    python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/
    python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-short/ --output_dir ./results --max_pages 4
    python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/ --start_from 2025.acl-long.50
    python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/ --keep_pdfs
"""

import torch
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
import pypdfium2 as pdfium
import json
import re
import sys
import os
import argparse
import requests
import time
from pathlib import Path


# ============================================================
# Model loading (done once)
# ============================================================

def load_model(model_name="Qwen/Qwen3-VL-8B-Instruct"):
    """Load the Qwen3-VL model and processor"""
    print(f"Loading model: {model_name}")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map="auto"
    )
    processor = AutoProcessor.from_pretrained(model_name)
    print("Model loaded successfully.")
    return model, processor


# ============================================================
# ACL Anthology scraping
# ============================================================

def get_paper_ids_from_volume(volume_url):
    """
    Scrape paper IDs from an ACL Anthology volume page.

    Args:
        volume_url: e.g., https://aclanthology.org/volumes/2025.acl-long/

    Returns:
        List of paper IDs like ['2025.acl-long.1', '2025.acl-long.2', ...]
    """
    print(f"Fetching volume page: {volume_url}")

    response = requests.get(volume_url, timeout=30)
    response.raise_for_status()
    html = response.text

    # Extract the volume prefix from URL
    # https://aclanthology.org/volumes/2025.acl-long/ -> 2025.acl-long
    volume_match = re.search(r'/volumes/([^/]+)/?', volume_url)
    if not volume_match:
        raise ValueError(f"Could not extract volume ID from URL: {volume_url}")
    volume_id = volume_match.group(1)

    # Find all paper IDs in the HTML
    # PDFs are linked as https://aclanthology.org/2025.acl-long.1.pdf
    pattern = rf'({re.escape(volume_id)}\.\d+)\.pdf'
    paper_ids = sorted(set(re.findall(pattern, html)),
                       key=lambda x: int(x.split('.')[-1]))

    # Filter out paper ID .0 (that's the frontmatter/proceedings itself)
    paper_ids = [pid for pid in paper_ids if not pid.endswith('.0')]

    print(f"Found {len(paper_ids)} papers in volume {volume_id}")
    return paper_ids


def download_pdf(paper_id, download_dir):
    """
    Download a PDF from ACL Anthology.

    Args:
        paper_id: e.g., '2025.acl-long.39'
        download_dir: Directory to save PDFs

    Returns:
        Path to downloaded PDF, or None if failed
    """
    pdf_url = f"https://aclanthology.org/{paper_id}.pdf"
    pdf_path = os.path.join(download_dir, f"{paper_id}.pdf")

    # Skip if already downloaded
    if os.path.exists(pdf_path):
        return pdf_path

    try:
        response = requests.get(pdf_url, timeout=60)
        response.raise_for_status()

        with open(pdf_path, 'wb') as f:
            f.write(response.content)

        return pdf_path

    except Exception as e:
        print(f"  ERROR downloading {paper_id}: {e}")
        return None


# ============================================================
# PDF to images
# ============================================================

def pdf_to_images(pdf_path, scale=2.0):
    """Convert PDF pages to PIL Images using pypdfium2"""
    pdf = pdfium.PdfDocument(pdf_path)
    images = []
    for page_number in range(len(pdf)):
        page = pdf[page_number]
        pil_image = page.render(scale=scale).to_pil()
        images.append(pil_image)
        page.close()
    pdf.close()
    return images


# ============================================================
# Metadata extraction prompt
# ============================================================

METADATA_EXTRACTION_PROMPT = """You are a metadata extraction assistant for academic papers in computational linguistics and NLP.

Given this research paper, extract the following metadata and return it as a JSON object:

1. **title**: The full title of the paper.

2. **authors**: A list of all authors as they appear in the paper.

3. **languages**: A list of languages the paper actually conducted experiments on or evaluated. 
   - Only include languages where results are reported.
   - Do NOT include languages that were merely mentioned, discussed as future work, or dropped/eliminated from the study.

4. **research_areas**: Select between 1 and 3 research areas from the list below that best describe the paper's core contributions. Be strict and selective:
   - Only choose areas that are central to the paper, not tangential.
   - If an area's description includes multiple sub-topics (e.g., "Multilinguality, Machine Translation and Translation Aids"), the paper must genuinely fit the relevant sub-topics, not just one keyword.
   - Prefer fewer, more accurate areas over more, loosely fitting ones.

Available research areas:
* T01 Applications Involving LRs and Evaluation for any area/domain of language and speech processing
* T02 Bias, Offensive and Non-inclusive Language; Guardrails, filters
* T03 Corpora, Treebanks and Annotation; Tools, Systems and Platforms
* T04 Dialogue, Conversational Systems, Chatbots, Human-Robot Interaction
* T05 Digital Humanities, Cultural Heritage and Computational Social Science
* T06 Discourse and Pragmatics
* T07 Document Classification, Information Retrieval and Cross-lingual Retrieval
* T08 Ethics, Research Reproducibility and Replicability, and Environmental Issues
* T09 Evaluation, Validation, Quality Assurance and Benchmarking Methodologies
* T10 Inference, Reasoning, Question Answering
* T11 Information Extraction and Text Mining
* T12 Interpretability/explainability of language models and language and speech processing tools
* T13 Knowledge discovery/representation (knowledge graphs, linked data, terminologies, lexicons, ontologies, etc.)
* T14 Language Modeling and LRs (including training, fine-tuning, representation learning, and generation of synthetic data)
* T15 Lexicon and Semantics
* T16 Multilinguality, Machine Translation (including Speech-to-Speech) and Translation Aids
* T17 Multimodality, Cross-modality (including Sign Languages, Vision and Other Modalities), Multimodal Applications, Grounded Language Acquisition
* T18 Natural Language Generation and Summarization
* T19 Simplification, Plain Language and Assistive Technologies
* T20 Opinion & Argument Mining, Sentiment Analysis, Emotion Recognition/Generation
* T21 Parsing, Tagging, Chunking, Grammar, Syntax, Morphosyntax, Morphology
* T22 Policy and Legal Issues (including Language Resource Infrastructures, Interoperability, Standards for LRs, Metadata)
* T23 Psycholinguistics, Cognitive Linguistics and Linguistic Theories
* T24 Social Media Processing
* T25 Speech Resources and Processing (including Phonetic Databases, Phonology, Prosody, Speech Recognition, Synthesis and Spoken Language Understanding)

Return ONLY a valid JSON object in the following format, with no additional text, explanation, or markdown fences:

{
  "title": "...",
  "authors": ["...", "..."],
  "languages": ["...", "..."],
  "research_areas": ["T09 Evaluation, Validation, Quality Assurance and Benchmarking Methodologies", "..."]
}"""


# ============================================================
# Metadata extraction
# ============================================================

def extract_metadata_from_pdf(model, processor, pdf_path, max_pages=5):
    """Extract metadata from a single PDF using the model"""
    images = pdf_to_images(pdf_path)
    pages_to_use = images

    content = []
    for img in pages_to_use:
        content.append({"type": "image", "image": img})
    content.append({"type": "text", "text": METADATA_EXTRACTION_PROMPT})

    messages = [{"role": "user", "content": content}]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt"
    )
    inputs = inputs.to(model.device)

    generated_ids = model.generate(
        **inputs,
        max_new_tokens=2048,
        temperature=0.1,
        do_sample=False
    )

    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0]

    return output_text


def parse_json_output(output_text):
    """Parse JSON from model output with multiple fallback strategies"""
    # Try direct parse
    try:
        return json.loads(output_text.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown fences
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    brace_match = re.search(r'\{.*\}', output_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ============================================================
# Batch processing
# ============================================================

def process_volume(volume_url, output_dir="./output", pdf_dir="./pdfs",
                   max_pages=5, start_from=None, keep_pdfs=False,
                   model_name="Qwen/Qwen3-VL-32B-Instruct"):
    """
    Process an entire ACL Anthology volume one paper at a time:
    download PDF -> extract metadata -> delete PDF -> next paper.

    Args:
        volume_url: ACL Anthology volume URL
        output_dir: Directory for output JSON files
        pdf_dir: Directory for downloaded PDFs
        max_pages: Max pages per paper to send to model
        start_from: Paper ID to resume from (e.g., '2025.acl-long.50')
        keep_pdfs: If True, keep PDFs after processing instead of deleting
        model_name: HuggingFace model name
    """
    # Create directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    # Step 1: Get paper IDs
    print(f"\n{'=' * 80}")
    print("STEP 1: Fetching paper IDs from ACL Anthology")
    print(f"{'=' * 80}")
    paper_ids = get_paper_ids_from_volume(volume_url)

    if not paper_ids:
        print("No papers found. Check the URL.")
        return

    # Handle --start_from for resuming
    if start_from:
        try:
            start_idx = paper_ids.index(start_from)
            paper_ids = paper_ids[start_idx:]
            print(f"Resuming from {start_from} ({len(paper_ids)} papers remaining)")
        except ValueError:
            print(f"WARNING: {start_from} not found in volume. Processing all papers.")

    # Step 2: Load model
    print(f"\n{'=' * 80}")
    print("STEP 2: Loading model")
    print(f"{'=' * 80}")
    model, processor_obj = load_model(model_name)

    # Step 3: Process each paper (download -> extract -> delete)
    print(f"\n{'=' * 80}")
    print(f"STEP 3: Processing {len(paper_ids)} papers (download → extract → cleanup)")
    print(f"{'=' * 80}")

    results_summary = {
        'success': [],
        'failed_parse': [],
        'failed_download': [],
        'failed_error': []
    }

    for i, paper_id in enumerate(paper_ids, 1):
        json_path = os.path.join(output_dir, f"{paper_id}.json")

        # Skip if already processed
        if os.path.exists(json_path):
            print(f"\n[{i}/{len(paper_ids)}] {paper_id} - already processed, skipping")
            results_summary['success'].append(paper_id)
            continue

        print(f"\n[{i}/{len(paper_ids)}] {paper_id}")
        pdf_path = os.path.join(pdf_dir, f"{paper_id}.pdf")

        # --- Download ---
        if not os.path.exists(pdf_path):
            print(f"  ⬇️  Downloading...")
            pdf_path = download_pdf(paper_id, pdf_dir)
            if pdf_path is None:
                results_summary['failed_download'].append(paper_id)
                continue
            time.sleep(0.5)  # Be polite to ACL servers

        # --- Extract metadata ---
        try:
            print(f"  🔍 Extracting metadata...")
            raw_output = extract_metadata_from_pdf(
                model, processor_obj, pdf_path, max_pages=max_pages
            )

            # Parse JSON
            metadata = parse_json_output(raw_output)

            if metadata is None:
                print(f"  ⚠️  Could not parse JSON for {paper_id}")
                raw_path = os.path.join(output_dir, f"{paper_id}_raw.txt")
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(raw_output)
                print(f"  Raw output saved to {raw_path}")
                results_summary['failed_parse'].append(paper_id)
            else:
                # Add paper_id to metadata
                metadata['paper_id'] = paper_id
                metadata['acl_url'] = f"https://aclanthology.org/{paper_id}/"

                # Save JSON
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

                print(f"  ✅ Saved: {json_path}")
                print(f"     Title: {metadata.get('title', 'N/A')[:70]}...")
                print(f"     Authors: {len(metadata.get('authors', []))} | "
                      f"Languages: {len(metadata.get('languages', []))} | "
                      f"Areas: {len(metadata.get('research_areas', []))}")
                results_summary['success'].append(paper_id)

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results_summary['failed_error'].append(paper_id)

        # --- Cleanup PDF ---
        if not keep_pdfs and os.path.exists(pdf_path):
            os.remove(pdf_path)
            print(f"  🗑️  PDF deleted")

    # Step 4: Print summary
    print(f"\n{'=' * 80}")
    print("PROCESSING COMPLETE")
    print(f"{'=' * 80}")
    total = len(paper_ids)
    print(f"Total papers:     {total}")
    print(f"✅ Success:        {len(results_summary['success'])}")
    print(f"❌ Parse failures: {len(results_summary['failed_parse'])}")
    print(f"❌ Download fails: {len(results_summary['failed_download'])}")
    print(f"❌ Other errors:   {len(results_summary['failed_error'])}")

    # Save summary
    summary_path = os.path.join(output_dir, "_processing_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results_summary, f, indent=2)
    print(f"\nSummary saved to {summary_path}")

    # List failures for easy re-processing
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
        description="Extract metadata from all papers in an ACL Anthology volume",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/
  python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-short/ --output_dir ./short_results
  python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/ --start_from 2025.acl-long.50
  python batch_extract_metadata.py https://aclanthology.org/volumes/2025.acl-long/ --keep_pdfs
        """
    )

    parser.add_argument("volume_url",
                        help="ACL Anthology volume URL (e.g., https://aclanthology.org/volumes/2025.acl-long/)")
    parser.add_argument("--output_dir", default="./output",
                        help="Directory for output JSON files (default: ./output)")
    parser.add_argument("--pdf_dir", default="./pdfs",
                        help="Directory for downloaded PDFs (default: ./pdfs)")
    parser.add_argument("--max_pages", type=int, default=5,
                        help="Max pages per paper to process (default: 5)")
    parser.add_argument("--start_from", default=None,
                        help="Paper ID to resume from (e.g., 2025.acl-long.50)")
    parser.add_argument("--keep_pdfs", action="store_true",
                        help="Keep PDFs after processing instead of deleting them")
    parser.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct",
                        help="HuggingFace model name (default: Qwen/Qwen3-VL-8B-Instruct)")

    args = parser.parse_args()

    process_volume(
        volume_url=args.volume_url,
        output_dir=args.output_dir,
        pdf_dir=args.pdf_dir,
        max_pages=args.max_pages,
        start_from=args.start_from,
        keep_pdfs=args.keep_pdfs,
        model_name=args.model
    )


if __name__ == "__main__":
    main()