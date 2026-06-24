#!/usr/bin/env python3
"""Scoring experiment: does combining confidence + support (+ IDF promiscuity penalty) rank targets better
than confidence alone? Re-ranks the SAME scaffold-split retrieval five ways and reports recall@k, with a
bootstrap CI on the best-vs-deployed recall@5 difference. Decides the scoring to freeze into the payload bake.
"""
import sys, json, random, collections, math
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
N_QUERIES, KNN, SEED, THR = 1500, 20, 42, 0.15

print("loading uncapped reference…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit(): cid_smiles[int(cid)] = sm
deg = collections.Counter(t for ts in cid_targets.values() for t in ts)
N = len(cid_targets)
idf = {t: math.log(N / (c + 1)) for t, c in deg.items()}     # promiscuous target (big deg) -> small idf
print(f"  {len(cid_smiles):,} molecules, {len(deg):,} targets", flush=True)

_scaf = {}
def scaffold(cid):
    if cid in _scaf: return _scaf[cid]
    s = cid_smiles.get(cid)
    try: sc = MurckoScaffold.MurckoScaffoldSmiles(s) if s else ""
    except Exception: sc = ""
    _scaf[cid] = sc; return sc

SCORERS = {
    "conf (deployed)":      lambda t, s, v, n: (s[t], v[t], n[t]),
    "vote (sim-weighted)":  lambda t, s, v, n: (v[t],),
    "vote x IDF":           lambda t, s, v, n: (v[t] * idf[t],),
    "conf x IDF":           lambda t, s, v, n: (s[t] * idf[t], v[t] * idf[t]),
    "support (count)":      lambda t, s, v, n: (n[t], s[t]),
}

def neighbours(qcid):
    qs = scaffold(qcid)
    res = eng.similarity(cid_smiles[qcid], THR, n_workers=4)
    supp = {}; vote = {}; nbr = {}; used = 0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid: continue
        if qs and scaffold(mid) == qs: continue                  # scaffold split
        for t in cid_targets.get(mid, ()):
            vote[t] = vote.get(t, 0.0) + co
            if co > supp.get(t, 0.0): supp[t] = co
            nbr[t] = nbr.get(t, 0) + 1
        used += 1
        if used >= KNN: break
    return supp, vote, nbr

rng = random.Random(SEED)
queries = [c for c in rng.sample(list(cid_targets), N_QUERIES * 2) if c in cid_smiles][:N_QUERIES]
hits = {name: {k: [] for k in (1, 5, 10)} for name in SCORERS}    # per-query booleans, for bootstrap
n = 0
for q in queries:
    supp, vote, nbr = neighbours(q)
    if not supp: continue
    n += 1
    truth = cid_targets[q]
    for name, key in SCORERS.items():
        ranked = sorted(supp, key=lambda t: tuple(-x for x in key(t, supp, vote, nbr)))
        for k in (1, 5, 10):
            hits[name][k].append(1 if (truth & set(ranked[:k])) else 0)

print(f"\n### SCORING EXPERIMENT — {n} held-out queries, SCAFFOLD split, among {len(deg):,} targets\n")
print(f"{'scoring':24}{'recall@1':>10}{'recall@5':>10}{'recall@10':>11}")
rate = lambda L: sum(L) / len(L)
for name in SCORERS:
    h = hits[name]; print(f"{name:24}{rate(h[1]):>9.1%}{rate(h[5]):>10.1%}{rate(h[10]):>10.1%}")

# bootstrap 95% CI on recall@5 difference: best-non-deployed vs deployed
base = "conf (deployed)"
others = [m for m in SCORERS if m != base]
best = max(others, key=lambda m: rate(hits[m][5]))
B = 2000; rbest = hits[best][5]; rbase = hits[base][5]
brng = random.Random(7); diffs = []
for _ in range(B):
    idx = [brng.randrange(n) for _ in range(n)]
    diffs.append(sum(rbest[i] for i in idx) / n - sum(rbase[i] for i in idx) / n)
diffs.sort()
lo, hi = diffs[int(.025 * B)], diffs[int(.975 * B)]
d = rate(rbest) - rate(rbase)
print(f"\nbest alternative = '{best}'  recall@5 {rate(rbest):.1%} vs deployed {rate(rbase):.1%}")
print(f"  diff = {d:+.1%}  95% CI [{lo:+.1%}, {hi:+.1%}]  -> {'SIGNIFICANT' if lo > 0 or hi < 0 else 'not significant (CI crosses 0)'}")
