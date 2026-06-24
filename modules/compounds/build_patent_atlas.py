#!/usr/bin/env python3
"""Build the PATENT TARGET ATLAS — annotate patent compounds with predicted protein targets, stored in Qdrant.

For each patent compound: predict top-20 targets by chemical k-NN to the ChEMBL reference (FPSim2, exact Tanimoto),
attach UniProt acc + gene + organism + confidence, flag novel (<0.3). Stored as a Qdrant collection (patent FP
vector + target payload) → queryable: filter by target → compounds claimed against it; novel filter; vector search.

PARALLEL across the 62 parquet chunks (one worker per chunk; all upsert to the same collection). The collection is
created (with deferred indexing) in the main process; workers only insert; the HNSW build is triggered after.

Usage:
  python build_patent_atlas.py [--workers N] [--collection NAME] [--limit-chunks K]
    --workers       worker processes (default 28; leaves cores for Qdrant)
    --collection    Qdrant collection (default patent_atlas)
    --limit-chunks  process only the first K chunks (for a parallel smoke test)
"""
import sys, os, glob, time, json, argparse
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, "/data/bioyoda")
import numpy as np, pyarrow.parquet as pq
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from qdrant_client import QdrantClient, models
from modules.qdrant.collection_profiles import (MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD,
                                                 DEFER_THRESHOLD, BUILD_THRESHOLD, MAX_INDEXING_THREADS)
PARQ = sorted(glob.glob("/data/bioyoda/raw_data/patents/chunked_compounds/compounds_chunk_*.parquet"))
GENE_CACHE = "/data/bioyoda/work/chembl_reference/target_genes.json"
MIN_HEAVY = 10                                  # skip solvents/fragments (toluene-class noise)

# ---------------- worker (per process) ----------------
_W = {}
def _init(name):
    sys.path.insert(0, "/data/bioyoda/modules/compounds"); sys.path.insert(0, "/data/bioyoda")
    import target as tgt
    tgt.engine()                                # load FPSim2 ChEMBL index + cid_targets (once per worker)
    _W.update(t=tgt, name=name, qc=QdrantClient(url="http://localhost:6333", timeout=600),
              g=json.load(open(GENE_CACHE)))

def _fp_norm(m):
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, a)
    n = np.linalg.norm(a); return (a / n) if n > 0 else None

def _process_chunk(f):
    tgt = _W["t"]; qc = _W["qc"]; G = _W["g"]; name = _W["name"]
    gene = lambda a: G.get(a, {}).get("gene", a)
    org = lambda a: G.get(a, {}).get("org", "")
    tb = pq.read_table(f, columns=["id", "smiles"])
    batch, n, novel_n = [], 0, 0
    for pid, sm in zip(tb.column("id").to_pylist(), tb.column("smiles").to_pylist()):
        if not sm: continue
        m = Chem.MolFromSmiles(sm)
        if m is None or m.GetNumHeavyAtoms() < MIN_HEAVY: continue
        v = _fp_norm(m)
        if v is None: continue
        preds, best = tgt.predict(sm, n_workers=1); top = preds   # single-thread search; store ALL targets (no top-N cap)
        novel = best < tgt.MIN_TAN; novel_n += novel
        batch.append(models.PointStruct(id=int(pid), vector=v.tolist(),
            payload={"surechembl_id": f"SCHEMBL{pid}", "smiles": sm,
                     "best_tanimoto": round(best, 3), "novel": bool(novel),
                     "targets": [t for t, _ in top],
                     "predicted": [{"acc": t, "gene": gene(t), "org": org(t), "conf": round(s, 3)} for t, s in top]}))
        n += 1
        if len(batch) >= 1000: qc.upsert(name, batch, wait=False); batch = []
    if batch: qc.upsert(name, batch, wait=True)
    return os.path.basename(f), n, novel_n

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=28)
    ap.add_argument("--collection", default="patent_atlas")
    ap.add_argument("--limit-chunks", type=int, default=None)
    a = ap.parse_args()
    chunks = PARQ[:a.limit_chunks] if a.limit_chunks else PARQ
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
    print(f"created {name}; annotating {len(chunks)} chunks with {a.workers} workers…", flush=True)

    t0 = time.time(); tot = nov = done = 0
    with mp.Pool(a.workers, initializer=_init, initargs=(name,)) as pool:
        for fn, n, nv in pool.imap_unordered(_process_chunk, chunks):
            tot += n; nov += nv; done += 1
            print(f"  [{done}/{len(chunks)}] {fn}: {n:,} annotated · total {tot:,} ({nov:,} novel) · {time.time()-t0:.0f}s", flush=True)
    print(f"\nannotated {tot:,} compounds ({nov:,} novel, {tot-nov:,} with a target) in {time.time()-t0:.0f}s", flush=True)

    print("triggering HNSW build…", flush=True)
    c.update_collection(name, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD))
    t = time.time()
    while True:
        info = c.get_collection(name)
        if info.status == models.CollectionStatus.GREEN and (info.indexed_vectors_count or 0) >= info.points_count * 0.99:
            print(f"DONE: {name} green, {info.points_count:,} points indexed in {time.time()-t:.0f}s", flush=True); break
        if time.time() - t > 3600: print(f"index wait timeout (status {info.status})"); break
        time.sleep(15)

if __name__ == "__main__":
    main()
