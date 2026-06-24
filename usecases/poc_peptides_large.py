#!/usr/bin/env python3
"""PoC (scaled): does ESM-2 (mean-centered) cluster REAL peptides by family >> shuffled null?
Corpus = UniProt reviewed peptide-hormone/neuropeptide precursors -> their annotated MATURE
peptide features (exact begin/end), labeled by the 'Belongs to the X family' similarity comment.
Same metric as the 20-peptide probe, now on hundreds with real labels + per-family breakdown."""
import sys, re, json, time, random, urllib.request, urllib.parse, collections
import numpy as np, torch, esm
from qdrant_client import QdrantClient

# ---- 1) build labeled mature-peptide corpus from UniProt ----
BASE="https://rest.uniprot.org/uniprotkb/search"
Q="(keyword:KW-0527 OR keyword:KW-0372) AND reviewed:true"
FIELDS="accession,sequence,ft_peptide,cc_similarity"
def fetch_all(cap_pages=12):
    url=f"{BASE}?"+urllib.parse.urlencode({"query":Q,"fields":FIELDS,"format":"json","size":500})
    out=[]
    for _ in range(cap_pages):
        req=urllib.request.Request(url,headers={"Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=60) as r:
            data=json.loads(r.read()); link=r.headers.get("Link","")
        out+=data.get("results",[])
        m=re.search(r'<([^>]+)>;\s*rel="next"',link)
        if not m: break
        url=m.group(1)
    return out

FAM_RE=re.compile(r"[Bb]elongs to the (.+?) family")
def family_of(entry):
    for c in entry.get("comments",[]):
        if c.get("commentType")=="SIMILARITY":
            for t in c.get("texts",[]):
                m=FAM_RE.search(t.get("value",""));
                if m: return m.group(1).strip().lower()
    return None

print("fetching UniProt peptide-hormone precursors…", flush=True)
entries=fetch_all()
print(f"  {len(entries)} precursors")
corpus=[]  # (acc, pepname, seq, family)
for e in entries:
    acc=e["primaryAccession"]; seq=e.get("sequence",{}).get("value","")
    fam=family_of(e)
    if not fam or not seq: continue
    for f in e.get("features",[]):
        if f.get("type")!="Peptide": continue
        try: s=f["location"]["start"]["value"]; en=f["location"]["end"]["value"]
        except Exception: continue
        if not (isinstance(s,int) and isinstance(en,int)): continue
        sub=seq[s-1:en]
        if 5<=len(sub)<=60 and set(sub)<=set("ACDEFGHIKLMNPQRSTVWY"):
            corpus.append((acc,f.get("description","") or "peptide",sub,fam))

# dedupe identical sequences, keep families with >=4 members, cap 40/family
seen=set(); dedup=[]
for r in corpus:
    if r[2] in seen: continue
    seen.add(r[2]); dedup.append(r)
byfam=collections.defaultdict(list)
for r in dedup: byfam[r[3]].append(r)
fams_keep={f:v[:40] for f,v in byfam.items() if len(v)>=4}
data=[r for v in fams_keep.values() for r in v]
print(f"  {len(data)} mature peptides across {len(fams_keep)} families (>=4 members)")
for f,v in sorted(fams_keep.items(),key=lambda x:-len(x[1]))[:15]:
    print(f"    {len(v):3d}  {f}")

# ---- 2) embed (ESM-2 650M, mean-pool layer-33) ----
print("loading ESM-2 650M…", flush=True)
model,alphabet=esm.pretrained.esm2_t33_650M_UR50D(); model.eval()
bc=alphabet.get_batch_converter()
def embed(seq):
    _,_,toks=bc([("x",seq)])
    with torch.no_grad():
        rep=model(toks,repr_layers=[33])["representations"][33][0]
    return rep[1:len(seq)+1].mean(0).numpy()

c=QdrantClient(url="http://localhost:6333",timeout=120)
print("estimating collection centroid…", flush=True)
pts,_=c.scroll("esm2",limit=5000,with_vectors=True)
C=np.mean(np.stack([np.array(p.vector) for p in pts]),axis=0)

random.seed(42)
def shuffled(s): l=list(s); random.shuffle(l); return "".join(l)

seqs=[r[2] for r in data]; fams=[r[3] for r in data]
print(f"embedding {len(seqs)} real + {len(seqs)} shuffled…", flush=True)
def emb_matrix(ss, center):
    V=np.stack([embed(s) for s in ss])
    if center: V=V-C
    return V/np.linalg.norm(V,axis=1,keepdims=True)

def evaluate(V, fams):
    S=V@V.T; np.fill_diagonal(S,-9)
    nn,withins,crosses,perfam=[],[],[],collections.defaultdict(list)
    for i in range(len(fams)):
        if sum(1 for j in range(len(fams)) if j!=i and fams[j]==fams[i])==0: continue
        j=int(np.argmax(S[i])); hit=fams[j]==fams[i]; nn.append(hit); perfam[fams[i]].append(hit)
        for k in range(len(fams)):
            if k==i: continue
            (withins if fams[k]==fams[i] else crosses).append(S[i,k])
    return np.mean(nn), np.mean(withins), np.mean(crosses), perfam

for center in (False, True):
    tag="CENTERED" if center else "RAW"
    Vr=emb_matrix(seqs,center); Vn=emb_matrix([shuffled(s) for s in seqs],center)
    nn,wi,cr,pf=evaluate(Vr,fams); nn0,wi0,cr0,_=evaluate(Vn,fams)
    print(f"\n=== {tag} ===")
    print(f"REAL  nn-fammate={nn:.0%}  within {wi:.3f} vs cross {cr:.3f}  (gap {wi-cr:+.3f})")
    print(f"NULL  nn-fammate={nn0:.0%}  within {wi0:.3f} vs cross {cr0:.3f}  (gap {wi0-cr0:+.3f})")
    if center:
        print("  per-family nn-fammate (real):")
        for f,h in sorted(pf.items(),key=lambda x:-len(x[1])):
            print(f"    {np.mean(h):4.0%}  ({len(h):2d})  {f}")
print("\nVERDICT: viable iff CENTERED REAL nn-fammate >> NULL on a real, multi-family corpus.")
