#!/usr/bin/env python3
"""
Print ACL Anthology volume URLs, one per line.

Modes:
  # explicit collection ids (as before)
  python extract_volume_urls.py 2025.acl D18

  # every collection for a given year (main confs + findings + workshops)
  python extract_volume_urls.py --year 2025

  # only the major conferences for a year
  python extract_volume_urls.py --year 2025 --main-only

Add --debug for verbose progress on stderr.
"""
import sys
import os
import argparse
import xml.etree.ElementTree as ET
import requests

RAW_BASE = "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml"
API_DIR = "https://api.github.com/repos/acl-org/acl-anthology/contents/data/xml"

# Main-conference venue slugs (modern naming). Extend as needed.
MAIN_VENUES = {
    "acl", "naacl", "emnlp", "eacl", "coling", "findings",
    "conll", "tacl", "cl", "lrec", "wmt", "semeval",
}

DEBUG = False


def log(msg):
    if DEBUG:
        print(msg, file=sys.stderr)


def list_year_collections(year, main_only=False):
    """Return collection ids like '2025.acl' for every 2025.*.xml file."""
    log(f"listing data/xml via GitHub API for year {year}")
    resp = requests.get(API_DIR, timeout=30,
                        headers={"Accept": "application/vnd.github+json"})
    log(f"  HTTP {resp.status_code}")
    resp.raise_for_status()
    entries = resp.json()

    coll_ids = []
    prefix = f"{year}."
    for e in entries:
        name = e.get("name", "")
        if name.startswith(prefix) and name.endswith(".xml"):
            coll_id = name[:-4]  # strip .xml
            if main_only:
                # coll_id looks like '2025.acl' or '2025.findings-acl'
                venue = coll_id.split(".", 1)[1].split("-", 1)[0]
                if venue not in MAIN_VENUES:
                    continue
            coll_ids.append(coll_id)
    coll_ids.sort()
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
    urls = []
    for vol in root.findall("volume"):
        vid = vol.get("id")
        if vid:
            urls.append(f"https://aclanthology.org/volumes/{coll_id}-{vid}/")
    return urls


def main():
    global DEBUG
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("collections", nargs="*",
                   help="explicit collection ids (e.g. 2025.acl D18)")
    p.add_argument("--year", help="emit all collections for this year (e.g. 2025)")
    p.add_argument("--main-only", action="store_true",
                   help="with --year, restrict to major conferences")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    DEBUG = args.debug

    if args.year:
        idents = list_year_collections(args.year, main_only=args.main_only)
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