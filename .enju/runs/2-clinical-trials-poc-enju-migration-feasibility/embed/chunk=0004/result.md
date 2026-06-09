[2026-06-09 14:35:01] [MEM: 481.7MB] System RAM: 125.7GB total, 115.9GB available
[2026-06-09 14:35:01] [MEM: 481.7MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0004.json
[2026-06-09 14:35:01] [MEM: 482.6MB] Loaded 50 trials from chunk file
[2026-06-09 14:35:01] [MEM: 482.6MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 14:35:01] [MEM: 482.6MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:35:01] [MEM: 482.6MB] Using device: cpu
[2026-06-09 14:35:04] [MEM: 505.3MB] CPU workers: 1
[2026-06-09 14:35:04] [MEM: 846.8MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:35:04] [MEM: 846.8MB] Processing chunk with 50 trials...
[2026-06-09 14:35:04] [MEM: 846.9MB] Generated 330 text chunks from 50 trials
[2026-06-09 14:35:04] [MEM: 846.9MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:35:11] [MEM: 932.0MB] Generated 330 embeddings with dimension 768
[2026-06-09 14:35:11] [MEM: 932.0MB] Generated 330 embeddings from 50 trials
[2026-06-09 14:35:11] [MEM: 932.0MB] Creating FAISS index for 330 vectors...
[2026-06-09 14:35:11] [MEM: 932.3MB] FAISS index created: 330 vectors
[2026-06-09 14:35:11] [MEM: 932.3MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0004.index
[2026-06-09 14:35:11] [MEM: 932.5MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0004_meta.json
[2026-06-09 14:35:11] [MEM: 932.5MB] Files saved successfully:
[2026-06-09 14:35:11] [MEM: 932.5MB]   Index: 1.0MB
[2026-06-09 14:35:11] [MEM: 932.5MB]   Metadata: 1.4MB
[2026-06-09 14:35:11] [MEM: 932.5MB] === Clinical Trials Chunk Processing Complete ===
