#!/usr/bin/env python3
"""PREDICT->VALIDATE the cross-modal moat (Mode C) — held-out polypharmacology recovery.

Claim under test: the ESM-2 twilight hop from a drug's PRIMARY target predicts the drug's OTHER known
targets — especially ones sequence search can't reach — better than chance AND better than "guess the
popular targets" (the degree-bias objection).

Per drug:
  primary  = mechanism target (held: the ONLY input to the prediction)
  secondary= other ChEMBL bioactivity targets (human, in esm2), minus mechanism  <- HELD OUT, to recover
  predict secondary from primary via 4 methods, score recall@K:
    ESM-2     : top-K embedding neighbors of primary            <- the moat
    DIAMOND   : top-K sequence homologs of primary              <- sequence-search baseline
    POPULARITY: the K globally-most-promiscuous targets (drug-agnostic) <- degree/popularity null
    RANDOM    : K random human in-esm2 proteins                 <- base rate
Moat holds iff ESM-2 recall >> DIAMOND (reaches targets sequence misses) AND >> POPULARITY (it's specific).
Also reports the fraction of ESM-2-recovered secondaries that are <30% identity to primary (beyond seq search).
Read-only. Identity from local SwissProt fasta; targets/chains from biobtree; homologs from DIAMOND tsv.
"""
import sys, re, random, time, subprocess, collections
sys.path.insert(0, "/data/sugi-atlas/src"); sys.path.insert(0, "/data/bioyoda")
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from Bio.Align import PairwiseAligner, substitution_matrices
import atlas.biobtree as B

FASTA = "/data/bioyoda/raw_data/esm2/uniprot_swissprot.fasta"
DIAMOND_TSV = "/data/bioyoda/snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv"
K, SEED = 50, 42
DRUGS = ["imatinib","dasatinib","nilotinib","bosutinib","ponatinib","sunitinib","sorafenib","regorafenib",
    "pazopanib","cabozantinib","lenvatinib","axitinib","crizotinib","ceritinib","lorlatinib","gefitinib",
    "erlotinib","osimertinib","afatinib","lapatinib","vandetanib","dabrafenib","vemurafenib","trametinib",
    "ruxolitinib","tofacitinib","ibrutinib","palbociclib","midostaurin","nintedanib","larotrectinib",
    "entrectinib","gilteritinib","quizartinib","selumetinib","binimetinib","fedratinib","baricitinib"]

print("loading SwissProt seqs + taxids…", flush=True)
SEQ, TAX = {}, {}; acc=None; buf=[]
with open(FASTA) as f:
    for line in f:
        if line.startswith(">"):
            if acc: SEQ[acc]="".join(buf)
            m=re.match(r">\w+\|([^|]+)\|", line); acc=m.group(1) if m else None
            ox=re.search(r"OX=(\d+)", line); TAX[acc]=ox.group(1) if ox else None; buf=[]
        else: buf.append(line.strip())
    if acc: SEQ[acc]="".join(buf)
HUMAN=set(a for a,t in TAX.items() if t=="9606")
c = QdrantClient(url="http://localhost:6333", timeout=120)
def in_esm2(a):
    p,_=c.scroll("esm2",scroll_filter=Filter(must=[FieldCondition(key="protein_id",match=MatchValue(value=a))]),limit=1); return bool(p)
def esm2_vec(a):
    p,_=c.scroll("esm2",scroll_filter=Filter(must=[FieldCondition(key="protein_id",match=MatchValue(value=a))]),limit=1,with_vectors=True); return p[0].vector if p else None
def targets(drug, chain):
    try: return [r.get("id") for r in B.map_all(drug, chain, cap=40) if r.get("id")]
    except Exception: return []
def diamond_topk(acc, k):
    out=subprocess.run(["grep","-F",f"sp|{acc}|",DIAMOND_TSV],capture_output=True,text=True).stdout
    scored=[]
    for line in out.splitlines():
        p=line.split("\t")
        if len(p)<12: continue
        q=p[0].split("|"); s=p[1].split("|")
        other=None
        if len(q)>=2 and q[1]==acc and len(s)>=2: other=s[1]
        elif len(s)>=2 and s[1]==acc and len(q)>=2: other=q[1]
        if other and other!=acc:
            try: scored.append((other,float(p[11])))
            except ValueError: pass
    scored.sort(key=lambda x:-x[1]); seen=[];
    for a,_ in scored:
        if a not in seen: seen.append(a)
    return seen[:k]
_aln=PairwiseAligner(); _aln.substitution_matrix=substitution_matrices.load("BLOSUM62"); _aln.mode="local"; _aln.open_gap_score=-11; _aln.extend_gap_score=-1
def identity(a,b):
    if a not in SEQ or b not in SEQ: return None
    try: al=_aln.align(SEQ[a],SEQ[b])[0]; return al.counts().identities/min(len(SEQ[a]),len(SEQ[b]))
    except Exception: return None

# ---- build the held-out gold set ----
print("building gold set (primary + held-out secondary targets per drug)…", flush=True)
gold=[]; sec_freq=collections.Counter()
for d in DRUGS:
    mech=[a for a in targets(d, ">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot") if a in HUMAN and in_esm2(a)]
    if not mech: continue
    primary=mech[0]
    act=[a for a in targets(d, ">>chembl_molecule>>chembl_activity>>chembl_target>>uniprot") if a in HUMAN and in_esm2(a)]
    secondary=sorted(set(act) - set(mech))
    if len(secondary) < 2: continue
    gold.append((d, primary, secondary));
    for s in secondary: sec_freq[s]+=1
    print(f"  {d:14} primary={primary} secondary={len(secondary)}", flush=True)
print(f"  -> {len(gold)} drugs with >=2 held-out human/in-esm2 secondary targets", flush=True)
POPULAR=[a for a,_ in sec_freq.most_common(K)]                     # popularity/degree null (drug-agnostic)
ALL_TARGETS=[a for a in sec_freq]                                  # pool for the random null

# ---- evaluate recall@K per method ----
rng=random.Random(SEED)
agg={m:[] for m in ("ESM-2","DIAMOND","POPULARITY","RANDOM")}
beyond=0; recov_esm=0
t0=time.time()
for d, primary, secondary in gold:
    S=set(secondary)
    esm=[h.payload["protein_id"] for h in c.query_points("esm2",query=esm2_vec(primary),limit=K+1,with_payload=["protein_id"]).points if h.payload["protein_id"]!=primary][:K]
    dia=diamond_topk(primary, K)
    pop=[a for a in POPULAR if a!=primary][:K]
    rnd=rng.sample(ALL_TARGETS, min(K,len(ALL_TARGETS)))
    preds={"ESM-2":esm,"DIAMOND":dia,"POPULARITY":pop,"RANDOM":rnd}
    for m,p in preds.items():
        agg[m].append(len(S & set(p))/len(S))
    # beyond-sequence: ESM-2-recovered secondaries that DIAMOND missed AND <30% id to primary
    for s in (S & set(esm)):
        recov_esm+=1
        idn=identity(primary,s)
        if s not in set(dia) and idn is not None and idn<0.30: beyond+=1

import numpy as np
print(f"\n### PREDICT->VALIDATE  (recall@{K}, {len(gold)} drugs, {sum(len(s) for _,_,s in gold)} held-out secondary targets ; {time.time()-t0:.0f}s)\n")
for m in ("ESM-2","DIAMOND","POPULARITY","RANDOM"):
    v=np.array(agg[m]); print(f"  {m:11} recall@{K} = {v.mean():.1%}  (median {np.median(v):.0%})")
print(f"\n  of {recov_esm} ESM-2-recovered secondary targets, {beyond} ({beyond/max(recov_esm,1):.0%}) are "
      f"DIAMOND-missed AND <30% identity to primary = recovered ONLY via the embedding (the moat).")
print(f"\nVERDICT: moat validated iff ESM-2 >> DIAMOND (reaches targets sequence misses) AND >> POPULARITY (specific, not degree-bias).")
