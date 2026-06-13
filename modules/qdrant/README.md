# Qdrant Module

Standalone vector database operations for BioYoda.

## Overview

This module manages Qdrant vector database operations **independently** from data processing:
- **Server Management**: Start/stop Qdrant server
- **Data Insertion**: Insert FAISS indices to Qdrant collections
- **Index Management**: Trigger HNSW index building after bulk inserts
- **Status Monitoring**: Check server and collection status

## Prerequisites

### Apptainer (Singularity)

Qdrant runs in a Singularity/Apptainer container. Install Apptainer (system package, not available via conda):

```bash
# Ubuntu 22.04/24.04
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt update
sudo apt install -y apptainer

# Verify installation
singularity --version
# Output: apptainer version 1.x.x
```

The Qdrant container (`modules/qdrant/setup/singularity/qdrant.sif`) is included in the repository.

## Quick Start

```bash
# 1. Start Qdrant server
./bioyoda.sh qdrant start

# 2. Insert data (after processing)
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials
./bioyoda.sh qdrant insert patents_compounds
./bioyoda.sh qdrant insert esm2

# 3. Trigger HNSW indexing for large collections
./bioyoda.sh qdrant reindex patents_compounds --monitor

# 4. Check status
./bioyoda.sh qdrant status

# 5. Stop server when done
./bioyoda.sh qdrant stop
```

## Commands

### Start Server

```bash
# Start Qdrant (uses qdrant by default)
./bioyoda.sh qdrant start

# Custom memory allocation
./bioyoda.sh qdrant start --memory 64000  # 64GB

# Use specific storage directory
./bioyoda.sh qdrant start --out-dir /path/to/storage
```

**Start Options**:
- `--memory <mb>`: Memory in MB (default: 32000)
- `--out-dir <path>`: Use specific storage directory
- `--config <file>`: Use custom config file

**Output**: Creates `qdrant/connection_info.txt` with server URL

### Stop Server

```bash
./bioyoda.sh qdrant stop
```

### Restart Server

```bash
# Restart with same storage
./bioyoda.sh qdrant restart
```

### Check Status

```bash
./bioyoda.sh qdrant status
```

Shows:
- Server running state
- Connection information
- Collections and point counts
- Storage size

### Insert Data

```bash
# Insert specific dataset
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials
./bioyoda.sh qdrant insert patents
./bioyoda.sh qdrant insert esm2

# Insert all datasets
./bioyoda.sh qdrant insert all

# Insert locally with specific cores
./bioyoda.sh qdrant insert pubmed --local --cores 4
```

**Incremental Updates:**
- Insertion automatically tracks processed files
- Skips already-inserted data
- Uses document-based point IDs for upsert (no duplicates)

### Trigger HNSW Indexing (Reindex)

After bulk insertion, HNSW indexing may need to be triggered manually for large collections:

```bash
# Trigger indexing for specific collection
./bioyoda.sh qdrant reindex patents_compounds

# Trigger and monitor progress
./bioyoda.sh qdrant reindex patents_compounds --monitor

# Reindex all collections
./bioyoda.sh qdrant reindex all

# Custom indexing threshold (default: 20000)
./bioyoda.sh qdrant reindex patents_compounds --threshold 10000
```

**Why is this needed?**

For performance during bulk inserts, some collections (e.g., `patents_compounds`) have a high `indexing_threshold` in config. This delays HNSW index building until after insertion completes.

The reindex command:
1. Lowers `indexing_threshold` to enable indexing
2. Inserts/deletes a dummy point to trigger the optimizer
3. Optionally monitors progress until complete

**Monitoring indexing:**
```bash
# Standalone monitoring script
./scripts/check_qdrant_indexing.sh

# Or with the reindex command
./bioyoda.sh qdrant reindex patents_compounds --monitor
```

**Note:** HNSW index building for 30M+ vectors takes several hours. Without the index, searches do full scans (100+ seconds per query).

## Storage Configuration

Qdrant storage is configured in `config/config.yaml`:

```yaml
qdrant:
  storage:
    path: "qdrant"  # Storage location
```

All snapshots insert to this shared Qdrant instance.

### Directory Structure

```
qdrant/
├── connection_info.txt     # Server URL (created on start)
├── qdrant.pid              # Process ID
├── storage/                # Qdrant data directory
│   ├── collections/
│   │   ├── pubmed_abstracts/
│   │   ├── clinical_trials/
│   │   ├── patents_text/
│   │   ├── patents_compounds/
│   │   └── esm2/
│   └── meta.json
└── snapshots/              # Qdrant snapshots
```

## Collections

| Collection | Source | Vectors | Description |
|------------|--------|---------|-------------|
| `pubmed_abstracts` | PubMed | ~30M | Literature abstracts |
| `clinical_trials` | ClinicalTrials.gov | ~3M | Trial documents (chunked) |
| `patents_text` | SureChEMBL | ~43M | Patent text embeddings |
| `patents_compounds` | SureChEMBL | ~30M | Chemical fingerprints |
| `esm2` | UniProt | ~570K | Protein embeddings |

## Insert from Snapshots

Each processing snapshot can insert to the shared Qdrant:

```bash
# From ESM2 snapshot
cd snapshots/esm2_latest/code
./bioyoda.sh qdrant insert esm2

# From Patents snapshot
cd snapshots/patents_latest/code
./bioyoda.sh qdrant insert patents

# From main project directory
./bioyoda.sh qdrant insert all
```

## Query Collections

```bash
# Source connection info
source qdrant/connection_info.txt

# List collections
curl $QDRANT_URL/collections

# Get collection info
curl $QDRANT_URL/collections/pubmed_abstracts

# Search (example)
curl -X POST "$QDRANT_URL/collections/pubmed_abstracts/points/search" \
  -H 'Content-Type: application/json' \
  -d '{
    "vector": [...],
    "limit": 10
  }'
```

## Troubleshooting

### Server Won't Start

```bash
# Check if already running
./bioyoda.sh qdrant status

# Check logs
tail -f work/logs/qdrant/server_*.log

# Stop and restart
./bioyoda.sh qdrant stop
./bioyoda.sh qdrant start
```

### Insertion Fails

```bash
# Check if server is running
./bioyoda.sh qdrant status

# Check if data exists
ls -lh work/data/processed/pubmed/baseline/*.index

# Check insertion logs
tail -f work/logs/qdrant/insert_pubmed.log

# Re-run insertion
./bioyoda.sh qdrant insert pubmed
```

### Connection Issues

```bash
# Verify connection file exists
cat qdrant/connection_info.txt

# Test connection
curl http://localhost:6333/collections
```

## Configuration

### Server Settings

Qdrant server settings in `config/qdrant_config.yaml`:

```yaml
service:
  host: 0.0.0.0
  http_port: 6333

storage:
  wal_capacity_mb: 256
  flush_interval_sec: 30
```

### Collection Settings

Per-collection settings in `config/config.yaml`:

```yaml
pubmed:
  qdrant:
    collection_name: "pubmed_abstracts"
    hnsw_m: 32
    hnsw_ef_construct: 256
    batch_size: 500
```

## Components

```
modules/qdrant/
├── Snakefile                    # Insertion workflows
├── README.md                    # This file
├── scripts/
│   ├── start_server.sh          # Start server
│   ├── stop_server.sh           # Stop server
│   ├── check_status.sh          # Status checker
│   └── insert_from_faiss.py     # Insertion script
└── setup/
    └── singularity/
        ├── qdrant.def           # Container definition
        └── qdrant.sif           # Qdrant container
```

## Performance

- **Insertion speed**: ~10K vectors/second
- **Memory**: 32GB+ recommended for large collections
- **Storage**: ~50-100GB for all collections

---

**Module Version**: 0.4.0
**Last Updated**: January 2026
**Changes**: Added `qdrant reindex` command for triggering HNSW index builds after bulk insertion
