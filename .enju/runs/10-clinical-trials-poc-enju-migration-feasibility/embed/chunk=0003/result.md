[2026-06-09 16:25:45] [MEM: 481.4MB] System RAM: 125.7GB total, 115.9GB available
[2026-06-09 16:25:45] [MEM: 481.4MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0003.json
[2026-06-09 16:25:45] [MEM: 482.5MB] Loaded 50 trials from chunk file
[2026-06-09 16:25:45] [MEM: 482.5MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 16:25:45] [MEM: 482.5MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:25:45] [MEM: 482.5MB] Using device: cpu
[2026-06-09 16:25:49] [MEM: 506.1MB] CPU workers: 1
[2026-06-09 16:25:49] [MEM: 847.6MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:25:49] [MEM: 847.6MB] Processing chunk with 50 trials...
[2026-06-09 16:25:49] [MEM: 847.6MB] Generated 426 text chunks from 50 trials
[2026-06-09 16:25:49] [MEM: 847.6MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:25:56] [MEM: 945.2MB] Generated 426 embeddings with dimension 768
[2026-06-09 16:25:56] [MEM: 945.2MB] Generated 426 embeddings from 50 trials
[2026-06-09 16:25:56] [MEM: 945.2MB] Creating FAISS index for 426 vectors...
[2026-06-09 16:25:56] [MEM: 945.6MB] FAISS index created: 426 vectors
[2026-06-09 16:25:56] [MEM: 945.6MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0003.index
[2026-06-09 16:25:56] [MEM: 945.8MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0003_meta.json
[2026-06-09 16:25:56] [MEM: 945.8MB] Files saved successfully:
[2026-06-09 16:25:56] [MEM: 945.8MB]   Index: 1.2MB
[2026-06-09 16:25:56] [MEM: 945.8MB]   Metadata: 1.9MB
[2026-06-09 16:25:56] [MEM: 945.8MB] === Clinical Trials Chunk Processing Complete ===
