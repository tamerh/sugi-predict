#!/usr/bin/env python3
"""Parameterized multi-modal grounded DOSSIER for ANY drug. Stress-test of the cross-modal join.
  drug -> SMILES + primary target (biobtree mechanism) -> ESM-2 family (esm2) ->
          Tanimoto analogs (patents_compounds) -> literature (pubmed) -> trials (CT) -> grounding.
Robust: gracefully skips any step whose inputs are missing (no SMILES / no mechanism target /
target not in esm2 / empty hits) and SAYS so — so we can see exactly where the pipeline is thin."""
import sys, time
sys.path.insert(0, "/data/bioyoda")
import numpy as np, torch
from transformers import AutoTokenizer, AutoModel
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from scripts.integrations import biobtree_client as bb

c = QdrantClient(url="http://localhost:6333", timeout=120)
print("loading MedCPT…", flush=True)
qtok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder"); qm = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()
def medcpt(t):
    with torch.no_grad():
        e = qtok([t], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(qm(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()

def gene_of(acc):
    try:
        for r in bb.rows(bb.search(acc, source="uniprot"))[:1]: return r.get("name", "")
    except Exception: pass
    return ""
def esm2_vec(acc):
    pts,_ = c.scroll("esm2", scroll_filter=Filter(must=[FieldCondition(key="protein_id", match=MatchValue(value=acc))]), limit=1, with_vectors=True)
    return pts[0].vector if pts else None
import urllib.request, urllib.parse, json
def get_smiles(drug):
    """SMILES + compound CURIE from biobtree search Attributes (PubChem/ChEMBL/ChEBI)."""
    try:
        url="http://127.0.0.1:9291/ws/?"+urllib.parse.urlencode({"i":drug})
        for res in json.load(urllib.request.urlopen(url,timeout=30)).get("results",[]):
            for src,a in (res.get("Attributes") or {}).items():
                if isinstance(a,dict) and a.get("smiles"):
                    cid=a.get("cid"); curie=(f"PubChem:{cid}" if cid else (f"{src}:{res.get('identifier')}"))
                    return a["smiles"], curie
    except Exception: pass
    return None, None

def dossier(drug, smiles=None, k_lit=3, k_tr=3):
    print(f"\n{'#'*74}\n# DOSSIER: {drug}\n{'#'*74}")
    t0=time.time()
    # 1) primary target: mechanism (principled) -> activity-ordered -> plain binding (fallbacks)
    prim = bb.map_targets(bb.bmap(drug, ">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot"))
    act  = bb.map_targets(bb.bmap(drug, ">>chembl_molecule>>chembl_activity>>chembl_target>>uniprot"))
    allt = bb.map_targets(bb.bmap(drug, ">>chembl_molecule>>chembl_target>>uniprot"))
    sm_curie=None
    if not smiles: smiles, sm_curie = get_smiles(drug)
    # pick the first target (by source priority) that's actually in esm2 (join-able)
    tgt=None; src=None
    for pool,label in [(prim,"mechanism✓"),(act,"activity~"),(allt,"binding?")]:
        for cand in pool:
            if esm2_vec(cand) is not None: tgt, src = cand, label; break
        if tgt: break
    gene = gene_of(tgt) if tgt else ""
    print(f"  compound grounding: {sm_curie or '?'}  | SMILES: {'yes' if smiles else 'NO'}")
    print(f"  target [{src or '-'}]: {tgt} ({gene or '?'})  | mech={bool(prim)} binding={len(allt)}")

    # 2) target -> ESM-2 family (deduped)
    fam=[]
    if tgt:
        v=esm2_vec(tgt)
        if v is not None:
            seen=set()
            for h in c.query_points("esm2", query=v, limit=40, with_payload=["protein_id"]).points:
                a=h.payload.get("protein_id")
                if a==tgt: continue
                g=gene_of(a) or "?"; key=g.split()[0] if g!="?" else a
                if key in seen: continue
                seen.add(key); fam.append((a,h.score,g))
                if len(fam)>=5: break
            print("  ESM-2 family: " + ", ".join(f"{g.split()[0] if g!='?' else a}({s:.2f})" for a,s,g in fam))
        else: print("  ESM-2 family: (target not in 574K SwissProt esm2 set)")
    else: print("  ESM-2 family: (no target)")

    # 3) compound -> Tanimoto analogs
    if smiles:
        m=Chem.MolFromSmiles(smiles)
        if m:
            bv=AllChem.GetMorganFingerprintAsBitVect(m,2,nBits=2048)
            arr=np.zeros((2048,),dtype=np.float32); DataStructs.ConvertToNumpyArray(bv,arr)
            cand=c.query_points("patents_compounds",query=arr.tolist(),limit=80,with_payload=["surechembl_id","smiles"]).points
            rr=[]
            for h in cand:
                s=h.payload.get("smiles"); mm=Chem.MolFromSmiles(s) if s else None
                if mm is None: continue
                t=DataStructs.TanimotoSimilarity(bv,AllChem.GetMorganFingerprintAsBitVect(mm,2,nBits=2048))
                if t<0.999: rr.append((h.payload.get("surechembl_id"),t))   # drop the drug itself
            rr.sort(key=lambda x:-x[1])
            print("  analogs (distinct): " + ", ".join(f"{sid}({t:.2f})" for sid,t in rr[:4]) if rr else "  analogs: (none distinct)")
        else: print("  analogs: (RDKit could not parse SMILES)")
    else: print("  analogs: (no SMILES)")

    # 4) literature + 5) trials (auto-query from drug + gene)
    gq = (gene.split()[0] if gene else "")
    lit=c.query_points("pubmed_abstracts_medcpt", query=medcpt(f"{drug} {gene} mechanism resistance treatment"), limit=k_lit).points
    print("  literature:")
    for h in lit: print(f"      {h.score:.3f} pmid={h.payload.get('pmid')}: {(h.payload.get('chunk_text') or '')[:78]}")
    seen=set(); tr=[]
    for h in c.query_points("clinical_trials_medcpt", query=medcpt(f"{drug} {gene}"), limit=20).points:
        n=h.payload.get("nct_id")
        if n in seen: continue
        seen.add(n); tr.append(h)
        if len(tr)>=k_tr: break
    print("  trials:")
    cond=None
    for h in tr:
        if cond is None:
            cc=h.payload.get("conditions"); cond = (cc[0] if isinstance(cc,list) and cc else cc)
        print(f"      {h.score:.3f} {h.payload.get('nct_id')}: {str(h.payload.get('brief_title'))[:62]}")
    if cond:
        dg,_=bb.ground(str(cond), source="mondo")
        print(f"  indication (from trials): {str(cond)[:40]} -> {dg}")
    print(f"  [built in {time.time()-t0:.1f}s]")

if __name__ == "__main__":
    drugs = sys.argv[1:] or ["osimertinib","imatinib","gefitinib","vemurafenib","aspirin"]
    for d in drugs: dossier(d)
