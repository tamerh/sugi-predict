[2026-06-09 15:01:21] [MEM: 115.5MB] ================================================================================
[2026-06-09 15:01:21] [MEM: 115.5MB] FAISS to Qdrant Sequential Insertion
[2026-06-09 15:01:21] [MEM: 115.5MB] ================================================================================
[2026-06-09 15:01:21] [MEM: 115.5MB] FAISS directory: test_out/pubmed_poc/processed
[2026-06-09 15:01:21] [MEM: 115.5MB] Collection: poc_pubmed
[2026-06-09 15:01:21] [MEM: 115.5MB] Qdrant URL: http://localhost:6333
[2026-06-09 15:01:21] [MEM: 115.5MB] Batch size: 200
[2026-06-09 15:01:21] [MEM: 115.5MB] Starting point ID: 0
[2026-06-09 15:01:21] [MEM: 115.5MB] 
[2026-06-09 15:01:21] [MEM: 115.5MB] Connecting to Qdrant...
[2026-06-09 15:01:21] [MEM: 122.3MB] ✓ Connected via HTTP
[2026-06-09 15:01:21] [MEM: 122.3MB]   Existing collections: 0
[2026-06-09 15:01:21] [MEM: 122.3MB]   Timeout: 300 seconds
[2026-06-09 15:01:21] [MEM: 122.3MB]   Tip: Use --prefer-grpc for 20-30% faster bulk inserts
[2026-06-09 15:01:21] [MEM: 122.4MB] Creating collection 'poc_pubmed'...
[2026-06-09 15:01:21] [MEM: 122.4MB]   ✓ Scalar quantization ENABLED (int8, quantile=0.99)
[2026-06-09 15:01:21] [MEM: 122.4MB]   HNSW config: m=16, ef_construct=100
[2026-06-09 15:01:21] [MEM: 122.4MB]   Segment config: default_segment_number=2, max_segment_size=2,000,000 points
[2026-06-09 15:01:21] [MEM: 122.4MB]   Indexing threshold: 1,000,000 points (higher = fewer segments during bulk insert)
[2026-06-09 15:01:22] [MEM: 122.4MB] Collection 'poc_pubmed' created with quantization=True
[2026-06-09 15:01:22] [MEM: 122.4MB] Found 1 FAISS files to process
[2026-06-09 15:01:22] [MEM: 122.4MB] 
[2026-06-09 15:01:22] [MEM: 123.2MB] Point ID strategy: pmid
[2026-06-09 15:01:22] [MEM: 123.2MB]   Using PMID as point ID (enables upsert for incremental updates)
[2026-06-09 15:01:22] [MEM: 123.2MB] 
[2026-06-09 15:01:22] [MEM: 123.2MB] [1/1] test_abstracts.index
[2026-06-09 15:01:22] [MEM: 123.3MB]   └─ Vectors: 50
[2026-06-09 15:01:22] [MEM: 126.6MB] Inserted final batch
[2026-06-09 15:01:22] [MEM: 126.6MB] 
[2026-06-09 15:01:22] [MEM: 126.6MB] ================================================================================
[2026-06-09 15:01:22] [MEM: 126.6MB] Insertion complete!
[2026-06-09 15:01:22] [MEM: 126.6MB] Total vectors inserted: 50
[2026-06-09 15:01:22] [MEM: 126.6MB] Final point ID: 50
[2026-06-09 15:01:22] [MEM: 126.6MB] ================================================================================
[2026-06-09 15:01:22] [MEM: 126.6MB] 
[2026-06-09 15:01:22] [MEM: 126.6MB] ================================================================================
[2026-06-09 15:01:22] [MEM: 126.6MB] WAITING FOR COLLECTION OPTIMIZATION
[2026-06-09 15:01:22] [MEM: 126.6MB] ================================================================================
[2026-06-09 15:01:22] [MEM: 126.6MB] Collection is optimizing in background (HNSW indexing, segment merging)
[2026-06-09 15:01:22] [MEM: 126.6MB] This is normal after bulk insertion - wait for GREEN status before queries
[2026-06-09 15:01:22] [MEM: 126.6MB] 
[2026-06-09 15:01:22] [MEM: 126.7MB] 
[2026-06-09 15:01:22] [MEM: 126.7MB] ✓ Collection is GREEN after 0s
[2026-06-09 15:01:22] [MEM: 126.7MB]   Points: 50
[2026-06-09 15:01:22] [MEM: 126.7MB]   Indexed: 0 (0.0%)
[2026-06-09 15:01:22] [MEM: 126.7MB]   Segments: 2
[2026-06-09 15:01:22] [MEM: 126.7MB]   Collection is ready for queries!
[2026-06-09 15:01:22] [MEM: 126.7MB] 
[2026-06-09 15:01:22] [MEM: 126.7MB] ================================================================================
[2026-06-09 15:01:22] [MEM: 126.7MB] COLLECTION READY FOR PRODUCTION
[2026-06-09 15:01:22] [MEM: 126.7MB] ================================================================================
[2026-06-09 15:01:22] [MEM: 126.7MB] Total insertion time: (see logs above)
[2026-06-09 15:01:22] [MEM: 126.7MB] Optimization time: 0s (0.0 minutes)
[2026-06-09 15:01:22] [MEM: 126.7MB] Final status: GREEN
[2026-06-09 15:01:22] [MEM: 126.7MB] ================================================================================
