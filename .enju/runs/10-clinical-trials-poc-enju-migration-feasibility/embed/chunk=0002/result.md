[2026-06-09 16:25:26] [MEM: 481.7MB] System RAM: 125.7GB total, 115.8GB available
[2026-06-09 16:25:26] [MEM: 481.7MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0002.json
[2026-06-09 16:25:26] [MEM: 482.6MB] Loaded 50 trials from chunk file
[2026-06-09 16:25:26] [MEM: 482.6MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 16:25:26] [MEM: 482.6MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:25:26] [MEM: 482.6MB] Using device: cpu
[2026-06-09 16:25:30] [MEM: 506.3MB] CPU workers: 1
[2026-06-09 16:25:30] [MEM: 847.8MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:25:30] [MEM: 847.8MB] Processing chunk with 50 trials...
[2026-06-09 16:25:30] [MEM: 847.8MB] Generated 363 text chunks from 50 trials
[2026-06-09 16:25:30] [MEM: 847.8MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:25:36] [MEM: 935.6MB] Generated 363 embeddings with dimension 768
[2026-06-09 16:25:36] [MEM: 935.6MB] Generated 363 embeddings from 50 trials
[2026-06-09 16:25:36] [MEM: 935.6MB] Creating FAISS index for 363 vectors...
[2026-06-09 16:25:36] [MEM: 936.0MB] FAISS index created: 363 vectors
[2026-06-09 16:25:36] [MEM: 936.0MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0002.index
[2026-06-09 16:25:36] [MEM: 936.2MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0002_meta.json
[2026-06-09 16:25:36] [MEM: 936.2MB] Files saved successfully:
[2026-06-09 16:25:36] [MEM: 936.2MB]   Index: 1.1MB
[2026-06-09 16:25:36] [MEM: 936.2MB]   Metadata: 1.4MB
[2026-06-09 16:25:36] [MEM: 936.2MB] === Clinical Trials Chunk Processing Complete ===
