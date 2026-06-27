#!/usr/bin/env python3
"""Precompute the MedCPT-Query target-vocabulary embeddings for the patent-text-support badge.

The validation pilot (usecases) showed a patent's full-text body independently corroborates the
chemistry-predicted target: the predicted target lands in the text's top-10 ~40% of the time at conf>=0.8
(recall@10 0.19 overall, vs 0.02 under a patent<->target null shuffle). To serve that as a per-prediction
badge WITHOUT loading MedCPT at request time, we embed every candidate target ONCE here and save the matrix.

At serve time the engine only: retrieves the compound's full-text patent vector(s) from patents_text_medcpt
and dot-products them against this precomputed matrix (both L2-normalised -> cosine) to rank targets. No model.

Query string per target: "{GENE} {protein full name}" — matched to how patents_text_medcpt was embedded
(MedCPT-Article-Encoder, CLS pool + L2 norm; see scripts/gpu/embed_text_medcpt_gpu.py). The article vectors
are L2-normalised (verified norm==1.0), so we L2-normalise the query embeddings the same way.

Vocabulary = every target in the prediction reference (work/chembl_reference/target_genes.json, 7,929 targets) —
the full universe a chemistry prediction can name. We also store a `human` mask (org == Homo sapiens, unknown
org counted human-keep — matching target.is_human). The serve-time ranking restricts to human targets, because
(a) the predictor itself defaults to human_only and (b) against the full vocab the text top-hits are dominated by
non-human/bacterial orthologs (nadE, etc.) — the same noise the predictor filters. ~4,884 human targets, which
is the regime the validation pilot ran in (its 400-target vocab was human).

BACKGROUND DE-BIAS (important): raw cosine to patent text is dominated by a few generic "attractor" targets
(e.g. SRI tops 494/500 random patents) — an artifact of where those query strings land in MedCPT space, not real
aboutness. We also compute a BACKGROUND vector = mean of a large sample of full-text patent vectors, and store
each target's background affinity (bg = emb @ mean_patent_vec). The serve path ranks on (score - bg), which
removes the attractors: a phosphodiesterase patent's debiased text-top becomes PDE3A/PDE2A/PDE5A/PDE4A... (all
PDEs) instead of SRI/ZNF207. This also recovers aggregate recall (raw recall@1 ~0 vs debiased ~0.08 over the
full 4,885-target human vocab, matching the pilot's 400-vocab numbers despite 12x more candidates).

Out: work/patent_text_support/target_query_emb.npz
     {emb (N,768) f32 L2-norm, acc (N,), gene (N,), human (N,) bool, bg (N,) f32 background affinity}
Run: python modules/compounds/build_patent_text_support.py
"""
import json
import os
import pathlib
import sys

import numpy as np

QDRANT_URL = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
BG_SAMPLE = 20000   # full-text patents sampled for the background mean

ROOT = os.environ.get("BIOYODA_ROOT", "/data/bioyoda")
REF = f"{ROOT}/work/chembl_reference/target_genes.json"
OUT_DIR = pathlib.Path(f"{ROOT}/work/patent_text_support")
OUT = OUT_DIR / "target_query_emb.npz"


def query_string(acc, meta):
    g = meta.get("gene") or acc
    nm = (meta.get("name") or "").split("(")[0].strip()
    return f"{g} {nm}".strip() if nm else g


def main():
    genes = json.load(open(REF))
    accs = sorted(genes)
    queries = [query_string(a, genes[a]) for a in accs]
    print(f"targets: {len(accs)}  e.g. {list(zip(accs[:3], queries[:3]))}")

    import torch
    from transformers import AutoTokenizer, AutoModel
    tok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
    model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()

    embs = []
    with torch.no_grad():
        for i in range(0, len(queries), 64):
            enc = tok(queries[i:i + 64], truncation=True, padding=True, max_length=64, return_tensors="pt")
            e = model(**enc).last_hidden_state[:, 0, :]          # CLS pool (MedCPT convention, matches Article)
            e = torch.nn.functional.normalize(e, dim=1)          # L2 norm so dot == cosine vs the article vectors
            embs.append(e.numpy().astype("float32"))
            if (i // 64) % 20 == 0:
                print(f"  {i + len(embs[-1])}/{len(queries)}", file=sys.stderr)
    emb = np.vstack(embs)
    assert emb.shape == (len(accs), 768), emb.shape
    assert abs(float(np.linalg.norm(emb[0])) - 1.0) < 1e-4

    # human mask: Homo sapiens, OR unknown org (human-keep — matches target.is_human so we never drop a target
    # we merely lack metadata for). The serve path ranks within this mask.
    human = np.array(["Homo sapiens" in (genes[a].get("org") or "") or not genes[a].get("org") for a in accs])

    # background: mean of a large sample of full-text patent vectors -> per-target background affinity.
    print(f"computing background over up to {BG_SAMPLE} full-text patents ...", file=sys.stderr)
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    qc = QdrantClient(url=QDRANT_URL, timeout=180)
    flt = Filter(must=[FieldCondition(key="has_full_text", match=MatchValue(value=True))])
    accum = np.zeros(768, dtype="float64"); n = 0; off = None
    while n < BG_SAMPLE:
        pts, off = qc.scroll("patents_text_medcpt", scroll_filter=flt, limit=2000,
                             with_payload=False, with_vectors=True, offset=off)
        if not pts:
            break
        for p in pts:
            accum += np.asarray(p.vector, dtype="float64"); n += 1
        if off is None:
            break
    mean_patent = (accum / n).astype("float32")
    bg = (emb @ mean_patent).astype("float32")    # (N,) each target's affinity to the average patent
    print(f"background over {n} patents; bg range [{bg.min():.3f}, {bg.max():.3f}]")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(OUT, emb=emb, acc=np.array(accs), gene=np.array([genes[a].get("gene") or a for a in accs]),
             human=human, bg=bg)
    print(f"human targets: {int(human.sum())}/{len(accs)}")
    print(f"wrote {OUT}  emb={emb.shape}  ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
