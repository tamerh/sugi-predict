#!/usr/bin/env python3
"""PoC: is ESM-2 embedding space meaningful for PEPTIDES? (feasibility, before any build)
Tests, against the existing 574K-SwissProt `esm2` collection (cosine, 650M layer-33 mean-pool):
  (1) parent recovery  — cleaved peptide -> its own preprohormone in top-k?
  (2) family coherence — same-family peptides cluster vs unrelated?
  (3) NULL control     — residue-shuffled (same composition) collapses both?
Honest: ESM-2 is a sequence model -> NO ligand->receptor test (peptide ligand is not
homologous to its receptor). Short (<=10aa) peptides reported separately."""
import sys, random
sys.path.insert(0, "/data/sugi-atlas/src")
import numpy as np, torch, esm
from qdrant_client import QdrantClient

# (name, sequence, parent_uniprot, family)  -- bioactive/therapeutic peptides
PEPS = [
    ("GLP-1",        "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR",            "P01275", "incretin"),
    ("glucagon",     "HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",             "P01275", "incretin"),
    ("GIP",          "YAEGTFISDYSIAMDKIHQQDFVNWLLAQKGKKNDWKHNITQ","P09681", "incretin"),
    ("secretin",     "HSDGTFTSELSRLREGARLQRLLQGLV",               "P09683", "incretin"),
    ("VIP",          "HSDAVFTDNYTRLRKQMAVKKYLNSILN",              "P01282", "incretin"),
    ("oxytocin",     "CYIQNCPLG",                                 "P01178", "neurohypophysial"),
    ("vasopressin",  "CYFQNCPRG",                                 "P01185", "neurohypophysial"),
    ("somatostatin", "AGCKNFFWKTFTSC",                            "P61278", "somatostatin"),
    ("ANP",          "SLRRSSCFGGRMDRIGAQSGLGCNSFRY",              "P01160", "natriuretic"),
    ("BNP",          "SPKMVQGSGCFGRKMDRISSSSGLGCKVLRRH",          "P16860", "natriuretic"),
    ("CNP",          "GLSKGCFGLKLDRIGSMSGLGC",                    "P23582", "natriuretic"),
    ("substance-P",  "RPKPQQFFGLM",                               "P20366", "tachykinin"),
    ("neurokinin-A", "HKTDSFVGLM",                                "P20366", "tachykinin"),
    ("bradykinin",   "RPPGFSPFR",                                 "P01042", "kinin"),
    ("angiotensin-II","DRVYIHPF",                                 "P01019", "RAS"),
    ("NPY",          "YPSKPDNPGEDAPAEDMARYYSALRHYINLITRQRY",      "P01303", "NPY-fam"),
    ("PYY",          "YPIKPEAPGEDASPEELNRYYASLRHYLNLVTRQRY",      "P10082", "NPY-fam"),
    ("GnRH",         "QHWSYGLRPG",                                "P01148", "releasing-hormone"),
    ("beta-endorphin","YGGFMTSEKSQTPLVTLFKNAIIKNAYKKGE",          "P01189", "opioid"),
    ("galanin",      "GWTLNSAGYLLGPHAVGNHRSFSDKNGLTS",            "P22466", "galanin"),
]

print("loading ESM-2 650M…", flush=True)
model, alphabet = esm.pretrained.esm2_t33_650M_UR50D(); model.eval()
bc = alphabet.get_batch_converter()
def embed(seq):
    _,_,toks = bc([("x", seq)])
    with torch.no_grad():
        rep = model(toks, repr_layers=[33])["representations"][33][0]
    return rep[1:len(seq)+1].mean(0).numpy()          # mean-pool, skip BOS/EOS (build convention)

c = QdrantClient(url="http://localhost:6333", timeout=120)
def topk(vec, k=50):
    return [(p.payload["protein_id"], p.score)
            for p in c.query_points("esm2", query=vec.tolist(), limit=k).points]

def parent_rank(seq, parent, k=50):
    hits = topk(embed(seq), k)
    for i,(acc,_) in enumerate(hits):
        if acc == parent: return i+1, hits[0][0]
    return None, hits[0][0]

random.seed(42)
def shuffled(seq):
    l = list(seq); random.shuffle(l); return "".join(l)

# ---- 1) parent recovery (real + null) ----
print("\n=== 1) PARENT RECOVERY (peptide -> own preprohormone, top-50) ===")
print(f"{'peptide':14}{'len':>4} {'parent':8}{'rank':>6} {'top-hit':9}  | {'NULL rank':>9}")
real_ranks, null_ranks, short_hits = [], [], []
for name, seq, parent, fam in PEPS:
    r, top = parent_rank(seq, parent)
    rn, _  = parent_rank(shuffled(seq), parent)
    real_ranks.append(r); null_ranks.append(rn)
    if len(seq) <= 10: short_hits.append((name, r))
    print(f"{name:14}{len(seq):>4} {parent:8}{str(r or '>50'):>6} {top:9}  | {str(rn or '>50'):>9}")

def hitrate(ranks, t): return sum(1 for r in ranks if r and r<=t)/len(ranks)
print(f"\nREAL  hit@1={hitrate(real_ranks,1):.0%}  @5={hitrate(real_ranks,5):.0%}  @10={hitrate(real_ranks,10):.0%}  @50={hitrate(real_ranks,50):.0%}")
print(f"NULL  hit@1={hitrate(null_ranks,1):.0%}  @5={hitrate(null_ranks,5):.0%}  @10={hitrate(null_ranks,10):.0%}  @50={hitrate(null_ranks,50):.0%}")
print(f"≤10-mers parent-recovery@50: " + ", ".join(f"{n}={'✓' if r else '✗'}" for n,r in short_hits))

# ---- 2) family coherence (peptide-peptide), real + null ----
def coherence(seqs, fams):
    V = np.stack([embed(s) for s in seqs])
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    S = V @ V.T
    # nearest-other-peptide is a family-mate?  (only for peptides with >=1 family-mate)
    nn_fammate, withins, crosses = [], [], []
    for i in range(len(seqs)):
        mates = [j for j in range(len(seqs)) if j!=i and fams[j]==fams[i]]
        for j in range(len(seqs)):
            if j==i: continue
            (withins if fams[j]==fams[i] else crosses).append(S[i,j])
        if mates:
            order = sorted([j for j in range(len(seqs)) if j!=i], key=lambda j:-S[i,j])
            nn_fammate.append(fams[order[0]]==fams[i])
    return (sum(nn_fammate)/len(nn_fammate), np.mean(withins), np.mean(crosses))

seqs = [p[1] for p in PEPS]; fams = [p[3] for p in PEPS]
print("\n=== 2) FAMILY COHERENCE (peptide↔peptide) ===")
nn, wi, cr = coherence(seqs, fams)
print(f"REAL  nearest-peptide-is-family-mate = {nn:.0%}   (within-fam sim {wi:.3f}  vs cross-fam {cr:.3f})")
nn0, wi0, cr0 = coherence([shuffled(s) for s in seqs], fams)
print(f"NULL  nearest-peptide-is-family-mate = {nn0:.0%}   (within-fam sim {wi0:.3f}  vs cross-fam {cr0:.3f})")

print("\nVERDICT: peptide embedding is meaningful iff REAL >> NULL on both tests.")

# ---- 3) ANISOTROPY FIX: mean-centering (subtract collection centroid) ----
if __name__ == "__main__" and "--center" in sys.argv:
    print("\n=== 3) MEAN-CENTERED retest (unmask anisotropy) ===", flush=True)
    import itertools
    # estimate collection centroid from a sample
    pts,_ = c.scroll("esm2", limit=5000, with_vectors=True)
    C = np.mean(np.stack([np.array(p.vector) for p in pts]), axis=0)
    def coh_centered(seqs, fams):
        V = np.stack([embed(s) for s in seqs]) - C
        V = V/np.linalg.norm(V,axis=1,keepdims=True); S=V@V.T
        nn,wi,cr=[],[],[]
        for i in range(len(seqs)):
            mates=[j for j in range(len(seqs)) if j!=i and fams[j]==fams[i]]
            for j in range(len(seqs)):
                if j==i: continue
                (wi if fams[j]==fams[i] else cr).append(S[i,j])
            if mates:
                o=sorted([j for j in range(len(seqs)) if j!=i],key=lambda j:-S[i,j])
                nn.append(fams[o[0]]==fams[i])
        return sum(nn)/len(nn), np.mean(wi), np.mean(cr)
    nn,wi,cr = coh_centered(seqs,fams)
    nn0,wi0,cr0 = coh_centered([shuffled(s) for s in seqs], fams)
    print(f"REAL(centered)  nn-fammate={nn:.0%}  within {wi:.3f} vs cross {cr:.3f}  (gap {wi-cr:+.3f})")
    print(f"NULL(centered)  nn-fammate={nn0:.0%}  within {wi0:.3f} vs cross {cr0:.3f}  (gap {wi0-cr0:+.3f})")
    # centered parent proximity: is fragment closer to its OWN parent than to other parents?
    parents = list(dict.fromkeys(p[2] for p in PEPS))
    pv={}
    from qdrant_client.models import Filter,FieldCondition,MatchValue
    for acc in parents:
        r,_=c.scroll("esm2",scroll_filter=Filter(must=[FieldCondition(key="protein_id",match=MatchValue(value=acc))]),limit=1,with_vectors=True)
        if r: pv[acc]=np.array(r[0].vector)-C
    def pnorm(v): return v/np.linalg.norm(v)
    correct=0; tot=0
    for name,seq,par,fam in PEPS:
        if par not in pv: continue
        q=pnorm(embed(seq)-C)
        sims={a:float(q@pnorm(v)) for a,v in pv.items()}
        rank=sorted(sims,key=lambda a:-sims[a]).index(par)+1
        correct+= (rank==1); tot+=1
    print(f"REAL(centered)  fragment→own-parent is #1 among {len(pv)} parents: {correct}/{tot} = {correct/tot:.0%}")
