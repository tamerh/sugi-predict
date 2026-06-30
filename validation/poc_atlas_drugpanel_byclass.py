#!/usr/bin/env python3
"""Per-target-CLASS breakdown of the LARGE (1,556-drug) approved-drug recovery panel.

Reuses the SAME cached panel (results/drugpanel_large_panel.json) and the SAME
generic-Bemis-Murcko-scaffold FPSim2 prediction (k=20, Tanimoto>=0.15, max-Tanimoto
rank, vote tie-break) as poc_atlas_drugpanel_large.py, then scores recall@1/@5 PER CLASS.

Class source: ChEMBL protein classification (results/gene_class.json, built by
_drugpanel_target_classes.py from chembl_targets.jsonl). The unit of a per-class
score is a (drug, mechanism-gene) pair whose gene is in the reference: the class is
that gene's class, and a hit = that specific gene appears in the drug's top-1/top-5
predicted genes. A drug spanning several classes contributes to each. The OVERALL
row is the standard drug-level recall (a drug hits if ANY of its mechanism genes is
recovered) -- identical to the headline large-panel number.
"""
import sys, os, json, math, collections
sys.path.insert(0, "/data/bioyoda"); sys.path.insert(0, "/data/bioyoda/modules/compounds")
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

REF = "/data/bioyoda/out_prod/work/chembl_reference"
RES = "/data/bioyoda/validation/results"
OUT = f"{RES}/drugpanel_large_byclass.txt"
K, THR = 20, 0.15

print("loading reference...", flush=True)
eng = FPSim2Engine(f"{REF}/chembl_reference_morgan_r2_2048.h5", in_memory_fps=True)
cid_targets = {int(k): set(v) for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
cid_smiles = {}
for line in open(f"{REF}/reference.tsv"):
    c, s = line.rstrip("\n").split("\t", 1)
    if c.isdigit(): cid_smiles[int(c)] = s
GENES = json.load(open(f"{REF}/target_genes.json"))
def gene(acc): return GENES.get(acc, {}).get("gene", acc)
ref_genes = {gene(t) for ts in cid_targets.values() for t in ts}
gene_class = json.load(open(f"{RES}/gene_class.json"))
def cls_of(g): return gene_class.get(g, "Other/unclassified")

_gen = {}
def gen_scaffold_smiles(s):
    out = ""
    if s:
        try:
            m = Chem.MolFromSmiles(s)
            if m is not None:
                core = MurckoScaffold.GetScaffoldForMol(m)
                if core is not None and core.GetNumAtoms() > 0:
                    out = Chem.MolToSmiles(MurckoScaffold.MakeScaffoldGeneric(core))
        except Exception: out = ""
    return out
def gen_scaffold_cid(cid):
    if cid in _gen: return _gen[cid]
    out = gen_scaffold_smiles(cid_smiles.get(cid)); _gen[cid] = out; return out

def predict(smiles, qscaf):
    res = eng.similarity(smiles, THR, n_workers=4)
    supp = {}; vote = {}; used = 0
    for mid, co in res:
        mid = int(mid); co = float(co)
        if qscaf and gen_scaffold_cid(mid) == qscaf: continue
        for t in cid_targets.get(mid, ()):
            vote[t] = vote.get(t, 0.0) + co
            if co > supp.get(t, 0.0): supp[t] = co
        used += 1
        if used >= K: break
    return sorted(supp, key=lambda t: (-supp[t], -vote[t]))

def ranked_genes(ranked):
    pg = []
    for t in ranked:
        g = gene(t)
        if g not in pg: pg.append(g)
    return pg

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z*z/n
    c = p + z*z/(2*n); m = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return ((c-m)/d, (c+m)/d)

panel = json.load(open(f"{RES}/drugpanel_large_panel.json"))
eval_rows = [(d, set(v["genes"]), v["smiles"]) for d, v in panel.items()
             if v.get("smiles") and v.get("genes") and (set(v["genes"]) & ref_genes)]
n = len(eval_rows)
print(f"large panel: {n} drugs (SMILES + mechanism gene in reference)", flush=True)

# class buckets: per (drug, recoverable mechanism-gene) pair
# Two per-class views (the protein-COMPLEX targets in ChEMBL drug_mechanism, e.g. the
# GABA-A receptor, expand to ~19 subunit genes -> one drug = ~19 ion-channel gene-pairs the
# subunit-blind FP model can't resolve, inflating sparse-class denominators. So we report BOTH):
#   (A) gene-pair view : unit = (drug, recoverable mechanism-gene); raw, subunit-explosion-prone
#   (B) drug-class view : unit = (drug, class); a drug counts ONCE per class of its mechanism
#                         genes, hit = ANY gene of that class recovered. The honest headline.
cls1 = collections.defaultdict(lambda: [0, 0]); cls5 = collections.defaultdict(lambda: [0, 0])   # (A)
cls10 = collections.defaultdict(lambda: [0, 0])
dc1 = collections.defaultdict(lambda: [0, 0]);  dc5 = collections.defaultdict(lambda: [0, 0])    # (B)
dc10 = collections.defaultdict(lambda: [0, 0])
o1 = o5 = o10 = 0
for i, (d, known, sm) in enumerate(eval_rows):
    qs = gen_scaffold_smiles(sm)
    pg = ranked_genes(predict(sm, qs))
    top1, top5, top10 = set(pg[:1]), set(pg[:5]), set(pg[:10])
    o1 += bool(known & top1); o5 += bool(known & top5); o10 += bool(known & top10)
    rec = {g for g in known if g in ref_genes}
    by_cls = collections.defaultdict(set)
    for g in rec:
        c = cls_of(g)
        by_cls[c].add(g)
        cls1[c][0] += g in top1; cls1[c][1] += 1     # (A) gene-pair
        cls5[c][0] += g in top5; cls5[c][1] += 1
        cls10[c][0] += g in top10; cls10[c][1] += 1
    for c, gs in by_cls.items():                       # (B) drug-class
        dc1[c][0] += bool(gs & top1); dc1[c][1] += 1
        dc5[c][0] += bool(gs & top5); dc5[c][1] += 1
        dc10[c][0] += bool(gs & top10); dc10[c][1] += 1
    if (i+1) % 300 == 0: print(f"  {i+1}/{n}", flush=True)

out = []
def emit(s=""):
    print(s, flush=True); out.append(s)

emit("### LARGE APPROVED-DRUG PANEL — per-target-CLASS recall")
emit(f"reference: {len(cid_smiles):,} ligands, {len(ref_genes):,} genes")
emit(f"panel: {n} drugs (SMILES + >=1 mechanism gene in reference)")
emit("prediction: FPSim2 k-NN (k=20, Tanimoto>=0.15), GENERIC Bemis-Murcko scaffold held out (same as headline run)")
emit("class source: ChEMBL protein classification (chembl_targets.jsonl protein_classes hierarchy);")
emit(f"  {len(gene_class)} human genes classed (Kinase/Protease/Other-enzyme split out of /Enzyme,")
emit("  GPCR split out of /Membrane receptor, Nuclear receptor split out of /Transcription factor).")
emit("")
lo1, hi1 = wilson(o1, n); lo5, hi5 = wilson(o5, n); lo10, hi10 = wilson(o10, n)
emit(f"OVERALL (drug-level: any mechanism gene recovered), n={n}")
emit(f"  recall@1  {o1}/{n} = {o1/n:.1%}  95% CI [{lo1:.1%},{hi1:.1%}]")
emit(f"  recall@5  {o5}/{n} = {o5/n:.1%}  95% CI [{lo5:.1%},{hi5:.1%}]")
emit(f"  recall@10 {o10}/{n} = {o10/n:.1%}  95% CI [{lo10:.1%},{hi10:.1%}]")
emit("")

def table(d1, d5, d10, unit_label, total_label):
    emit(f"{'class':28}{'n':>6}{'recall@1':>17}{'recall@5':>17}{'recall@10':>17}   (unit: {unit_label})")
    emit("-" * 102)
    for c in sorted(d1, key=lambda c: -d1[c][1]):
        h1, nn = d1[c]; h5, _ = d5[c]; h10, _ = d10[c]
        l1, hh1 = wilson(h1, nn); l5, hh5 = wilson(h5, nn); l10, hh10 = wilson(h10, nn)
        emit(f"{c:28}{nn:>6}  {h1/nn:>5.1%} [{l1:.0%},{hh1:.0%}]  {h5/nn:>5.1%} [{l5:.0%},{hh5:.0%}]  {h10/nn:>5.1%} [{l10:.0%},{hh10:.0%}]")
    emit("-" * 102)
    emit(f"{total_label:28}{sum(v[1] for v in d1.values()):>6}")
    emit("")

emit("(B) DRUG-CLASS view [HEADLINE] — a drug counts ONCE per class; hit = ANY gene of that class recovered")
table(dc1, dc5, dc10, "(drug, class) pairs", "(all drug-class pairs)")
emit("(A) GENE-PAIR view [raw] — one row per (drug, mechanism-gene); protein-complex targets (e.g. GABA-A,")
emit("    nicotinic AChR) explode to many subunit genes the FP model can't resolve -> depresses sparse classes")
table(cls1, cls5, cls10, "(drug, gene) pairs", "(all gene-pairs)")
os.makedirs(RES, exist_ok=True)
open(OUT, "w").write("\n".join(out) + "\n")
emit("")
emit(f"written -> {OUT}")
