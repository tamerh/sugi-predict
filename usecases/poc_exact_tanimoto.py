#!/usr/bin/env python3
"""PoC 1 (the simple/bounded one): how much does an EXACT-Tanimoto companion add over the current
binary-ANN compound search?  patents_compounds ranks by COSINE on 2048-bit Morgan FPs — not Tanimoto.
Two gaps, both decision-relevant for an FTO / 'what-is-claimed' product:
  (i)  METRIC mismatch  — cosine-ranked top-100 vs exact-Tanimoto top-100 on the SAME 150K universe.
  (ii) ANN RECALL       — does Qdrant ANN over the full 30.9M miss high-Tanimoto neighbors a 150K
       random sample (0.5%) already reveals? (extrapolate sample density ×N -> estimated true count).
Fully local (popcount in numpy on the stored 0/1 vectors)."""
import sys, time, numpy as np, urllib.request, urllib.parse, json
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from qdrant_client import QdrantClient

c=QdrantClient(url="http://localhost:6333",timeout=300)
TOTAL=30937359; SAMPLE=150000
def smiles(d):
    try:
        for r in json.load(urllib.request.urlopen("http://127.0.0.1:9291/ws/?"+urllib.parse.urlencode({"i":d}),timeout=30)).get("results",[]):
            for s,a in (r.get("Attributes") or {}).items():
                if isinstance(a,dict) and a.get("smiles"): return a["smiles"]
    except Exception: pass
def fp01(sm):
    m=Chem.MolFromSmiles(sm);
    if m is None: return None
    bv=AllChem.GetMorganFingerprintAsBitVect(m,2,nBits=2048); a=np.zeros(2048,dtype=np.uint8); DataStructs.ConvertToNumpyArray(bv,a); return a

print(f"scrolling {SAMPLE} sample vectors…",flush=True)
M=np.zeros((SAMPLE,2048),dtype=np.uint8); ids=[]; off=None; n=0; t=time.time()
while n<SAMPLE:
    pts,off=c.scroll("patents_compounds",limit=10000,offset=off,with_vectors=True,with_payload=["surechembl_id"])
    for p in pts:
        if n>=SAMPLE: break
        M[n]=(np.asarray(p.vector)>0).astype(np.uint8); ids.append(p.payload.get("surechembl_id")); n+=1  # stored vecs are L2-normalized -> binarize
    if off is None: break
M=M[:n]; Mpop=M.sum(1).astype(np.int32)
print(f"  {n} vectors in {time.time()-t:.0f}s ; mean bits set {Mpop.mean():.1f}",flush=True)
FACTOR=TOTAL/n

def analyze(name, q):
    qp=int(q.sum()); inter=(M@q).astype(np.int32)
    tani=inter/np.maximum(Mpop+qp-inter,1); cos=inter/np.sqrt(np.maximum(Mpop*qp,1))
    tt=set(np.argsort(-tani)[:100]); ct=set(np.argsort(-cos)[:100])
    rec=len(tt&ct)/100
    # sample claimed-density -> extrapolated full-collection estimate
    est={th:int((tani>=th).sum()*FACTOR) for th in (0.7,0.5,0.4,0.3)}
    # real Qdrant ANN over FULL collection, exact-Tanimoto rerank
    ANNLIM=1000
    ann=c.query_points("patents_compounds",query=q.astype(np.float32).tolist(),limit=ANNLIM,with_payload=["smiles"]).points
    at=[]
    for h in ann:
        s=h.payload.get("smiles"); a=fp01(s) if s else None
        if a is None: continue
        ai=int(a@q); at.append(ai/max(int(a.sum())+qp-ai,1))
    at=np.array(at)
    ann_cnt={th:int((at>=th).sum()) for th in (0.7,0.5,0.4,0.3)}
    print(f"\n### {name}  (|fp|={qp} bits)")
    print(f"  metric mismatch: exact-Tanimoto top-100 recovered by cosine top-100 = {rec:.0%}  (cosine ≠ Tanimoto ranking)")
    print(f"  {'thr':>5} {'ANN-returned≥thr':>17} {'est. true in 30.9M':>20} {'ANN recall(est)':>16}")
    for th in (0.7,0.5,0.4,0.3):
        e=est[th]; a=ann_cnt[th]; r=(a/e) if e else float('nan')
        print(f"  {th:>5} {a:>17} {e:>20} {('%.0f%%'%(100*r)) if e else 'n/a':>16}")

for d in ["osimertinib","imatinib","cyclosporine"]:
    sm=smiles(d); q=fp01(sm) if sm else None
    if q is not None: analyze(d,q)
# a random patent compound as a 4th query
analyze("random patent cmpd", M[12345])

print("\nVERDICT: an exact-Tanimoto companion is worth it if (i) cosine top-100 misses much of exact top-100,")
print("AND/OR (ii) ANN recall vs estimated true count is well below 100% at the FTO-relevant thresholds (≥0.4).")
# production engine availability
try:
    import FPSim2; print("\nFPSim2 importable -> production exact-Tanimoto engine available.")
except Exception:
    print("\nFPSim2 not installed (pip install FPSim2) — chemfp/FPSim2 = the production exact/threshold engine.")
