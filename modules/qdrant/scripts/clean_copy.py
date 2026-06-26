#!/usr/bin/env python3
"""Clean-copy a Qdrant collection into a fresh one with the SAME profile, then build the HNSW once.

Use when a collection's optimizer state gets tangled by repeated stop-start optimizations (e.g. running
ingest -> provenance -> denoise as separate steps, each triggering its own optimize). The DATA is fine; the
index state is confused and a restart just reloads the same tangle. This moves the points into a brand-new
collection (un-confused optimizer) and builds ONE clean HNSW with the intended profile (big segments + binary
quant -> fast query latency). No recompute. The source is left intact as a fallback until you swap the alias.

PARALLEL: collect ids once (cheap, ids-only scroll), partition round-robin, N workers each retrieve-by-id
(vectors+payloads) and upsert. Serial single-process copy of 30M x 2048-float vectors is ~250/s (~a day);
16 workers brings it to ~tens of minutes.

  python clean_copy.py --src patent_compounds --dst patent_compounds_v2 --workers 16
  # then, after verifying dst is green + correct:  delete src, create alias src -> dst
"""
import sys, time, argparse
import multiprocessing as mp
sys.path.insert(0, "/data/bioyoda")
from qdrant_client import QdrantClient, models
from modules.qdrant.collection_profiles import (MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD,
                                                 DEFER_THRESHOLD, BUILD_THRESHOLD, MAX_INDEXING_THREADS)

QURL = "http://localhost:6333"
_W = {}


def _init(src, dst):
    _W.update(src=src, dst=dst, qc=QdrantClient(url=QURL, timeout=600, check_compatibility=False))


def _copy(id_part):
    """retrieve this id partition (vectors+payloads) from src, upsert to dst."""
    qc, src, dst = _W["qc"], _W["src"], _W["dst"]
    n = 0
    for i in range(0, len(id_part), 1000):
        ids = id_part[i:i + 1000]
        pts = qc.retrieve(src, ids=ids, with_payload=True, with_vectors=True)
        if pts:
            qc.upsert(dst, [models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in pts], wait=False)
            n += len(pts)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    qc = QdrantClient(url=QURL, timeout=600, check_compatibility=False)

    dim = qc.get_collection(a.src).config.params.vectors.size
    total = qc.count(a.src).count
    print(f"src {a.src}: {total:,} points, dim {dim}", flush=True)

    # pause the source's (wedged) optimizer so it stops competing for CPU during the copy
    qc.update_collection(a.src, optimizer_config=models.OptimizersConfigDiff(indexing_threshold=DEFER_THRESHOLD))
    print("  source optimizer paused", flush=True)

    # fresh collection, SAME profile, indexing DEFERRED during the copy
    if qc.collection_exists(a.dst):
        qc.delete_collection(a.dst)
    qc.create_collection(a.dst,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE, on_disk=True),
        hnsw_config=models.HnswConfigDiff(m=32, ef_construct=256, on_disk=False, max_indexing_threads=MAX_INDEXING_THREADS),
        quantization_config=models.BinaryQuantization(binary=models.BinaryQuantizationConfig(always_ram=True)),
        optimizers_config=models.OptimizersConfigDiff(max_segment_size=MAX_SEGMENT_SIZE,
            memmap_threshold=MEMMAP_THRESHOLD, indexing_threshold=DEFER_THRESHOLD))
    for f, t in [("targets", models.PayloadSchemaType.KEYWORD),
                 ("novel", models.PayloadSchemaType.BOOL),
                 ("best_tanimoto", models.PayloadSchemaType.FLOAT)]:
        qc.create_payload_index(a.dst, f, field_schema=t)
    print(f"  created {a.dst} (profile preserved, indexing deferred)", flush=True)

    # collect all ids (cheap: ids-only scroll), partition round-robin
    print("  collecting ids ...", flush=True)
    ids = []; offset = None
    while True:
        pts, offset = qc.scroll(a.src, limit=20000, offset=offset, with_payload=False, with_vectors=False)
        ids.extend(p.id for p in pts)
        if offset is None:
            break
    print(f"  {len(ids):,} ids; copying with {a.workers} workers ...", flush=True)
    parts = [ids[i::a.workers] for i in range(a.workers)]

    copied = 0; t0 = time.time()
    with mp.Pool(a.workers, initializer=_init, initargs=(a.src, a.dst)) as pool:
        for n in pool.imap_unordered(_copy, parts):
            copied += n
            r = copied / max(time.time() - t0, 1)
            print(f"  copied {copied:,}/{total:,} ({r:.0f}/s)", flush=True)
    print(f"copied {copied:,} in {time.time()-t0:.0f}s; waiting for flush ...", flush=True)
    while qc.count(a.dst).count < total * 0.999:
        time.sleep(10)

    # ONE clean HNSW build on the un-confused collection
    qc.update_collection(a.dst, optimizer_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD))
    print("  HNSW build triggered (single, clean)", flush=True)
    while True:
        i = qc.get_collection(a.dst)
        if str(i.status).endswith("green") and (i.indexed_vectors_count or 0) >= i.points_count * 0.99:
            break
        time.sleep(30)
    print(f"GREEN: {qc.count(a.dst).count:,} points, fully indexed -> swap alias when verified", flush=True)


if __name__ == "__main__":
    main()
