#!/usr/bin/env python3
"""Export (payload incl. text) JSONL shards from a Qdrant collection — the LOCAL feed for
embed_text_medcpt_gpu.py (the MedCPT migration, #Q1).

Scrolls a collection and writes shards where each record = the point's full payload with the
text normalized under key 'text'. The whole payload is preserved so the re-embedded points
keep their ids/discriminators (pmid / nct_id+global_chunk_id / patent_id / chunk_type ...).
Then: rclone push the shards to gdrive:bioyoda/medcpt_input/<collection>/ and embed on Colab.

NOTE on text availability: pubmed/clinical_trials store the FULL text in payload
('chunk_text') — the 75-token truncation was at EMBED time, not storage, so re-embedding from
payload recovers the full text. patents_text mostly stored title-only payload (older points
have no full combined text) → those need a re-PARSE from raw instead of this export. Use
--text-field accordingly and check the skipped count.

Usage (Qdrant must be up):
    python scripts/gpu/export_text_for_embed.py --collection pubmed_abstracts \
        --text-field chunk_text --output-dir work/data/medcpt_input/pubmed_abstracts
    ./bioyoda.sh ... (or rclone copy that dir to gdrive:bioyoda/medcpt_input/pubmed_abstracts)
"""
import os, json, argparse, time


def main():
    from qdrant_client import QdrantClient
    ap = argparse.ArgumentParser()
    ap.add_argument('--qdrant-url', default='http://localhost:6333')
    ap.add_argument('--collection', required=True)
    ap.add_argument('--text-field', default='chunk_text', help="payload key holding the text (pubmed/CT: chunk_text)")
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--shard-size', type=int, default=50000)
    ap.add_argument('--scroll-batch', type=int, default=10000)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    c = QdrantClient(url=args.qdrant_url, timeout=600)
    off = None; n = 0; skipped = 0; shard = 0; buf = []
    t0 = time.time()

    def flush():
        nonlocal shard, buf
        if not buf:
            return
        p = os.path.join(args.output_dir, f"shard_{shard:05d}.jsonl")
        with open(p, 'w') as f:
            for r in buf:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        shard += 1; buf = []

    while True:
        pts, off = c.scroll(args.collection, with_payload=True, with_vectors=False,
                            limit=args.scroll_batch, offset=off)
        for p in pts:
            pl = p.payload or {}
            txt = pl.get(args.text_field) or ''
            if not txt:
                skipped += 1
                continue
            rec = dict(pl)
            rec['text'] = txt          # normalize text under 'text' for the embed script
            buf.append(rec); n += 1
            if len(buf) >= args.shard_size:
                flush()
        if n and n % 500000 < args.scroll_batch:
            print(f"[{time.strftime('%H:%M:%S')}] exported {n:,}  skipped(no-text) {skipped:,}  "
                  f"({n/max(1e-9,time.time()-t0):.0f}/s)", flush=True)
        if off is None:
            break
    flush()
    print(f"DONE: {n:,} records -> {shard} shards in {args.output_dir}  (skipped no-text: {skipped:,})")
    if skipped > n:
        print("WARNING: more skipped than exported — this collection likely lacks full text in "
              "payload; re-parse from raw instead of exporting from Qdrant.")


if __name__ == '__main__':
    main()
