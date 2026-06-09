[2026-06-09 16:25:06] [MEM: 481.5MB] System RAM: 125.7GB total, 115.9GB available
[2026-06-09 16:25:06] [MEM: 481.5MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0001.json
[2026-06-09 16:25:06] [MEM: 482.9MB] Loaded 50 trials from chunk file
[2026-06-09 16:25:06] [MEM: 482.9MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 16:25:06] [MEM: 482.9MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:25:06] [MEM: 482.9MB] Using device: cpu
[2026-06-09 16:25:10] [MEM: 506.4MB] CPU workers: 1
[2026-06-09 16:25:10] [MEM: 847.8MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:25:10] [MEM: 847.8MB] Processing chunk with 50 trials...
[2026-06-09 16:25:10] [MEM: 847.9MB] Generated 423 text chunks from 50 trials
[2026-06-09 16:25:10] [MEM: 847.9MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:25:17] [MEM: 935.9MB] Generated 423 embeddings with dimension 768
[2026-06-09 16:25:17] [MEM: 935.9MB] Generated 423 embeddings from 50 trials
[2026-06-09 16:25:17] [MEM: 935.9MB] Creating FAISS index for 423 vectors...
[2026-06-09 16:25:17] [MEM: 937.4MB] FAISS index created: 423 vectors
[2026-06-09 16:25:17] [MEM: 937.4MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0001.index
[2026-06-09 16:25:17] [MEM: 937.6MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0001_meta.json
[2026-06-09 16:25:17] [MEM: 937.6MB] Files saved successfully:
[2026-06-09 16:25:17] [MEM: 937.6MB]   Index: 1.2MB
[2026-06-09 16:25:17] [MEM: 937.6MB]   Metadata: 2.3MB
[2026-06-09 16:25:17] [MEM: 937.6MB] === Clinical Trials Chunk Processing Complete ===
