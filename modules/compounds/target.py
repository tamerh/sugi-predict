#!/usr/bin/env python3
"""Ligand→target prediction — the validated patent target-atlas engine.

For a molecule (SMILES | SCHEMBL<id> | drug-name), predict its likely protein target(s) by chemical k-NN to
the 1,248,456-molecule ChEMBL ligand→target reference (biobtree-assembled, FPSim2-indexed), ranked top-5 with a
Tanimoto CONFIDENCE per target, grounded to gene via biobtree. The honest output: ranked candidates + confidence,
NOT a single hard label; <0.3 Tanimoto = novel chemotype / chemical whitespace.

Validation — lead with the deployment-relevant number: TEMPORAL recall@1 ~41% (train on past, predict future
targets — the regime the atlas actually runs in). The leave-one-out (~83%) and scaffold-split (~77%) splits are
INTERPOLATION upper bounds, not the deployment figure (usecases/poc_atlas_fullscale_validate.py). Coverage: ~1/3
of patent compounds high-confidence (poc_atlas_coverage.py).

CLI: python target.py "<query>" [--top 5]
"""
import sys, os, json, collections, argparse
ROOT = os.environ.get("BIOYODA_ROOT", "/data/bioyoda")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                     # for `import fto`
sys.path.insert(0, os.environ.get("SUGI_ATLAS_SRC", "/data/sugi-atlas/src"))
sys.path.insert(0, ROOT)
from FPSim2 import FPSim2Engine
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
import atlas.biobtree as B
import fto                                                                          # query resolver
from modules.paths import CHEMBL_REF

REF = str(CHEMBL_REF)
H5 = f"{REF}/chembl_reference_morgan_r2_2048.h5"
KNN, MIN_TAN = 20, 0.30
_eng = _ct = None
def engine():
    global _eng, _ct
    if _eng is None:
        if not os.path.exists(H5):
            sys.exit(f"reference index missing: {H5}\nbuild it:  python {ROOT}/modules/compounds/build_chembl_reference.py")
        _eng = FPSim2Engine(H5, in_memory_fps=True)
        _ct = {int(k): v for k, v in json.load(open(f"{REF}/cid_targets.json")).items()}
    return _eng, _ct
_name = {}
def gene(acc):
    if acc in _name: return _name[acc]
    nm = acc
    try:
        rs = B.rows(B.search(acc, source="uniprot"))
        if rs: nm = rs[0].get("name", acc) or acc
    except Exception: pass
    _name[acc] = nm; return nm
def band(t): return "HIGH" if t >= 0.5 else "MODERATE" if t >= 0.4 else "LOW" if t >= 0.3 else "NOVEL"

# per-target gene/name/organism metadata (biobtree-assembled, ChEMBL→UniProt). Used to label predictions by
# GENE SYMBOL and to default the displayed ranking to HUMAN targets (drops non-human orthologs / bacterial noise).
_genes = None
def genes():
    global _genes
    if _genes is None:
        p = f"{REF}/target_genes.json"
        _genes = json.load(open(p)) if os.path.exists(p) else {}
    return _genes
def is_human(acc):
    """True if the target is a Homo sapiens entry (per target_genes.json org). Unknown orgs count as human-keep
    so we never silently drop a target we simply lack metadata for."""
    g = genes().get(acc)
    return (g is None) or ("Homo sapiens" in (g.get("org") or ""))
def gene_sym(acc):
    """Short gene symbol for display (primary label); falls back to the accession."""
    g = genes().get(acc)
    return (g.get("gene") if g else None) or acc
def full_name(acc):
    """Full protein name (secondary label / tooltip)."""
    g = genes().get(acc)
    return (g.get("name") if g else None) or gene(acc)

def predict(smiles, n_workers=4, human_only=False, with_support=False):
    """→ ([(uniprot, confidence_tanimoto), ...] FULL ranked list, best_tanimoto). Confidence = best Tanimoto to
    a known ligand of that target. Keeps exact matches (a real query may itself be a known compound).
    n_workers: FPSim2 search threads — use 1 inside a multiprocess build (parallelism is across processes).
    human_only: restrict the displayed ranking to Homo sapiens targets (drops non-human orthologs / bacterial noise).
    with_support: also return supp = {uniprot: neighbour_count} — how many of the top-KNN nearest ligands back the
    target. This is the DISCRIMINATOR that separates tied 1.00-confidence targets (e.g. EGFR 18/20 vs noise 1/20)."""
    eng, ct = engine()
    res = eng.similarity(smiles, MIN_TAN, n_workers=n_workers)                      # (cid, tanimoto) desc
    vote, supp = collections.defaultdict(float), collections.defaultdict(float)
    nbr = collections.defaultdict(int)                                             # neighbour support count
    for i, (cid, co) in enumerate(res):
        if i >= KNN: break
        co = float(co)
        for t in ct.get(int(cid), ()):
            vote[t] += co; supp[t] = max(supp[t], co); nbr[t] += 1
    # rank by CONFIDENCE (best Tanimoto to a known ligand of the target), then by NEIGHBOUR SUPPORT (how many of
    # the top-KNN back it — the discriminator for tied exact-match confidences), then vote-support.
    # validated slightly better than vote-ranking under the interpolation (LOO) split AND gives a monotonic
    # confidence column. (Deployment regime is temporal recall@1 ~41%; the LOO numbers are an upper bound.)
    targets = supp
    if human_only:
        targets = {t: c for t, c in supp.items() if is_human(t)}
    ranked = sorted(targets, key=lambda t: (-targets[t], -nbr[t], -vote[t]))
    out = [(t, supp[t]) for t in ranked]
    best = (float(res[0][1]) if len(res) else 0.0)
    if with_support:
        return out, best, dict(nbr)
    return out, best

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("query"); ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    sm, label = fto.resolve(a.query)
    if not sm: sys.exit(f"could not resolve query: {a.query!r}")
    preds, best, supp = predict(sm, human_only=True, with_support=True)
    known = best >= 0.999
    tag = "  [KNOWN — the molecule is itself in ChEMBL]" if known else ""
    print(f"query: {label}   (best Tanimoto to a known ligand: {best:.2f}){tag}")
    if best < MIN_TAN or not preds:
        print("  → NOVEL chemotype — no close known ligand → no confident target (chemical whitespace).")
    else:
        shown = preds[:a.top]
        print(f"  predicted (human) targets — showing top {len(shown)} of {len(preds)} (--top N for the full profile;")
        print("  ranked by chemical k-NN over 1.25M ChEMBL ligands, grounded):")
        for i, (t, s) in enumerate(shown, 1):
            print(f"    {i:>2}. {gene_sym(t):10} conf {s:.2f} · {supp.get(t,0):>2}/{KNN} nbrs  {band(s):8} {t}  {full_name(t)[:38]}")
        print("  confidence = best Tanimoto to a known ligand of that target (<0.3 = novel/low).")
        print(f"  support = how many of the top-{KNN} nearest known ligands back that target (the discriminator).")
