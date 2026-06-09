[2026-06-09 14:33:54] [MEM: 476.1MB] System RAM: 125.7GB total, 115.2GB available
[2026-06-09 14:33:54] [MEM: 476.1MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0002.json
[2026-06-09 14:33:54] [MEM: 477.0MB] Loaded 50 trials from chunk file
[2026-06-09 14:33:54] [MEM: 477.0MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 14:33:54] [MEM: 477.0MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:33:54] [MEM: 477.0MB] Using device: cpu
[2026-06-09 14:33:58] [MEM: 500.6MB] CPU workers: 1
[2026-06-09 14:33:59] [MEM: 842.0MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:33:59] [MEM: 842.0MB] Processing chunk with 50 trials...
[2026-06-09 14:33:59] [MEM: 842.1MB] Generated 363 text chunks from 50 trials
[2026-06-09 14:33:59] [MEM: 842.1MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:34:45] [MEM: 930.2MB] Generated 363 embeddings with dimension 768
[2026-06-09 14:34:45] [MEM: 930.2MB] Generated 363 embeddings from 50 trials
[2026-06-09 14:34:45] [MEM: 930.2MB] Creating FAISS index for 363 vectors...
[2026-06-09 14:34:45] [MEM: 930.5MB] FAISS index created: 363 vectors
[2026-06-09 14:34:45] [MEM: 930.5MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0002.index
[2026-06-09 14:34:45] [MEM: 930.8MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0002_meta.json
[2026-06-09 14:34:45] [MEM: 930.8MB] Files saved successfully:
[2026-06-09 14:34:45] [MEM: 930.8MB]   Index: 1.1MB
[2026-06-09 14:34:45] [MEM: 930.8MB]   Metadata: 1.4MB
[2026-06-09 14:34:45] [MEM: 930.8MB] === Clinical Trials Chunk Processing Complete ===
