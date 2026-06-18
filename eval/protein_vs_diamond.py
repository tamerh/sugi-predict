#!/usr/bin/env python3
"""Benchmark: esm2 DENSE retrieval (vector ANN) vs DIAMOND sequence-homology ground truth.
For sampled query proteins, does esm2's embedding-NN recover DIAMOND's top sequence homologs,
and how fast? Honest framing: ESM-2 ~= structure/function similarity, DIAMOND = sequence
alignment — related but not identical; recall vs DIAMOND is a homology-capture proxy (misses are
often legit remote/structural neighbors DIAMOND can't see)."""
import time
import numpy as np
from collections import OrderedDict
from qdrant_client import QdrantClient, models

DIAMOND="snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv"
NQ=80; K=50
def acc(s): return s.split("|")[1] if "|" in s else s   # sp|ACC|NAME -> ACC

# 1) read DIAMOND top-K homologs for the first NQ distinct queries
q2t=OrderedDict()
with open(DIAMOND) as f:
    next(f)  # header
    for line in f:
        p=line.split("\t")
        q,t=acc(p[0]),acc(p[1])
        if q==t: continue
        q2t.setdefault(q,[])
        if len(q2t[q])<K: q2t[q].append(t)
        if len(q2t)>NQ and q not in q2t: break
        if len(q2t)>=NQ and all(len(v)>=K for v in q2t.values()): break
q2t={q:t for q,t in list(q2t.items())[:NQ]}
print(f"loaded DIAMOND ground truth: {len(q2t)} queries, ~{K} homologs each")

c=QdrantClient(url="http://localhost:6333",timeout=60)
def vec(pid):
    r=c.scroll("esm2", scroll_filter=models.Filter(must=[models.FieldCondition(
        key="protein_id", match=models.MatchValue(value=pid))]), limit=1, with_vectors=True)[0]
    return r[0].vector if r else None

rec50=[]; rec100=[]; lat=[]; n_eval=0
for q,targets in q2t.items():
    v=vec(q)
    if v is None: continue
    t0=time.perf_counter()
    hits=c.query_points("esm2", query=v, limit=101).points
    lat.append((time.perf_counter()-t0)*1000)
    got=[h.payload.get("protein_id") for h in hits if h.payload.get("protein_id")!=q]
    tset=set(targets)
    rec50.append(len(tset & set(got[:50]))/len(tset))
    rec100.append(len(tset & set(got[:100]))/len(tset))
    n_eval+=1
P=lambda a,q: sorted(a)[int(len(a)*q)]
print(f"\nRESULT (esm2 dense retrieval vs DIAMOND top-50 homologs, {n_eval} queries):")
print(f"  recall in esm2 top-50:  mean={np.mean(rec50)*100:.0f}%  median={np.median(rec50)*100:.0f}%")
print(f"  recall in esm2 top-100: mean={np.mean(rec100)*100:.0f}%  median={np.median(rec100)*100:.0f}%  (bigger net)")
print(f"  esm2 query latency (brute-force over 574K): mean={np.mean(lat):.0f}ms  p95={P(lat,.95):.0f}ms")
print(f"  (DIAMOND all-vs-all over 574K SwissProt = hours on ~8 cores; one esm2 lookup = ~{np.mean(lat):.0f}ms; ~10ms w/ HNSW)")
