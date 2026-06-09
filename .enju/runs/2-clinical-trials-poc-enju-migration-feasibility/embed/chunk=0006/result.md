[2026-06-09 14:35:14] [MEM: 481.4MB] System RAM: 125.7GB total, 115.2GB available
[2026-06-09 14:35:14] [MEM: 481.4MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0006.json
[2026-06-09 14:35:14] [MEM: 482.2MB] Loaded 40 trials from chunk file
[2026-06-09 14:35:14] [MEM: 482.2MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 14:35:14] [MEM: 482.2MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:35:14] [MEM: 482.2MB] Using device: cpu
[2026-06-09 14:35:18] [MEM: 504.9MB] CPU workers: 1
[2026-06-09 14:35:18] [MEM: 846.3MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:35:18] [MEM: 846.3MB] Processing chunk with 40 trials...
[2026-06-09 14:35:18] [MEM: 846.4MB] Generated 236 text chunks from 40 trials
[2026-06-09 14:35:18] [MEM: 846.4MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:35:22] [MEM: 927.6MB] Generated 236 embeddings with dimension 768
[2026-06-09 14:35:22] [MEM: 927.6MB] Generated 236 embeddings from 40 trials
[2026-06-09 14:35:22] [MEM: 927.6MB] Creating FAISS index for 236 vectors...
[2026-06-09 14:35:22] [MEM: 928.0MB] FAISS index created: 236 vectors
[2026-06-09 14:35:22] [MEM: 928.0MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0006.index
[2026-06-09 14:35:22] [MEM: 928.2MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0006_meta.json
[2026-06-09 14:35:22] [MEM: 928.2MB] Files saved successfully:
[2026-06-09 14:35:22] [MEM: 928.2MB]   Index: 0.7MB
[2026-06-09 14:35:22] [MEM: 928.2MB]   Metadata: 1.7MB
[2026-06-09 14:35:22] [MEM: 928.2MB] === Clinical Trials Chunk Processing Complete ===
