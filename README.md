# BioYoda

AI-powered biomedical search system with vector database backend.

## Overview

BioYoda is a Snakemake-based pipeline for processing biomedical literature and clinical trial data into searchable vector databases. The system processes PubMed abstracts and clinical trial information, creating FAISS indices and Qdrant vector database collections for semantic search.

**New Architecture (v0.2.0)**: Data processing and vector database operations are now **fully separated** for maximum flexibility and efficiency.

## Features

- **PubMed Processing**: Process 30M+ PubMed abstracts with S-BioBERT embeddings
- **Clinical Trials**: Integrate ClinicalTrials.gov data (500K+ trials)
- **Vector Database**: Qdrant server with independent insertion workflow
- **HPC Ready**: Designed for SGE cluster with GPU support and Singularity containers
- **Modular Architecture**: Independent data processing and database management
- **Flexible Deployment**: Run Qdrant on GPU nodes for long-running sessions

## Quick Start

### Prerequisites

```bash
# Create conda environment (CPU)
conda env create -f tamer.yml
conda activate bioyoda

# OR: Create GPU environment (for accelerated processing)
conda env create -f config/tamer_gpu.yml       # CUDA 12.4
conda env create -f config/tamer_gpu_cuda11.yml # CUDA 11.8
conda activate bioyoda_gpu

# Verify Snakemake is installed
snakemake --version
```

### Test with Small Dataset

```bash
# Step 1: Process data (creates FAISS indices)
./bioyoda.sh run pubmed --config config/test_config.yaml --local

# Step 2: Start Qdrant server
./bioyoda.sh qdrant start

# Step 3: Insert data to Qdrant
./bioyoda.sh qdrant insert pubmed

# Step 4: Check status
./bioyoda.sh qdrant status

# Step 5: Stop server when done
./bioyoda.sh qdrant stop
```

### Production Workflow

```bash
# Step 1: Process all data on cluster (with GPU acceleration)
./bioyoda.sh run pubmed --cluster --bg --jobs 100 --config config/config_gpu.yaml
./bioyoda.sh run clinical_trials --cluster --bg --jobs 20 --config config/config_gpu.yaml

# For CUDA 11.4 nodes (scc116, scc117, scc066):
./bioyoda.sh run clinical_trials --cluster --bg --config config/config_gpu.yaml --cuda11.4

# Step 2: Start Qdrant on GPU node for long-running session
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# Step 3: Insert data when ready (can be done days later)
./bioyoda.sh qdrant insert all --cluster --jobs 20 --config config/config_gpu.yaml

# Step 4: Monitor
./bioyoda.sh qdrant status
tail -f logs/qdrant/insert_pubmed.log

# Step 5: Stop when done
./bioyoda.sh qdrant stop
```

## Architecture

### New Modular Design

```
┌─────────────────────────────────────────────────────────────┐
│                   Data Processing Pipeline                   │
│                         (Independent)                         │
├─────────────────────────────────────────────────────────────┤
│  PubMed Module          Clinical Trials Module               │
│  ↓ Download             ↓ Download                           │
│  ↓ Process              ↓ Process                            │
│  ↓ Create FAISS         ↓ Create FAISS                       │
│                                                               │
│  Output: data/processed/pubmed/                              │
│          data/final/clinical_trials/                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
                   (Data files ready)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Qdrant Vector Database                     │
│                      (Independent)                            │
├─────────────────────────────────────────────────────────────┤
│  Start Server           Insert Data          Query/Search    │
│  (Local/Cluster)        (When ready)         (API)           │
│                                                               │
│  Storage: data/qdrant/storage/                               │
└─────────────────────────────────────────────────────────────┘
```

### Key Benefits of Separation

✅ **Independence** - Data processing never waits for Qdrant
✅ **Flexibility** - Insert data anytime to running server
✅ **GPU Support** - Run Qdrant on GPU nodes for better performance
✅ **Long-running** - Keep Qdrant server up for days/weeks
✅ **Idempotent** - Retry insertions without reprocessing data

### Module Structure

```
modules/
├── Snakefile               # Main data processing orchestrator
├── pubmed/                 # PubMed dataset module
│   ├── Snakefile
│   ├── README.md
│   └── scripts/
├── clinical_trials/        # Clinical Trials dataset module
│   ├── Snakefile
│   ├── README.md
│   └── scripts/
└── qdrant/                 # Qdrant operations (separate)
    ├── Snakefile           # Standalone insertion workflows
    ├── README.md
    └── scripts/
        ├── start_server.sh
        ├── stop_server.sh
        ├── check_status.sh
        └── insert_from_faiss.py
```

## Commands

### Data Processing

```bash
# Process PubMed data (CPU)
./bioyoda.sh run pubmed --cluster --bg --jobs 50

# Process with GPU acceleration
./bioyoda.sh run pubmed --cluster --bg --jobs 50 --config config/config_gpu.yaml

# Process Clinical Trials with GPU (CUDA 12.4 nodes)
./bioyoda.sh run clinical_trials --cluster --bg --jobs 20 --config config/config_gpu.yaml

# Process with CUDA 11.4 nodes (scc116, scc117, scc066)
./bioyoda.sh run clinical_trials --cluster --bg --config config/config_gpu.yaml --cuda11.4

# Process all datasets
./bioyoda.sh run all --cluster --bg --jobs 100

# Use test configuration (small dataset)
./bioyoda.sh run pubmed --config config/test_config.yaml --local

# Monitor progress
tail -f logs/bioyoda_pubmed_main.log
```

### Qdrant Operations

```bash
# Start server (local mode)
./bioyoda.sh qdrant start

# Start server on GPU cluster node
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# Check status
./bioyoda.sh qdrant status

# Insert data
./bioyoda.sh qdrant insert pubmed
./bioyoda.sh qdrant insert clinical_trials
./bioyoda.sh qdrant insert all

# Insert with cluster resources and GPU acceleration
./bioyoda.sh qdrant insert pubmed --cluster --jobs 10 --config config/config_gpu.yaml

# Insert with CUDA 11.4 nodes
./bioyoda.sh qdrant insert pubmed --cluster --jobs 10 --config config/config_gpu.yaml --cuda11.4

# Stop server
./bioyoda.sh qdrant stop
```

### Monitor & Status

```bash
# Check overall pipeline status
./bioyoda.sh status

# Check Qdrant server and collections
./bioyoda.sh qdrant status

# Monitor logs
tail -f logs/bioyoda_pubmed_main.log
tail -f logs/qdrant/insert_pubmed.log

# Validate outputs
./bioyoda.sh validate pubmed
```

### Management

```bash
# Stop running pipeline
./bioyoda.sh stop pubmed --clean

# Clean specific module
./bioyoda.sh clean pubmed
./bioyoda.sh clean qdrant

# Unlock after crash
./bioyoda.sh unlock

# Dry run (see what would execute)
./bioyoda.sh dryrun pubmed

# Generate workflow DAG
./bioyoda.sh dag pubmed
```

## Configuration

### Test Mode (`config/test_config.yaml`)

Small dataset for fast validation:
- PubMed: 2 files, ~2000 vectors
- Clinical Trials: 100 trials
- Qdrant: Small batches
- Runtime: ~30 minutes

### Production Mode (`config/config.yaml`)

Full datasets (CPU optimized):
- PubMed: ~30M abstracts
- Clinical Trials: ~500K trials
- Qdrant: Optimized batches
- Runtime: ~10-12 hours for data processing

### GPU Mode (`config/config_gpu.yaml`)

GPU-accelerated processing:
- Larger batch sizes (256 vs 128)
- More memory per job (16GB)
- Optimized for GPU nodes
- Faster processing times
- Use with `--config config/config_gpu.yaml`

### GPU Environments

Two CUDA versions supported:
- **CUDA 12.4**: `tamer_gpu.yml` - Default GPU nodes (scc213, scc192, spiderman, hulk, scc195-199)
- **CUDA 11.8**: `tamer_gpu_cuda11.yml` - Older GPU nodes (scc116, scc117, scc066) - use with `--cuda11.4` flag

## Directory Structure

All outputs are organized in dedicated directories:

```
bioyoda/
├── bioyoda.sh              # Main orchestration script
├── config/
│   ├── config.yaml         # Production config (outputs to out/)
│   └── test_config.yaml    # Test config (outputs to test_out/)
├── modules/                # Pipeline code (never contains data)
│   ├── Snakefile           # Main data processing workflow
│   ├── pubmed/             # PubMed module
│   ├── clinical_trials/    # Clinical Trials module
│   └── qdrant/             # Qdrant operations (standalone)
├── out/                    # Production outputs (configurable via base_dir)
│   ├── raw_data/           # Downloaded raw data
│   │   ├── pubmed/
│   │   └── clinical_trials/
│   ├── data/               # Generated/processed data
│   │   ├── processed/      # Per-file FAISS indices
│   │   ├── final/          # Final indices (merged or single)
│   │   └── qdrant/         # Qdrant storage & connection info
│   └── logs/               # Pipeline logs
│       ├── cluster/        # SGE job logs
│       ├── pubmed/
│       ├── clinical_trials/
│       └── qdrant/
├── test_out/               # Test outputs (same structure as out/)
│   └── ...                 # Cleaned at start of each test run
└── tests/                  # Test suite
    ├── unit/               # Fast unit tests
    └── integration/        # E2E pipeline tests
```

**Key Design:**
- **out/** - Production pipeline outputs (gitignored)
- **test_out/** - Test pipeline outputs (gitignored, cleaned per test)
- **modules/** - Code only, no data (version controlled)
- **Separation** - Easy to clean generated data without touching code

## Example Workflows

### Workflow 1: Local Testing

```bash
# 1. Process small dataset
./bioyoda.sh run pubmed --config config/test_config.yaml --local

# 2. Start Qdrant locally
./bioyoda.sh qdrant start

# 3. Insert data
./bioyoda.sh qdrant insert pubmed

# 4. Check results
./bioyoda.sh qdrant status

# 5. Clean up
./bioyoda.sh qdrant stop
```

### Workflow 2: Production with GPU Server

```bash
# 1. Process data on cluster
./bioyoda.sh run all --cluster --bg --jobs 100

# 2. Start Qdrant on GPU node (long-running)
./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168

# 3. Wait for data processing to complete
./bioyoda.sh status

# 4. Insert when ready (can be days later)
./bioyoda.sh qdrant insert all --cluster --jobs 20

# 5. Server keeps running for queries
./bioyoda.sh qdrant status

# 6. Stop when done (after days/weeks)
./bioyoda.sh qdrant stop
```

### Workflow 3: Incremental Updates

```bash
# Qdrant server already running from previous session

# 1. Process new PubMed data
./bioyoda.sh run pubmed --cluster --bg --jobs 50

# 2. Insert new data (server keeps running)
./bioyoda.sh qdrant insert pubmed --cluster --jobs 10

# 3. Verify
./bioyoda.sh qdrant status
```

## Documentation

- **This File**: Overview and quick start
- **Module READMEs**: Technical details for each module
  - `modules/pubmed/README.md` - PubMed processing details
  - `modules/clinical_trials/README.md` - Clinical trials processing
  - `modules/qdrant/README.md` - Qdrant operations and architecture
- **Configuration**: `config/README.md` - Configuration options

## Troubleshooting

### Data Processing Issues

```bash
# Check status
./bioyoda.sh status

# Check logs
tail -f logs/bioyoda_pubmed_main.log

# Clean and restart
./bioyoda.sh stop pubmed --clean
./bioyoda.sh unlock
./bioyoda.sh run pubmed --cluster --bg
```

### Qdrant Issues

```bash
# Check server status
./bioyoda.sh qdrant status

# Check connection
cat data/qdrant/connection_info.txt

# Check logs
tail -f logs/qdrant/server.log
tail -f logs/qdrant/insert_pubmed.log

# Restart server
./bioyoda.sh qdrant stop
./bioyoda.sh qdrant start

# Re-run insertion
./bioyoda.sh qdrant insert pubmed
```

## Performance

### Test Mode
- Data: ~2000 vectors
- Processing: ~10-20 minutes
- Insertion: ~5 minutes
- Memory: 4-8GB

### Production Mode
- Data: 30M+ vectors
- Processing: 10-12 hours (parallel on cluster)
- Insertion: 2-4 hours (sequential to Qdrant)
- Memory: 8-12GB per job, 32GB+ for Qdrant server

## License

Apache 2.0

---

**Version**: 0.2.0
**Last Updated**: October 2025
**Major Changes**: Separated data processing and Qdrant operations for increased flexibility
