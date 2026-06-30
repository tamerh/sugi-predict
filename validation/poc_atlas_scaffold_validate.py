#!/usr/bin/env python3
"""The HONEST validation (panel #1 ask): how much does recall drop under a SCAFFOLD split vs. standard LOO?

Standard leave-one-out (exclude self + Tanimoto>=0.99 near-dups) measures retrieval within known chemotype
space — an interpolation UPPER BOUND. The scaffold split additionally excludes EVERY reference ligand sharing the
query's Bemis-Murcko scaffold, so no same-series analog can leak — the number that actually predicts generalization
to the novel chemotypes typical of patents. Uses the DEPLOYED ranking (max-Tanimoto confidence, tie-break vote) on
the UNCAPPED reference, predicting among all 7,929 targets, vs popularity/random baselines, stratified by Tanimoto.
"""
import sys, json, random, collections
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
N_QUERIES, KNN, SEED, THR = 2000, 20, 42, 0.15

print("loading uncapped reference index + labels…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit(): cid_smiles[int(cid)] = sm
deg = collections.Counter(t for ts in cid_targets.values() for t in ts)
POP = [t for t, _ in deg.most_common()]; ALLT = list(deg)
print(f"  {len(cid_smiles):,} molecules, {len(deg):,} targets", flush=True)

_scaf = {}
def scaffold(cid):
    if cid in _scaf: return _scaf[cid]
    s = cid_smiles.get(cid)
    try: sc = MurckoScaffold.MurckoScaffoldSmiles(s) if s else ""
    except Exception: sc = ""
    _scaf[cid] = sc; return sc

def predict(qcid, mode):
    """mode='loo' (exclude self + >=0.99) or 'scaffold' (exclude self + same Bemis-Murcko scaffold).
    Returns (ranked targets by DEPLOYED supp/vote ranking, top-neighbour Tanimoto used)."""
    qs = scaffold(qcid) if mode == "scaffold" else None
    res = eng.similarity(cid_smiles[qcid], THR, n_workers=4)
    supp = {}; vote = {}; used = 0; top_tan = 0.0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid: continue
        if mode == "loo" and co >= 0.99: continue
        if mode == "scaffold" and qs and scaffold(mid) == qs: continue
        if used == 0: top_tan = co
        for t in cid_targets.get(mid, ()):
            vote[t] = vote.get(t, 0.0) + co
            if co > supp.get(t, 0.0): supp[t] = co
        used += 1
        if used >= KNN: break
    ranked = sorted(supp, key=lambda t: (-supp[t], -vote[t]))      # deployed ranking
    return ranked, top_tan

rng = random.Random(SEED)
queries = [c for c in rng.sample(list(cid_targets), N_QUERIES * 2) if c in cid_smiles][:N_QUERIES]

res = {m: {"r1": 0, "r5": 0, "strat": collections.defaultdict(lambda: [0, 0])} for m in ("loo", "scaffold")}
pop1 = pop5 = rnd1 = rnd5 = 0
for q in queries:
    truth = cid_targets[q]
    for m in ("loo", "scaffold"):
        ranked, tt = predict(q, m)
        h1 = bool(ranked[:1]) and bool(truth & set(ranked[:1]))
        res[m]["r1"] += h1; res[m]["r5"] += bool(truth & set(ranked[:5]))
        band = "≥0.7" if tt >= 0.7 else "0.5-0.7" if tt >= 0.5 else "0.3-0.5" if tt >= 0.3 else "<0.3"
        res[m]["strat"][band][0] += h1; res[m]["strat"][band][1] += 1
    pop1 += bool(truth & set(POP[:1])); pop5 += bool(truth & set(POP[:5]))
    rsel = rng.sample(ALLT, 5); rnd1 += bool(truth & set(rsel[:1])); rnd5 += bool(truth & set(rsel))

n = len(queries)
print(f"\n### VALIDATION — {n} held-out queries, deployed ranking, among {len(deg):,} targets\n")
print(f"{'condition':28}{'recall@1':>10}{'recall@5':>10}")
print(f"{'LOO (self+near-dup excl.)':28}{res['loo']['r1']/n:>9.1%}{res['loo']['r5']/n:>10.1%}   <- interpolation upper bound")
print(f"{'SCAFFOLD split':28}{res['scaffold']['r1']/n:>9.1%}{res['scaffold']['r5']/n:>10.1%}   <- HONEST generalization number")
print(f"{'popularity baseline':28}{pop1/n:>9.1%}{pop5/n:>10.1%}")
print(f"{'random baseline':28}{rnd1/n:>9.1%}{rnd5/n:>10.1%}")
for m in ("loo", "scaffold"):
    print(f"\n{m} recall@1 by top-neighbour Tanimoto:")
    for b in ("≥0.7", "0.5-0.7", "0.3-0.5", "<0.3"):
        h, c = res[m]["strat"][b]
        if c: print(f"  {b:8} {h/c:>6.1%}  (n={c})")
