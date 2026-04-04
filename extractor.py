import torch
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from PIL import Image
import pypdfium2 as pdfium
import json
import re
import sys

# Load the model
model = Qwen3VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen3-VL-8B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-8B-Instruct")


# Convert PDF to images using pypdfium2
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


# Metadata extraction prompt
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
   - ONLY include natural human languages (e.g., English, French, Mandarin Chinese). NEVER include programming languages (Python, Java, C++, JavaScript, SQL, Rust, etc.), markup languages (HTML, XML), or formal languages.
   - Always use the FULL English name of the language, never ISO 639 codes. For example: - Use "Arabic" not "ar" or "ara" - Use "German" not "de" or "deu" - Use "Swahili" not "swa" - Use "English" not "eng"
   - Normalize language name variants to a single canonical form: - "Mandarin", "Mandarin Chinese", "Chinese (Mandarin)", "Simplified Chinese", "Chinese (Simplified)" → "Chinese" - "Traditional Chinese", "Chinese (Traditional)" → "Chinese" - "Cantonese" should remain "Cantonese" (it is distinct) - "Brazilian Portuguese" → "Portuguese" - "Farsi" → "Persian" - "Panjabi" → "Punjabi" - "Uighur" → "Uyghur" - "isiZulu" → "Zulu" - "isiXhosa" → "Xhosa" - "Bahasa Indonesian" → "Indonesian"
   - Do NOT include: - Language families (Indo-European, Sino-Tibetan, Polynesian) - Writing systems or scripts (Cyrillic, CJK, Latin) - Dialects listed only as labels (l2-standard, buckeye) - Mathematical or symbolic systems - Sign languages unless the paper specifically studies them

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
  "research_areas": ["...", "..."]
}"""


def extract_metadata_from_pdf(pdf_path, max_pages=5):
    """
    Extract metadata from an academic paper PDF.

    Args:
        pdf_path: Path to the PDF file
        max_pages: Maximum number of pages to send to the model.
                   Usually the first few pages contain all needed info
                   (title, authors, abstract, intro, results table).
                   Increase if the paper has results/language lists later.
    """
    print(f"Converting PDF to images...")
    images = pdf_to_images(pdf_path)

    # Use first N pages (title, abstract, intro, methods, results)
    pages_to_use = images
    print(f"Using {len(pages_to_use)} of {len(images)} pages for metadata extraction.")

    # Build message content with multiple images
    content = []
    for img in pages_to_use:
        content.append({"type": "image", "image": img})
    content.append({"type": "text", "text": METADATA_EXTRACTION_PROMPT})

    messages = [
        {
            "role": "user",
            "content": content
        }
    ]

    print("Running model inference...")
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
    """
    Parse the model output into a JSON object.
    Handles cases where the model wraps output in markdown fences or adds extra text.
    """
    # Try direct parse first
    try:
        return json.loads(output_text.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code fences
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    brace_match = re.search(r'\{.*\}', output_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    print("WARNING: Could not parse JSON from model output.")
    print("Raw output:")
    print(output_text)
    return None


def save_metadata(metadata, output_path):
    """Save metadata to a JSON file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Metadata saved to {output_path}")


def print_metadata(metadata):
    """Print extracted metadata in a readable format"""
    print(f"\n{'=' * 80}")
    print("EXTRACTED METADATA")
    print(f"{'=' * 80}")
    print(f"\nTitle: {metadata.get('title', 'N/A')}")
    print(f"\nAuthors ({len(metadata.get('authors', []))}):")
    for author in metadata.get('authors', []):
        print(f"  - {author}")
    print(f"\nLanguages ({len(metadata.get('languages', []))}):")
    for lang in metadata.get('languages', []):
        print(f"  - {lang}")
    print(f"\nResearch Areas ({len(metadata.get('research_areas', []))}):")
    for area in metadata.get('research_areas', []):
        print(f"  - {area}")
    print(f"\n{'=' * 80}")


# Main execution
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_metadata.py <pdf_path> [output_json_path] [max_pages]")
        print("Example: python extract_metadata.py paper.pdf metadata.json 5")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace('.pdf', '_metadata.json')
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    print(f"PDF: {pdf_path}")
    print(f"Output: {output_path}")
    print(f"Max pages: {max_pages}")
    print()

    # Step 1: Extract metadata using the model
    print("STEP 1: Extracting metadata from PDF...")
    raw_output = extract_metadata_from_pdf(pdf_path, max_pages=max_pages)

    # Step 2: Parse JSON from model output
    print("\nSTEP 2: Parsing model output...")
    metadata = parse_json_output(raw_output)

    if metadata is None:
        print("Failed to extract metadata. Saving raw output for inspection.")
        with open(output_path.replace('.json', '_raw.txt'), 'w', encoding='utf-8') as f:
            f.write(raw_output)
        sys.exit(1)

    # Step 3: Print and save
    print_metadata(metadata)
    save_metadata(metadata, output_path)

    print(f"\nDone! Metadata saved to {output_path}")