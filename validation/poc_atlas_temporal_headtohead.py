#!/usr/bin/env python3
"""HONEST HEAD-TO-HEAD on the TEMPORAL (deployment-realistic) split.

Question (the single most-requested missing benchmark): how does OUR chemical k-NN target prediction
compare against the established ligand-based target-prediction methods it descends from, on the SAME
held-out temporal split, with NO leakage, evaluated identically?

Split discipline (identical to poc_atlas_temporal_validate.py — no leakage):
  * reference (train) = reference ligands with first-disclosure year <= CUTOFF.
  * queries  (test)   = ligands with year > CUTOFF, sampled (SEED, N_QUERIES).
  * For each query, the neighbour pool EXCLUDES (a) the query itself and (b) every post-cutoff ligand,
    so a query can ONLY be answered by genuinely older chemistry. This is the regime the patent atlas
    actually runs in. Years: first-disclosure year per CID (work/chembl_reference/_cid_year.json).

ONE retrieval per query (FPSim2 similarity above a low floor SEA_POOL), restricted to the pre-cutoff pool;
ALL methods rank targets from that SAME neighbour set so the comparison is apples-to-apples:

  OURS (deployed)   : per target, confidence = max Tanimoto to any of its top-KNN neighbours; rank by
                      (-confidence, -support, -vote) where support = #of-top-KNN backing the target,
                      vote = sum Tanimoto. (modules/compounds/target.py logic.)
  SINGLE-NN (1-NN)  : trivial baseline — predict the target(s) of the single nearest pre-cutoff ligand,
                      ordered by that ligand's annotation; ties broken by global popularity. Isolates the
                      value of using 20 neighbours + support over just the top hit.
  SEA               : Similarity Ensemble Approach (Keiser 2007 / Lounkine 2012). Set-based: score a
                      target by the SUM of above-threshold query-vs-ligand Tanimotos over the WHOLE
                      pre-cutoff ensemble (not just top-20), then a set-size (random-background) correction
                      turns the raw sum into a z-score that penalises large/promiscuous ligand sets:
                          raw[t]   = Σ_{lig∈t, Tan>=SEA_THR} Tanimoto(query, lig)              (full pool)
                          mu(n)    = n * E[contribution of one random reference ligand]
                          sigma(n) = sqrt(n * Var[contribution of one random reference ligand])
                          z[t]     = (raw[t] - mu(n_t)) / sigma(n_t)
                      where n_t = #pre-cutoff reference ligands annotated to t, and the per-ligand
                      contribution moments E[.],Var[.] are the SEA random background — estimated once from
                      random query/ligand pairs (a ligand below SEA_THR contributes 0). This is SEA's
                      E-value / set-size-correction idea (raw → significance accounting for n_t) without
                      the full extreme-value-distribution fit; the load-bearing correction is faithful.
  POPULARITY        : the floor — rank targets by pre-cutoff ligand frequency (ignores the query).
  NAIVE-BAYES (NB)  : Laplace-smoothed Bernoulli NB over the 2048 Morgan bits, trained on the pre-cutoff
                      reference (target = class). Scored only over targets that appear among the query's
                      retrieved neighbours (the candidate set), so it is a fair re-ranker of the same
                      candidates — comparable to the multi-category-NB used by ChEMBL/PPB2.

We report recall@1/@5/@10 overall AND stratified by the top-neighbour Tanimoto confidence band, so the
verdict is honest about WHERE each method wins (high-similarity vs the 0.3-0.5 twilight).

Run:  /data/miniconda3/envs/bioyoda/bin/python docs/internal/usecases/poc_atlas_temporal_headtohead.py
"""
import sys, os, json, random, collections, math, time
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
import numpy as np

REF = "/data/bioyoda/out_prod/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"

# ----- protocol constants (match poc_atlas_temporal_validate.py) -----
CUTOFF      = 2018          # train: year <= 2018 ; test: year > 2018 (first-disclosure)
N_QUERIES   = 2000
KNN         = 20            # OURS / single-NN top-k pool
SEED        = 42
SEA_POOL    = 0.15          # FPSim2 retrieval floor (shared by all methods)
# ----- SEA-specific -----
SEA_THR     = 0.40          # SEA similarity-of-interest cutoff (Lounkine 2012 used ~0.57 for ECFP4)
BG_QUERIES  = 200           # random queries to estimate the SEA background moments
# ----- NB-specific -----
NB_MAX_TRAIN_PER_T = None   # cap ligands/target for NB fit (None = all); kept for speed knob
NBITS       = 2048

t_start = time.time()
print("loading uncapped reference index + labels + years…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_year = {int(k): int(v) for k, v in json.load(open(f"{REF}/_cid_year.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit():
        cid_smiles[int(cid)] = sm

dated = {c for c in cid_smiles if c in cid_year and c in cid_targets}
PRE  = {c for c in dated if cid_year[c] <= CUTOFF}     # eligible neighbours (train)
POST = {c for c in dated if cid_year[c] >  CUTOFF}     # eligible queries  (test)
print(f"  {len(cid_smiles):,} molecules, {len(cid_year):,} with a year", flush=True)
print(f"  cutoff {CUTOFF}: train(<=) {len(PRE):,}  |  test(>) {len(POST):,}", flush=True)

# popularity / random universe from the TRAIN reference only (what a deployed system would know)
deg = collections.Counter(t for c in PRE for t in cid_targets[c])
POP = [t for t, _ in deg.most_common()]
ALLT = list(deg)
# SEA set size n_t = # of PRE-cutoff reference ligands annotated to t
n_target = collections.Counter()
for c in PRE:
    for t in cid_targets[c]:
        n_target[t] += 1
print(f"  {len(deg):,} targets in the pre-cutoff training universe", flush=True)

# ---------------------------------------------------------------------------
# SEA random background: per-random-ligand contribution moments above SEA_THR.
# For many random queries, similarity(q, SEA_THR) returns all reference ligands clearing SEA_THR.
# p_hit = (#hits) / (#queries * |PRE|) ; conditional moments from the hit similarities. A ligand
# below SEA_THR contributes 0, so the per-ligand contribution has:
#   mu_per  = p_hit * E[s | s>=SEA_THR]
#   var_per = p_hit * E[s^2 | s>=SEA_THR] - mu_per^2
# Background is estimated over the PRE pool (consistent with the n_t set-size correction).
# ---------------------------------------------------------------------------
def estimate_background(rng, n_q=BG_QUERIES):
    qs = [c for c in rng.sample(list(PRE), min(len(PRE), n_q * 3)) if c in cid_smiles][:n_q]
    n_hits = 0; s1 = 0.0; s2 = 0.0; n_pairs = 0
    NPRE = len(PRE)
    for q in qs:
        res = eng.similarity(cid_smiles[q], SEA_THR, n_workers=4)
        n_pairs += NPRE
        for mid, co in res:
            mid = int(mid)
            if mid == q or mid not in PRE:
                continue
            co = float(co)
            n_hits += 1; s1 += co; s2 += co * co
    p_hit = n_hits / max(1, n_pairs)
    m1 = s1 / max(1, n_hits)
    m2 = s2 / max(1, n_hits)
    return p_hit, m1, m2

bg_rng = random.Random(SEED + 7)
p_hit, m1, m2 = estimate_background(bg_rng)
mu_per  = p_hit * m1
var_per = max(p_hit * m2 - mu_per * mu_per, 1e-12)
print(f"  SEA bg @THR={SEA_THR}: p_hit={p_hit:.3e}  E[s|hit]={m1:.3f}  "
      f"mu_per={mu_per:.3e}  sd_per={math.sqrt(var_per):.3e}", flush=True)

# ---------------------------------------------------------------------------
# NAIVE BAYES (Bernoulli over Morgan bits), trained on the PRE reference.
# For each target t we keep bit-presence counts over its pre-cutoff ligands. NB score for query q and
# target t = sum over bits of log P(bit | t) with Laplace smoothing; restricted at scoring time to the
# query's candidate targets (those present among its retrieved neighbours), so NB re-ranks the same
# candidate set the similarity methods see — a fair head-to-head, not NB over all 7k classes.
# We build per-target bit counts lazily but bounded: only targets that ever appear as a candidate need
# their model. To keep memory sane we precompute counts for ALL pre-cutoff targets in one streaming pass.
# ---------------------------------------------------------------------------
def morgan_bits(smiles):
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=NBITS)
    return list(bv.GetOnBits())

print("training Bernoulli-NB bit counts over the pre-cutoff reference…", flush=True)
t0 = time.time()
t_bitcount = collections.defaultdict(lambda: collections.Counter())  # t -> Counter(bit -> #ligands with bit)
t_n = collections.Counter()                                          # t -> #ligands (NB class prior count)
cnt = 0
for c in PRE:
    bits = morgan_bits(cid_smiles[c])
    if bits is None:
        continue
    ts = cid_targets[c]
    for t in ts:
        t_n[t] += 1
        ctr = t_bitcount[t]
        for b in bits:
            ctr[b] += 1
    cnt += 1
    if cnt % 100000 == 0:
        print(f"    NB fit: {cnt:,} ligands ({time.time()-t0:.0f}s)…", flush=True)
print(f"  NB fitted on {cnt:,} pre-cutoff ligands, {len(t_n):,} targets ({time.time()-t0:.0f}s)", flush=True)

LOG_ALPHA = 1.0  # Laplace smoothing
def nb_score(query_bits, t):
    """log-likelihood of the query bit-vector under target t's Bernoulli model (presence terms only).
    Sum over the query's ON bits of log P(bit=1 | t), Laplace-smoothed. Presence-only (standard ECFP-NB
    practice — absent bits dominate and wash out class signal). Higher = better."""
    n = t_n[t]
    if n == 0:
        return -1e18
    ctr = t_bitcount[t]
    s = 0.0
    denom = n + 2.0 * LOG_ALPHA
    for b in query_bits:
        s += math.log((ctr.get(b, 0) + LOG_ALPHA) / denom)
    return s

# ---------------------------------------------------------------------------
# Per-query: one retrieval (restricted to PRE), derive ALL rankings.
# ---------------------------------------------------------------------------
def predict_all(qcid, qbits):
    res = eng.similarity(cid_smiles[qcid], SEA_POOL, n_workers=4)   # desc Tanimoto

    supp = {}; vote = {}; nbr = collections.Counter()              # OURS
    sea_raw = collections.defaultdict(float)                       # SEA
    first_nn_targets = None; top_tan = 0.0
    cand = set()                                                   # candidate targets (for NB)
    used = 0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid or mid not in PRE:      # leakage guard: self + post-cutoff excluded
            continue
        ts = cid_targets.get(mid, ())
        # --- OURS / single-NN: top-KNN pool ---
        if used < KNN:
            if used == 0:
                top_tan = co
                first_nn_targets = list(ts)
            for t in ts:
                if co > supp.get(t, 0.0): supp[t] = co
                vote[t] = vote.get(t, 0.0) + co
                nbr[t] += 1
                cand.add(t)
            used += 1
        # --- SEA: whole ensemble above SEA_THR ---
        if co >= SEA_THR:
            for t in ts:
                sea_raw[t] += co
                cand.add(t)
        if used >= KNN and co < SEA_THR:
            break

    # OURS: confidence, then support, then vote
    ours = sorted(supp, key=lambda t: (-supp[t], -nbr[t], -vote[t]))

    # single-NN: targets of the single nearest pre-cutoff ligand, popularity-ordered; pad with POP
    fnt = first_nn_targets or []
    snn = sorted(fnt, key=lambda t: -deg.get(t, 0))
    snn = snn + [t for t in POP if t not in set(snn)]

    # SEA z-score
    sea = []
    for t, raw in sea_raw.items():
        n = n_target[t]
        if n == 0:
            continue
        mu = n * mu_per
        sd = math.sqrt(max(n * var_per, 1e-12))
        sea.append((t, (raw - mu) / sd))
    sea_ranked = [t for t, _ in sorted(sea, key=lambda x: -x[1])]

    # NB: re-rank the candidate set by NB log-likelihood
    nb_ranked = sorted(cand, key=lambda t: -nb_score(qbits, t))

    return ours, snn, sea_ranked, nb_ranked, top_tan

# ---------------------------------------------------------------------------
# Same query sample as the temporal validator (SEED, shuffle POST, take N).
# ---------------------------------------------------------------------------
rng = random.Random(SEED)
pool = list(POST); rng.shuffle(pool)
queries = pool[:N_QUERIES]

methods = ["OURS (conf+supp)", "single-NN (1-NN)", "SEA (set-size z)", "POPULARITY", "NAIVE-BAYES"]
Ks = (1, 5, 10)
hits = {m: {k: 0 for k in Ks} for m in methods}
strat = collections.defaultdict(lambda: {m: 0 for m in methods} | {"_n": 0})  # band -> r@1 per method
bands = ("≥0.7", "0.5-0.7", "0.3-0.5", "<0.3")

n = 0; t0 = time.time()
for q in queries:
    truth = cid_targets[q]
    qbits = morgan_bits(cid_smiles[q])
    if qbits is None:
        continue
    ours, snn, sea, nb, tt = predict_all(q, qbits)
    pop = POP
    ranks = {
        "OURS (conf+supp)": ours,
        "single-NN (1-NN)": snn,
        "SEA (set-size z)": sea,
        "POPULARITY":       pop,
        "NAIVE-BAYES":      nb,
    }
    for m, r in ranks.items():
        for k in Ks:
            if truth & set(r[:k]):
                hits[m][k] += 1
    band = "≥0.7" if tt >= 0.7 else "0.5-0.7" if tt >= 0.5 else "0.3-0.5" if tt >= 0.3 else "<0.3"
    strat[band]["_n"] += 1
    for m, r in ranks.items():
        if truth & set(r[:1]):
            strat[band][m] += 1
    n += 1
    if n % 250 == 0:
        print(f"    {n}/{len(queries)} queries ({time.time()-t0:.0f}s)…", flush=True)

# ---------------------------------------------------------------------------
print(f"\n### TEMPORAL HEAD-TO-HEAD — train year<= {CUTOFF}, test year> {CUTOFF}")
print(f"### {n} post-cutoff queries · predict among {len(deg):,} targets · neighbours restricted to pre-cutoff\n")
hdr = f"{'method':20}" + "".join(f"{'recall@'+str(k):>12}" for k in Ks)
print(hdr)
print("-" * len(hdr))
for m in methods:
    print(f"{m:20}" + "".join(f"{hits[m][k]/n:>11.1%} " for k in Ks))

print("\nrecall@1 by top-neighbour Tanimoto band (where each method wins):")
print(f"{'band':10}{'n':>6}" + "".join(f"{m.split()[0]:>14}" for m in methods))
for b in bands:
    s = strat[b]; c = s["_n"]
    if not c:
        continue
    print(f"{b:10}{c:>6}" + "".join(f"{s[m]/c:>13.1%} " for m in methods))

print(f"\n[done in {time.time()-t_start:.0f}s · SEED={SEED} · KNN={KNN} · SEA_THR={SEA_THR} · CUTOFF={CUTOFF}]")
