#!/usr/bin/env python3
"""Build the unified `patent_compounds` collection — consolidates patents_compounds (raw) + patent_atlas (predictions).

ALL June compounds get structure (smiles/inchi/inchi_key/mol_weight) + a Morgan-r2/2048 FP vector.
The drug-like ones (those with k-NN neighbours in work/atlas_nbrs/) ALSO get predictions, joined by compound id.
"atlas" becomes a FILTERED VIEW over this one collection (predicted exists / by target / novel / conf).
Nothing is dropped: fragments/solvents stay (valid for structure search), they just carry no predictions.

Why three passes: the neighbours are NOT aligned with the June chunking (they're the Dec chunking + the delta),
so we join by compound id, not by chunk position:
  1. score every neighbour row              -> {pid: (best, novel, [predicted...])}   (main process, ~10GB)
  2. write per-June-chunk aligned pred files -> work/atlas_preds_aligned/  (then the big dict is freed)
  3. parallel: each worker ingests one June chunk = FP + structure + (its aligned preds) -> patent_compounds
     (no shared dict across forks -> no copy-on-write refcount bloat)

Usage: python build_patent_compounds.py [--workers 16] [--collection patent_compounds] [--skip-align]
"""
import sys, os, glob, time, json, argparse, pickle
import multiprocessing as mp
sys.path.insert(0, "/data/bioyoda")
import numpy as np, pyarrow.parquet as pq
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from qdrant_client import QdrantClient, models
from modules.qdrant.collection_profiles import (MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD,
                                                 DEFER_THRESHOLD, BUILD_THRESHOLD, MAX_INDEXING_THREADS)
REF = "/data/bioyoda/work/chembl_reference"
NBRS = "/data/bioyoda/work/atlas_nbrs"
COMPOUNDS = "/data/bioyoda/raw_data/patents/chunked_compounds"
PREDDIR = "/data/bioyoda/work/atlas_preds_aligned"
KNN, MIN_TAN = 20, 0.30


def _fp(sm):
    m = Chem.MolFromSmiles(sm) if sm else None
    if m is None:
        return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, a)
    n = np.linalg.norm(a); return (a / n) if n > 0 else None


def _score(nbr_cids, nbr_sims, ct, human):
    """top-KNN human-target transfer, ranked by max-Tanimoto (tie-break support count then vote). Same as the atlas."""
    supp = {}; cnt = {}; vote = {}; used = 0
    for cid, s in zip(nbr_cids, nbr_sims):
        s = float(s)
        if s < MIN_TAN or used >= KNN:
            break                                     # neighbours are sorted desc
        for t in ct.get(int(cid), ()):
            if t not in human:
                continue                              # human default (non-human orthologs are off-target noise)
            cnt[t] = cnt.get(t, 0) + 1; vote[t] = vote.get(t, 0.0) + s
            if s > supp.get(t, 0.0):
                supp[t] = s
        used += 1
    return sorted(supp, key=lambda t: (-supp[t], -cnt[t], -vote[t])), supp, cnt


# ---------- Pass 1+2: score neighbours, align predictions to the June chunks ----------
def build_aligned_preds():
    ct = {int(k): v for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
    G = json.load(open(f"{REF}/target_genes.json"))
    human = {t for t in set().union(*ct.values()) if "Homo sapiens" in G.get(t, {}).get("org", "")}
    gene = lambda t: G.get(t, {}).get("gene", t)

    print("  Pass 1: scoring neighbours -> preds dict ...", flush=True)
    preds = {}
    for f in sorted(glob.glob(f"{NBRS}/nbrs_*.parquet")):
        t = pq.read_table(f, columns=["pid", "best_tanimoto", "novel", "nbr_cids", "nbr_sims"])
        for pid, best, novel, ncids, nsims in zip(t.column("pid").to_pylist(), t.column("best_tanimoto").to_pylist(),
                                                  t.column("novel").to_pylist(), t.column("nbr_cids").to_pylist(),
                                                  t.column("nbr_sims").to_pylist()):
            ranked, supp, cnt = _score(ncids, nsims, ct, human)
            if ranked:
                # intern acc/gene so the ~300M target strings collapse onto ~1.25M unique objects (keeps the dict ~10-15GB)
                preds[int(pid)] = (round(float(best), 3), bool(novel),
                                   [(sys.intern(a), sys.intern(gene(a)), round(supp[a], 3), cnt[a]) for a in ranked])
    print(f"  {len(preds):,} compounds scored. Pass 2: aligning to June chunks ...", flush=True)

    os.makedirs(PREDDIR, exist_ok=True)
    for f in sorted(glob.glob(f"{COMPOUNDS}/compounds_chunk_*.parquet")):
        ids = pq.read_table(f, columns=["id"]).column("id").to_pylist()
        sub = {pid: preds[pid] for pid in ids if pid in preds}
        out = os.path.join(PREDDIR, os.path.basename(f).replace(".parquet", ".pkl"))
        pickle.dump(sub, open(out, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
    print("  aligned pred files written.", flush=True)


# ---------- Pass 3: ingest every June compound (structure + FP; predictions where present) ----------
_W = {}
def _init(name):
    _W.update(name=name, qc=QdrantClient(url="http://localhost:6333", timeout=600))


def _ingest(chunk_file):
    qc = _W["qc"]; name = _W["name"]
    preds = pickle.load(open(os.path.join(PREDDIR, os.path.basename(chunk_file).replace(".parquet", ".pkl")), "rb"))
    t = pq.read_table(chunk_file, columns=["id", "smiles", "inchi", "inchi_key", "mol_weight"])
    ids, smis = t.column("id").to_pylist(), t.column("smiles").to_pylist()
    inchis, iks, mws = t.column("inchi").to_pylist(), t.column("inchi_key").to_pylist(), t.column("mol_weight").to_pylist()
    batch = []; n = withp = skip = 0
    for i in range(len(ids)):
        pid = ids[i]; sm = smis[i]
        v = _fp(sm)
        if v is None:                                 # unparseable SMILES -> can't represent; skip
            skip += 1; continue
        payload = {"surechembl_id": f"SCHEMBL{pid}", "smiles": sm, "inchi": inchis[i],
                   "inchi_key": iks[i], "mol_weight": float(mws[i]) if mws[i] is not None else None}
        pr = preds.get(pid)
        if pr is not None:                            # drug-like: enrich with predictions
            best, novel, plist = pr
            payload.update(best_tanimoto=best, novel=novel, exact_match=bool(best >= 0.999),
                           targets=[a for a, _, _, _ in plist],
                           predicted=[{"acc": a, "gene": g, "conf": c, "support": s} for a, g, c, s in plist])
            withp += 1
        batch.append(models.PointStruct(id=int(pid), vector=v.tolist(), payload=payload))
        n += 1
        if len(batch) >= 1000:
            qc.upsert(name, batch, wait=False); batch = []
    if batch:
        qc.upsert(name, batch, wait=True)
    return os.path.basename(chunk_file), n, withp, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--collection", default="patent_compounds")
    ap.add_argument("--skip-align", action="store_true", help="reuse existing work/atlas_preds_aligned/")
    ap.add_argument("--align-only", action="store_true", help="run Pass 1+2 (score+align) then exit; no Qdrant")
    a = ap.parse_args()
    name = a.collection

    if not a.skip_align:
        build_aligned_preds()
    if a.align_only:
        print("align-only: done.", flush=True); return

    c = QdrantClient(url="http://localhost:6333", timeout=600)
    if c.collection_exists(name):
        print(f"deleting existing {name}", flush=True); c.delete_collection(name)
    c.create_collection(name,
        vectors_config=models.VectorParams(size=2048, distance=models.Distance.COSINE, on_disk=True),
        hnsw_config=models.HnswConfigDiff(m=32, ef_construct=256, on_disk=False, max_indexing_threads=MAX_INDEXING_THREADS),
        quantization_config=models.BinaryQuantization(binary=models.BinaryQuantizationConfig(always_ram=True)),
        optimizers_config=models.OptimizersConfigDiff(max_segment_size=MAX_SEGMENT_SIZE,
            memmap_threshold=MEMMAP_THRESHOLD, indexing_threshold=DEFER_THRESHOLD))
    c.create_payload_index(name, "targets", field_schema=models.PayloadSchemaType.KEYWORD)
    c.create_payload_index(name, "novel", field_schema=models.PayloadSchemaType.BOOL)
    c.create_payload_index(name, "best_tanimoto", field_schema=models.PayloadSchemaType.FLOAT)  # web hiconf range filter

    print(f"Pass 3: ingest all June compounds -> {name} ({a.workers} workers)", flush=True)
    chunks = sorted(glob.glob(f"{COMPOUNDS}/compounds_chunk_*.parquet"))
    tot = totp = tsk = 0; t0 = time.time()
    with mp.Pool(a.workers, initializer=_init, initargs=(name,)) as pool:
        for cb, n, withp, skip in pool.imap_unordered(_ingest, chunks):
            tot += n; totp += withp; tsk += skip
            print(f"  {cb}: {n:,} (+{withp:,} predicted, {skip} bad) | total {tot:,} ({totp:,} predicted) | {time.time()-t0:.0f}s", flush=True)
    print(f"DONE: {tot:,} compounds ({totp:,} predicted, {tsk:,} unparseable) -> {name}", flush=True)

    print("triggering HNSW build (indexing_threshold -> BUILD)...", flush=True)
    c.update_collection(name, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD))
    while True:
        info = c.get_collection(name)
        if info.status == models.CollectionStatus.GREEN and (info.indexed_vectors_count or 0) >= info.points_count * 0.99:
            break
        time.sleep(30)
    print(f"GREEN: {c.count(name).count:,} points indexed", flush=True)


if __name__ == "__main__":
    main()
