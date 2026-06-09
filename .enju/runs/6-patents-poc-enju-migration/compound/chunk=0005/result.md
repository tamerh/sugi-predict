[2026-06-09 14:56:09] [MEM: 123.0MB] System RAM: 125.7GB total, 116.2GB available
[2026-06-09 14:56:09] [MEM: 123.0MB] === Starting Compound Processing (Streaming Mode) ===
[2026-06-09 14:56:09] [MEM: 150.4MB] RDKit loaded successfully (using MorganGenerator)
[2026-06-09 14:56:09] [MEM: 150.4MB] === Step 3: Processing compounds in batches ===
[2026-06-09 14:56:09] [MEM: 150.4MB] Counting total compounds to process...
[2026-06-09 14:56:09] [MEM: 150.4MB] Total compounds to process: 2,000
[2026-06-09 14:56:09] [MEM: 150.4MB] Estimated memory needed: 0.02 GB
[2026-06-09 14:56:09] [MEM: 150.4MB] Pre-allocating final array (2000 x 2048)...
[2026-06-09 14:56:09] [MEM: 150.4MB] Successfully allocated 0.02 GB array
[2026-06-09 14:56:09] [MEM: 150.4MB] Loading compounds from snapshots/raw_data/patents/chunked_compounds/compounds_chunk_0005.parquet
[2026-06-09 14:56:09] [MEM: 157.2MB] Total compounds in file: 500,000
[2026-06-09 14:56:09] [MEM: 157.2MB] Will process: 2,000 compounds
[2026-06-09 14:56:09] [MEM: 323.9MB]   Loaded batch: 2,000 / 2,000 compounds
[2026-06-09 14:56:09] [MEM: 323.9MB] Processing batch 1 with 2,000 compounds
[2026-06-09 14:56:09] [MEM: 323.9MB] Processing 2000 compounds...
[2026-06-09 14:56:09] [MEM: 342.6MB] Completed: 1999 valid fingerprints, 1 invalid/skipped
[2026-06-09 14:56:09] [MEM: 358.2MB] Copied 1,999 fingerprints to final array at offset 0
[2026-06-09 14:56:09] [MEM: 358.2MB] Batch 1 complete. Total processed so far: 1,999
[2026-06-09 14:56:09] [MEM: 306.6MB] Successfully processed 2,000 compound records
[2026-06-09 14:56:09] [MEM: 278.8MB] Trimming array from 2,000 to 1,999 valid compounds
[2026-06-09 14:56:09] [MEM: 278.8MB] Final fingerprints shape: (1999, 2048)
[2026-06-09 14:56:09] [MEM: 278.8MB] Creating FAISS index for 1999 fingerprints...
[2026-06-09 14:56:09] [MEM: 278.8MB] Fingerprints ready: dtype=float32, shape=(1999, 2048), C-contiguous=True
[2026-06-09 14:56:09] [MEM: 278.8MB] Creating FAISS IndexFlatL2...
[2026-06-09 14:56:09] [MEM: 279.1MB] Adding 1999 vectors to index...
[2026-06-09 14:56:09] [MEM: 294.7MB] FAISS index created: 1999 vectors
[2026-06-09 14:56:09] [MEM: 294.7MB] Saving FAISS index to test_out/patents_poc/compounds/compounds_0005.index
[2026-06-09 14:56:09] [MEM: 295.0MB] Saving metadata to test_out/patents_poc/compounds/compounds_0005.json
[2026-06-09 14:56:09] [MEM: 295.1MB] Files saved successfully:
[2026-06-09 14:56:09] [MEM: 295.1MB]   Index: 15.6MB
[2026-06-09 14:56:09] [MEM: 295.1MB]   Metadata: 0.5MB
[2026-06-09 14:56:09] [MEM: 295.1MB] === Compound Processing Complete ===
