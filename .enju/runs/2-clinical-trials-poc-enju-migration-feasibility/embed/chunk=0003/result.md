[2026-06-09 14:33:54] [MEM: 478.1MB] System RAM: 125.7GB total, 115.2GB available
[2026-06-09 14:33:54] [MEM: 478.1MB] Loading trial chunk from test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_0003.json
[2026-06-09 14:33:54] [MEM: 479.2MB] Loaded 50 trials from chunk file
[2026-06-09 14:33:54] [MEM: 479.2MB] === Starting Clinical Trials Chunk Processing ===
[2026-06-09 14:33:54] [MEM: 479.2MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:33:54] [MEM: 479.2MB] Using device: cpu
[2026-06-09 14:33:58] [MEM: 501.8MB] CPU workers: 1
[2026-06-09 14:34:02] [MEM: 843.6MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:34:02] [MEM: 843.6MB] Processing chunk with 50 trials...
[2026-06-09 14:34:02] [MEM: 843.7MB] Generated 426 text chunks from 50 trials
[2026-06-09 14:34:02] [MEM: 843.7MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:34:47] [MEM: 951.2MB] Generated 426 embeddings with dimension 768
[2026-06-09 14:34:47] [MEM: 951.2MB] Generated 426 embeddings from 50 trials
[2026-06-09 14:34:47] [MEM: 951.2MB] Creating FAISS index for 426 vectors...
[2026-06-09 14:34:47] [MEM: 951.6MB] FAISS index created: 426 vectors
[2026-06-09 14:34:47] [MEM: 951.6MB] Saving FAISS index to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0003.index
[2026-06-09 14:34:47] [MEM: 951.8MB] Saving metadata to test_out/ct_poc/data/processed/clinical_trials/full/trials_chunk_0003_meta.json
[2026-06-09 14:34:47] [MEM: 951.9MB] Files saved successfully:
[2026-06-09 14:34:47] [MEM: 951.9MB]   Index: 1.2MB
[2026-06-09 14:34:47] [MEM: 951.9MB]   Metadata: 1.9MB
[2026-06-09 14:34:47] [MEM: 951.9MB] === Clinical Trials Chunk Processing Complete ===
