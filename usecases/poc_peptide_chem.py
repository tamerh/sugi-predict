#!/usr/bin/env python3
"""Test (a): does the EXISTING patents_compounds (30.9M Morgan/ECFP4, binary) contain a meaningful
CHEMICAL neighborhood for peptide DRUGS?  i.e. is the surviving peptide path — route modified/therapeutic
peptides through the compound modality — actually supported by the data we own?
Two-stage (binary-ANN top-k -> exact Tanimoto rerank), the production recipe. Small-molecule drugs
included as calibration (what a DENSE patent neighborhood looks like)."""
import sys, json, urllib.request, urllib.parse
sys.path.insert(0,"/data/bioyoda")
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs, Descriptors
from qdrant_client import QdrantClient
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

# name -> kind. peptide drugs (incl cyclic/modified) + small-molecule calibrators
DRUGS=[("osimertinib","small-mol"),("imatinib","small-mol"),
       ("cyclosporine","cyclic-peptide"),("octreotide","cyclic-peptide"),("lanreotide","cyclic-peptide"),
       ("desmopressin","peptide"),("oxytocin","peptide"),("vasopressin","peptide"),("leuprolide","peptide"),
       ("bacitracin","peptide-abx"),("polymyxin B","peptide-abx"),("vancomycin","glycopeptide"),
       ("semaglutide","glp1-large"),("liraglutide","glp1-large")]

def smiles(drug):
    try:
        url="http://127.0.0.1:9291/ws/?"+urllib.parse.urlencode({"i":drug})
        for res in json.load(urllib.request.urlopen(url,timeout=30)).get("results",[]):
            for src,a in (res.get("Attributes") or {}).items():
                if isinstance(a,dict) and a.get("smiles"): return a["smiles"]
    except Exception: pass
    return None

def fp(m): return AllChem.GetMorganFingerprintAsBitVect(m,2,nBits=2048)
c=QdrantClient(url="http://localhost:6333",timeout=120)

mols={}  # name -> (mol, bv, mw)
print(f"{'drug':14}{'kind':16}{'MW':>7}{'best':>7}{'>=.7':>6}{'>=.5':>6}{'>=.4':>6}  top-SureChEMBL")
rows=[]
for name,kind in DRUGS:
    sm=smiles(name); m=Chem.MolFromSmiles(sm) if sm else None
    if m is None:
        print(f"{name:14}{kind:16}{'—':>7}{'  no SMILES / unparseable (chemically not representable)'}"); rows.append((name,kind,None)); continue
    bv=fp(m); mw=Descriptors.MolWt(m)
    arr=np.zeros((2048,),dtype=np.float32); DataStructs.ConvertToNumpyArray(bv,arr)
    ts=[]; top=[]
    for h in c.query_points("patents_compounds",query=arr.tolist(),limit=200,with_payload=["surechembl_id","smiles"]).points:
        s2=h.payload.get("smiles"); mm=Chem.MolFromSmiles(s2) if s2 else None
        if mm is None: continue
        t=DataStructs.TanimotoSimilarity(bv,fp(mm))
        if t<0.999: ts.append(t); top.append((h.payload.get("surechembl_id"),t))
    ts=np.array(ts); top.sort(key=lambda x:-x[1])
    best=ts.max() if len(ts) else 0
    n7=int((ts>=.7).sum()); n5=int((ts>=.5).sum()); n4=int((ts>=.4).sum())
    print(f"{name:14}{kind:16}{mw:>7.0f}{best:>7.2f}{n7:>6}{n5:>6}{n4:>6}  {', '.join(f'{i}:{t:.2f}' for i,t in top[:2])}")
    rows.append((name,kind,(bv,mw,best,n4)))

# peptide<->peptide chemical clustering (is there a coherent peptide region?)
print("\n=== peptide↔peptide Morgan-Tanimoto (own panel) ===")
pep=[(n,r[0]) for n,k,r in rows if r and k!='small-mol']
for i,(ni,bvi) in enumerate(pep):
    sims=sorted([(nj,DataStructs.TanimotoSimilarity(bvi,bvj)) for j,(nj,bvj) in enumerate(pep) if j!=i],key=lambda x:-x[1])[:3]
    print(f"  {ni:14} nearest: "+", ".join(f"{n}={t:.2f}" for n,t in sims))

print("\nVERDICT: chemical-peptide path viable iff patent neighborhoods are non-trivial (cf. small-mol calibrators)")
print("AND/OR peptide drugs form a coherent chemical region. Sparse everywhere => patent_compounds lacks peptide chemistry.")
