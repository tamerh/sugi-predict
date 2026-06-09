[2026-06-09 16:26:24] [MEM: 481.5MB] System RAM: 125.7GB total, 115.8GB available
[2026-06-09 16:26:24] [MEM: 481.5MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0005.json
[2026-06-09 16:26:24] [MEM: 482.4MB] Loaded 50 trials from chunk file
[2026-06-09 16:26:24] [MEM: 482.4MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 16:26:24] [MEM: 482.4MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:26:24] [MEM: 482.4MB] Using device: cpu
[2026-06-09 16:26:27] [MEM: 506.1MB] CPU workers: 1
[2026-06-09 16:26:27] [MEM: 847.6MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:26:27] [MEM: 847.6MB] Processing chunk with 50 trials...
[2026-06-09 16:26:27] [MEM: 847.6MB] Generated 321 text chunks from 50 trials
[2026-06-09 16:26:27] [MEM: 847.6MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:26:33] [MEM: 932.4MB] Generated 321 embeddings with dimension 768
[2026-06-09 16:26:33] [MEM: 932.4MB] Generated 321 embeddings from 50 trials
[2026-06-09 16:26:33] [MEM: 932.4MB] Creating FAISS index for 321 vectors...
[2026-06-09 16:26:33] [MEM: 934.5MB] FAISS index created: 321 vectors
[2026-06-09 16:26:33] [MEM: 934.5MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0005.index
[2026-06-09 16:26:33] [MEM: 934.7MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0005_meta.json
[2026-06-09 16:26:33] [MEM: 934.7MB] Files saved successfully:
[2026-06-09 16:26:33] [MEM: 934.7MB]   Index: 0.9MB
[2026-06-09 16:26:33] [MEM: 934.7MB]   Metadata: 1.2MB
[2026-06-09 16:26:33] [MEM: 934.7MB] === Clinical Trials Chunk Processing Complete ===
