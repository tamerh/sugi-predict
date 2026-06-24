#!/usr/bin/env python3
"""SPOT-VALIDATION: "predicted target atlas of patent chemical space".

Question under test:
  patents_compounds (30.9M SureChEMBL Morgan r2/2048, NO target labels) can be turned into a
  *predicted target atlas* by chemical k-NN to a labeled ChEMBL ligand->target reference. Does that
  prediction actually recover the TRUE mechanism target of a PATENT compound — checked only where an
  independent ground truth exists?

Design (honest, held-out):
  REFERENCE  : the prior 16-target / 480-ligand ChEMBL set (Morgan r2/2048 FPs, UniProt label/ligand).
               (reused as-is from poc_ligand_target.py + work/ligand_smiles_cache.json; see caveats.)
  QUERY      : marketed / well-characterized drugs that (a) have an INDEPENDENT mechanism-of-action
               target from biobtree ChEMBL (>>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot),
               and (b) are CONFIRMED present in the owned patent corpus by a near-exact (Tanimoto>=0.99)
               SureChEMBL hit in patents_compounds Qdrant.
  PREDICT    : transfer the target(s) of the nearest REFERENCE ligand(s) by Tanimoto, EXCLUDING the query
               itself and any exact/near-exact twin in the reference (Tanimoto>=0.99 held out) so we never
               score memorization of the molecule we are predicting.
  SCORE      : recall@1 / recall@5 of the TRUE mechanism target vs POPULARITY (most-ligand-rich reference
               targets) and RANDOM (guess into a ~500-target universe). recall@1 stratified by top-neighbor
               Tanimoto to show the signal is graded, not just exact-twin recall.

Read-only. Run:  /data/miniconda3/envs/bioyoda/bin/python usecases/poc_patent_target_atlas.py 2>&1 | grep -v -iE "warn|deprecat"
"""
import sys, os, json, time, random, urllib.request, collections
sys.path.insert(0, "/data/sugi-atlas/src")
import atlas.biobtree as B
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
import numpy as np
from qdrant_client import QdrantClient

KG    = "/data/biobtree_kg/out/kg/qual_chembl.tsv"
CACHE = "/data/bioyoda/work/ligand_smiles_cache.json"
SEED  = 42; rng = random.Random(SEED)
N_PER_TARGET = 30
NEAR_EXACT   = 0.99       # Tanimoto threshold for "this molecule IS present" / "this is a held-out twin"
Ks = (1, 5)

qc = QdrantClient(url="http://localhost:6333", timeout=180)

# ---- the 16 reference targets (same as the prior ligand->target probe) ----
TARGETS = {
 "P00519":"ABL1 kinase","P00533":"EGFR kinase","P36888":"FLT3 kinase","Q05655":"PKC-delta",
 "P08172":"M2 musc. GPCR","P34972":"CB2 GPCR","P28223":"5-HT2A GPCR","P14416":"D2 dopamine GPCR",
 "P10275":"Androgen recep.","P03372":"Estrogen recep.","P37231":"PPAR-gamma",
 "P00734":"Thrombin protease","P00742":"Factor Xa","P08246":"Neutrophil elastase",
 "P35372":"mu-opioid GPCR","P28335":"5-HT2C GPCR",
}
REF_SET = set(TARGETS)

# ---- candidate QUERY drugs (marketed / well-characterized; mechanism target resolved live) ----
QUERY_DRUGS = [
 "imatinib","gefitinib","erlotinib","osimertinib","dasatinib","nilotinib","sunitinib","sorafenib",
 "lapatinib","vemurafenib","crizotinib","ruxolitinib","ibrutinib","afatinib","bosutinib","ponatinib",
 "bicalutamide","enzalutamide","apalutamide","tamoxifen","raloxifene","fulvestrant","toremifene",
 "rosiglitazone","pioglitazone","apixaban","rivaroxaban","edoxaban","betrixaban","dabigatran",
 "argatroban","melagatran","fentanyl","sufentanil","alfentanil","haloperidol","risperidone",
 "clozapine","olanzapine","aripiprazole","quetiapine","ziprasidone","paliperidone","rimonabant",
 "naloxone","morphine","buprenorphine","loperamide",
]

# ============================ SMILES resolution (cached) ============================
_cache = {}
if os.path.exists(CACHE):
    try: _cache = json.load(open(CACHE))
    except Exception: _cache = {}

def _smiles_from_results(d):
    for r in d.get("results", []):
        for _, v in (r.get("Attributes") or {}).items():
            if isinstance(v, dict) and v.get("smiles"): return v["smiles"]
    return None

def name_smiles(name):
    key = "NAME:" + name
    if key in _cache: return _cache[key]
    s = None
    try:
        d = json.load(urllib.request.urlopen(
            "http://127.0.0.1:9291/ws/?i=" + urllib.request.quote(name), timeout=25))
        s = _smiles_from_results(d)
    except Exception: pass
    _cache[key] = s
    return s

def cid_smiles(cid):
    try:
        d = json.load(urllib.request.urlopen("http://127.0.0.1:9291/ws/?i=" + cid, timeout=25))
        return _smiles_from_results(d)
    except Exception: return None

def chembl_smiles(chembl):
    if chembl in _cache: return _cache[chembl]
    s = None
    try:
        rows = B.map_all(chembl, ">>chembl_molecule>>pubchem", cap=1)
        if rows: s = cid_smiles(rows[0]["id"])
    except Exception: pass
    _cache[chembl] = s
    return s

def fp(smiles):
    m = Chem.MolFromSmiles(smiles) if smiles else None
    if not m: return None, None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    arr = np.zeros((2048,), dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, arr)
    return arr, bv

# ============================ REFERENCE library (16 targets) ============================
print("building REFERENCE ligand->target library (16 targets, ChEMBL)…", flush=True)
want = {f"UniProtKB:{u}" for u in TARGETS}
tgt2cmpd = collections.defaultdict(set)
with open(KG) as f:
    next(f)
    for line in f:
        p = line.split("\t")
        if len(p) < 4: continue
        subj, obj = p[1], p[3]
        if obj in want and subj.startswith("CHEMBL.COMPOUND:"):
            tgt2cmpd[obj[len("UniProtKB:"):]].add(subj.split(":")[1])

records = []   # (chembl, uniprot, bv)
for u, cmpds in tgt2cmpd.items():
    pool = sorted(cmpds); rng.shuffle(pool); got = 0
    for c in pool:
        if got >= N_PER_TARGET: break
        s = chembl_smiles(c)
        if not s: continue
        _, bv = fp(s)
        if bv is None: continue
        records.append((c, u, bv)); got += 1
json.dump(_cache, open(CACHE, "w"))

cmpd_targets = collections.defaultdict(set)
cmpd_bv = {}
for c, u, bv in records:
    cmpd_targets[c].add(u); cmpd_bv.setdefault(c, bv)
ref = [(c, cmpd_bv[c], cmpd_targets[c]) for c in cmpd_bv]   # reference items
print(f"  reference = {len(ref)} unique ligands across {len(TARGETS)} targets")

# ---- decoy universe (~500 real human ChEMBL targets) for honest RANDOM/POPULARITY baselines ----
ucount = collections.Counter()
with open(KG) as f:
    next(f)
    for line in f:
        p = line.split("\t")
        if len(p) < 4: continue
        if p[3].startswith("UniProtKB:") and p[1].startswith("CHEMBL.COMPOUND:"):
            ucount[p[3][len("UniProtKB:"):]] += 1
universe = [u for u, _ in ucount.most_common(500)]
for u in TARGETS:
    if u not in universe: universe.append(u)
popular = [u for u, _ in sorted(ucount.items(), key=lambda x: -x[1]) if u in set(universe)]
print(f"  decoy universe = {len(universe)} targets; base rate ~= {1/len(universe):.2%}")

# ============================ QUERY set: mechanism target + patent presence ============================
print("\nbuilding QUERY set (mechanism target + CONFIRMED in patents_compounds)…", flush=True)
queries = []   # (name, true_targets(set), bv, top_patent_tanimoto, schembl_id)
for name in QUERY_DRUGS:
    mech = B.map_all(name, ">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot", cap=30)
    true_t = {r["id"] for r in mech if r.get("id")}
    if not true_t:
        print(f"  {name:14} skip: no mechanism target"); continue
    sm = name_smiles(name)
    arr, bv = fp(sm)
    if bv is None:
        print(f"  {name:14} skip: no SMILES"); continue
    # confirm presence in owned patent corpus via near-exact SureChEMBL hit
    hits = qc.query_points("patents_compounds", query=arr.tolist(), limit=5,
                           with_payload=["surechembl_id", "smiles"]).points
    best_tan, best_id = 0.0, None
    for h in hits:
        hsm = h.payload.get("smiles")
        hm = Chem.MolFromSmiles(hsm) if hsm else None
        if not hm: continue
        t = DataStructs.TanimotoSimilarity(bv, AllChem.GetMorganFingerprintAsBitVect(hm, 2, nBits=2048))
        if t > best_tan: best_tan, best_id = t, h.payload.get("surechembl_id")
    in_patent = best_tan >= NEAR_EXACT
    inref = ",".join(sorted(true_t & REF_SET)) or "-"
    print(f"  {name:14} mech={len(true_t):>2}t (in-ref:{inref:18}) patent_tan={best_tan:.3f} "
          f"{'PRESENT '+str(best_id) if in_patent else 'absent'}")
    if in_patent:
        queries.append((name, true_t, bv, best_tan, best_id))
json.dump(_cache, open(CACHE, "w"))

confirmed = len(queries)
# evaluable = at least one mechanism target lies inside the reference space (else k-NN cannot possibly hit)
evaluable = [q for q in queries if q[1] & REF_SET]
print(f"\nconfirmed-in-patent-space: {confirmed}/{len(QUERY_DRUGS)} drugs")
print(f"of those, evaluable (>=1 mechanism target inside the 16-target reference): {len(evaluable)}")

# ============================ PREDICT + SCORE ============================
print("\n### PATENT-COMPOUND -> TARGET prediction (k-NN to reference, held-out)")
def predict_knn(qbv, kmax):
    sims = sorted(((DataStructs.TanimotoSimilarity(qbv, rbv), idx)
                   for idx, (_, rbv, _) in enumerate(ref)), reverse=True)
    # drop exact/near-exact twins so we never score memorization of the query molecule
    sims = [(s, idx) for s, idx in sims if s < NEAR_EXACT]
    top_tan = sims[0][0] if sims else 0.0
    pred = []
    for _, idx in sims:
        for t in ref[idx][2]:
            if t not in pred: pred.append(t)
        if len(pred) >= kmax: break
    return pred, top_tan

hits = {("knn", k): 0 for k in Ks}
hits.update({("pop", k): 0 for k in Ks}); hits.update({("rnd", k): 0 for k in Ks})
strat = collections.defaultdict(lambda: [0, 0])   # band -> [hit, total] for recall@1
rows_out = []
for name, true_t, qbv, ptan, sid in evaluable:
    pred, top_tan = predict_knn(qbv, max(Ks))
    rnd = rng.sample(universe, max(Ks))
    r1 = 1 if (true_t & set(pred[:1])) else 0
    for k in Ks:
        hits[("knn", k)] += 1 if (true_t & set(pred[:k])) else 0
        hits[("pop", k)] += 1 if (true_t & set(popular[:k])) else 0
        hits[("rnd", k)] += 1 if (true_t & set(rnd[:k])) else 0
    band = ("[0.9,1.0)" if top_tan >= 0.9 else "[0.7,0.9)" if top_tan >= 0.7 else
            "[0.5,0.7)" if top_tan >= 0.5 else "[0.3,0.5)" if top_tan >= 0.3 else "[0.0,0.3)")
    strat[band][0] += r1; strat[band][1] += 1
    rows_out.append((name, top_tan, r1, pred[0] if pred else "-", sorted(true_t & REF_SET)))

n = len(evaluable)
print(f"\nevaluable queries = {n}   universe = {len(universe)} targets")
print(f"\n{'recall@k':10} {'k-NN (chem)':>14} {'POPULARITY':>12} {'RANDOM':>10}")
for k in Ks:
    print(f"  @{k:<7} {hits[('knn',k)]/n:>13.1%} {hits[('pop',k)]/n:>12.1%} {hits[('rnd',k)]/n:>10.1%}")

print(f"\nrecall@1 stratified by top-neighbor Tanimoto (graded signal check):")
for band in ["[0.9,1.0)", "[0.7,0.9)", "[0.5,0.7)", "[0.3,0.5)", "[0.0,0.3)"]:
    h, t = strat[band]
    if t: print(f"  top-tan {band}:  recall@1 = {h/t:5.1%}   (n={t})")

print(f"\nper-query (held-out twins excluded):")
for name, top_tan, r1, p0, tref in sorted(rows_out, key=lambda x: -x[1]):
    print(f"  {name:14} top-tan={top_tan:.3f}  pred={p0}  true(in-ref)={tref}  hit@1={'Y' if r1 else 'n'}")

print(f"""
VERDICT inputs:
  confirmed-in-patent-space : {confirmed}/{len(QUERY_DRUGS)}
  evaluable (target in ref) : {n}
  recall@1 k-NN={hits[('knn',1)]/n:.1%}  pop={hits[('pop',1)]/n:.1%}  rnd={hits[('rnd',1)]/n:.1%}
  recall@5 k-NN={hits[('knn',5)]/n:.1%}  pop={hits[('pop',5)]/n:.1%}  rnd={hits[('rnd',5)]/n:.1%}
""")
