#!/usr/bin/env python3
"""Spot-check on real molecules: a diverse panel of approved drugs (all present in the patent corpus) with
externally-established targets. Each is predicted with ITS OWN Bemis-Murcko scaffold held out of the reference
(no self/series leakage), and we check whether the known target's GENE is recovered in the top-1/top-5. Reports
by target class to test breadth (not just kinases). The most deployment-realistic, human-readable validation."""
import sys, json, collections
sys.path.insert(0, "/data/bioyoda"); sys.path.insert(0, "/data/bioyoda/modules/compounds")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
import fto

REF = "/data/bioyoda/work/chembl_reference"
eng = FPSim2Engine(f"{REF}/chembl_reference_morgan_r2_2048.h5", in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    c, s = line.rstrip("\n").split("\t", 1)
    if c.isdigit(): cid_smiles[int(c)] = s
GENES = json.load(open(f"{REF}/target_genes.json"))
def gene(acc): return GENES.get(acc, {}).get("gene", acc)
ref_genes = {gene(t) for ts in cid_targets.values() for t in ts}   # genes that exist in the reference at all

# (drug, {known target GENE symbol(s)}, class)
PANEL = [
    ("gefitinib", {"EGFR"}, "kinase"), ("erlotinib", {"EGFR"}, "kinase"),
    ("imatinib", {"ABL1", "KIT", "PDGFRB"}, "kinase"), ("nilotinib", {"ABL1"}, "kinase"),
    ("vemurafenib", {"BRAF"}, "kinase"), ("dabrafenib", {"BRAF"}, "kinase"),
    ("crizotinib", {"ALK", "MET"}, "kinase"), ("ibrutinib", {"BTK"}, "kinase"),
    ("palbociclib", {"CDK4", "CDK6"}, "kinase"), ("lapatinib", {"EGFR", "ERBB2"}, "kinase"),
    ("propranolol", {"ADRB1", "ADRB2"}, "GPCR"), ("atenolol", {"ADRB1"}, "GPCR"),
    ("losartan", {"AGTR1"}, "GPCR"), ("candesartan", {"AGTR1"}, "GPCR"),
    ("fexofenadine", {"HRH1"}, "GPCR"), ("loratadine", {"HRH1"}, "GPCR"),
    ("montelukast", {"CYSLTR1"}, "GPCR"), ("ondansetron", {"HTR3A"}, "ion channel"),
    ("sumatriptan", {"HTR1B", "HTR1D"}, "GPCR"),
    ("captopril", {"ACE"}, "protease/enzyme"), ("enalapril", {"ACE"}, "protease/enzyme"),
    ("lisinopril", {"ACE"}, "protease/enzyme"), ("sitagliptin", {"DPP4"}, "protease/enzyme"),
    ("saxagliptin", {"DPP4"}, "protease/enzyme"),
    ("tamoxifen", {"ESR1"}, "nuclear receptor"), ("raloxifene", {"ESR1"}, "nuclear receptor"),
    ("dexamethasone", {"NR3C1"}, "nuclear receptor"), ("spironolactone", {"NR3C2"}, "nuclear receptor"),
    ("finasteride", {"SRD5A2"}, "enzyme"),
    ("sildenafil", {"PDE5A"}, "enzyme"), ("tadalafil", {"PDE5A"}, "enzyme"),
    ("atorvastatin", {"HMGCR"}, "enzyme"), ("simvastatin", {"HMGCR"}, "enzyme"),
    ("celecoxib", {"PTGS2"}, "enzyme"), ("methotrexate", {"DHFR"}, "enzyme"),
    ("allopurinol", {"XDH"}, "enzyme"), ("acetazolamide", {"CA2"}, "enzyme"),
    ("amlodipine", {"CACNA1C"}, "ion channel"), ("nifedipine", {"CACNA1C"}, "ion channel"),
]

_scaf = {}
def scaffold(cid):
    if cid in _scaf: return _scaf[cid]
    s = cid_smiles.get(cid)
    try: sc = MurckoScaffold.MurckoScaffoldSmiles(s) if s else ""
    except Exception: sc = ""
    _scaf[cid] = sc; return sc

def predict_scaffold_out(smiles, qscaf, k=20):
    res = eng.similarity(smiles, 0.15, n_workers=4)
    supp = {}; vote = {}; used = 0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if qscaf and scaffold(mid) == qscaf: continue          # hold out the query's whole scaffold
        for t in cid_targets.get(mid, ()):
            vote[t] = vote.get(t, 0.0) + co
            if co > supp.get(t, 0.0): supp[t] = co
        used += 1
        if used >= k: break
    return sorted(supp, key=lambda t: (-supp[t], -vote[t]))

print(f"reference: {len(cid_smiles):,} ligands, {len(set().union(*cid_targets.values())):,} targets\n")
print(f"{'drug':15}{'class':17}{'known':14}{'in ref?':8}{'@1':4}{'@5':4} top-5 predicted genes")
rows = []
for name, known, cls in PANEL:
    sm, _ = fto.resolve(name)
    if not sm:
        print(f"{name:15}{cls:17}{'/'.join(sorted(known)):14}{'?':8} (could not resolve)"); continue
    m = Chem.MolFromSmiles(sm); qscaf = MurckoScaffold.MurckoScaffoldSmiles(sm) if m else ""
    ranked = predict_scaffold_out(sm, qscaf)
    pgenes = []
    for t in ranked:
        g = gene(t)
        if g not in pgenes: pgenes.append(g)
    inref = bool(known & ref_genes)
    h1 = bool(known & set(pgenes[:1])); h5 = bool(known & set(pgenes[:5]))
    rows.append((cls, inref, h1, h5))
    print(f"{name:15}{cls:17}{'/'.join(sorted(known)):14}{('yes' if inref else 'NO'):8}{('Y' if h1 else '.'):4}{('Y' if h5 else '.'):4}{', '.join(pgenes[:5])}")

ev = [r for r in rows if r[1]]    # only drugs whose target IS in the reference (can be recovered)
n = len(ev)
print(f"\n=== summary (drugs whose target is in the reference: {n}/{len(rows)}) ===")
print(f"  top-1 (gene): {sum(r[2] for r in ev)}/{n} = {sum(r[2] for r in ev)/n:.0%}")
print(f"  top-5 (gene): {sum(r[3] for r in ev)}/{n} = {sum(r[3] for r in ev)/n:.0%}")
print("  by class:")
for cls in sorted(set(r[0] for r in ev)):
    c = [r for r in ev if r[0] == cls]
    print(f"    {cls:17} top-1 {sum(r[2] for r in c)}/{len(c)} · top-5 {sum(r[3] for r in c)}/{len(c)}")
