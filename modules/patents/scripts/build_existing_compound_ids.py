#!/usr/bin/env python3
"""
Build the set of already-fingerprinted SureChEMBL compound IDs for the
incremental compound ID-delta (process_compounds.py --existing-ids).

Two sources:
  1. --metadata-dir : scan the FAISS sidecar metadata JSONs produced by
     process_compounds.py (each maps vector_id -> {"surechembl_id": ...}).
     Fast, local, no running server. The normal bootstrap.
  2. --qdrant-url / --collection : scroll patents_compounds and read the
     `surechembl_id` payload. Use when local metadata is unavailable.

Output: a gzipped (or plain) file of unique surechembl_ids, one per line
(e.g. SCHEMBL123), suitable for process_compounds.py --existing-ids.

Compounds are immutable (a SureChEMBL id = a fixed structure), so additions-only
is fully correct; and the insert point-id is hash(surechembl_id), so an imperfect
set at worst re-fingerprints to the same point (no corruption).
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
    ids = set()
    files = glob.glob(os.path.join(metadata_dir, "**", "*.json"), recursive=True)
    log(f"Scanning {len(files):,} compound metadata JSON files under {metadata_dir}")
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
                sid = rec.get("surechembl_id")
                if sid:
                    ids.add(str(sid))
        if (i + 1) % 10 == 0:
            log(f"  {i+1}/{len(files)} files, {len(ids):,} unique ids so far")
    return ids


def from_qdrant(url, collection, batch=10000):
    from qdrant_client import QdrantClient
    client = QdrantClient(url=url)
    ids = set()
    offset = None
    n = 0
    log(f"Scrolling Qdrant {url}/{collection}")
    while True:
        points, offset = client.scroll(
            collection_name=collection, with_payload=["surechembl_id"],
            with_vectors=False, limit=batch, offset=offset,
        )
        for p in points:
            sid = (p.payload or {}).get("surechembl_id")
            if sid:
                ids.add(str(sid))
        n += len(points)
        if n % 1000000 < batch:
            log(f"  scrolled {n:,} points, {len(ids):,} unique ids")
        if offset is None:
            break
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata-dir", help="Directory of compound FAISS sidecar metadata JSONs")
    ap.add_argument("--qdrant-url")
    ap.add_argument("--collection", default="patents_compounds")
    ap.add_argument("--output", required=True, help="Output ids file (.gz for gzip)")
    args = ap.parse_args()

    if args.metadata_dir:
        ids = from_metadata_dir(args.metadata_dir)
    elif args.qdrant_url:
        ids = from_qdrant(args.qdrant_url, args.collection)
    else:
        log("ERROR: provide --metadata-dir or --qdrant-url")
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    opener = gzip.open if args.output.endswith(".gz") else open
    with opener(args.output, "wt") as f:
        for sid in ids:
            f.write(sid + "\n")
    log(f"Wrote {len(ids):,} unique surechembl_ids to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
