#!/usr/bin/env python3
"""
Build the set of already-embedded PubMed PMIDs for incremental PMID-delta refresh.

Two sources:
  1. --metadata-dir : scan the FAISS sidecar metadata JSONs produced by index.py
     (each maps vector_id -> {"pmid": ..., "chunk_text": ...}). Fast, local, no
     running server needed. This is the normal bootstrap.
  2. --qdrant-url / --collection : scroll an existing Qdrant collection and read
     the `pmid` payload. Use when the local metadata is unavailable.

Output: a gzipped (or plain) file of unique PMIDs, one per line, suitable for
index.py --existing-pmids.

Usage:
  python build_existing_pmids.py --metadata-dir snapshots/prod_latest/data/processed/pubmed \
      --output work/state/pubmed/existing_pmids.txt.gz
  python build_existing_pmids.py --qdrant-url http://localhost:6333 \
      --collection pubmed_abstracts --output work/state/pubmed/existing_pmids.txt.gz
"""
import argparse
import glob
import gzip
import json
import os
import sys
from datetime import datetime


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def from_metadata_dir(metadata_dir):
    pmids = set()
    files = glob.glob(os.path.join(metadata_dir, "**", "*.json"), recursive=True)
    log(f"Scanning {len(files):,} metadata JSON files under {metadata_dir}")
    for i, path in enumerate(files):
        try:
            with open(path) as f:
                meta = json.load(f)
        except Exception as e:
            log(f"  skip {os.path.basename(path)}: {e}")
            continue
        # meta is {vector_id: {"pmid": ..., ...}}
        records = meta.values() if isinstance(meta, dict) else meta
        for rec in records:
            if isinstance(rec, dict):
                pmid = rec.get("pmid")
                if pmid:
                    pmids.add(str(pmid))
        if (i + 1) % 200 == 0:
            log(f"  {i+1:,}/{len(files):,} files, {len(pmids):,} unique PMIDs so far")
    return pmids


def from_qdrant(url, collection, batch=10000):
    from qdrant_client import QdrantClient
    client = QdrantClient(url=url)
    pmids = set()
    offset = None
    n = 0
    log(f"Scrolling Qdrant {url}/{collection}")
    while True:
        points, offset = client.scroll(
            collection_name=collection, with_payload=["pmid"], with_vectors=False,
            limit=batch, offset=offset,
        )
        for p in points:
            pmid = (p.payload or {}).get("pmid")
            if pmid:
                pmids.add(str(pmid))
        n += len(points)
        if n % 500000 < batch:
            log(f"  scrolled {n:,} points, {len(pmids):,} unique PMIDs")
        if offset is None:
            break
    return pmids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata-dir", help="Directory of FAISS sidecar metadata JSONs")
    ap.add_argument("--qdrant-url")
    ap.add_argument("--collection", default="pubmed_abstracts")
    ap.add_argument("--output", required=True, help="Output PMID file (.gz for gzip)")
    args = ap.parse_args()

    if args.metadata_dir:
        pmids = from_metadata_dir(args.metadata_dir)
    elif args.qdrant_url:
        pmids = from_qdrant(args.qdrant_url, args.collection)
    else:
        log("ERROR: provide --metadata-dir or --qdrant-url")
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    opener = gzip.open if args.output.endswith(".gz") else open
    with opener(args.output, "wt") as f:
        for pmid in pmids:
            f.write(pmid + "\n")
    log(f"Wrote {len(pmids):,} unique PMIDs to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
