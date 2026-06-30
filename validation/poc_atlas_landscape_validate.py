#!/usr/bin/env python3
"""Quantitative validation of the TARGET -> LANDSCAPE direction (the flagship use-case the reviewer flags as
unvalidated). Forward validation measures recall@1 (did the top prediction match). The landscape direction is a
PRECISION question: when the atlas surfaces a compound in target X's landscape at confidence >= t, how often is X
really a target of that compound?

We measure this on SCAFFOLD-held-out ChEMBL ligands (every same-Bemis-Murcko-scaffold reference ligand withheld, so
no same-series leak) as a gold-standard proxy for patent compounds. Reports global precision at the deployed
confidence thresholds, plus a macro (per-target) view and the surfaced-recall. ChEMBL target annotations are
INCOMPLETE, so a 'wrong' high-confidence call may be an untested true target -> the precision here is a LOWER BOUND.
"""
import sys, json, random, collections
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/out_prod/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
N_QUERIES, KNN, SEED, THR = 2000, 20, 42, 0.15
THRESH = [0.5, 0.7]            # deployed high-confidence cut-offs

print("loading uncapped reference index + labels…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit(): cid_smiles[int(cid)] = sm
print(f"  {len(cid_smiles):,} molecules", flush=True)

_scaf = {}
def scaffold(cid):
    if cid in _scaf: return _scaf[cid]
    s = cid_smiles.get(cid)
    try: sc = MurckoScaffold.MurckoScaffoldSmiles(s) if s else ""
    except Exception: sc = ""
    _scaf[cid] = sc; return sc

def predict_supp(qcid):
    """scaffold-held-out per-target confidence (max-Tanimoto to a supporting neighbour)."""
    qs = scaffold(qcid)
    res = eng.similarity(cid_smiles[qcid], THR, n_workers=4)
    supp = {}; used = 0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid: continue
        if qs and scaffold(mid) == qs: continue
        for t in cid_targets.get(mid, ()):
            if co > supp.get(t, 0.0): supp[t] = co
        used += 1
        if used >= KNN: break
    return supp

rng = random.Random(SEED)
queries = [c for c in rng.sample(list(cid_targets), N_QUERIES * 2) if c in cid_smiles][:N_QUERIES]

tp = {t: 0 for t in THRESH}; tot = {t: 0 for t in THRESH}        # global (micro) precision
per_t = {t: collections.defaultdict(lambda: [0, 0]) for t in THRESH}   # per-target [correct, total]
surf_hit = {t: 0 for t in THRESH}; surf_tot = 0                  # surfaced-recall: true target found at conf>=t

for q in queries:
    truth = cid_targets[q]
    supp = predict_supp(q)
    surf_tot += len(truth)
    for thr in THRESH:
        surfaced_for_q = {t for t, c in supp.items() if c >= thr}
        for t in surfaced_for_q:
            tot[thr] += 1; per_t[thr][t][1] += 1
            if t in truth:
                tp[thr] += 1; per_t[thr][t][0] += 1
        surf_hit[thr] += len(truth & surfaced_for_q)

n = len(queries)
print(f"\n### LANDSCAPE PRECISION — {n} scaffold-held-out queries (lower bound; ChEMBL labels incomplete)\n")
print(f"{'confidence cut':16}{'precision (micro)':>20}{'precision (macro)':>20}{'surfaced-recall':>18}")
for thr in THRESH:
    micro = tp[thr] / tot[thr] if tot[thr] else 0
    pts = [c / n_ for c, n_ in per_t[thr].values() if n_ >= 3]
    macro = sum(pts) / len(pts) if pts else 0
    rec = surf_hit[thr] / surf_tot if surf_tot else 0
    print(f"  conf >= {thr:<6}{micro:>19.1%}{macro:>20.1%}{rec:>18.1%}   ({tot[thr]:,} surfaced assignments)")
print("\nmicro = over all surfaced (compound,target) assignments; macro = averaged over targets with >=3 surfaced;")
print("surfaced-recall = fraction of a compound's true targets that the landscape surfaces at that confidence.")
