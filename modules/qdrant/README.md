# Qdrant Module

Standalone vector database operations for BioYoda.

## Overview

This module manages Qdrant vector database operations **independently** from data processing:
- **Server Management**: Start/stop Qdrant server (local or cluster)
- **Data Insertion**: Insert FAISS indices to Qdrant collections
- **Status Monitoring**: Check server and collection status
- **Flexible Deployment**: Run on GPU nodes for long-running sessions

**Key Architecture Change (v0.2.0)**: Qdrant operations are now **completely separate** from data processing pipelines.

## Quick Start

### Basic Workflow

```bash
# 1. Start Qdrant server
./bioyoda.sh qdrant start

# 2. Insert data (after processing)
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials

# 3. Check status
./bioyoda.sh qdrant status

# 4. Stop server
./bioyoda.sh qdrant stop
```

### Production Workflow (GPU Node)

```bash
# 1. Start on GPU node for long-running session
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# 2. Insert data when ready (can be days later)
./bioyoda.sh qdrant insert all --cluster --jobs 20

# 3. Server keeps running for weeks
./bioyoda.sh qdrant status

# 4. Stop when done
./bioyoda.sh qdrant stop
```

## Commands

### Start Server

```bash
# Local mode (default)
./bioyoda.sh qdrant start

# Cluster mode on SCC queue
./bioyoda.sh qdrant start --mode cluster --queue scc --runtime 48

# Cluster mode on GPU queue (recommended for production)
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# Custom memory allocation
./bioyoda.sh qdrant start --memory 64000  # 64GB
```

**Start Options**:
- `--mode <local|cluster>`: Run mode (default: local)
- `--queue <name>`: SGE queue (default: scc, options: gpu)
- `--runtime <hours>`: Server runtime in hours (default: 48)
- `--memory <mb>`: Memory in MB (default: 32000)

**Output**: Creates `data/qdrant/connection_info.txt` with server URL

### Stop Server

```bash
# Stop server and clean up
./bioyoda.sh qdrant stop
```

Stops both local and cluster-based servers, removes PID files and connection info.

### Check Status

```bash
# Comprehensive status check
./bioyoda.sh qdrant status
```

Shows:
- Server running state (local/cluster)
- Connection information
- Collections and point counts
- Storage size
- Insertion completion markers

### Insert Data

```bash
# Insert specific dataset
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials

# Insert all datasets
./bioyoda.sh qdrant insert all

# Insert with cluster resources
./bioyoda.sh qdrant insert pubmed --cluster --jobs 10

# Insert locally
./bioyoda.sh qdrant insert pubmed --local --cores 4
```

**Insert Options**:
- `--cluster`: Submit insertion jobs to cluster
- `--local`: Run insertion locally (default)
- `--cores N`: Number of cores for local mode
- `--jobs N`: Max parallel jobs for cluster mode

## Architecture

### Standalone Design

```
Data Processing                    Qdrant Module
(Independent)                      (Independent)
     ↓                                  ↓
FAISS Files  ─────────────→  Server Running
(data ready)                   (local/cluster)
                                      ↓
                              Insert Operations
                                (Snakemake)
                                      ↓
                              Collections Ready
                                (searchable)
```

### Components

```
modules/qdrant/
├── Snakefile                    # Insertion workflows (standalone)
├── README.md                    # This file
├── scripts/
│   ├── start_server.sh          # Start server (bash)
│   ├── stop_server.sh           # Stop server (bash)
│   ├── check_status.sh          # Status checker (bash)
│   └── insert_from_faiss.py     # Insertion script (Snakemake)
└── setup/
    └── singularity/
        ├── qdrant.sif           # Qdrant container
        └── config.yaml          # Qdrant config
```

### Workflow Logic

**Server Management** (Pure Bash):
- Simple operations: start/stop/status
- Direct execution via `bioyoda.sh`
- No Snakemake overhead

**Data Insertion** (Snakemake):
- Complex workflow with dependencies
- Automatic resumability
- Batch tracking with `.done` markers

## Collections

### PubMed Abstracts (`pubmed_abstracts`)

- **Source**: `data/processed/pubmed/`
- **Vectors**: ~30M (production), ~2000 (test)
- **Metadata**: PMID, title, abstract, journal, MeSH terms
- **Insertion Time**: 2-4 hours (production)

### Clinical Trials (`clinical_trials`)

- **Source**: `data/final/clinical_trials/`
- **Vectors**: ~3M chunks (production), ~500 (test)
- **Metadata**: NCT ID, chunk type, title, status, conditions
- **Insertion Time**: 30-60 minutes (production)

## Configuration

Settings in `config/config.yaml`:

```yaml
qdrant:
  storage_dir: "data/qdrant"
  log_dir: "logs/qdrant"
  batch_size: 500                    # Insertion batch size

  server:
    memory_mb: 32000                 # 32GB (adjust as needed)
    runtime_hours: 48                # 2 days default

pubmed:
  qdrant:
    collection_name: "pubmed_abstracts"
    memory_mb: 16384                 # Memory for insertion job

clinical_trials:
  qdrant:
    collection_name: "clinical_trials"
    memory_mb: 16384
```

## Output & Storage

### Directory Structure

```
data/qdrant/
├── connection_info.txt          # Server URL (created on start)
├── qdrant.pid                   # Process ID (local mode only)
├── storage/                     # Qdrant data directory
│   ├── collections/
│   │   ├── pubmed_abstracts/
│   │   └── clinical_trials/
│   └── meta.json
└── collections/
    ├── pubmed_abstracts.done    # Insertion markers
    └── clinical_trials.done
```

### Connection Info

After starting server, check connection:

```bash
cat data/qdrant/connection_info.txt
# Output:
# export QDRANT_URL="http://nodeXXX:6333"
# export QDRANT_HOST="nodeXXX"
# export QDRANT_PORT="6333"
```

### Query Collections

```bash
# Source connection info
source data/qdrant/connection_info.txt

# List collections
curl $QDRANT_URL/collections

# Get collection info
curl $QDRANT_URL/collections/pubmed_abstracts

# Query vectors (example)
curl -X POST "$QDRANT_URL/collections/pubmed_abstracts/points/search" \
  -H 'Content-Type: application/json' \
  -d '{
    "vector": [...],  # Your query vector
    "limit": 10
  }'
```

## Troubleshooting

### Server Won't Start

```bash
# Check if already running
./bioyoda.sh qdrant status

# Check logs
tail -f logs/qdrant/server.log

# Stop and restart
./bioyoda.sh qdrant stop
./bioyoda.sh qdrant start
```

### Insertion Fails

```bash
# Check if server is running
./bioyoda.sh qdrant status

# Check if data exists
ls -lh data/processed/pubmed/baseline/*.index
ls -lh data/final/clinical_trials/*.index

# Check insertion logs
tail -f logs/qdrant/insert_pubmed.log

# Re-run insertion
./bioyoda.sh qdrant insert pubmed
```

### Connection Issues

```bash
# Verify connection file exists
cat data/qdrant/connection_info.txt

# Test connection
source data/qdrant/connection_info.txt
curl $QDRANT_URL/collections

# Check if server is on correct node
qstat -u $(whoami) | grep q_server
```

### Performance Issues

**Slow insertions**:
- Increase batch size in config (default: 500)
- Check NFS performance (Qdrant on network storage)
- Consider local SSD for Qdrant storage

**Memory issues**:
- Increase server memory: `--memory 64000`
- Reduce batch size in config
- Use GPU node with more RAM

## Performance

### Test Mode
- Data: ~2500 vectors total
- Insertion: 5-10 minutes
- Memory: 16GB server, 4GB insertion jobs

### Production Mode
- Data: ~33M vectors total
- Insertion: 2-4 hours
- Memory: 32GB+ server, 16GB insertion jobs
- Storage: 50-100GB

**Optimization Tips**:
- Run server on GPU nodes (more RAM, better I/O)
- Use local SSD instead of NFS for storage
- Increase batch size for faster insertion
- Keep server running for multiple insertions

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **PubMed Module**: `../pubmed/README.md` - Data processing
- **Clinical Trials Module**: `../clinical_trials/README.md` - Data processing
- **Configuration**: `../../config/README.md` - Config options

---

**Module Version**: 0.2.0
**Last Updated**: October 2025
**Major Changes**: Standalone operation, separated from data processing pipeline
