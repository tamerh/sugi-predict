[2026-06-09 14:56:11] [MEM: 482.0MB] System RAM: 125.7GB total, 115.9GB available
[2026-06-09 14:56:11] [MEM: 482.0MB] === Starting Patent Processing ===
[2026-06-09 14:56:11] [MEM: 482.0MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 14:56:11] [MEM: 482.0MB] Using device: cpu
[2026-06-09 14:56:15] [MEM: 506.0MB] CPU workers: 1
[2026-06-09 14:56:15] [MEM: 847.4MB] Model loaded successfully. Dimension: 768
[2026-06-09 14:56:15] [MEM: 847.4MB] Loading patents from snapshots/raw_data/patents/surechembl/2025-12-15/patents.parquet
[2026-06-09 14:56:15] [MEM: 857.6MB] Total patents in file: 43,821,244
[2026-06-09 14:56:15] [MEM: 857.6MB] Will process: 200 patents
[2026-06-09 14:56:15] [MEM: 1165.8MB]   Loaded batch: 200 / 200 patents
[2026-06-09 14:56:15] [MEM: 1165.9MB] Successfully loaded 200 patent records
[2026-06-09 14:56:15] [MEM: 1117.2MB] Processing batch with 200 patents...
[2026-06-09 14:56:15] [MEM: 1117.2MB] Generated 179 text chunks from 200 patents
[2026-06-09 14:56:15] [MEM: 1117.2MB] Generating embeddings (batch_size=32)...
[2026-06-09 14:56:18] [MEM: 1199.0MB] Generated 179 embeddings with dimension 768
[2026-06-09 14:56:18] [MEM: 1199.0MB] Generated 179 embeddings from 200 patents
[2026-06-09 14:56:18] [MEM: 1199.0MB] Creating FAISS index for 179 vectors...
[2026-06-09 14:56:18] [MEM: 1199.3MB] FAISS index created: 179 vectors
[2026-06-09 14:56:18] [MEM: 1199.3MB] Saving FAISS index to test_out/patents_poc/text/patents_text.index
[2026-06-09 14:56:18] [MEM: 1199.6MB] Saving metadata to test_out/patents_poc/text/patents_text.json
[2026-06-09 14:56:18] [MEM: 1199.6MB] Files saved successfully:
[2026-06-09 14:56:18] [MEM: 1199.6MB]   Index: 0.5MB
[2026-06-09 14:56:18] [MEM: 1199.6MB]   Metadata: 0.2MB
[2026-06-09 14:56:18] [MEM: 1199.6MB] === Patent Processing Complete ===
