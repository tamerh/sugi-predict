#!/usr/bin/env python3
"""Build the `patent_atlas` Qdrant collection from GPU-precomputed predictions (local, after the pull).

No prediction here — that was done on the GPU. Each worker joins one local patent chunk (pid→SMILES, for the
Morgan vector) with its matching pulled predictions chunk (pid→targets/confs/best/novel), attaches gene+organism
from the cache, and upserts. Parallel per-chunk. Mirrors the payload of modules/compounds/build_patent_atlas.py.

Usage:
  python build_atlas_from_predictions.py --preds DIR --patents DIR [--workers N] [--collection patent_atlas]
"""
import sys, os, glob, time, json, argparse
import multiprocessing as mp
sys.path.insert(0, "/data/bioyoda")
import numpy as np, pyarrow.parquet as pq
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from qdrant_client import QdrantClient, models
from modules.qdrant.collection_profiles import (MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD,
                                                 DEFER_THRESHOLD, BUILD_THRESHOLD, MAX_INDEXING_THREADS)
from modules.paths import TARGET_GENES_JSON
GENE_CACHE = str(TARGET_GENES_JSON)

_W = {}
def _init(name, preds_dir):
    _W.update(name=name, preds=preds_dir, qc=QdrantClient(url="http://localhost:6333", timeout=600),
              g=json.load(open(GENE_CACHE)))

def _fp_norm(m):
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, a)
    n = np.linalg.norm(a); return (a / n) if n > 0 else None

def _process(pchunk):
    name = _W["name"]; qc = _W["qc"]; G = _W["g"]
    gene = lambda acc: G.get(acc, {}).get("gene", acc)
    org = lambda acc: G.get(acc, {}).get("org", "")
    predp = f"{_W['preds']}/preds_{os.path.basename(pchunk)}"
    if not os.path.exists(predp): return os.path.basename(pchunk), 0   # chunk wasn't predicted
    pt = pq.read_table(predp)
    PB, PT, PC, PN = (pt.column("best_tanimoto").to_pylist(), pt.column("targets").to_pylist(),
                      pt.column("confs").to_pylist(), pt.column("novel").to_pylist())
    pred = {int(p): (b, t, c, nv) for p, b, t, c, nv in zip(pt.column("pid").to_pylist(), PB, PT, PC, PN)}
    sm = pq.read_table(pchunk, columns=["id", "smiles"])
    sm_by = dict(zip(sm.column("id").to_pylist(), sm.column("smiles").to_pylist()))
    batch, n = [], 0
    for pid, (best, targets, confs, novel) in pred.items():
        s = sm_by.get(pid)
        m = Chem.MolFromSmiles(s) if s else None
        if m is None: continue
        v = _fp_norm(m)
        if v is None: continue
        batch.append(models.PointStruct(id=int(pid), vector=v.tolist(),
            payload={"surechembl_id": f"SCHEMBL{pid}", "smiles": s,
                     "best_tanimoto": float(best), "novel": bool(novel), "targets": list(targets),
                     "predicted": [{"acc": t, "gene": gene(t), "org": org(t), "conf": float(c)}
                                   for t, c in zip(targets, confs)]}))
        n += 1
        if len(batch) >= 1000: qc.upsert(name, batch, wait=False); batch = []
    if batch: qc.upsert(name, batch, wait=True)
    return os.path.basename(pchunk), n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True); ap.add_argument("--patents", required=True)
    ap.add_argument("--workers", type=int, default=16); ap.add_argument("--collection", default="patent_atlas")
    a = ap.parse_args()
    name = a.collection
    c = QdrantClient(url="http://localhost:6333", timeout=600)
    if c.collection_exists(name): print(f"deleting existing {name}"); c.delete_collection(name)
    c.create_collection(name,
        vectors_config=models.VectorParams(size=2048, distance=models.Distance.COSINE, on_disk=True),
        hnsw_config=models.HnswConfigDiff(m=32, ef_construct=256, on_disk=False, max_indexing_threads=MAX_INDEXING_THREADS),
        quantization_config=models.BinaryQuantization(binary=models.BinaryQuantizationConfig(always_ram=True)),
        optimizers_config=models.OptimizersConfigDiff(max_segment_size=MAX_SEGMENT_SIZE,
            memmap_threshold=MEMMAP_THRESHOLD, indexing_threshold=DEFER_THRESHOLD))
    c.create_payload_index(name, "targets", field_schema=models.PayloadSchemaType.KEYWORD)
    c.create_payload_index(name, "novel", field_schema=models.PayloadSchemaType.BOOL)
    chunks = sorted(glob.glob(f"{a.patents}/compounds_chunk_*.parquet"))
    print(f"created {name}; ingesting {len(chunks)} chunks with {a.workers} workers…", flush=True)
    t0 = time.time(); tot = 0
    with mp.Pool(a.workers, initializer=_init, initargs=(name, a.preds)) as pool:
        for fn, n in pool.imap_unordered(_process, chunks):
            tot += n; print(f"  {fn}: {n:,} ingested · total {tot:,} · {time.time()-t0:.0f}s", flush=True)
    print(f"\ningested {tot:,} compounds in {time.time()-t0:.0f}s; triggering HNSW build…", flush=True)
    c.update_collection(name, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD))
    t = time.time()
    while True:
        info = c.get_collection(name)
        if info.status == models.CollectionStatus.GREEN and (info.indexed_vectors_count or 0) >= info.points_count * 0.99:
            print(f"DONE: {name} green, {info.points_count:,} indexed in {time.time()-t:.0f}s", flush=True); break
        if time.time() - t > 7200: print(f"index wait timeout (status {info.status})"); break
        time.sleep(15)

if __name__ == "__main__":
    main()
