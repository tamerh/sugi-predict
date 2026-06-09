[2026-06-09 16:28:51] [MEM: 122.8MB] System RAM: 125.7GB total, 116.2GB available
[2026-06-09 16:28:51] [MEM: 122.8MB] === Starting Compound Processing (Streaming Mode) ===
[2026-06-09 16:28:51] [MEM: 150.7MB] RDKit loaded successfully (using MorganGenerator)
[2026-06-09 16:28:51] [MEM: 150.7MB] === Step 3: Processing compounds in batches ===
[2026-06-09 16:28:51] [MEM: 150.7MB] Counting total compounds to process...
[2026-06-09 16:28:51] [MEM: 150.7MB] Total compounds to process: 2,000
[2026-06-09 16:28:51] [MEM: 150.7MB] Estimated memory needed: 0.02 GB
[2026-06-09 16:28:51] [MEM: 150.7MB] Pre-allocating final array (2000 x 2048)...
[2026-06-09 16:28:51] [MEM: 150.7MB] Successfully allocated 0.02 GB array
[2026-06-09 16:28:51] [MEM: 150.7MB] Loading compounds from snapshots/raw_data/patents/chunked_compounds/compounds_chunk_0002.parquet
[2026-06-09 16:28:51] [MEM: 157.5MB] Total compounds in file: 500,000
[2026-06-09 16:28:51] [MEM: 157.5MB] Will process: 2,000 compounds
[2026-06-09 16:28:51] [MEM: 325.9MB]   Loaded batch: 2,000 / 2,000 compounds
[2026-06-09 16:28:51] [MEM: 325.9MB] Processing batch 1 with 2,000 compounds
[2026-06-09 16:28:51] [MEM: 325.9MB] Processing 2000 compounds...
[2026-06-09 16:28:52] [MEM: 344.6MB] Completed: 2000 valid fingerprints, 0 invalid/skipped
[2026-06-09 16:28:52] [MEM: 360.2MB] Copied 2,000 fingerprints to final array at offset 0
[2026-06-09 16:28:52] [MEM: 360.2MB] Batch 1 complete. Total processed so far: 2,000
[2026-06-09 16:28:52] [MEM: 311.5MB] Successfully processed 2,000 compound records
[2026-06-09 16:28:52] [MEM: 289.3MB] Final fingerprints shape: (2000, 2048)
[2026-06-09 16:28:52] [MEM: 289.3MB] Creating FAISS index for 2000 fingerprints...
[2026-06-09 16:28:52] [MEM: 289.3MB] Fingerprints ready: dtype=float32, shape=(2000, 2048), C-contiguous=True
[2026-06-09 16:28:52] [MEM: 289.3MB] Creating FAISS IndexFlatL2...
[2026-06-09 16:28:52] [MEM: 289.6MB] Adding 2000 vectors to index...
[2026-06-09 16:28:52] [MEM: 304.6MB] FAISS index created: 2000 vectors
[2026-06-09 16:28:52] [MEM: 304.6MB] Saving FAISS index to test_out/patents_poc/compounds/compounds_0002.index
[2026-06-09 16:28:52] [MEM: 304.8MB] Saving metadata to test_out/patents_poc/compounds/compounds_0002.json
[2026-06-09 16:28:52] [MEM: 305.0MB] Files saved successfully:
[2026-06-09 16:28:52] [MEM: 305.0MB]   Index: 15.6MB
[2026-06-09 16:28:52] [MEM: 305.0MB]   Metadata: 0.5MB
[2026-06-09 16:28:52] [MEM: 305.0MB] === Compound Processing Complete ===
