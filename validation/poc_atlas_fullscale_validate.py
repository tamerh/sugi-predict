#!/usr/bin/env python3
"""STEP 3 — the go/no-go: does ligand→target k-NN still beat baselines at FULL proteome scale?
Reference = full ChEMBL (683,544 molecules, 7,929 targets, biobtree-assembled). Unbiased leave-one-out:
sample reference compounds, HOLD OUT the query + its near-duplicates (Tanimoto≥0.99), predict its target by
chemical k-NN over all 7,929 targets, score recall@1/@5 vs POPULARITY (degree null) + RANDOM. Stratify by
top-neighbor Tanimoto (graded signal, not duplicate memorization). The honest number that decides 'build it'."""
import sys, json, random, collections
sys.path.insert(0, "/data/bioyoda")
import numpy as np
from FPSim2 import FPSim2Engine
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
N_QUERIES, KNN, SEED = 1500, 20, 42

print("loading reference index + labels…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit(): cid_smiles[int(cid)] = sm
# popularity null: targets ranked by #molecules (degree)
deg = collections.Counter(t for ts in cid_targets.values() for t in ts)
POP = [t for t, _ in deg.most_common()]
ALLT = list(deg)
print(f"  {len(cid_smiles):,} molecules, {len(deg):,} targets", flush=True)

rng = random.Random(SEED)
queries = [c for c in rng.sample(list(cid_targets), N_QUERIES*2) if c in cid_smiles][:N_QUERIES]

def predict(qcid):
    res = eng.similarity(cid_smiles[qcid], 0.20, n_workers=4)   # (mol_id, coeff) desc
    votes = collections.defaultdict(float); top_tan = 0.0; used = 0
    for mid, co in res:
        mid = int(mid)
        if mid == qcid or co >= 0.99: continue                 # held out: self + near-duplicates
        if used == 0: top_tan = float(co)
        for t in cid_targets.get(mid, ()): votes[t] += float(co)
        used += 1
        if used >= KNN: break
    ranked = [t for t, _ in sorted(votes.items(), key=lambda x: -x[1])]
    return ranked, top_tan

knn1 = knn5 = pop1 = pop5 = rnd1 = rnd5 = 0
strat = collections.defaultdict(lambda: [0, 0])   # tan band -> [hits@1, n]
for q in queries:
    truth = cid_targets[q]
    ranked, tt = predict(q)
    h1 = bool(ranked[:1]) and bool(truth & set(ranked[:1]))
    knn1 += h1; knn5 += bool(truth & set(ranked[:5]))
    pop1 += bool(truth & set(POP[:1])); pop5 += bool(truth & set(POP[:5]))
    rsel = rng.sample(ALLT, 5); rnd1 += bool(truth & set(rsel[:1])); rnd5 += bool(truth & set(rsel))
    band = "≥0.7" if tt >= 0.7 else "0.5-0.7" if tt >= 0.5 else "0.3-0.5" if tt >= 0.3 else "<0.3"
    strat[band][0] += h1; strat[band][1] += 1
n = len(queries)
print(f"\n### FULL-SCALE VALIDATION ({n} held-out queries, predicting among {len(deg):,} targets)\n")
print(f"{'method':16}{'recall@1':>10}{'recall@5':>10}")
print(f"{'k-NN (chem)':16}{knn1/n:>9.1%}{knn5/n:>10.1%}")
print(f"{'POPULARITY':16}{pop1/n:>9.1%}{pop5/n:>10.1%}")
print(f"{'RANDOM':16}{rnd1/n:>9.1%}{rnd5/n:>10.1%}")
print("\nk-NN recall@1 by top-neighbor Tanimoto (graded → real signal, not duplicate memorization):")
for b in ("≥0.7", "0.5-0.7", "0.3-0.5", "<0.3"):
    h, c = strat[b]
    if c: print(f"  {b:8} {h/c:>6.1%}  (n={c})")
print("\nVERDICT: atlas is good at scale iff k-NN >> POPULARITY/RANDOM and recall holds at modest Tanimoto.")
