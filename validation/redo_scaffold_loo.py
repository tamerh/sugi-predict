#!/usr/bin/env python3
"""Scaffold-split + LOO validation, REDONE for the preprint review.

Fixes over poc_atlas_scaffold_validate.py:
 - GENERIC Bemis-Murcko framework (GetScaffoldForMol -> MakeScaffoldGeneric), not the exact
   atom-labelled MurckoScaffoldSmiles, so minor-variant / homologous same-series analogues are
   also withheld (the old exact-SMILES match leaked them).
 - Acyclic / no-scaffold queries are EXCLUDED from the scaffold split (a scaffold split is
   undefined for them; the old code silently withheld NOTHING for them -> near-LOO leakage).
   The excluded fraction is reported.
 - LOO and scaffold are evaluated on the SAME cyclic query set, so the LOO->scaffold drop is a
   fair within-query comparison (the old paper compared two different scripts/query sets).
 - Multiple seeds -> mean +/- sd (confidence intervals).
Deployed ranking (max-Tanimoto confidence, vote tie-break) on the uncapped reference,
predicting among all targets. Writes validation/results/scaffold_loo_redo.txt.
"""
import sys, os, json, random, collections, statistics
sys.path.insert(0, "/data/bioyoda")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/out_prod/work/chembl_reference"
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
N_QUERIES, KNN, THR, SEEDS = 2000, 20, 0.15, [42, 43, 44, 45, 46]
OUT = "/data/bioyoda/validation/results/scaffold_loo_redo.txt"

print("loading uncapped reference index + labels...", flush=True)
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
def gscaf(cid):
    """Generic Bemis-Murcko framework SMILES (ring systems+linkers, all atoms->C, bonds->single).
    '' for acyclic / unparseable molecules."""
    if cid in _scaf: return _scaf[cid]
    s = cid_smiles.get(cid); out = ""
    if s:
        try:
            m = Chem.MolFromSmiles(s)
            if m is not None:
                core = MurckoScaffold.GetScaffoldForMol(m)
                if core is not None and core.GetNumAtoms() > 0:
                    out = Chem.MolToSmiles(MurckoScaffold.MakeScaffoldGeneric(core))
        except Exception:
            out = ""
    _scaf[cid] = out
    return out

_escaf = {}
def escaf(cid):
    """Exact (standard) Bemis-Murcko scaffold SMILES (atom-labelled core rings + linkers).
    '' for acyclic / unparseable molecules."""
    if cid in _escaf: return _escaf[cid]
    s = cid_smiles.get(cid); out = ""
    if s:
        try: out = MurckoScaffold.MurckoScaffoldSmiles(s) or ""
        except Exception: out = ""
    _escaf[cid] = out
    return out

def predict(qcid, mode, qs):
    res = eng.similarity(cid_smiles[qcid], THR, n_workers=4)
    supp = {}; vote = {}; used = 0; top_tan = 0.0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if mid == qcid: continue
        if mode == "loo" and co >= 0.99: continue
        if mode == "scaffold" and gscaf(mid) == qs: continue   # qs is a non-empty generic scaffold
        if mode == "scaffold_exact" and escaf(mid) == qs: continue   # qs is the exact Bemis-Murcko scaffold
        if used == 0: top_tan = co
        for t in cid_targets.get(mid, ()):
            vote[t] = vote.get(t, 0.0) + co
            if co > supp.get(t, 0.0): supp[t] = co
        used += 1
        if used >= KNN: break
    return sorted(supp, key=lambda t: (-supp[t], -vote[t])), top_tan

S = {k: [] for k in ("loo_r1", "loo_r5", "loo_r10", "se_r1", "se_r5", "se_r10", "sc_r1", "sc_r5", "sc_r10", "ncyc", "nacyc", "pop1", "rnd1")}
strat = {m: collections.defaultdict(lambda: [0, 0]) for m in ("loo", "scaffold")}
seed_rows = []
for SEED in SEEDS:
    rng = random.Random(SEED)
    samp = [c for c in rng.sample(list(cid_targets), N_QUERIES * 3) if c in cid_smiles][:N_QUERIES]
    cyclic = [(c, gscaf(c)) for c in samp]; cyclic = [(c, q) for c, q in cyclic if q]
    nacyc = len(samp) - len(cyclic)
    l1 = l5 = l10 = e1 = e5 = e10 = s1 = s5 = s10 = p1 = rd1 = 0
    for q, qs in cyclic:
        truth = cid_targets[q]
        rL, ttL = predict(q, "loo", qs); rS, ttS = predict(q, "scaffold", qs); rE, _ = predict(q, "scaffold_exact", escaf(q))
        hL = bool(rL[:1]) and bool(truth & set(rL[:1])); hS = bool(rS[:1]) and bool(truth & set(rS[:1])); hE = bool(rE[:1]) and bool(truth & set(rE[:1]))
        l1 += hL; l5 += bool(truth & set(rL[:5])); l10 += bool(truth & set(rL[:10]))
        e1 += hE; e5 += bool(truth & set(rE[:5])); e10 += bool(truth & set(rE[:10]))
        s1 += hS; s5 += bool(truth & set(rS[:5])); s10 += bool(truth & set(rS[:10]))
        p1 += bool(truth & set(POP[:1])); rd1 += bool(truth & set(rng.sample(ALLT, 1)))
        for m, tt, h in (("loo", ttL, hL), ("scaffold", ttS, hS)):
            b = "≥0.7" if tt >= 0.7 else "0.5-0.7" if tt >= 0.5 else "0.3-0.5" if tt >= 0.3 else "<0.3"
            strat[m][b][0] += h; strat[m][b][1] += 1
    nq = len(cyclic)
    S["loo_r1"].append(l1/nq); S["loo_r5"].append(l5/nq); S["loo_r10"].append(l10/nq)
    S["se_r1"].append(e1/nq); S["se_r5"].append(e5/nq); S["se_r10"].append(e10/nq)
    S["sc_r1"].append(s1/nq); S["sc_r5"].append(s5/nq); S["sc_r10"].append(s10/nq)
    S["ncyc"].append(nq); S["nacyc"].append(nacyc); S["pop1"].append(p1/nq); S["rnd1"].append(rd1/nq)
    seed_rows.append(f"  seed {SEED}: {nq} cyclic (+{nacyc} acyclic dropped)  LOO@1 {l1/nq:.3f} @5 {l5/nq:.3f}  SCAF@1 {s1/nq:.3f} @5 {s5/nq:.3f}")
    print(seed_rows[-1], flush=True)

def ms(x): return (statistics.mean(x), statistics.stdev(x) if len(x) > 1 else 0.0)
out = list(seed_rows) + [""]
out.append(f"### SCAFFOLD-SPLIT REDO — {len(SEEDS)} seeds x {N_QUERIES} sampled queries, GENERIC Bemis-Murcko, among {len(deg):,} targets")
out.append(f"acyclic/no-scaffold queries excluded from the scaffold split: {statistics.mean(S['nacyc'])/N_QUERIES:.1%} per seed (mean)")
for lbl, a, b, c in (("LOO (self + Tanimoto>=0.99)", "loo_r1", "loo_r5", "loo_r10"), ("SCAFFOLD (Bemis-Murcko, standard)", "se_r1", "se_r5", "se_r10"), ("SCAFFOLD (generic framework)", "sc_r1", "sc_r5", "sc_r10")):
    m1, sd1 = ms(S[a]); m5, sd5 = ms(S[b]); m10, sd10 = ms(S[c])
    out.append(f"  {lbl:34} recall@1 {m1:.1%} +/- {sd1:.1%}   recall@5 {m5:.1%} +/- {sd5:.1%}   recall@10 {m10:.1%} +/- {sd10:.1%}")
out.append(f"  popularity recall@1 {ms(S['pop1'])[0]:.1%}    random recall@1 {ms(S['rnd1'])[0]:.1%}")
out.append(f"  LOO -> Bemis-Murcko scaffold drop: {(ms(S['loo_r1'])[0]-ms(S['se_r1'])[0])*100:.1f} points (recall@1, same queries)")
out.append("recall@1 by top-neighbour Tanimoto (pooled over seeds):")
for m in ("loo", "scaffold"):
    out.append(f"  {m}:")
    for b in ("≥0.7", "0.5-0.7", "0.3-0.5", "<0.3"):
        h, c = strat[m][b]
        if c: out.append(f"    {b:8} {h/c:.1%}  (n={c})")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(out) + "\n")
print("\n" + "\n".join(out[len(seed_rows)+1:]), flush=True)
print(f"\nwritten -> {OUT}", flush=True)
