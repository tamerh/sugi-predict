#!/usr/bin/env python3
"""Validate the de-noise floor before applying it: leave-one-out over the ChEMBL reference (production-like,
no scaffold split), bucket every neighbour-transferred prediction as DROP (support==1 AND conf<FLOOR) vs KEEP,
and measure (a) how often each bucket is actually correct, and (b) how many genuinely-correct targets the floor
would lose. Answers "is dropping support-1/low-conf risky?" with numbers.
"""
import sys, json, random
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
N_QUERIES, KNN, SEED, THR, FLOOR = 2000, 20, 42, 0.15, 0.4

print("loading reference…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit():
        cid_smiles[int(cid)] = sm
print(f"  {len(cid_smiles):,} molecules", flush=True)


def neighbours(qcid):
    res = eng.similarity(cid_smiles[qcid], THR, n_workers=4)
    supp, nbr, used = {}, {}, 0
    for mid, co in res:
        mid, co = int(mid), float(co)
        if mid == qcid:
            continue
        for t in cid_targets.get(mid, ()):
            if co > supp.get(t, 0.0):
                supp[t] = co
            nbr[t] = nbr.get(t, 0) + 1
        used += 1
        if used >= KNN:
            break
    return supp, nbr


rng = random.Random(SEED)
queries = [c for c in rng.sample(list(cid_targets), N_QUERIES * 3) if c in cid_smiles][:N_QUERIES]

drop_tot = drop_ok = keep_tot = keep_ok = 0
true_rec = true_lost = 0
n = 0
for q in queries:
    supp, nbr = neighbours(q)
    if not supp:
        continue
    n += 1
    truth = cid_targets[q]
    drop_t, keep_t = set(), set()
    for t, c in supp.items():
        dropped = (nbr[t] == 1 and c < FLOOR)
        ok = t in truth
        if dropped:
            drop_tot += 1; drop_ok += ok; drop_t.add(t)
        else:
            keep_tot += 1; keep_ok += ok; keep_t.add(t)
    for t in (truth & set(supp)):                 # correctly-recovered true targets
        true_rec += 1
        if t in drop_t and t not in keep_t:        # would be lost by the floor
            true_lost += 1

print(f"\nqueries used: {n}   (leave-one-out, top-{KNN} neighbours, floor: support==1 & conf<{FLOOR})")
print(f"DROP bucket: {drop_tot:,} predictions  ->  {100*drop_ok/max(drop_tot,1):.1f}% actually correct")
print(f"KEEP bucket: {keep_tot:,} predictions  ->  {100*keep_ok/max(keep_tot,1):.1f}% actually correct")
print(f"volume dropped: {100*drop_tot/(drop_tot+keep_tot):.1f}% of all predictions")
print(f"RECALL RISK: of {true_rec:,} correctly-recovered targets, "
      f"{true_lost:,} ({100*true_lost/max(true_rec,1):.2f}%) would be LOST by the floor")
