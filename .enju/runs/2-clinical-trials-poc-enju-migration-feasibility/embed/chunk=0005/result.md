[2026-06-09 14:35:07] [MEM: 481.4MB] System RAM: 125.7GB total, 115.4GB available
[2026-06-09 14:35:07] [MEM: 481.4MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0005.json
[2026-06-09 14:35:07] [MEM: 482.3MB] Loaded 50 trials from chunk file
[2026-06-09 14:35:07] [MEM: 482.3MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 14:35:07] [MEM: 482.3MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:35:07] [MEM: 482.3MB] Using device: cpu
[2026-06-09 14:35:11] [MEM: 505.9MB] CPU workers: 1
[2026-06-09 14:35:11] [MEM: 847.4MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:35:11] [MEM: 847.4MB] Processing chunk with 50 trials...
[2026-06-09 14:35:11] [MEM: 847.5MB] Generated 321 text chunks from 50 trials
[2026-06-09 14:35:11] [MEM: 847.5MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:35:17] [MEM: 988.5MB] Generated 321 embeddings with dimension 768
[2026-06-09 14:35:17] [MEM: 988.5MB] Generated 321 embeddings from 50 trials
[2026-06-09 14:35:17] [MEM: 988.5MB] Creating FAISS index for 321 vectors...
[2026-06-09 14:35:17] [MEM: 988.8MB] FAISS index created: 321 vectors
[2026-06-09 14:35:17] [MEM: 988.8MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0005.index
[2026-06-09 14:35:17] [MEM: 989.0MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0005_meta.json
[2026-06-09 14:35:17] [MEM: 989.0MB] Files saved successfully:
[2026-06-09 14:35:17] [MEM: 989.0MB]   Index: 0.9MB
[2026-06-09 14:35:17] [MEM: 989.0MB]   Metadata: 1.2MB
[2026-06-09 14:35:17] [MEM: 989.0MB] === Clinical Trials Chunk Processing Complete ===
