#!/usr/bin/env python3
"""
Print one ACL Anthology volume URL per line, from collection XML.

Give collection ids (2025.acl, D18) or local .xml paths. Collection files
are fetched from the acl-org/acl-anthology GitHub repo if not local.

    python extract_volume_urls.py 2025.acl D18 > volume_urls.txt
"""
import sys, os
import xml.etree.ElementTree as ET
import requests

RAW_BASE = "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml"

def load_collection(ident):
    if os.path.isfile(ident):
        root = ET.parse(ident).getroot()
        return root.get("id"), root
    coll_id = ident[:-4] if ident.endswith(".xml") else ident
    resp = requests.get(f"{RAW_BASE}/{coll_id}.xml", timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    return root.get("id", coll_id), root

def volume_urls(ident):
    coll_id, root = load_collection(ident)
    return [
        f"https://aclanthology.org/volumes/{coll_id}-{vol.get('id')}/"
        for vol in root.findall("volume") if vol.get("id")
    ]

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    for ident in sys.argv[1:]:
        for url in volume_urls(ident):
            print(url)

if __name__ == "__main__":
    main()