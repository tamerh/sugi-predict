#!/usr/bin/env python3
"""Build the `patent_atlas` Qdrant collection from the GPU raw-neighbour output (work/atlas_nbrs/).

Scoring (cheap, local — the GPU only did the k-NN): for each patent compound, take its top-20 nearest reference
neighbours (Tanimoto >= 0.3), transfer their targets, keep HUMAN targets (the validated default — non-human
orthologs are bacterial-noise off-targets), rank by max-Tanimoto confidence (tie-break support count then vote).
Payload carries the support count + the exact-match handling. Patent Morgan FP is the vector (for similarity /
cross-modal). The full top-100 neighbours remain in work/atlas_nbrs/ as the complete substrate for re-scoring.

Usage: python build_atlas_from_neighbours.py [--workers 16] [--collection patent_atlas]
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
from modules.paths import CHEMBL_REF, ATLAS_NBRS, CHUNKED_COMPOUNDS
REF = str(CHEMBL_REF)
NBRS = str(ATLAS_NBRS)
PATENTS = str(CHUNKED_COMPOUNDS)
KNN, MIN_TAN = 20, 0.30

_W = {}
def _init(name):
    ct = {int(k): v for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
    G = json.load(open(f"{REF}/target_genes.json"))
    human = {t for t in set().union(*ct.values()) if "Homo sapiens" in G.get(t, {}).get("org", "")}
    _W.update(name=name, qc=QdrantClient(url="http://localhost:6333", timeout=600),
              ct=ct, G=G, human=human)

def _fp(sm):
    m = Chem.MolFromSmiles(sm) if sm else None
    if m is None: return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, a)
    n = np.linalg.norm(a); return (a / n) if n > 0 else None

def _score(nbr_cids, nbr_sims, ct, human):
    supp = {}; cnt = {}; vote = {}; used = 0
    for cid, s in zip(nbr_cids, nbr_sims):
        s = float(s)
        if s < MIN_TAN or used >= KNN: break          # neighbours sorted desc
        for t in ct.get(int(cid), ()):
            if t not in human: continue               # human default
            cnt[t] = cnt.get(t, 0) + 1; vote[t] = vote.get(t, 0.0) + s
            if s > supp.get(t, 0.0): supp[t] = s
        used += 1
    return sorted(supp, key=lambda t: (-supp[t], -cnt[t], -vote[t])), supp, cnt

def _process(chunk_base):
    name = _W["name"]; qc = _W["qc"]; ct = _W["ct"]; G = _W["G"]; human = _W["human"]
    gene = lambda t: G.get(t, {}).get("gene", t)
    nbrf = f"{NBRS}/nbrs_{chunk_base}"; patf = f"{PATENTS}/{chunk_base}"
    if not os.path.exists(nbrf): return chunk_base, 0
    nb = pq.read_table(nbrf)
    sm = pq.read_table(patf, columns=["id", "smiles"])
    smi = dict(zip(sm.column("id").to_pylist(), sm.column("smiles").to_pylist()))
    pids = nb.column("pid").to_pylist(); bests = nb.column("best_tanimoto").to_pylist()
    novels = nb.column("novel").to_pylist(); CIDS = nb.column("nbr_cids").to_pylist(); SIMS = nb.column("nbr_sims").to_pylist()
    batch, n = [], 0
    for pid, best, novel, ncids, nsims in zip(pids, bests, novels, CIDS, SIMS):
        s = smi.get(pid)
        v = _fp(s)
        if v is None: continue
        ranked, supp, cnt = _score(ncids, nsims, ct, human)
        batch.append(models.PointStruct(id=int(pid), vector=v.tolist(),
            payload={"surechembl_id": f"SCHEMBL{pid}", "smiles": s,
                     "best_tanimoto": round(float(best), 3), "novel": bool(novel),
                     "exact_match": bool(best >= 0.999), "targets": ranked,
                     "predicted": [{"acc": t, "gene": gene(t), "conf": round(supp[t], 3), "support": cnt[t]}
                                   for t in ranked]}))
        n += 1
        if len(batch) >= 1000: qc.upsert(name, batch, wait=False); batch = []
    if batch: qc.upsert(name, batch, wait=True)
    return chunk_base, n

def main():
    ap = argparse.ArgumentParser()
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
    chunks = [os.path.basename(f) for f in sorted(glob.glob(f"{PATENTS}/compounds_chunk_*.parquet"))]
    print(f"created {name}; scoring+ingesting {len(chunks)} chunks with {a.workers} workers…", flush=True)
    t0 = time.time(); tot = 0
    with mp.Pool(a.workers, initializer=_init, initargs=(name,)) as pool:
        for cb, n in pool.imap_unordered(_process, chunks):
            tot += n; print(f"  {cb}: {n:,} → total {tot:,} · {time.time()-t0:.0f}s", flush=True)
    print(f"\ningested {tot:,} in {time.time()-t0:.0f}s; triggering HNSW build…", flush=True)
    c.update_collection(name, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD))
    t = time.time()
    while True:
        info = c.get_collection(name)
        if info.status == models.CollectionStatus.GREEN and (info.indexed_vectors_count or 0) >= info.points_count * 0.99:
            print(f"DONE: {name} green, {info.points_count:,} indexed in {time.time()-t:.0f}s", flush=True); break
        if time.time() - t > 9000: print(f"index wait timeout (status {info.status})"); break
        time.sleep(20)

if __name__ == "__main__":
    main()
