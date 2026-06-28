#!/usr/bin/env python3
"""Local target-scoring for the patent atlas — turns raw k-NN neighbours into ranked targets.

This is the CHEAP, ITERABLE step (the GPU only produces raw neighbours). Several scorings are implemented so we
can compare them on the panel's named failure cases (aspirin -> demethylase, gefitinib's flat-1.00 saturation)
and pick the one that ranks the pharmacologically right target highest.

scorings(nbrs, ct, tsize, N) -> {name: [(target, score), ... ranked desc]}
  nbrs  = [(neighbour_cid, tanimoto), ...]  (top-K, desc)
  ct    = {cid: [uniprot, ...]}             (reference ligand -> targets)
  tsize = {uniprot: n_ligands}              (target promiscuity / set size)
  N     = total reference ligands

  maxtan      : rank by max-Tanimoto (the current method), tie-break by summed-sim   [baseline]
  agreement   : rank by #neighbours supporting the target, then max-Tanimoto         [discriminates ties]
  enrichment  : SEA-like — observed summed-sim minus expected-by-prevalence (down-weights promiscuous targets)

CLI (compare on known drugs):  python score_atlas.py
"""
import math, collections

def _agg(nbrs, ct, thr=0.30):
    supp = collections.defaultdict(float); vote = collections.defaultdict(float); cnt = collections.Counter()
    tot = 0.0
    for cid, s in nbrs:
        if s < thr: continue
        tot += s
        for t in ct.get(int(cid), ()):
            vote[t] += s; cnt[t] += 1
            if s > supp[t]: supp[t] = s
    return supp, vote, cnt, tot

def scorings(nbrs, ct, tsize, N):
    supp, vote, cnt, tot = _agg(nbrs, ct)
    out = {}
    out["maxtan"]    = sorted(supp, key=lambda t: (-supp[t], -vote[t]))
    out["agreement"] = sorted(supp, key=lambda t: (-cnt[t], -supp[t], -vote[t]))
    # enrichment: how much more does this target appear than a random target of its size would?
    enrich = {t: vote[t] - tot * (tsize.get(t, 1) / N) for t in vote}
    out["enrichment"] = sorted(enrich, key=lambda t: -enrich[t])
    return out, supp, vote, cnt, enrich

# ----------------- comparison harness on known drugs -----------------
if __name__ == "__main__":
    import sys, os, json
    sys.path.insert(0, "/data/bioyoda/modules/compounds"); sys.path.insert(0, "/data/bioyoda")
    from modules.paths import TARGET_GENES_JSON
    from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
    import target, fto
    eng, ct = target.engine()
    N = len(ct)
    tsize = collections.Counter()
    for ts in ct.values():
        for t in ts: tsize[t] += 1
    G = json.load(open(TARGET_GENES_JSON))
    gene = lambda a: G.get(a, {}).get("gene", a)

    # (drug, set of acceptable "right" targets by UniProt)
    DRUGS = [
        ("aspirin",    {"P23219", "P35354"}),                 # COX-1 / COX-2
        ("gefitinib",  {"P00533"}),                           # EGFR
        ("imatinib",   {"P00519", "P10721", "P16234"}),       # ABL1 / KIT / PDGFRa
        ("celecoxib",  {"P35354"}),                           # COX-2
        ("sildenafil", {"O76074"}),                           # PDE5
        ("atorvastatin", {"P04035"}),                         # HMGCR
        ("diphenhydramine", {"P35367"}),                      # HRH1
    ]
    def rank_of(ranked, right):
        for i, t in enumerate(ranked, 1):
            if t in right: return i
        return None
    print(f"reference: {N:,} ligands, {len(tsize):,} targets\n")
    methods = ["maxtan", "agreement", "enrichment"]
    summary = {m: [] for m in methods}
    for drug, right in DRUGS:
        sm, _ = fto.resolve(drug)
        nbrs = [(int(cid), float(s)) for cid, s in eng.similarity(sm, 0.0, n_workers=1)[:20]]
        out, supp, vote, cnt, enrich = scorings(nbrs, ct, tsize, N)
        print(f"=== {drug}  (right target: {sorted(right)}) ===")
        for m in methods:
            ranked = out[m]; r = rank_of(ranked, right)
            summary[m].append(r)
            top5 = ", ".join(f"{gene(t)}" for t in ranked[:5])
            mark = f"#{r}" if r else "MISS"
            print(f"  {m:11} right@{mark:5}  top5: {top5}")
        print()
    print("=== summary (rank of the correct target; lower=better, X=missed) ===")
    for m in methods:
        ranks = summary[m]
        top1 = sum(1 for r in ranks if r == 1); top5 = sum(1 for r in ranks if r and r <= 5)
        print(f"  {m:11}: top1 {top1}/{len(ranks)} · top5 {top5}/{len(ranks)} · ranks {[r or 'X' for r in ranks]}")
