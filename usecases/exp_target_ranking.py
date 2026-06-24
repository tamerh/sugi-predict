#!/usr/bin/env python3
"""Experiment: (1) pivot the cross-modal join on the PRIMARY target EGFR (P00533) — does ESM-2
return EGFR-family kinases? (2) can biobtree give us the principled primary target (mechanism)?"""
import sys; sys.path.insert(0,"/data/bioyoda")
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from scripts.integrations import biobtree_client as bb
c=QdrantClient(url="http://localhost:6333",timeout=120)

def gene_of(acc):
    try:
        for r in bb.rows(bb.search(acc, source="uniprot"))[:1]: return r.get("name","")
    except Exception: pass
    return ""
def esm2_vec(acc):
    pts,_=c.scroll("esm2",scroll_filter=Filter(must=[FieldCondition(key="protein_id",match=MatchValue(value=acc))]),limit=1,with_vectors=True)
    return pts[0].vector if pts else None

print("="*72,"\nEXP 1: pivot on EGFR (P00533) directly -> ESM-2 neighbors (dedup by gene)\n","="*72)
v=esm2_vec("P00533")
if v is None:
    print("  EGFR P00533 NOT in esm2 set")
else:
    hits=c.query_points("esm2",query=v,limit=40,with_payload=["protein_id"]).points
    seen=set(); shown=0
    for h in hits:
        a=h.payload.get("protein_id")
        if a=="P00533": continue
        g=gene_of(a) or "?"
        key=g.split()[0] if g!="?" else a
        if key in seen: continue          # dedup orthologs/near-dups by gene name
        seen.add(key)
        print(f"   {a}  sim={h.score:.3f}  {g[:55]}")
        shown+=1
        if shown>=10: break

print("\n"+"="*72,"\nEXP 2: biobtree -> PRIMARY/mechanism target for osimertinib\n","="*72)
for chain in [">>chembl_molecule>>chembl_mechanism",
              ">>chembl_molecule>>chembl_mechanism>>uniprot",
              ">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot"]:
    try:
        mp=bb.bmap("osimertinib", chain)
        tg=bb.map_targets(mp)
        rows=bb.rows(mp)
        print(f"  chain {chain!r}: targets={tg[:6]}  rows={len(rows)}")
    except Exception as e:
        print(f"  chain {chain!r}: ERROR {e}")

print("\n"+"="*72,"\nEXP 2b: what genes are the 41 plain chembl_target hits? (EGFR rank?)\n","="*72)
mp=bb.bmap("osimertinib", ">>chembl_molecule>>chembl_target>>uniprot")
tg=bb.map_targets(mp)
for i,acc in enumerate(tg[:15]):
    g=gene_of(acc) or "?"
    mark=" <== EGFR (primary)" if acc=="P00533" else ""
    print(f"   {i+1:2d}. {acc}  {g[:50]}{mark}")
