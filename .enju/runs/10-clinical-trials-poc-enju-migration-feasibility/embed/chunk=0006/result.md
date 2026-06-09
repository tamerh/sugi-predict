[2026-06-09 16:26:42] [MEM: 482.0MB] System RAM: 125.7GB total, 115.7GB available
[2026-06-09 16:26:42] [MEM: 482.0MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0006.json
[2026-06-09 16:26:42] [MEM: 482.8MB] Loaded 40 trials from chunk file
[2026-06-09 16:26:42] [MEM: 482.8MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 16:26:42] [MEM: 482.8MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:26:42] [MEM: 482.8MB] Using device: cpu
[2026-06-09 16:26:46] [MEM: 505.6MB] CPU workers: 1
[2026-06-09 16:26:46] [MEM: 847.1MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:26:46] [MEM: 847.1MB] Processing chunk with 40 trials...
[2026-06-09 16:26:46] [MEM: 847.1MB] Generated 236 text chunks from 40 trials
[2026-06-09 16:26:46] [MEM: 847.1MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:26:50] [MEM: 925.9MB] Generated 236 embeddings with dimension 768
[2026-06-09 16:26:50] [MEM: 925.9MB] Generated 236 embeddings from 40 trials
[2026-06-09 16:26:50] [MEM: 925.9MB] Creating FAISS index for 236 vectors...
[2026-06-09 16:26:50] [MEM: 926.8MB] FAISS index created: 236 vectors
[2026-06-09 16:26:50] [MEM: 926.8MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0006.index
[2026-06-09 16:26:50] [MEM: 927.0MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0006_meta.json
[2026-06-09 16:26:50] [MEM: 927.1MB] Files saved successfully:
[2026-06-09 16:26:50] [MEM: 927.1MB]   Index: 0.7MB
[2026-06-09 16:26:50] [MEM: 927.1MB]   Metadata: 1.7MB
[2026-06-09 16:26:50] [MEM: 927.1MB] === Clinical Trials Chunk Processing Complete ===
