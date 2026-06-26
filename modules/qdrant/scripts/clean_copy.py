#!/usr/bin/env python3
"""Clean-copy a Qdrant collection into a fresh one with the SAME profile, then build the HNSW once.

Use when a collection's optimizer state gets tangled by repeated stop-start optimizations (e.g. running
ingest -> provenance -> denoise as separate steps, each triggering its own optimize). The DATA is fine; the
index state is confused and a restart just reloads the same tangle. This moves the points into a brand-new
collection (un-confused optimizer) and builds ONE clean HNSW with the intended profile (big segments + binary
quant -> fast query latency). No recompute. The source is left intact as a fallback until you swap the alias.

  python clean_copy.py --src patent_compounds --dst patent_compounds_v2
  # then, after verifying dst is green + correct:  delete src, create alias src -> dst
"""
import sys, time, argparse
sys.path.insert(0, "/data/bioyoda")
from qdrant_client import QdrantClient, models
from modules.qdrant.collection_profiles import (MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD,
                                                 DEFER_THRESHOLD, BUILD_THRESHOLD, MAX_INDEXING_THREADS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--scroll", type=int, default=2000)
    ap.add_argument("--batch", type=int, default=500)   # keep upsert request < 33MB (prov payloads are big)
    a = ap.parse_args()
    qc = QdrantClient(url=a.qdrant, timeout=600, check_compatibility=False)

    src_info = qc.get_collection(a.src)
    dim = src_info.config.params.vectors.size
    total = qc.count(a.src).count
    print(f"src {a.src}: {total:,} points, dim {dim}", flush=True)

    # pause the source's (wedged) optimizer so it stops competing for CPU during the copy
    qc.update_collection(a.src, optimizer_config=models.OptimizersConfigDiff(indexing_threshold=DEFER_THRESHOLD))
    print("  source optimizer paused", flush=True)

    # 1) fresh collection, SAME profile, indexing DEFERRED during the copy
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

    # 2) copy every point (vectors + payloads) — no recompute
    copied = 0; offset = None; t0 = time.time()
    while True:
        pts, offset = qc.scroll(a.src, limit=a.scroll, offset=offset, with_payload=True, with_vectors=True)
        if not pts:
            break
        for i in range(0, len(pts), a.batch):
            b = pts[i:i + a.batch]
            qc.upsert(a.dst, [models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in b], wait=False)
        copied += len(pts)
        if copied % 200_000 < a.scroll:
            r = copied / max(time.time() - t0, 1)
            print(f"  copied {copied:,}/{total:,} ({r:.0f}/s, eta {(total-copied)/max(r,1)/60:.0f}min)", flush=True)
        if offset is None:
            break
    print(f"copied {copied:,} in {time.time()-t0:.0f}s; waiting for flush...", flush=True)
    while qc.count(a.dst).count < total:
        time.sleep(10)

    # 3) ONE clean HNSW build on the un-confused collection
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
