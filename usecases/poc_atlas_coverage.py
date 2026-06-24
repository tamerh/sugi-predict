#!/usr/bin/env python3
"""COVERAGE: what fraction of the 30.9M patent compounds are close enough to a known ChEMBL ligand to get a
CONFIDENT target prediction? For a random sample of patent compounds, find best Tanimoto to the 683K ChEMBL
reference, bucket by confidence. This bounds how much of the patent corpus the atlas can confidently annotate."""
import sys, glob, random, collections
import pyarrow.parquet as pq
from FPSim2 import FPSim2Engine
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

H5 = "/data/bioyoda/work/chembl_reference/chembl_reference_morgan_r2_2048.h5"
PARQ = sorted(glob.glob("/data/bioyoda/raw_data/patents/chunked_compounds/compounds_chunk_*.parquet"))
PER_CHUNK, SEED = 1500, 42
rng = random.Random(SEED)

print("loading ChEMBL reference index…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
print(f"  {eng.fps.shape[0]:,} reference fps", flush=True)

# sample patent SMILES spread across the id range (every ~10th chunk)
sample = []
for f in PARQ[::10]:
    t = pq.read_table(f, columns=["smiles"]); sm = t.column("smiles").to_pylist()
    sample += rng.sample(sm, min(PER_CHUNK, len(sm)))
print(f"sampling {len(sample)} patent compounds across {len(PARQ[::10])} chunks…", flush=True)

THR = (0.7, 0.5, 0.4, 0.3, 0.2)
buckets = collections.Counter(); best_list = []; bad = 0
for s in sample:
    if not s: bad += 1; continue
    try:
        res = eng.similarity(s, min(THR), n_workers=4)   # neighbors ≥0.2, sorted desc
    except Exception:
        bad += 1; continue
    best = float(res[0][1]) if len(res) else 0.0
    best_list.append(best)
    placed = False
    for t in THR:
        if best >= t: buckets[t] += 1; placed = True; break
    if not placed: buckets["<0.2"] += 1
n = len(best_list)
print(f"\n### COVERAGE — best Tanimoto of {n} random patent compounds to the ChEMBL reference (dropped {bad})\n")
print(f"  {'best Tanimoto band':22}{'count':>8}{'% of sample':>13}{'cumulative ≥':>14}")
cum = 0
for t in THR:
    cum += buckets[t]
    print(f"  ≥ {t:<20}{buckets[t]:>8}{buckets[t]/n:>12.1%}{cum/n:>13.1%}")
print(f"  < 0.2 (no confident neighbor){buckets['<0.2']:>{8-4}}{buckets['<0.2']/n:>12.1%}")
import numpy as np
b = np.array(best_list)
print(f"\n  median best-Tanimoto = {np.median(b):.3f}   mean = {b.mean():.3f}")
print(f"\nREAD: '≥0.5' ≈ high-confidence annotation (~90% accurate), '0.3-0.5' moderate, '<0.3' low/none.")
print("This is the fraction of the 30.9M patent corpus the atlas can confidently target-annotate.")
