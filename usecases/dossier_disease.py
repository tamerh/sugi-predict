#!/usr/bin/env python3
"""DISEASE-FIRST cross-modal dossier — proves the substrate answers from the CLINICAL side.
  disease -> CAREFUL grounding (MONDO node + parent + children) -> grounded trials (vector +
  disease_curie filter = predict x ground) -> literature -> PROPER disease GENE COHORT
  (biobtree gencc + civic via sugi-atlas client) -> human UniProt (>>hgnc>>uniprot) ->
  ESM-2 protein family. Uses the mature sugi-atlas biobtree client for correct multi-attr parsing."""
import sys, time, collections
sys.path.insert(0, "/data/sugi-atlas/src")   # mature biobtree client (proper row parsing)
sys.path.insert(0, "/data/bioyoda")
import torch
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import atlas.biobtree as B
from scripts.integrations import biobtree_client as bb   # for ground()

c = QdrantClient(url="http://localhost:6333", timeout=120)
print("loading MedCPT…", flush=True)
qtok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder"); qm = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()
def medcpt(t):
    with torch.no_grad():
        e = qtok([t], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(qm(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()
def esm2_vec(acc):
    p,_=c.scroll("esm2",scroll_filter=Filter(must=[FieldCondition(key="protein_id",match=MatchValue(value=acc))]),limit=1,with_vectors=True)
    return p[0].vector if p else None
def gene_sym(acc):  # uniprot acc -> short protein/gene name
    try:
        for r in B.rows(B.search(acc, source="uniprot"))[:1]:
            return (r.get("name") or "").split()[0]
    except Exception: pass
    return acc

def mondo_id(name):
    for r in B.rows(B.search(name, source="mondo")):
        if str(r.get("id","")).startswith("MONDO"): return r["id"]
def hgnc_uniprot(gene):
    try:
        for acc in [r.get("id") for r in B.map_all(gene, ">>hgnc>>uniprot", cap=10) if r.get("id")]:
            if esm2_vec(acc) is not None: return acc            # prefer the human one in esm2
    except Exception: pass
    return None
def gene_cohort(mid, top=8):
    genes=[]
    for r in B.map_all(mid, ">>mondo>>gencc", cap=30):           # curated Mendelian
        g=r.get("gene_symbol")
        if g and g not in genes: genes.append(g)
    civ=collections.Counter()
    for r in B.map_all(mid, ">>mondo>>civic_evidence", cap=300): # somatic/cancer drivers
        mp=(r.get("molecular_profile") or "").split()
        if mp and mp[0][:1].isalpha() and mp[0].upper()==mp[0] and mp[0].replace("-","").isalnum():
            civ[mp[0]]+=1
    for g,_ in civ.most_common(top):
        if g not in genes: genes.append(g)
    return genes[:top]

def dossier_disease(term):
    print(f"\n{'#'*74}\n# DISEASE DOSSIER: {term}\n{'#'*74}")
    t0=time.time()
    # 1) careful grounding: node + tree
    curie,_ = bb.ground(term, "mondo"); mid=curie or mondo_id(term)
    kids = [r.get("name") for r in B.map_all(term, ">>mondo>>mondochild", cap=20) if r.get("name")]
    par  = [r.get("name") for r in B.map_all(term, ">>mondo>>mondoparent", cap=10) if r.get("name")]
    print(f"  GROUNDED: {mid}  | parent: {par[:2]}  | children: {kids[:4]}")

    # 2) grounded trials (vector + disease_curie filter = predict x ground)
    qv=medcpt(f"{term} targeted therapy treatment")
    flt=Filter(must=[FieldCondition(key="disease_curie", match=MatchValue(value=mid))]) if mid else None
    g=c.query_points("clinical_trials_medcpt", query=qv, query_filter=flt, limit=20).points if flt else []
    seen=[]
    for h in g:
        if h.payload.get("nct_id") not in [s.payload.get('nct_id') for s in seen]: seen.append(h)
    print(f"  GROUNDED TRIALS (vector + disease_curie={mid}): {len(g)} hits")
    for h in seen[:3]: print(f"      {h.score:.3f} {h.payload.get('nct_id')}: {str(h.payload.get('brief_title'))[:56]}")

    # 3) literature
    print("  LITERATURE:")
    for h in c.query_points("pubmed_abstracts_medcpt", query=medcpt(f"{term} driver oncogene targeted therapy"), limit=2).points:
        print(f"      {h.score:.3f} pmid={h.payload.get('pmid')}: {(h.payload.get('chunk_text') or '')[:72]}")

    # 4) PROPER disease gene cohort -> UniProt -> ESM-2 family   (the upgrade)
    genes=gene_cohort(mid)
    print(f"  DISEASE GENE COHORT (gencc+civic): {genes}")
    print("  -> human UniProt -> ESM-2 structural family:")
    shown=0
    for gname in genes:
        u=hgnc_uniprot(gname)
        if not u: continue
        hits=c.query_points("esm2", query=esm2_vec(u), limit=8, with_payload=["protein_id"]).points
        fam=[]; sg=set()
        for h in hits:
            a=h.payload.get("protein_id")
            if a==u: continue
            s=gene_sym(a)
            if s in sg: continue
            sg.add(s); fam.append(s)
            if len(fam)>=3: break
        print(f"      {gname:7s} ({u}) -> {fam}")
        shown+=1
        if shown>=5: break
    print(f"  [built in {time.time()-t0:.1f}s]")

if __name__ == "__main__":
    for d in (sys.argv[1:] or ["non-small cell lung carcinoma","melanoma"]): dossier_disease(d)
