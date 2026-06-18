#!/usr/bin/env python3
"""Rebuild a BioYoda Qdrant collection from its FAISS source, using the proven per-collection
profile (modules/qdrant/collection_profiles.py). Encodes the recipe we hard-won in 2026-06:

  create (RIGHT config: quant/on_disk/hnsw, indexing DEFERRED) -> insert (can't OOM) ->
  trigger HNSW build (bounded threads) -> wait until ~fully indexed -> verify.

Usage:
  python modules/qdrant/scripts/rebuild_collection.py <collection> [--recreate] [--qdrant-url URL]

  --recreate   drop the collection first (default: refuse if it already exists with points)
"""
import sys, os, time, argparse, subprocess
sys.path.insert(0, "/data/bioyoda")
from qdrant_client import QdrantClient, models
from modules.qdrant.collection_profiles import (
    PROFILES, MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD, DEFER_THRESHOLD,
    BUILD_THRESHOLD, MAX_INDEXING_THREADS,
)

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def quant_config(q):
    if q["type"] == "binary":
        return models.BinaryQuantization(binary=models.BinaryQuantizationConfig(always_ram=q["always_ram"]))
    return models.ScalarQuantization(scalar=models.ScalarQuantizationConfig(
        type=models.ScalarType.INT8, quantile=0.99, always_ram=q["always_ram"]))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("collection", choices=list(PROFILES))
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--recreate", action="store_true")
    a = ap.parse_args()
    p = PROFILES[a.collection]
    src = p.get("faiss_source")
    if not src:
        log(f"FATAL: no faiss_source in profile for {a.collection} (TODO: locate it)."); sys.exit(2)

    c = QdrantClient(url=a.qdrant_url, timeout=300)
    exists = c.collection_exists(a.collection)
    if exists and not a.recreate:
        n = c.get_collection(a.collection).points_count
        if n: log(f"FATAL: {a.collection} exists with {n:,} points. Use --recreate to rebuild."); sys.exit(2)
    if exists and a.recreate:
        log(f"--recreate: dropping {a.collection}"); c.delete_collection(a.collection)

    # 1) create with the RIGHT config, indexing DEFERRED (insert can't trigger a build)
    log(f"creating {a.collection} | dim={p['dim']} on_disk_vecs={p['vectors_on_disk']} "
        f"quant={p['quant']['type']}(always_ram={p['quant']['always_ram']}) hnsw m={p['hnsw_m']}/ef={p['hnsw_ef']}")
    c.create_collection(
        a.collection,
        vectors_config=models.VectorParams(size=p["dim"], distance=models.Distance.COSINE,
                                           on_disk=p["vectors_on_disk"]),
        hnsw_config=models.HnswConfigDiff(m=p["hnsw_m"], ef_construct=p["hnsw_ef"],
                                          full_scan_threshold=10000, on_disk=False),
        quantization_config=quant_config(p["quant"]),
        optimizers_config=models.OptimizersConfigDiff(
            default_segment_number=0, max_segment_size=MAX_SEGMENT_SIZE,
            memmap_threshold=MEMMAP_THRESHOLD, indexing_threshold=DEFER_THRESHOLD,
            flush_interval_sec=30),
        on_disk_payload=True)

    # 2) insert from FAISS source(s) via the battle-tested loader (point-ids/payload by name)
    sources = [src] + p.get("faiss_source_extra", [])
    for s in sources:
        if not os.path.isdir(s):
            log(f"WARN: source dir missing: {s} — skipping"); continue
        log(f"inserting from {s} (deferred index)…")
        r = subprocess.run([sys.executable, "modules/qdrant/scripts/insert_from_faiss.py",
                            "--faiss-dir", s, "--collection", a.collection,
                            "--vector-size", str(p["dim"]), "--qdrant-url", a.qdrant_url,
                            "--prefer-grpc", "--batch-size", "1500"],
                           cwd="/data/bioyoda")
        if r.returncode != 0: log(f"FATAL: insert failed for {s}"); sys.exit(3)

    pts = c.get_collection(a.collection).points_count
    log(f"inserted: {pts:,} points")

    # 3) trigger the HNSW build (bounded threads) — the monitored, RAM-safe step
    log(f"triggering HNSW build (threshold={BUILD_THRESHOLD}, threads={MAX_INDEXING_THREADS})…")
    c.update_collection(a.collection,
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD),
        hnsw_config=models.HnswConfigDiff(max_indexing_threads=MAX_INDEXING_THREADS))

    # 4) wait until ~fully indexed (mutable tail means green may never hit 100%; 99% = done)
    t0 = time.time(); last = -1
    while True:
        r = c.get_collection(a.collection); idx = r.indexed_vectors_count or 0
        if idx != last: log(f"  indexed {idx:,}/{pts:,} ({100*idx/max(1,pts):.1f}%) status={r.status}"); last = idx
        if idx >= pts * 0.99: break
        if time.time() - t0 > 12 * 3600: log("WARN: build >12h, stopping wait"); break
        time.sleep(30)
    log(f"BUILD DONE in {(time.time()-t0)/60:.0f} min | {a.collection}: {pts:,} points, "
        f"{c.get_collection(a.collection).indexed_vectors_count:,} indexed")

if __name__ == "__main__":
    main()
