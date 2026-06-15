#!/usr/bin/env python3
"""Embed (payload+text) JSONL shards with MedCPT-Article-Encoder on GPU -> FAISS + sidecar,
in the exact format modules/qdrant/scripts/insert_from_faiss.py consumes.

For the MedCPT text-encoder migration (#Q1): CPU is infeasible at ~72M-vector scale
(~1 text/s), GPU does thousands/s. Run on Colab/cloud GPU. Mirrors the existing
batch_*_gpu.py Colab pattern (Drive-mounted paths, resume).

Colab usage:
    from google.colab import drive; drive.mount('/content/drive')
    !pip -q install transformers faiss-cpu
    !nohup python embed_text_medcpt_gpu.py \
        --input-dir  /content/drive/MyDrive/bioyoda/medcpt_input/pubmed_abstracts \
        --output-dir /content/drive/MyDrive/bioyoda/medcpt_output/pubmed_abstracts \
        > medcpt_pubmed.log 2>&1 &

Input  : <shard>.jsonl, one JSON record/line. Each record is a payload dict containing a
         text field (default key "text"); ALL other keys are preserved into the sidecar so
         the re-inserted points keep their ids/payloads (pmid / nct_id+global_chunk_id /
         patent_id ...). The text is also re-stored as 'chunk_text'.
Output : <shard>.index (FAISS IP, 768d) + <shard>.json ({i: payload}). Resume-safe
         (skips a shard whose .index+.json already exist).
"""
import os, sys, json, glob, argparse, time
import numpy as np

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def load_model(model_name, device, fp16):
    from transformers import AutoTokenizer, AutoModel
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device).eval()
    if fp16 and str(device).startswith('cuda'):
        model = model.half()
    return tok, model


def embed(texts, tok, model, device, max_length, batch):
    import torch
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i+batch], truncation=True, padding=True,
                      max_length=max_length, return_tensors='pt').to(device)
            emb = model(**enc).last_hidden_state[:, 0, :]      # CLS pooling (MedCPT convention)
            emb = torch.nn.functional.normalize(emb, dim=1)
            out.append(emb.float().cpu().numpy())
    return np.vstack(out).astype(np.float32)


def process_shard(path, out_dir, tok, model, device, args):
    import faiss
    name = os.path.splitext(os.path.basename(path))[0]
    idx_path = os.path.join(out_dir, name + '.index')
    meta_path = os.path.join(out_dir, name + '.json')
    if os.path.exists(idx_path) and os.path.exists(meta_path):
        return -1  # already done (resume)
    records, texts = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            t = r.get(args.text_field, '')
            if not t:
                continue
            records.append(r); texts.append(t)
    if not texts:
        return 0
    vecs = embed(texts, tok, model, device, args.max_length, args.batch_size)
    os.makedirs(out_dir, exist_ok=True)
    index = faiss.IndexFlatIP(vecs.shape[1]); index.add(vecs)
    faiss.write_index(index, idx_path)
    meta = {}
    for i, r in enumerate(records):
        m = {k: v for k, v in r.items() if k != args.text_field}
        m['chunk_text'] = r.get(args.text_field, '')
        meta[str(i)] = m
    with open(meta_path, 'w') as f:
        json.dump(meta, f, ensure_ascii=False)
    return len(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-dir', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--model', default='ncbi/MedCPT-Article-Encoder')
    ap.add_argument('--text-field', default='text')
    ap.add_argument('--max-length', type=int, default=512)
    ap.add_argument('--batch-size', type=int, default=64)
    ap.add_argument('--no-fp16', dest='fp16', action='store_false', default=True)
    ap.add_argument('--device', default='auto')
    args = ap.parse_args()

    import torch
    device = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device == 'cpu':
        log("WARNING: running on CPU — this is for GPU; expect ~1 text/s. Use a GPU runtime.")
    log(f"device={device} model={args.model} fp16={args.fp16}")
    tok, model = load_model(args.model, device, args.fp16)

    shards = sorted(glob.glob(os.path.join(args.input_dir, '*.jsonl')))
    log(f"{len(shards)} input shards in {args.input_dir}")
    os.makedirs(args.output_dir, exist_ok=True)
    total, done = 0, 0
    t0 = time.time()
    for i, sp in enumerate(shards, 1):
        n = process_shard(sp, args.output_dir, tok, model, device, args)
        if n == -1:
            done += 1; continue
        total += max(0, n)
        rate = total / max(1e-9, time.time() - t0)
        log(f"[{i}/{len(shards)}] {os.path.basename(sp)} -> {n} vecs | total {total:,} | {rate:.0f} vec/s")
    log(f"DONE: {total:,} new vectors ({done} shards already present)")


if __name__ == '__main__':
    main()
