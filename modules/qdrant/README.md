# Qdrant Infrastructure Module

Automatic vector database insertion for BioYoda datasets.

## Overview

The Qdrant module is an **infrastructure module** that automatically inserts processed data from dataset modules (PubMed, Clinical Trials) into Qdrant vector database. It is **not run standalone** - instead, it's automatically triggered when you run dataset modules.

**Key Concept**: When you run `./bioyoda.sh run pubmed`, the system:
1. Creates FAISS indices (PubMed module's job)
2. Auto-starts Qdrant server (this module)
3. Sequentially inserts FAISS data to Qdrant (this module)

## Architecture

### Sequential Insertion from Unmerged FAISS

```
PubMed Module → 1200 FAISS files (parallel creation on cluster)
  ↓
Qdrant Module:
  1. Auto-start Qdrant server on cluster node
  2. Create connection_info.txt
  3. Sequential insertion:
     - Read FAISS file #1 → batch insert to Qdrant
     - Read FAISS file #2 → batch insert to Qdrant
     - ... (1200 files)
  4. Mark completion
```

**Why Sequential?**
- ✅ Avoids network chaos (1200 parallel connections would bottleneck)
- ✅ Reuses existing parallel FAISS creation
- ✅ **Skips expensive merge step** (no 90GB file needed!)
- ✅ Memory efficient (~100MB constant)

### Snakemake Dependency Chain

```python
# modules/Snakefile

rule pubmed:
    input:
        rules.pubmed_all.input,                     # FAISS creation
        rules.insert_pubmed_to_qdrant.output.done  # Auto-trigger Qdrant

# modules/qdrant/Snakefile

rule start_qdrant_server:
    output:
        connection_info = "data/qdrant/connection_info.txt"

rule insert_pubmed_to_qdrant:
    input:
        faiss_dir = "data/processed/pubmed",        # Waits for FAISS
        connection_info = ...                        # Waits for server
    output:
        done = "data/qdrant/collections/pubmed_abstracts.done"
```

**Snakemake automatically ensures:**
- All FAISS files are complete before insertion starts
- Qdrant server is running before insertion starts
- Sequential execution (no parallel chaos)

## Directory Structure

```
modules/qdrant/
├── README.md                      # This file
├── TESTING.md                     # Testing guide
├── Snakefile                      # Workflow rules
├── scripts/
│   └── insert_from_faiss.py      # Sequential insertion script
└── setup/
    ├── build_container.sh         # Singularity container builder
    └── singularity/
        ├── qdrant.def             # Container definition
        ├── config.yaml            # Qdrant server config
        └── qdrant.sif             # Built container (created by script)
```

## One-Time Setup

### Build Singularity Container

```bash
cd modules/qdrant/setup
./build_container.sh
```

**Creates:** `singularity/qdrant.sif` (~500MB)

Only needs to be done once. The container is used by Snakemake to run Qdrant server.

## Usage (Automatic)

### Through Dataset Modules

```bash
# Run PubMed - Qdrant insertion happens automatically
./bioyoda.sh run pubmed --cluster --bg --jobs 50

# What happens:
# 1. PubMed creates FAISS files (parallel)
# 2. Qdrant server auto-starts (this module)
# 3. FAISS data sequentially inserted to Qdrant (this module)
# 4. Collection 'pubmed_abstracts' created
```

### Monitor Qdrant Insertion

```bash
# Check Qdrant server log
tail -f logs/qdrant/server.log

# Check insertion progress
tail -f logs/qdrant/insert_pubmed.log

# Detailed script logs
tail -f logs/qdrant/insert_YYYYMMDD_HHMMSS.log
```

### Check Status

```bash
# Overall status
./bioyoda.sh status

# Qdrant-specific validation
./bioyoda.sh validate qdrant
```

## How It Works

### 1. Server Auto-Start

When dataset module triggers Qdrant:

```bash
# Snakemake submits Qdrant server job
qsub -N qdrant_server -l h_vmem=128G,h_rt=48:00:00 ...

# Server creates connection info
cat data/qdrant/connection_info.txt
# QDRANT_HOST=node042
# QDRANT_PORT=6333
# QDRANT_URL=http://node042:6333
```

### 2. Sequential Insertion

```python
# modules/qdrant/scripts/insert_from_faiss.py

# Find all FAISS files
faiss_files = glob("data/processed/pubmed/**/*.index")  # ~1200 files

# Process sequentially
for faiss_file in sorted(faiss_files):
    # Load small FAISS index (~25-50MB)
    index = faiss.read_index(faiss_file)
    metadata = load_metadata(faiss_file)

    # Extract vectors
    vectors = index.reconstruct_n(0, index.ntotal)

    # Batch insert to Qdrant
    for batch in chunks(vectors, batch_size=1000):
        client.upsert(collection="pubmed_abstracts", points=batch)

    # Clear memory
    del index, vectors, metadata
    gc.collect()
```

**Memory Profile:**
- Per FAISS file: ~25-50MB
- Batch buffer: ~3MB
- Total: ~100MB constant (no growth)

### 3. Collection Schema

**PubMed Collection (`pubmed_abstracts`):**
```json
{
  "id": 0,
  "vector": [0.1, 0.2, ...],  // 768 dimensions
  "payload": {
    "pmid": "12345678",
    "title": "Article title",
    "abstract": "Abstract text",
    "source": "pubmed",
    "date_processed": "2025-10-03T14:30:00"
  }
}
```

**Clinical Trials Collection (`clinical_trials`):**
```json
{
  "id": 30000000,
  "vector": [0.3, 0.4, ...],
  "payload": {
    "nct_id": "NCT00000000",
    "brief_title": "Trial title",
    // ... trial-specific fields
    "source": "clinical_trials",
    "date_processed": "2025-10-03T16:00:00"
  }
}
```

## Configuration

Settings in `config/config.yaml`:

```yaml
qdrant:
  storage_dir: "/path/to/data/qdrant"
  batch_size: 1000

  server:
    memory_mb: 131072      # 128GB
    runtime_hours: 48      # 2 days

pubmed:
  qdrant:
    collection_name: "pubmed_abstracts"
    memory_mb: 8192        # 8GB for insertion job
    runtime_hours: 8       # 8 hours

clinical_trials:
  qdrant:
    collection_name: "clinical_trials"
    memory_mb: 8192
    runtime_hours: 4
```

## Output

### Storage Structure

```
data/qdrant/
├── storage/                           # Qdrant data (persistent)
│   └── collections/
│       ├── pubmed_abstracts/
│       │   ├── segments/
│       │   └── config.json
│       └── clinical_trials/
│           ├── segments/
│           └── config.json
├── connection_info.txt                # Server URL (created by job)
└── collections/
    ├── pubmed_abstracts.done          # Completion markers
    └── clinical_trials.done
```

### Logs

```
logs/qdrant/
├── server.log                         # Qdrant server output
├── insert_pubmed.log                  # PubMed insertion log
├── insert_clinical_trials.log         # CT insertion log
└── insert_YYYYMMDD_HHMMSS.log         # Detailed script logs
```

## Performance

### Test Mode (config/test_config.yaml)

| Metric | Value |
|--------|-------|
| FAISS files | 2 |
| Total vectors | ~2000 |
| Processing time | 5-10 minutes |
| Memory | ~100MB |
| Storage | ~50-100MB |

### Production Mode (config/config.yaml)

| Metric | Value |
|--------|-------|
| FAISS files | ~1200 |
| Total vectors | ~30M |
| Processing time | 6-8 hours |
| Memory | ~100MB constant |
| Storage | ~100GB |

**Total Pipeline:**
- Server startup: ~1-2 min
- PubMed insertion: 6-8 hours
- CT insertion: 3-4 hours
- **Total: ~10-12 hours**

## Verification

### Check Server

```bash
# Source connection info
source data/qdrant/connection_info.txt

# Check server health
curl $QDRANT_URL/health

# List collections
curl $QDRANT_URL/collections
```

### Check Collections

```bash
# PubMed collection info
curl $QDRANT_URL/collections/pubmed_abstracts

# Expected response:
{
  "result": {
    "status": "green",
    "points_count": 30000000,
    "vectors_count": 30000000,
    "config": {
      "params": {
        "vectors": {
          "size": 768,
          "distance": "Cosine"
        }
      }
    }
  }
}
```

### Sample Search

```bash
# Get sample points
curl "$QDRANT_URL/collections/pubmed_abstracts/points?limit=3"

# Search by vector (requires actual 768-dim vector)
curl -X POST "$QDRANT_URL/collections/pubmed_abstracts/points/search" \
  -H 'Content-Type: application/json' \
  -d '{"vector": [...], "limit": 10}'
```

## Troubleshooting

### Container Not Found

```
ERROR: Qdrant container not found
```

**Solution:**
```bash
cd modules/qdrant/setup
./build_container.sh
```

### Server Timeout

```
ERROR: Qdrant server did not start within 5 minutes
```

**Check:**
```bash
cat logs/qdrant/server.log
qstat | grep qdrant_server
ls -l data/qdrant/connection_info.txt
```

### Connection Refused

```
ERROR: Failed to connect to Qdrant
```

**Debug:**
```bash
source data/qdrant/connection_info.txt
curl $QDRANT_URL/collections
qstat | grep qdrant
```

### No FAISS Files

```
WARNING: No FAISS index files found
```

**Solution:** Ensure dataset module completed:
```bash
./bioyoda.sh status
ls -l data/processed/pubmed/baseline/*.index
```

### Out of Memory

Server or insertion job killed:

**Increase memory in config:**
```yaml
qdrant:
  server:
    memory_mb: 262144  # Increase to 256GB
```

## Advanced

### Resume After Failure

The insertion script supports resuming from specific point ID:

```bash
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir data/processed/pubmed \
    --collection pubmed_abstracts \
    --qdrant-url http://nodeXXX:6333 \
    --start-id 15000000  # Resume from 15M
```

### Manual Qdrant Server

For development/testing, you can start Qdrant manually:

```bash
# Submit server job manually
cd modules/qdrant/setup
qsub -N qdrant -l h_vmem=128G,h_rt=48:00:00 \
  -b y singularity run \
  --bind /path/to/storage:/qdrant/storage \
  singularity/qdrant.sif
```

### Collection Optimization

Qdrant collections use these optimizations:

```python
HnswConfig:
  m: 16                  # Graph connectivity
  ef_construct: 100      # Index build quality
  full_scan_threshold: 10000

OptimizersConfig:
  deleted_threshold: 0.2
  vacuum_min_vector_number: 1000
  max_segment_size: 5000000  # 5M vectors per segment
```

## Design Decisions

### Why Not Run Qdrant Standalone?

Qdrant is infrastructure, not a dataset. Dataset modules create data; Qdrant stores it.

**Benefits:**
- Clear separation of concerns
- Dataset modules don't need Qdrant knowledge
- Easy to add new datasets
- Qdrant can be swapped/upgraded independently

### Why Sequential Insertion?

**Rejected:** 1200 parallel streams to Qdrant
- ❌ Network bottleneck
- ❌ Connection chaos
- ❌ No real parallelization benefit

**Selected:** Sequential from unmerged FAISS
- ✅ Reuses existing parallel FAISS creation
- ✅ Single controlled connection
- ✅ Skips expensive 90GB merge step
- ✅ Memory efficient

### Why Auto-Start Server?

**Benefits:**
- No manual intervention
- Automatic dependency management
- Server lifecycle tied to pipeline
- Connection info automatically propagated

**Trade-off:**
- Less manual control
- Server shuts down when job ends

For production deployment, Qdrant will run as persistent service (separate from pipeline).

## Related Documentation

- **Main README**: `../../README.md` - Project overview
- **Testing Guide**: `TESTING.md` - Test procedures
- **Setup Guide**: `../../QDRANT_SETUP_COMPLETE.md` - Quick start
- **Design Doc**: `../../vibe/qdrant_snakemake_integration_plan.md` - Architecture

## Next Steps

1. ✅ Container built
2. ⏳ Test with small dataset
3. ⏳ Verify collections
4. ⏳ Full production run
5. ⏳ FAISS export utility
6. ⏳ Production deployment
7. ⏳ Incremental updates

---

**Module Type:** Infrastructure (auto-triggered, not run standalone)
**Trigger:** Automatically runs when dataset modules complete
**Purpose:** Vector database backend for semantic search
