#!/usr/bin/env python3
"""
Build the set of already-embedded UniProt accessions for the incremental ESM-2 delta.

The analog of pubmed/build_existing_pmids.py, for proteins. After an insert, refresh this
set so the NEXT `prepare_delta.py` (default delta) skips proteins already in the `esm2`
collection and only embeds genuinely new ones.

Two sources:
  1. --metadata-dir : scan the FAISS sidecar metadata JSONs (chunk_*.json) produced by the
     embed step. Each maps vector_id -> {"protein_id": <accession>}. Fast, local, no server.
  2. --qdrant-url / --collection : scroll the live `esm2` collection and read `protein_id`
     payloads. Use to bootstrap the set from the existing 574K-point collection.

Output: a gzipped (or plain) file of unique accessions, one per line, for
prepare_delta.py --existing-proteins.

Usage:
  python build_existing_proteins.py --metadata-dir work/data/esm2_output/embeddings \
      --output work/state/esm2/existing_proteins.txt.gz
  python build_existing_proteins.py --qdrant-url http://localhost:6333 \
      --collection esm2 --output work/state/esm2/existing_proteins.txt.gz
"""
import argparse
import glob
import gzip
import json
import os
import sys
from datetime import datetime


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def from_metadata_dir(metadata_dir):
    acc = set()
    files = glob.glob(os.path.join(metadata_dir, "**", "*.json"), recursive=True)
    log(f"Scanning {len(files):,} metadata JSON files under {metadata_dir}")
    for i, path in enumerate(files):
        try:
            with open(path) as f:
                meta = json.load(f)
        except Exception as e:
            log(f"  skip {os.path.basename(path)}: {e}")
            continue
        records = meta.values() if isinstance(meta, dict) else meta
        for rec in records:
            if isinstance(rec, dict):
                pid = rec.get("protein_id")
                if pid:
                    acc.add(str(pid))
        if (i + 1) % 200 == 0:
            log(f"  {i+1:,}/{len(files):,} files, {len(acc):,} unique accessions so far")
    return acc


def from_qdrant(url, collection, batch=10000):
    from qdrant_client import QdrantClient
    client = QdrantClient(url=url, timeout=120, check_compatibility=False)
    acc = set()
    offset = None
    n = 0
    log(f"Scrolling Qdrant {url}/{collection}")
    while True:
        points, offset = client.scroll(
            collection_name=collection, with_payload=["protein_id"], with_vectors=False,
            limit=batch, offset=offset,
        )
        for p in points:
            pid = (p.payload or {}).get("protein_id")
            if pid:
                acc.add(str(pid))
        n += len(points)
        if n % 500000 < batch:
            log(f"  scrolled {n:,} points, {len(acc):,} unique accessions")
        if offset is None:
            break
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata-dir", help="Directory of FAISS sidecar metadata JSONs (chunk_*.json)")
    ap.add_argument("--qdrant-url")
    ap.add_argument("--collection", default="esm2")
    ap.add_argument("--output", required=True, help="Output accession file (.gz for gzip)")
    ap.add_argument("--merge", action="store_true",
                    help="Union with any accessions already in --output (refresh, don't replace)")
    args = ap.parse_args()

    if args.metadata_dir:
        acc = from_metadata_dir(args.metadata_dir)
    elif args.qdrant_url:
        acc = from_qdrant(args.qdrant_url, args.collection)
    else:
        log("ERROR: provide --metadata-dir or --qdrant-url")
        return 1

    if args.merge and os.path.exists(args.output):
        opener = gzip.open if args.output.endswith(".gz") else open
        before = len(acc)
        with opener(args.output, "rt") as f:
            for line in f:
                a = line.strip()
                if a:
                    acc.add(a)
        log(f"merged with existing {args.output}: {before:,} -> {len(acc):,} accessions")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    opener = gzip.open if args.output.endswith(".gz") else open
    with opener(args.output, "wt") as f:
        for a in acc:
            f.write(a + "\n")
    log(f"Wrote {len(acc):,} unique accessions to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
