[2026-06-09 16:26:05] [MEM: 481.9MB] System RAM: 125.7GB total, 115.8GB available
[2026-06-09 16:26:05] [MEM: 481.9MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0004.json
[2026-06-09 16:26:05] [MEM: 482.8MB] Loaded 50 trials from chunk file
[2026-06-09 16:26:05] [MEM: 482.8MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 16:26:05] [MEM: 482.8MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:26:05] [MEM: 482.8MB] Using device: cpu
[2026-06-09 16:26:09] [MEM: 506.5MB] CPU workers: 1
[2026-06-09 16:26:09] [MEM: 848.0MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:26:09] [MEM: 848.0MB] Processing chunk with 50 trials...
[2026-06-09 16:26:09] [MEM: 848.0MB] Generated 330 text chunks from 50 trials
[2026-06-09 16:26:09] [MEM: 848.0MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:26:14] [MEM: 966.1MB] Generated 330 embeddings with dimension 768
[2026-06-09 16:26:14] [MEM: 966.1MB] Generated 330 embeddings from 50 trials
[2026-06-09 16:26:14] [MEM: 966.1MB] Creating FAISS index for 330 vectors...
[2026-06-09 16:26:14] [MEM: 966.5MB] FAISS index created: 330 vectors
[2026-06-09 16:26:14] [MEM: 966.5MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0004.index
[2026-06-09 16:26:14] [MEM: 966.7MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0004_meta.json
[2026-06-09 16:26:14] [MEM: 966.7MB] Files saved successfully:
[2026-06-09 16:26:14] [MEM: 966.7MB]   Index: 1.0MB
[2026-06-09 16:26:14] [MEM: 966.7MB]   Metadata: 1.4MB
[2026-06-09 16:26:14] [MEM: 966.7MB] === Clinical Trials Chunk Processing Complete ===
