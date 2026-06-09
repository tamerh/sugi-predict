[2026-06-09 16:28:38] [MEM: 482.2MB] System RAM: 125.7GB total, 116.0GB available
[2026-06-09 16:28:38] [MEM: 482.2MB] === Starting Patent Processing ===
[2026-06-09 16:28:38] [MEM: 482.2MB] Loading model: pritamdeka/S-BioBERT-snli-multinli-stsb
[2026-06-09 16:28:38] [MEM: 482.2MB] Using device: cpu
[2026-06-09 16:28:41] [MEM: 506.1MB] CPU workers: 1
[2026-06-09 16:28:41] [MEM: 847.6MB] Model loaded successfully. Dimension: 768
[2026-06-09 16:28:41] [MEM: 847.6MB] Loading patents from snapshots/raw_data/patents/surechembl/2025-12-15/patents.parquet
[2026-06-09 16:28:41] [MEM: 857.7MB] Total patents in file: 43,821,244
[2026-06-09 16:28:41] [MEM: 857.7MB] Will process: 200 patents
[2026-06-09 16:28:42] [MEM: 1149.1MB]   Loaded batch: 200 / 200 patents
[2026-06-09 16:28:42] [MEM: 1149.2MB] Successfully loaded 200 patent records
[2026-06-09 16:28:42] [MEM: 1100.2MB] Processing batch with 200 patents...
[2026-06-09 16:28:42] [MEM: 1100.2MB] Generated 179 text chunks from 200 patents
[2026-06-09 16:28:42] [MEM: 1100.2MB] Generating embeddings (batch_size=32)...
[2026-06-09 16:28:45] [MEM: 1151.5MB] Generated 179 embeddings with dimension 768
[2026-06-09 16:28:45] [MEM: 1151.5MB] Generated 179 embeddings from 200 patents
[2026-06-09 16:28:45] [MEM: 1151.5MB] Creating FAISS index for 179 vectors...
[2026-06-09 16:28:45] [MEM: 1151.8MB] FAISS index created: 179 vectors
[2026-06-09 16:28:45] [MEM: 1151.8MB] Saving FAISS index to test_out/patents_poc/text/patents_text.index
[2026-06-09 16:28:45] [MEM: 1152.1MB] Saving metadata to test_out/patents_poc/text/patents_text.json
[2026-06-09 16:28:45] [MEM: 1152.1MB] Files saved successfully:
[2026-06-09 16:28:45] [MEM: 1152.1MB]   Index: 0.5MB
[2026-06-09 16:28:45] [MEM: 1152.1MB]   Metadata: 0.2MB
[2026-06-09 16:28:45] [MEM: 1152.1MB] === Patent Processing Complete ===
