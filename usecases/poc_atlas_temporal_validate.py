#!/usr/bin/env python3
"""The DEPLOYMENT-REALISTIC validation: how well does chemical k-NN target prediction generalize OVER TIME?

The scaffold split (poc_atlas_scaffold_validate.py) answers "novel chemotype" generalization within a single
ChEMBL snapshot. The temporal split is the most deployment-realistic test for the patent use case: train the
reference on compounds first disclosed in year <= CUTOFF, then predict targets for compounds first disclosed
LATER (year > CUTOFF) using ONLY the pre-cutoff reference. This proxies "predict targets for genuinely NEW
chemistry the model has never seen", exactly what a patent-CI pipeline faces.

Year source (offline, real): ChEMBL 37 SQLite dump. For each reference PubChem CID we computed the InChIKey
(rdkit), matched it to ChEMBL compound_structures.standard_inchi_key, and took the EARLIEST document year
(MIN over docs.year across all activities of that molecule) — i.e. first-disclosure year. Built once into
work/chembl_reference/_cid_year.json (see build_cid_year.py provenance). No fabricated years.

Split discipline (no leakage):
  * reference (train) = all reference ligands with year <= CUTOFF.
  * queries (test)    = ligands with year > CUTOFF, sampled.
  * For each query we exclude (a) the query itself and (b) every post-cutoff ligand from the neighbour pool,
    so a query can ONLY be answered by genuinely older chemistry. Uses the DEPLOYED ranking (max-Tanimoto
    confidence, vote tie-break), predicting among all targets, vs popularity/random baselines, stratified by
    top-neighbour Tanimoto.
"""
import sys, json, random, collections
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine

REF = "/data/bioyoda/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
CUTOFF = 2018            # train: year <= 2018; test: year >= 2019 (first-disclosure)
N_QUERIES, KNN, SEED, THR = 2000, 20, 42, 0.15

print("loading uncapped reference index + labels + years…", flush=True)
eng = FPSim2Engine(H5, in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_year = {int(k): int(v) for k, v in json.load(open(f"{REF}/_cid_year.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    cid, sm = line.rstrip("\n").split("\t", 1)
    if cid.isdigit():
        cid_smiles[int(cid)] = sm

# only molecules that have BOTH a structure (for fp/smiles) and a year participate in the temporal split
dated = {c for c in cid_smiles if c in cid_year and c in cid_targets}
PRE = {c for c in dated if cid_year[c] <= CUTOFF}     # eligible neighbours (train)
POST = {c for c in dated if cid_year[c] > CUTOFF}     # eligible queries (test)
print(f"  {len(cid_smiles):,} molecules total, {len(cid_year):,} with a year ({len(cid_year)/len(cid_smiles):.0%})", flush=True)
print(f"  cutoff {CUTOFF}: train(<=) {len(PRE):,}  |  test(>) {len(POST):,}", flush=True)

# popularity / random baselines computed on the TRAIN reference only (what a deployed system would know)
deg = collections.Counter(t for c in PRE for t in cid_targets[c])
POP = [t for t, _ in deg.most_common()]
ALLT = list(deg)


def predict(qcid):
    """DEPLOYED ranking, neighbour pool restricted to pre-cutoff ligands (and never the query itself)."""
    res = eng.similarity(cid_smiles[qcid], THR, n_workers=4)
    supp = {}; vote = {}; used = 0; top_tan = 0.0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid:
            continue
        if mid not in PRE:           # leakage guard: only older chemistry may answer
            continue
        if used == 0:
            top_tan = co
        for t in cid_targets.get(mid, ()):
            vote[t] = vote.get(t, 0.0) + co
            if co > supp.get(t, 0.0):
                supp[t] = co
        used += 1
        if used >= KNN:
            break
    ranked = sorted(supp, key=lambda t: (-supp[t], -vote[t]))      # deployed ranking
    return ranked, top_tan


rng = random.Random(SEED)
pool = list(POST)
rng.shuffle(pool)
queries = pool[:N_QUERIES]

r1 = r5 = 0
pop1 = pop5 = rnd1 = rnd5 = 0
strat = collections.defaultdict(lambda: [0, 0])
n = 0
for q in queries:
    truth = cid_targets[q]
    ranked, tt = predict(q)
    h1 = bool(ranked[:1]) and bool(truth & set(ranked[:1]))
    r1 += h1
    r5 += bool(truth & set(ranked[:5]))
    band = "≥0.7" if tt >= 0.7 else "0.5-0.7" if tt >= 0.5 else "0.3-0.5" if tt >= 0.3 else "<0.3"
    strat[band][0] += h1
    strat[band][1] += 1
    pop1 += bool(truth & set(POP[:1])); pop5 += bool(truth & set(POP[:5]))
    rsel = rng.sample(ALLT, 5); rnd1 += bool(truth & set(rsel[:1])); rnd5 += bool(truth & set(rsel))
    n += 1

print(f"\n### TEMPORAL VALIDATION — train year<= {CUTOFF}, test year> {CUTOFF}")
print(f"### {n} post-cutoff queries, deployed ranking, neighbours restricted to pre-cutoff reference\n")
print(f"{'condition':34}{'recall@1':>10}{'recall@5':>10}")
print(f"{'TEMPORAL split (year>'+str(CUTOFF)+')':34}{r1/n:>9.1%}{r5/n:>10.1%}   <- generalization-over-time")
print(f"{'popularity baseline (pre-cutoff)':34}{pop1/n:>9.1%}{pop5/n:>10.1%}")
print(f"{'random baseline':34}{rnd1/n:>9.1%}{rnd5/n:>10.1%}")
print("\nrecall@1 by top-neighbour Tanimoto (to nearest pre-cutoff ligand):")
for b in ("≥0.7", "0.5-0.7", "0.3-0.5", "<0.3"):
    h, c = strat[b]
    if c:
        print(f"  {b:8} {h/c:>6.1%}  (n={c})")
