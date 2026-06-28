#!/usr/bin/env python3
"""Build the `chembl` Qdrant collection — the ChEMBL ligand→target answer-key as a first-class, general,
target-labeled modality (symmetric with patents_compounds: both Morgan/ECFP4 in Qdrant + FPSim2).

Source: work/chembl_reference/{reference.tsv (cid+smiles), cid_targets.json (cid→targets)} — biobtree-assembled.
Vectors: Morgan r2/2048, L2-normalized (matches patents_compounds storage), Cosine, BINARY quant, in-RAM.
Payload: {cid (pubchem), smiles, targets:[UniProt], source}. Point id = pubchem cid.
Enables: general similarity over ChEMBL, filter ligands by target, cross-modal joins (patent↔chembl↔lit).
(The target-prediction engine keeps using the exact-Tanimoto FPSim2 index for its confidence.)
"""
import sys, json, time, argparse
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from qdrant_client import QdrantClient, models
sys.path.insert(0, "/data/bioyoda")
from modules.qdrant.collection_profiles import (MAX_SEGMENT_SIZE, MEMMAP_THRESHOLD,
                                                DEFER_THRESHOLD, BUILD_THRESHOLD, MAX_INDEXING_THREADS)
from modules.paths import CHEMBL_REF
ap = argparse.ArgumentParser()
ap.add_argument("--collection", default="chembl")
ap.add_argument("--ref", default=str(CHEMBL_REF))
args = ap.parse_args()
REF = args.ref; NAME = args.collection
c = QdrantClient(url="http://localhost:6333", timeout=600, check_compatibility=False)

if c.collection_exists(NAME):
    print(f"deleting existing {NAME}"); c.delete_collection(NAME)
c.create_collection(NAME,
    vectors_config=models.VectorParams(size=2048, distance=models.Distance.COSINE, on_disk=False),
    hnsw_config=models.HnswConfigDiff(m=32, ef_construct=256, on_disk=False, max_indexing_threads=MAX_INDEXING_THREADS),
    quantization_config=models.BinaryQuantization(binary=models.BinaryQuantizationConfig(always_ram=True)),
    optimizers_config=models.OptimizersConfigDiff(max_segment_size=MAX_SEGMENT_SIZE,
        memmap_threshold=MEMMAP_THRESHOLD, indexing_threshold=DEFER_THRESHOLD))
print(f"created collection {NAME} (2048-d cosine, binary quant, index deferred)", flush=True)

cid_targets = {int(k): v for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
def fp_norm(sm):
    m = Chem.MolFromSmiles(sm)
    if m is None: return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, a)
    n = np.linalg.norm(a)
    return (a / n).tolist() if n > 0 else None

batch, n, skipped, t0 = [], 0, 0, time.time()
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if not cid.isdigit(): continue
    cid = int(cid); v = fp_norm(sm)
    if v is None: skipped += 1; continue
    batch.append(models.PointStruct(id=cid, vector=v,
        payload={"cid": cid, "smiles": sm, "targets": cid_targets.get(cid, []), "source": "chembl"}))
    if len(batch) >= 2000:
        c.upsert(NAME, batch, wait=False); n += len(batch); batch = []
        if n % 100000 == 0: print(f"  {n:,} inserted · {time.time()-t0:.0f}s", flush=True)
if batch: c.upsert(NAME, batch, wait=True); n += len(batch)
print(f"inserted {n:,} ({skipped} unparseable skipped) in {time.time()-t0:.0f}s", flush=True)

print("triggering HNSW build…", flush=True)
c.update_collection(NAME, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=BUILD_THRESHOLD),
                    hnsw_config=models.HnswConfigDiff(max_indexing_threads=MAX_INDEXING_THREADS))
t = time.time()
while True:
    info = c.get_collection(NAME)
    idx = info.indexed_vectors_count or 0; tot = info.points_count
    # tiny collections (< BUILD_THRESHOLD) are never HNSW-indexed by Qdrant, so indexed stays 0 forever
    # (a brute-force scan serves them). Green + below-threshold = done; don't wait on idx>=tot (would hang).
    if info.status == models.CollectionStatus.GREEN and (idx >= tot * 0.99 or tot < BUILD_THRESHOLD):
        print(f"DONE: {NAME} green, {idx:,}/{tot:,} indexed in {time.time()-t:.0f}s", flush=True); break
    if time.time() - t > 1800: print(f"timeout waiting (status {info.status}, {idx}/{tot})"); break
    time.sleep(10)
