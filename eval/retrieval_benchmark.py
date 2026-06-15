#!/usr/bin/env python3
"""BioYoda retrieval-quality benchmark (the preprint's results-section spine).

Evaluates text encoders on standard biomedical IR benchmarks (BEIR via ir_datasets):
nDCG@10, Recall@100, MRR@10. Compares:
  - sbiobert@75   : current prod config (pritamdeka/S-BioBERT, max_seq_length=75) <- the truncation
  - sbiobert@512  : same model, max_seq_length bumped to 512 (the cheap fix)
  - medcpt        : ncbi/MedCPT (asymmetric Article/Query encoders) — the upgrade candidate
  - bm25          : lexical baseline
Self-contained: embeds the (small) benchmark corpora locally; does NOT touch prod Qdrant.

Usage: python eval/retrieval_benchmark.py --datasets beir/nfcorpus/test --encoders sbiobert@75 sbiobert@512 medcpt bm25
"""
import argparse, time, numpy as np

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def load_dataset(name):
    import ir_datasets
    ds = ir_datasets.load(name)
    docs = {d.doc_id: ((getattr(d, 'title', '') or '') + ' ' + (getattr(d, 'text', '') or '')).strip()
            for d in ds.docs_iter()}
    queries = {q.query_id: q.text for q in ds.queries_iter()}
    qrels = {}
    for qr in ds.qrels_iter():
        if qr.relevance > 0:
            qrels.setdefault(qr.query_id, {})[qr.doc_id] = qr.relevance
    queries = {qid: t for qid, t in queries.items() if qid in qrels}  # judged queries only
    log(f"{name}: {len(docs):,} docs, {len(queries):,} judged queries")
    return docs, queries, qrels


def encode_st(model_name, texts, max_seq, batch=64, cores='0-7'):
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(model_name)
    m.max_seq_length = max_seq
    return np.asarray(m.encode(texts, batch_size=batch, show_progress_bar=False,
                               normalize_embeddings=True, convert_to_numpy=True), dtype=np.float32)


def encode_medcpt(texts, which, batch=64):
    import torch
    from transformers import AutoTokenizer, AutoModel
    name = "ncbi/MedCPT-Query-Encoder" if which == 'query' else "ncbi/MedCPT-Article-Encoder"
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModel.from_pretrained(name).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i+batch], truncation=True, padding=True, max_length=512, return_tensors='pt')
            emb = model(**enc).last_hidden_state[:, 0, :]  # CLS pooling (MedCPT convention)
            emb = torch.nn.functional.normalize(emb, dim=1)
            out.append(emb.cpu().numpy())
    return np.vstack(out).astype(np.float32)


def dense_retrieve(doc_emb, query_emb, topk=100):
    # cosine == dot on normalized vectors
    return np.argsort(-(query_emb @ doc_emb.T), axis=1)[:, :topk]


def bm25_retrieve(doc_texts, query_texts, topk=100):
    from rank_bm25 import BM25Okapi
    tok = lambda s: s.lower().split()
    bm = BM25Okapi([tok(d) for d in doc_texts])
    ranks = []
    for q in query_texts:
        scores = bm.get_scores(tok(q))
        ranks.append(np.argsort(-scores)[:topk])
    return np.vstack(ranks)


def metrics(ranked_doc_ids, query_ids, qrels, doc_ids, k_ndcg=10, k_recall=100, k_mrr=10):
    ndcg, recall, mrr = [], [], []
    for row, qid in zip(ranked_doc_ids, query_ids):
        rel = qrels[qid]
        ranked = [doc_ids[i] for i in row]
        gains = [rel.get(d, 0) for d in ranked]
        dcg = sum(g / np.log2(r + 2) for r, g in enumerate(gains[:k_ndcg]))
        ideal = sorted(rel.values(), reverse=True)[:k_ndcg]
        idcg = sum(g / np.log2(r + 2) for r, g in enumerate(ideal))
        ndcg.append(dcg / idcg if idcg else 0.0)
        nrel = len(rel)
        recall.append(len(set(ranked[:k_recall]) & set(rel)) / nrel if nrel else 0.0)
        rr = 0.0
        for r, d in enumerate(ranked[:k_mrr]):
            if d in rel:
                rr = 1.0 / (r + 1); break
        mrr.append(rr)
    return {'nDCG@10': np.mean(ndcg), 'Recall@100': np.mean(recall), 'MRR@10': np.mean(mrr)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--datasets', nargs='+', default=['beir/nfcorpus/test'])
    ap.add_argument('--encoders', nargs='+', default=['sbiobert@75', 'sbiobert@512', 'medcpt', 'bm25'])
    args = ap.parse_args()
    SB = 'pritamdeka/S-BioBERT-snli-multinli-stsb'
    rows = []
    for dsname in args.datasets:
        docs, queries, qrels = load_dataset(dsname)
        doc_ids = list(docs); doc_texts = [docs[d] for d in doc_ids]
        q_ids = list(queries); q_texts = [queries[q] for q in q_ids]
        for enc in args.encoders:
            t = time.time()
            if enc == 'bm25':
                ranked = bm25_retrieve(doc_texts, q_texts)
            elif enc.startswith('sbiobert@'):
                ms = int(enc.split('@')[1])
                de = encode_st(SB, doc_texts, ms); qe = encode_st(SB, q_texts, ms)
                ranked = dense_retrieve(de, qe)
            elif enc == 'medcpt':
                de = encode_medcpt(doc_texts, 'article'); qe = encode_medcpt(q_texts, 'query')
                ranked = dense_retrieve(de, qe)
            else:
                log(f"unknown encoder {enc}"); continue
            m = metrics(ranked, q_ids, qrels, doc_ids)
            dt = time.time() - t
            rows.append((dsname, enc, m, dt))
            log(f"  {enc:14s} nDCG@10={m['nDCG@10']:.4f}  Recall@100={m['Recall@100']:.4f}  MRR@10={m['MRR@10']:.4f}  ({dt:.0f}s)")
    print("\n=== RESULTS ===")
    print(f"{'dataset':22s} {'encoder':14s} {'nDCG@10':>9s} {'Recall@100':>11s} {'MRR@10':>8s}")
    for ds, enc, m, dt in rows:
        print(f"{ds:22s} {enc:14s} {m['nDCG@10']:>9.4f} {m['Recall@100']:>11.4f} {m['MRR@10']:>8.4f}")


if __name__ == '__main__':
    main()
