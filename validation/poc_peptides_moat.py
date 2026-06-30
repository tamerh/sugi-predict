#!/usr/bin/env python3
"""MOAT TEST (PoC-C analog for peptides): does an EMBEDDING reach functional peptide
relatives that SEQUENCE SEARCH cannot?  + encoder bake-off (ESM-2 vs k-mer baseline vs null).

Corpus  : UniProt reviewed mature peptides, labeled by 'Belongs to the X family' (= functional truth).
Seq-search baseline : exhaustive Smith-Waterman (BLOSUM62) + the literature 30%-identity twilight cutoff.
   (SW is the GENEROUS version of sequence search — no BLAST word-seeding floor — so any moat shown is conservative.)
Twilight relative of p = same-family peptide with <30% identity to p (sequence search effectively blind).
MOAT metric = twilight-recall@k : of p's <30%-identity family-mates, how many an encoder surfaces in top-k.
Real embedding moat iff  ESM-2 twilight-recall  >>  (k-mer baseline, shuffled null, and SW itself)."""
import sys, re, json, random, collections, itertools
import numpy as np, torch, esm
from Bio.Align import PairwiseAligner, substitution_matrices

CAP=25; IDENT_TW=0.30; K=10
# ---------- corpus ----------
import urllib.request, urllib.parse
BASE="https://rest.uniprot.org/uniprotkb/search"
Q="(keyword:KW-0527 OR keyword:KW-0372) AND reviewed:true"
def fetch_all(cap_pages=12):
    url=f"{BASE}?"+urllib.parse.urlencode({"query":Q,"fields":"accession,sequence,ft_peptide,cc_similarity","format":"json","size":500})
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
def family_of(e):
    for c in e.get("comments",[]):
        if c.get("commentType")=="SIMILARITY":
            for t in c.get("texts",[]):
                m=FAM_RE.search(t.get("value",""))
                if m: return m.group(1).strip().lower()
    return None
print("fetching corpus…",flush=True)
entries=fetch_all(); corpus=[]
for e in entries:
    acc=e["primaryAccession"]; seq=e.get("sequence",{}).get("value",""); fam=family_of(e)
    if not fam or not seq: continue
    for f in e.get("features",[]):
        if f.get("type")!="Peptide": continue
        try: s=f["location"]["start"]["value"]; en=f["location"]["end"]["value"]
        except Exception: continue
        if isinstance(s,int) and isinstance(en,int):
            sub=seq[s-1:en]
            if 5<=len(sub)<=60 and set(sub)<=set("ACDEFGHIKLMNPQRSTVWY"):
                corpus.append((acc,sub,fam))
seen=set(); dd=[]
for r in corpus:
    if r[1] in seen: continue
    seen.add(r[1]); dd.append(r)
byfam=collections.defaultdict(list)
for r in dd: byfam[r[2]].append(r)
keep={f:v[:CAP] for f,v in byfam.items() if len(v)>=4}
data=[r for v in keep.values() for r in v]
ACC=[r[0] for r in data]; SEQ=[r[1] for r in data]; FAM=[r[2] for r in data]
N=len(data)
print(f"  {N} peptides / {len(keep)} families (cap {CAP})",flush=True)

# ---------- encoders ----------
print("loading ESM-2 650M…",flush=True)
model,alphabet=esm.pretrained.esm2_t33_650M_UR50D(); model.eval(); bc=alphabet.get_batch_converter()
def esm_embed(seq):
    _,_,toks=bc([("x",seq)])
    with torch.no_grad(): rep=model(toks,repr_layers=[33])["representations"][33][0]
    return rep[1:len(seq)+1].mean(0).numpy()
print("loading ProtT5…",flush=True)
from transformers import T5Tokenizer, T5EncoderModel
t5tok=T5Tokenizer.from_pretrained('Rostlab/prot_t5_xl_half_uniref50-enc',do_lower_case=False)
t5=T5EncoderModel.from_pretrained('Rostlab/prot_t5_xl_half_uniref50-enc').float().eval()  # fp32 on CPU
def t5_embed(seq):
    s=" ".join(re.sub(r"[UZOB]","X",seq))
    ids=t5tok(s,add_special_tokens=True,return_tensors='pt')
    with torch.no_grad(): h=t5(**ids).last_hidden_state[0]
    return h[:len(seq)].mean(0).numpy()   # mean over residues (exclude </s>)
AAs="ACDEFGHIKLMNPQRSTVWY"; KM=[a for a in AAs]+[a+b for a in AAs for b in AAs]  # 1+2-mer (420)
kidx={k:i for i,k in enumerate(KM)}
def kmer_vec(s):
    v=np.zeros(len(KM))
    for a in s: v[kidx[a]]+=1
    for a,b in zip(s,s[1:]): v[kidx[a+b]]+=1
    return v
def matrix(fn,seqs):                       # uniform centering: subtract own peptide-set mean, then L2
    V=np.stack([fn(s) for s in seqs]); V=V-V.mean(0); return V/np.linalg.norm(V,axis=1,keepdims=True)
random.seed(42)
def shuf(s): l=list(s); random.shuffle(l); return "".join(l)
print("embedding (ESM-2 real+null, ProtT5, k-mer)…",flush=True)
E_esm=matrix(esm_embed, SEQ)
E_null=matrix(lambda s:esm_embed(shuf(s)), SEQ)
E_t5=matrix(t5_embed, SEQ)
E_km=matrix(kmer_vec, SEQ)

# ---------- sequence search: SW score (all-vs-all) + within-family identity ----------
print("Smith-Waterman all-vs-all…",flush=True)
aln=PairwiseAligner(); aln.substitution_matrix=substitution_matrices.load("BLOSUM62")
aln.mode="local"; aln.open_gap_score=-11; aln.extend_gap_score=-1
SW=np.zeros((N,N))
for i in range(N):
    for j in range(i+1,N):
        sc=aln.score(SEQ[i],SEQ[j]); SW[i,j]=SW[j,i]=sc
def identity(a,b):
    al=aln.align(a,b)[0]
    try: idn=al.counts().identities
    except Exception:
        idn=sum(1 for x,y in zip(al[0],al[1]) if x==y and x!="-")
    return idn/min(len(a),len(b))

# precompute within-family identity -> twilight classification
print("within-family identity (twilight split)…",flush=True)
fam_idx=collections.defaultdict(list)
for i,f in enumerate(FAM): fam_idx[f].append(i)
TWILIGHT=[set() for _ in range(N)]; REACH=[set() for _ in range(N)]
for f,idxs in fam_idx.items():
    for a,b in itertools.combinations(idxs,2):
        if ACC[a]==ACC[b]: continue
        idn=identity(SEQ[a],SEQ[b])
        (TWILIGHT[a] if idn<IDENT_TW else REACH[a]).add(b)
        (TWILIGHT[b] if idn<IDENT_TW else REACH[b]).add(a)

# ---------- metrics ----------
def topk_idx(M,i,k=K):
    order=np.argsort(-M[i]); return [j for j in order if j!=i and ACC[j]!=ACC[i]][:k]
def recall(query_set, getnn):
    num=den=0
    for i in range(N):
        S=query_set(i)
        if not S: continue
        nn=set(getnn(i)); num+=len(nn&S); den+=min(K,len(S))
    return num/den if den else 0.0
def fammates(i): return {j for j in fam_idx[FAM[i]] if j!=i and ACC[j]!=ACC[i]}
encoders={"ESM-2(centered)":E_esm@E_esm.T,"ProtT5(centered)":E_t5@E_t5.T,"k-mer 1+2":E_km@E_km.T,"ESM-2 NULL(shuffled)":E_null@E_null.T,"Smith-Waterman":SW}

tw_total=sum(len(t) for t in TWILIGHT); rc_total=sum(len(r) for r in REACH)
print(f"\nfamily-mate pairs: {(tw_total+rc_total)//2} | twilight(<{int(IDENT_TW*100)}% id)={tw_total//2} ({tw_total/(tw_total+rc_total):.0%}) — the gap sequence-search is blind to")
print(f"\n{'encoder':22}{'family-recall@'+str(K):>16}{'TWILIGHT-recall@'+str(K):>18}")
for name,M in encoders.items():
    fr=recall(fammates,lambda i:topk_idx(M,i)); tw=recall(lambda i:TWILIGHT[i],lambda i:topk_idx(M,i))
    print(f"{name:22}{fr:>15.0%}{tw:>18.0%}")
print(f"\nMOAT iff ESM-2 TWILIGHT-recall >> k-mer, NULL, and Smith-Waterman.")
print("(twilight pairs are <30%-id BY DEFINITION → SW/seq-search ~floor; question is whether the EMBEDDING, and not mere composition, recovers them.)")
