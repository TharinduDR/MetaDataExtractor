#!/usr/bin/env python3
"""
Print ACL Anthology volume URLs, one per line.

  python extract_volume_urls.py 2025.acl D18
  python extract_volume_urls.py --year 2025
  python extract_volume_urls.py --year 2025 --main-only
  python extract_volume_urls.py --year 2025 --no-api   # probe raw, skip the API

Set GITHUB_TOKEN in the environment to raise the API rate limit.
Add --debug for verbose progress on stderr.
"""
import sys
import os
import argparse
import xml.etree.ElementTree as ET
import requests

RAW_BASE = "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml"
API_DIR = "https://api.github.com/repos/acl-org/acl-anthology/contents/data/xml"

MAIN_VENUES = {
    "acl", "naacl", "emnlp", "eacl", "coling", "findings",
    "conll", "tacl", "cl", "lrec", "wmt", "semeval",
}

# Candidate venue slugs to probe when the API is unavailable (--no-api / fallback).
# Extend freely; unknown ones just 404 and are skipped.
CANDIDATE_VENUES = sorted(MAIN_VENUES | {
    "aacl", "starsem", "bea", "wnut", "wassa", "sigmorphon", "sigdial",
    "nlp4call", "louhi", "clinicalnlp", "blackboxnlp", "repl4nlp",
    "mwe", "textgraphs", "gebnlp", "americasnlp", "africanlp", "arabicnlp",
    "calcs", "case", "codi", "crac", "cmcl", "dialdoc", "ecnlp", "fever",
    "fieldmatters", "gem", "humeval", "insights", "iwslt", "law", "loresmt",
    "matching", "nlp4pi", "nlperspectives", "nlposs", "privatenlp",
    "sdp", "sicon", "slpat", "trustnlp", "unlp", "wmt", "wnu", "woah", "nlp4dh",
})

DEBUG = False


def log(msg):
    if DEBUG:
        print(msg, file=sys.stderr)


def _headers():
    h = {"Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
        log("using GITHUB_TOKEN for API auth")
    return h


def list_year_collections_api(year, main_only=False):
    log(f"listing data/xml via GitHub API for year {year}")
    resp = requests.get(API_DIR, timeout=30, headers=_headers())
    log(f"  HTTP {resp.status_code}")
    if resp.status_code == 403:
        log("  API 403 (rate limit?) — caller should fall back to --no-api")
    resp.raise_for_status()
    entries = resp.json()
    prefix = f"{year}."
    coll_ids = []
    for e in entries:
        name = e.get("name", "")
        if name.startswith(prefix) and name.endswith(".xml"):
            coll_ids.append(name[:-4])
    return _filter(coll_ids, main_only)


def list_year_collections_probe(year, main_only=False):
    """Discover collections by HEAD-probing raw URLs for candidate venues."""
    log(f"probing raw for {year}.* candidate collections")
    venues = MAIN_VENUES if main_only else CANDIDATE_VENUES
    coll_ids = []
    for v in sorted(venues):
        cid = f"{year}.{v}"
        url = f"{RAW_BASE}/{cid}.xml"
        r = requests.head(url, timeout=15, allow_redirects=True)
        log(f"  {cid}.xml -> HTTP {r.status_code}")
        if r.status_code == 200:
            coll_ids.append(cid)
    return _filter(coll_ids, main_only)


def _filter(coll_ids, main_only):
    if main_only:
        coll_ids = [c for c in coll_ids
                    if c.split(".", 1)[1].split("-", 1)[0] in MAIN_VENUES]
    coll_ids = sorted(set(coll_ids))
    log(f"  {len(coll_ids)} collections: {coll_ids}")
    return coll_ids


def load_collection(ident):
    if os.path.isfile(ident):
        root = ET.parse(ident).getroot()
        return root.get("id"), root
    coll_id = ident[:-4] if ident.endswith(".xml") else ident
    url = f"{RAW_BASE}/{coll_id}.xml"
    log(f"fetching: {url}")
    resp = requests.get(url, timeout=30)
    log(f"  HTTP {resp.status_code}, {len(resp.content)} bytes")
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    return root.get("id", coll_id), root


def volume_urls(ident):
    coll_id, root = load_collection(ident)
    return [f"https://aclanthology.org/volumes/{coll_id}-{vol.get('id')}/"
            for vol in root.findall("volume") if vol.get("id")]


def main():
    global DEBUG
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("collections", nargs="*")
    p.add_argument("--year")
    p.add_argument("--main-only", action="store_true")
    p.add_argument("--no-api", action="store_true",
                   help="skip the GitHub API, discover collections by probing raw")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    DEBUG = args.debug

    if args.year:
        if args.no_api:
            idents = list_year_collections_probe(args.year, args.main_only)
        else:
            try:
                idents = list_year_collections_api(args.year, args.main_only)
            except Exception as e:
                log(f"API listing failed ({e}); falling back to raw probe")
                idents = list_year_collections_probe(args.year, args.main_only)
    elif args.collections:
        idents = args.collections
    else:
        p.print_help(sys.stderr)
        sys.exit(1)

    total = 0
    for ident in idents:
        try:
            for url in volume_urls(ident):
                print(url)
                total += 1
        except Exception as e:
            print(f"ERROR processing {ident}: {e}", file=sys.stderr)

    log(f"total URLs printed: {total}")
    if total == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()