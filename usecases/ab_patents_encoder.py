#!/usr/bin/env python3
"""Did we ever compare MedCPT vs S-BioBERT on PATENT text? No -- the earlier A/B was on PubMed only.
This runs a controlled retrieval test on patent titles to decide whether re-embedding patents_text with
MedCPT is worth the GPU job.

Build an eval corpus from patents_text payloads: title-keyword "relevant" patents for a set of drug
targets + a random non-matching haystack. Embed the same corpus with BOTH encoders (MedCPT is dual:
Article encoder for documents, Query encoder for queries; S-BioBERT is single). For each target, query
"<target> inhibitor" and score precision@k (fraction of top-k whose title actually matches the target).
"""
import re, random, sys
import numpy as np
from qdrant_client import QdrantClient

TARGETS = {
    "EGFR":  r"\b(EGFR|epidermal growth factor receptor)\b",
    "PDE5":  r"\b(PDE[- ]?5|phosphodiesterase[ -]?(?:type[ -]?)?5)\b",
    "BRAF":  r"\bBRAF\b",
    "JAK":   r"\b(JAK[- ]?[123]?|janus kinase)\b",
    "VEGFR": r"\b(VEGFR|vascular endothelial growth factor receptor)\b",
    "HDAC":  r"\b(HDAC|histone deacetylase)\b",
    "DPP4":  r"\b(DPP[- ]?4|dipeptidyl peptidase)\b",
    "COX2":  r"\b(COX[- ]?2|cyclo[- ]?oxygenase[- ]?2)\b",
    "BTK":   r"\b(BTK|bruton'?s tyrosine kinase)\b",
    "ALK":   r"\b(ALK|anaplastic lymphoma kinase)\b",
}
RX = {t: re.compile(p, re.I) for t, p in TARGETS.items()}
N_SCAN, MAX_REL, HAYSTACK, K = 500_000, 50, 5000, 10

print("scanning patents_text titles…", flush=True)
qc = QdrantClient(url="http://localhost:6333", timeout=180)
rel = {t: [] for t in TARGETS}; hay = []; nxt = None; scanned = 0
while scanned < N_SCAN:
    pts, nxt = qc.scroll("patents_text", limit=4000, offset=nxt, with_payload=["title"])
    for p in pts:
        ti = (p.payload.get("title") or "").strip()
        if not ti:
            continue
        scanned += 1
        m = [t for t, rx in RX.items() if rx.search(ti) and len(rel[t]) < MAX_REL]
        if m:
            for t in m:
                rel[t].append((p.id, ti))
        elif len(hay) < HAYSTACK and random.random() < 0.04:
            hay.append((p.id, ti))
    if nxt is None:
        break

docs, doc_ids, seen = [], [], set()
for items in rel.values():
    for pid, ti in items:
        if pid not in seen:
            seen.add(pid); docs.append(ti); doc_ids.append(pid)
for pid, ti in hay:
    if pid not in seen:
        seen.add(pid); docs.append(ti); doc_ids.append(pid)
titles = dict(zip(doc_ids, docs))
print(f"corpus: {len(docs)} docs  (haystack {len(hay)})  | relevant per target:",
      {t: len(v) for t, v in rel.items()}, flush=True)

# ---- encoders ----
_sb = None
def sbiobert(texts):
    global _sb
    if _sb is None:
        import os; os.environ.setdefault("HF_HUB_OFFLINE", "1"); os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        _sb = SentenceTransformer("pritamdeka/S-BioBERT-snli-multinli-stsb")
    return np.asarray(_sb.encode(texts, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)

import torch
from transformers import AutoTokenizer, AutoModel
_mc = {}
def medcpt(texts, which):                                  # which: "Query" | "Article"
    if which not in _mc:
        import os; os.environ.setdefault("HF_HUB_OFFLINE", "1"); os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        tok = AutoTokenizer.from_pretrained(f"ncbi/MedCPT-{which}-Encoder")
        m = AutoModel.from_pretrained(f"ncbi/MedCPT-{which}-Encoder").eval()
        _mc[which] = (tok, m)
    tok, m = _mc[which]
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            b = tok(texts[i:i + 64], truncation=True, padding=True, max_length=256, return_tensors="pt")
            e = torch.nn.functional.normalize(m(**b).last_hidden_state[:, 0, :], dim=1)
            out.append(e.numpy())
    return np.vstack(out).astype(np.float32)

print("embedding S-BioBERT…", flush=True); sb_docs = sbiobert(docs)
print("embedding MedCPT (Article)…", flush=True); mc_docs = medcpt(docs, "Article")

def evaluate(doc_vecs, query_fn, label):
    print(f"\n=== {label} ===")
    ps = []
    for t, rx in RX.items():
        q = query_fn(f"{t} inhibitor")
        order = np.argsort(-(doc_vecs @ q))[:K]
        hits = [doc_ids[i] for i in order]
        p_at_k = sum(1 for pid in hits if rx.search(titles[pid])) / K
        ps.append(p_at_k)
        print(f"  {t:6s} P@{K} {p_at_k:.2f}")
    print(f"  MEAN P@{K}: {np.mean(ps):.3f}")
    return np.mean(ps)

sb = evaluate(sb_docs, lambda q: sbiobert([q])[0], "S-BioBERT")
mc = evaluate(mc_docs, lambda q: medcpt([q], "Query")[0], "MedCPT")
print(f"\nRESULT: S-BioBERT {sb:.3f}  vs  MedCPT {mc:.3f}  ->  "
      f"{'MedCPT better' if mc > sb else 'S-BioBERT better' if sb > mc else 'tie'} "
      f"by {abs(mc - sb):.3f} mean P@{K}")
