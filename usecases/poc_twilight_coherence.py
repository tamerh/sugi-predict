#!/usr/bin/env python3
"""PoC C (reproducible) — the protein twilight-zone moat, with the controls the claim needs.

Question: are a protein's ESM-2 nearest neighbors FUNCTIONALLY COHERENT (share an InterPro domain) at a
rate far above chance, and do a meaningful fraction reach functional relatives that SEQUENCE SEARCH misses?

This replaces the unreproducible "92%/1%/37%" prose with a runnable experiment + explicit controls:
  - coherence (real)  : % of ESM-2 top-K neighbors that share >=1 InterPro domain with the query
  - coherence (NULL)  : % for RANDOM protein pairs (the base rate of InterPro sharing) -> degree/popularity control
  - TWILIGHT (strict) : neighbor coherent AND <30% sequence identity (exact Smith-Waterman, NOT a DIAMOND proxy)
  - twilight (DIAMOND): neighbor coherent AND not in the query's DIAMOND filtered_top100 (complementary metric)

Queries = a fixed random sample of human SwissProt proteins with >=1 InterPro domain (seed=42).
Read-only. Sequences/identity from the local SwissProt FASTA; coherence from biobtree InterPro.
"""
import sys, re, random, time, subprocess
sys.path.insert(0, "/data/sugi-atlas/src"); sys.path.insert(0, "/data/bioyoda")
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from Bio.Align import PairwiseAligner, substitution_matrices
import atlas.biobtree as B

FASTA = "/data/bioyoda/raw_data/esm2/uniprot_swissprot.fasta"
DIAMOND_TSV = "/data/bioyoda/snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv"
N_QUERIES, K, IDENT_TW, SEED = 40, 10, 0.30, 42

print("loading SwissProt sequences…", flush=True)
SEQ, TAX = {}, {}
acc = None; buf = []
with open(FASTA) as f:
    for line in f:
        if line.startswith(">"):
            if acc: SEQ[acc] = "".join(buf)
            m = re.match(r">\w+\|([^|]+)\|", line); acc = m.group(1) if m else None
            ox = re.search(r"OX=(\d+)", line); TAX[acc] = ox.group(1) if ox else None
            buf = []
        else: buf.append(line.strip())
    if acc: SEQ[acc] = "".join(buf)
human = [a for a, t in TAX.items() if t == "9606" and a in SEQ]
print(f"  {len(SEQ)} sequences ; {len(human)} human", flush=True)

c = QdrantClient(url="http://localhost:6333", timeout=120)
def esm2_vec(a):
    p, _ = c.scroll("esm2", scroll_filter=Filter(must=[FieldCondition(key="protein_id", match=MatchValue(value=a))]), limit=1, with_vectors=True)
    return p[0].vector if p else None
_ip = {}
def interpro(a):
    if a in _ip: return _ip[a]
    s = set()
    try:
        for r in B.map_all(a, ">>uniprot>>interpro", cap=30):
            if r.get("id"): s.add(r["id"])
    except Exception: pass
    _ip[a] = s; return s
def diamond_set(a):
    out = subprocess.run(["grep", "-F", f"sp|{a}|", DIAMOND_TSV], capture_output=True, text=True).stdout
    s = set()
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) < 2: continue
        for col in (p[0], p[1]):
            q = col.split("|")
            if len(q) >= 2 and q[1] != a: s.add(q[1])
    return s
_aln = PairwiseAligner(); _aln.substitution_matrix = substitution_matrices.load("BLOSUM62")
_aln.mode = "local"; _aln.open_gap_score = -11; _aln.extend_gap_score = -1
def identity(a, b):
    if a not in SEQ or b not in SEQ: return None
    try:
        al = _aln.align(SEQ[a], SEQ[b])[0]
        idn = al.counts().identities
    except Exception: return None
    return idn / min(len(SEQ[a]), len(SEQ[b]))

# fixed query sample: human + has InterPro + in esm2
random.seed(SEED); random.shuffle(human)
queries = []
for a in human:
    if esm2_vec(a) is None or not interpro(a): continue
    queries.append(a)
    if len(queries) >= N_QUERIES: break
print(f"  {len(queries)} query proteins (human, InterPro-annotated, in esm2)\n", flush=True)

rng = random.Random(SEED)
coh_real = coh_null = n_pairs = tw_strict = tw_diamond = coh_count = 0
per_q = []
t0 = time.time()
for q in queries:
    qv = esm2_vec(q); qip = interpro(q); dia = diamond_set(q)
    hits = [h.payload["protein_id"] for h in c.query_points("esm2", query=qv, limit=K + 1, with_payload=["protein_id"]).points if h.payload["protein_id"] != q][:K]
    nulls = rng.sample(human, K)                                   # random-pairs null
    qc = qtw = 0
    for n in hits:
        n_pairs += 1
        coh = bool(qip & interpro(n))
        coh_real += coh; qc += coh
        if coh:
            coh_count += 1
            idn = identity(q, n)
            if idn is not None and idn < IDENT_TW: tw_strict += 1; qtw += 1
            if n not in dia: tw_diamond += 1
    for n in nulls:
        coh_null += bool(qip & interpro(n))
    per_q.append((q, qc, qtw))
print(f"### RESULT  ({len(queries)} queries × {K} neighbors = {n_pairs} pairs ; {time.time()-t0:.0f}s)\n")
print(f"coherence   REAL (ESM-2 neighbors share InterPro) : {coh_real/n_pairs:.0%}")
print(f"coherence   NULL (random protein pairs)           : {coh_null/n_pairs:.0%}   <- base rate")
print(f"TWILIGHT strict  (coherent AND <{int(IDENT_TW*100)}% identity): {tw_strict/n_pairs:.0%} of all neighbors "
      f"({tw_strict}/{n_pairs}) ; {tw_strict/max(coh_count,1):.0%} of coherent ones")
print(f"twilight DIAMOND (coherent AND not in DIAMOND top100): {tw_diamond/n_pairs:.0%} ({tw_diamond}/{n_pairs})")
print(f"\nVERDICT: moat holds iff coherence REAL >> NULL (embedding finds real homologs, not noise) AND a")
print(f"meaningful TWILIGHT-strict fraction exists (functional relatives BELOW sequence-search's <30%-id floor).")
