#!/usr/bin/env python3
"""CONTAINED USE-CASE: osimertinib -> full multi-modal, grounded dossier.
Exercises the WHOLE pipeline end-to-end across all 5 collections + biobtree grounding:
  compound id/ground -> target (biobtree) -> ESM-2 similar proteins (esm2, grounded)
  -> Tanimoto-similar compounds (patents_compounds) -> literature (pubmed_medcpt)
  -> trials (clinical_trials_medcpt, disease-grounded).
The point: a single grounded inference no single-modality tool can make. We then ANALYSE it."""
import sys, time
sys.path.insert(0, "/data/bioyoda")
import numpy as np, torch
from transformers import AutoTokenizer, AutoModel
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from scripts.integrations import biobtree_client as bb

OSI_SMILES = "C=CC(=O)Nc1cc(Nc2nccc(-c3cn(C)c4ccccc34)n2)c(OC)cc1N(C)CCN(C)C"
c = QdrantClient(url="http://localhost:6333", timeout=120)

def hdr(t): print(f"\n{'='*72}\n{t}\n{'='*72}")

# ---- text (MedCPT) ----
print("loading MedCPT query encoder…")
qtok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder"); qm = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()
def medcpt(t):
    with torch.no_grad():
        e = qtok([t], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(qm(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()

# ---- compound fingerprint ----
def morgan(smiles):
    m = Chem.MolFromSmiles(smiles)
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    arr = np.zeros((2048,), dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, arr)
    return arr, bv

# ---- protein (esm2) ----
def esm2_vec(acc):
    pts,_ = c.scroll("esm2", scroll_filter=Filter(must=[FieldCondition(key="protein_id", match=MatchValue(value=acc))]), limit=1, with_vectors=True)
    return pts[0].vector if pts else None
def gene_of(acc):
    try:
        for r in bb.rows(bb.search(acc, source="uniprot"))[:1]: return r.get("name","")
    except Exception: pass
    return ""

t0=time.time()
hdr("INPUT: osimertinib (3rd-gen EGFR-TKI)")
print(f"  SMILES: {OSI_SMILES}")

# 1) ground the compound + map to the PRIMARY (mechanism-of-action) target (biobtree)
hdr("1) COMPOUND -> PRIMARY TARGET  (biobtree mechanism-of-action)")
prim = bb.map_targets(bb.bmap("osimertinib", ">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot"))
allt = bb.map_targets(bb.bmap("osimertinib", ">>chembl_molecule>>chembl_target>>uniprot"))
targets = prim or allt   # principled primary first; fall back to all binding targets
print(f"  primary (mechanism) target: {prim}  |  (all {len(allt)} binding targets exist too)")

# 2) target -> ESM-2 structurally-similar proteins, grounded + ortholog-deduped (PREDICTIVE)
hdr("2) PRIMARY TARGET -> SIMILAR PROTEINS  (esm2 predictive, grounded, ortholog-deduped)")
pivot=None
for tgt in targets:
    v = esm2_vec(tgt)
    if v is not None:
        pivot=tgt
        hits = c.query_points("esm2", query=v, limit=40, with_payload=["protein_id"]).points
        print(f"  pivot: {tgt} ({gene_of(tgt) or '?'}) -> ESM-2 nearest proteins (deduped by gene):")
        seen=set(); shown=0
        for h in hits:
            a=h.payload.get("protein_id")
            if a==tgt: continue
            g=gene_of(a) or "?"; key=g.split()[0] if g!="?" else a
            if key in seen: continue
            seen.add(key); print(f"      {a}  sim={h.score:.3f}  {g[:52]}")
            shown+=1
            if shown>=6: break
        break
if not pivot: print("  (no target landed in the 574K SwissProt esm2 set)")

# 3) compound -> Tanimoto-similar patent compounds (binary ANN + exact rerank)
hdr("3) COMPOUND -> SIMILAR COMPOUNDS  (patents_compounds, Tanimoto rerank)")
arr,bv = morgan(OSI_SMILES)
cand = c.query_points("patents_compounds", query=arr.tolist(), limit=50, with_payload=["surechembl_id","smiles"]).points
# exact Tanimoto rerank
res=[]
for h in cand:
    s=h.payload.get("smiles")
    if not s: continue
    mm=Chem.MolFromSmiles(s)
    if mm is None: continue
    t=DataStructs.TanimotoSimilarity(bv, AllChem.GetMorganFingerprintAsBitVect(mm,2,nBits=2048))
    res.append((h.payload.get("surechembl_id"), t, s))
res.sort(key=lambda x:-x[1])
print(f"  top Tanimoto-similar patent compounds (of {len(cand)} ANN candidates):")
for sid,t,s in res[:5]: print(f"      {sid}  Tanimoto={t:.3f}  {s[:60]}")

# 4) literature (pubmed_medcpt)
hdr("4) LITERATURE  (pubmed_abstracts_medcpt, MedCPT)")
for h in c.query_points("pubmed_abstracts_medcpt", query=medcpt("osimertinib EGFR T790M C797S acquired resistance mechanism NSCLC"), limit=4).points:
    print(f"      {h.score:.3f} pmid={h.payload.get('pmid')}: {(h.payload.get('chunk_text') or '')[:90]}")

# 5) trials (clinical_trials_medcpt), disease-grounded
hdr("5) CLINICAL TRIALS  (clinical_trials_medcpt, MedCPT)  + disease grounding")
seen=set()
for h in c.query_points("clinical_trials_medcpt", query=medcpt("osimertinib resistance EGFR-mutant non-small cell lung cancer"), limit=20).points:
    nct=h.payload.get("nct_id")
    if nct in seen: continue
    seen.add(nct)
    print(f"      {h.score:.3f} {nct} [{h.payload.get('chunk_type')}]: {str(h.payload.get('brief_title'))[:60]}")
    if len(seen)>=4: break
dg,_ = bb.ground("non-small cell lung carcinoma", source="mondo")
print(f"  disease grounding: 'NSCLC' -> {dg}")

print(f"\n[dossier built in {time.time()-t0:.0f}s — all 5 collections + biobtree]")
