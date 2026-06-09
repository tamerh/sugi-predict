[2026-06-09 14:33:54] [MEM: 475.8MB] System RAM: 125.7GB total, 115.2GB available
[2026-06-09 14:33:54] [MEM: 475.8MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0001.json
[2026-06-09 14:33:54] [MEM: 477.2MB] Loaded 50 trials from chunk file
[2026-06-09 14:33:54] [MEM: 477.2MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 14:33:54] [MEM: 477.2MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:33:54] [MEM: 477.2MB] Using device: cpu
[2026-06-09 14:33:58] [MEM: 501.1MB] CPU workers: 1
[2026-06-09 14:33:58] [MEM: 842.4MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:33:58] [MEM: 842.4MB] Processing chunk with 50 trials...
[2026-06-09 14:33:58] [MEM: 842.4MB] Generated 423 text chunks from 50 trials
[2026-06-09 14:33:58] [MEM: 842.4MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:34:46] [MEM: 936.2MB] Generated 423 embeddings with dimension 768
[2026-06-09 14:34:46] [MEM: 936.2MB] Generated 423 embeddings from 50 trials
[2026-06-09 14:34:46] [MEM: 936.2MB] Creating FAISS index for 423 vectors...
[2026-06-09 14:34:46] [MEM: 936.6MB] FAISS index created: 423 vectors
[2026-06-09 14:34:46] [MEM: 936.6MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0001.index
[2026-06-09 14:34:46] [MEM: 936.8MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0001_meta.json
[2026-06-09 14:34:46] [MEM: 936.8MB] Files saved successfully:
[2026-06-09 14:34:46] [MEM: 936.8MB]   Index: 1.2MB
[2026-06-09 14:34:46] [MEM: 936.8MB]   Metadata: 2.3MB
[2026-06-09 14:34:46] [MEM: 936.8MB] === Clinical Trials Chunk Processing Complete ===
