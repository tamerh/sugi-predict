#!/usr/bin/env python3
"""HEAD-TO-HEAD: deployed max-Tanimoto k-NN ranking vs. a SEA-style (set-size-corrected) ranking.

Reviewer ask: our target-prediction ranks targets by max-Tanimoto (per target) + vote tie-break, with NO
set-size correction / E-value, so it is allegedly "weaker than SEA" (Similarity Ensemble Approach,
Keiser 2007 / Lounkine 2012). SEA's signature is exactly that correction: it scores a target by the SUM of
above-threshold pairwise Tanimotos between the query and that target's ligand set, then corrects for the
fact that a LARGE (promiscuous) ligand set accumulates a high raw sum by chance. We implement a faithful-enough
SEA z-score and run it on the SAME scaffold-split held-out protocol + SAME 2000-query sample (SEED=42) as the
deployed validator (poc_atlas_scaffold_validate.py), so recall@1/@5 are apples-to-apples.

Both methods share ONE retrieval (FPSim2 similarity above a low floor); they differ ONLY in how they rank
targets from that neighbour set:
  - DEPLOYED : supp[t] = max Tanimoto over t's neighbours; tie-break by vote = sum Tanimoto. (top-KNN=20 pool,
               identical to the deployed validator.)
  - SEA      : raw[t]  = sum of (Tanimoto) over t's neighbours with Tanimoto >= SEA_THR  (over the FULL pool,
               not just top-20 — SEA aggregates the whole ensemble). Then a set-size correction turns raw[t]
               into a z-score that penalises large targets:
                   mu(n)    = n * p_hit * E[s | s>=SEA_THR]              expected raw sum for a random size-n set
                   sigma(n) = sqrt(n * p_hit * E[s^2 | s>=SEA_THR])      ~ variance of that sum (indep. approx.)
                   z[t]     = (raw[t] - mu(n_t)) / sigma(n_t)
               where p_hit and the conditional similarity moments are the BACKGROUND probability/moments that a
               random reference ligand clears SEA_THR against an arbitrary query, estimated once from random
               query/ligand pairs. This is SEA's E-value idea (raw score is converted to a significance that
               accounts for n_target) without the full EVD fit — the key, set-size correction, is faithful.

Run:  /data/miniconda3/envs/bioyoda/bin/python /data/bioyoda/usecases/poc_atlas_sea_compare.py
"""
import sys, json, random, collections, math
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/out_prod/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"

# ----- protocol constants copied EXACTLY from poc_atlas_scaffold_validate.py -----
N_QUERIES, KNN, SEED, THR = 2000, 20, 42, 0.15
# ----- SEA-specific -----
SEA_THR   = 0.40    # SEA similarity-of-interest cutoff (Lounkine 2012 used ~0.57 for ECFP4; we sweep below)
SEA_POOL  = 0.15    # retrieval floor for the SEA neighbour pool (== THR; SEA aggregates the WHOLE ensemble)
BG_PAIRS  = 4000    # random query/ligand pairs to estimate the SEA background moments

print("loading uncapped reference index + labels…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit(): cid_smiles[int(cid)] = sm
deg = collections.Counter(t for ts in cid_targets.values() for t in ts)
POP = [t for t, _ in deg.most_common()]; ALLT = list(deg)
# target set size n_t = number of REFERENCE LIGANDS annotated to target t (the SEA set size)
n_target = collections.Counter()
for cid, ts in cid_targets.items():
    for t in ts: n_target[t] += 1
N_REF = len(cid_smiles)
print(f"  {len(cid_smiles):,} molecules, {len(deg):,} targets", flush=True)

_scaf = {}
def scaffold(cid):
    if cid in _scaf: return _scaf[cid]
    s = cid_smiles.get(cid)
    try: sc = MurckoScaffold.MurckoScaffoldSmiles(s) if s else ""
    except Exception: sc = ""
    _scaf[cid] = sc; return sc

# ------------------------------------------------------------------------------
# Estimate SEA background: for a random query vs random reference ligand, what is
#   p_hit  = P(Tanimoto >= SEA_THR)
#   m1     = E[Tanimoto | Tanimoto >= SEA_THR]
#   m2     = E[Tanimoto^2 | Tanimoto >= SEA_THR]
# We get these cheaply: run similarity(query, SEA_THR) for many random queries; each returned hit is a
# random-ligand pair clearing SEA_THR. p_hit = (#hits) / (#queries * N_REF). Moments from the hit similarities.
# ------------------------------------------------------------------------------
def estimate_background(rng, n_q=200):
    qs = [c for c in rng.sample(list(cid_smiles), n_q * 2) if c in cid_smiles][:n_q]
    n_hits = 0; s1 = 0.0; s2 = 0.0; n_pairs = 0
    for q in qs:
        res = eng.similarity(cid_smiles[q], SEA_THR, n_workers=4)
        n_pairs += N_REF
        for mid, co in res:
            if int(mid) == q: continue
            co = float(co)
            n_hits += 1; s1 += co; s2 += co * co
    p_hit = n_hits / max(1, n_pairs)
    m1 = s1 / max(1, n_hits)
    m2 = s2 / max(1, n_hits)
    return p_hit, m1, m2

bg_rng = random.Random(SEED + 7)
p_hit, m1, m2 = estimate_background(bg_rng, n_q=max(100, BG_PAIRS // 20))
# per-ligand contribution moments (over ALL random ligands, incl. the (1-p_hit) that contribute 0):
mu_per   = p_hit * m1                       # E[contribution of one random ligand]
var_per  = p_hit * m2 - mu_per * mu_per     # Var[contribution of one random ligand]
print(f"  SEA background @THR={SEA_THR}: p_hit={p_hit:.3e}  E[s|hit]={m1:.3f}  "
      f"mu_per={mu_per:.3e}  sd_per={math.sqrt(max(var_per,1e-12)):.3e}", flush=True)

# ------------------------------------------------------------------------------
# Retrieve ONE neighbour set per query, then derive BOTH rankings from it.
# DEPLOYED uses the top-KNN pool (self/leak filtered) exactly like the validator.
# SEA uses the FULL above-SEA_POOL pool (self/leak filtered) and aggregates per target.
# ------------------------------------------------------------------------------
def predict_both(qcid, mode):
    qs = scaffold(qcid) if mode == "scaffold" else None
    res = eng.similarity(cid_smiles[qcid], SEA_POOL, n_workers=4)   # res sorted by descending Tanimoto

    # ---- deployed ranking (identical logic to validator: top-KNN pool) ----
    supp = {}; vote = {}; used = 0; top_tan = 0.0
    # ---- SEA accumulators (full pool) ----
    sea_raw = collections.defaultdict(float)
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid: continue
        if mode == "loo" and co >= 0.99: continue
        if mode == "scaffold" and qs and scaffold(mid) == qs: continue

        # deployed: only first KNN neighbours
        if used < KNN:
            if used == 0: top_tan = co
            for t in cid_targets.get(mid, ()):
                vote[t] = vote.get(t, 0.0) + co
                if co > supp.get(t, 0.0): supp[t] = co
            used += 1
        # SEA: whole ensemble above SEA_THR
        if co >= SEA_THR:
            for t in cid_targets.get(mid, ()):
                sea_raw[t] += co
        if used >= KNN and co < SEA_THR:
            break   # past KNN AND below SEA cutoff -> nothing more to gather (res is sorted)

    deployed = sorted(supp, key=lambda t: (-supp[t], -vote[t]))

    # ---- SEA set-size correction -> z-score ----
    sea = []
    for t, raw in sea_raw.items():
        n = n_target[t]
        mu = n * mu_per
        sd = math.sqrt(max(n * var_per, 1e-12))
        z = (raw - mu) / sd
        sea.append((t, z))
    sea_ranked = [t for t, _ in sorted(sea, key=lambda x: -x[1])]
    return deployed, sea_ranked, top_tan

# ------------------------------------------------------------------------------
# SAME query sample as the validator (SEED=42, sample N*2 then filter to N).
# ------------------------------------------------------------------------------
rng = random.Random(SEED)
queries = [c for c in rng.sample(list(cid_targets), N_QUERIES * 2) if c in cid_smiles][:N_QUERIES]

res_acc = {m: {"dep_r1": 0, "dep_r5": 0, "sea_r1": 0, "sea_r5": 0,
               "strat": collections.defaultdict(lambda: [0, 0, 0])} for m in ("loo", "scaffold")}
for q in queries:
    truth = cid_targets[q]
    for m in ("loo", "scaffold"):
        dep, sea, tt = predict_both(q, m)
        d1 = bool(dep[:1]) and bool(truth & set(dep[:1]))
        s1 = bool(sea[:1]) and bool(truth & set(sea[:1]))
        res_acc[m]["dep_r1"] += d1; res_acc[m]["dep_r5"] += bool(truth & set(dep[:5]))
        res_acc[m]["sea_r1"] += s1; res_acc[m]["sea_r5"] += bool(truth & set(sea[:5]))
        band = "≥0.7" if tt >= 0.7 else "0.5-0.7" if tt >= 0.5 else "0.3-0.5" if tt >= 0.3 else "<0.3"
        st = res_acc[m]["strat"][band]; st[0] += d1; st[1] += s1; st[2] += 1

n = len(queries)
print(f"\n### HEAD-TO-HEAD — {n} held-out queries, among {len(deg):,} targets  (SEA_THR={SEA_THR})\n")
print(f"{'split':14}{'method':20}{'recall@1':>10}{'recall@5':>10}")
for m in ("loo", "scaffold"):
    a = res_acc[m]
    print(f"{m:14}{'deployed max-Tan':20}{a['dep_r1']/n:>9.1%}{a['dep_r5']/n:>10.1%}")
    print(f"{m:14}{'SEA set-size z':20}{a['sea_r1']/n:>9.1%}{a['sea_r5']/n:>10.1%}")
print("\n(scaffold split = HONEST generalization number; deployed scaffold should reproduce ~77%/88%)")
print("\nscaffold-split recall@1 by top-neighbour Tanimoto (deployed | SEA):")
for b in ("≥0.7", "0.5-0.7", "0.3-0.5", "<0.3"):
    d, s, c = res_acc["scaffold"]["strat"][b]
    if c: print(f"  {b:8} deployed {d/c:>6.1%}  SEA {s/c:>6.1%}  (n={c})")

# ------------------------------------------------------------------------------
# SANITY CHECK — known drugs, no leak filtering (mode='live'), top-3 each method.
# ------------------------------------------------------------------------------
DRUGS = {
    "gefitinib": ("COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1", "EGFR P00533"),
    "imatinib":  ("Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1", "ABL1 P00519"),
    "captopril": ("CC(CS)C(=O)N1CCCC1C(=O)O", "ACE P12821"),
    "sildenafil":("CCCc1nn(C)c2c1nc(-c1cc(S(=O)(=O)N3CCN(C)CC3)ccc1OCC)[nH]c2=O", "PDE5A O76074"),
}
def rank_live(smiles):
    res = eng.similarity(smiles, SEA_POOL, n_workers=4)
    supp = {}; vote = {}; used = 0; sea_raw = collections.defaultdict(float)
    for mid, co in res:
        mid = int(mid); co = float(co)
        if used < KNN:
            for t in cid_targets.get(mid, ()):
                vote[t] = vote.get(t, 0.0) + co
                if co > supp.get(t, 0.0): supp[t] = co
            used += 1
        if co >= SEA_THR:
            for t in cid_targets.get(mid, ()):
                sea_raw[t] += co
    dep = sorted(supp, key=lambda t: (-supp[t], -vote[t]))[:3]
    sea = []
    for t, raw in sea_raw.items():
        nn = n_target[t]; mu = nn * mu_per; sd = math.sqrt(max(nn * var_per, 1e-12))
        sea.append((t, (raw - mu) / sd))
    sea = [t for t, _ in sorted(sea, key=lambda x: -x[1])][:3]
    return dep, sea

print("\n### SANITY CHECK — known drugs (no leak filter); top-3 targets each method")
for name, (sm, expect) in DRUGS.items():
    try:
        dep, sea = rank_live(sm)
        print(f"  {name:11} expect~{expect:13}  deployed={dep}  SEA={sea}")
    except Exception as e:
        print(f"  {name:11} ERROR {e}")
