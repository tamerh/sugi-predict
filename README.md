# Patent Target Atlas — engine

The open, reproducible **data engine** that builds and serves the **Patent Target Atlas**.

## Overview

The engine builds and serves the **Patent Target Atlas**: ~30 million SureChEMBL patent compounds, each annotated with its likely human protein targets by chemical k-nearest-neighbour transfer from a 1.25M-pair ChEMBL ligand→target reference, joined to **patent provenance** (which patents claim each compound — assignee, publication date, claimed-vs-disclosed). The atlas is browsable both directions — *what does this molecule hit?* and *what patented chemistry is predicted against this target, and who claimed it?* — and served openly as a web atlas (`sugi.bio/patent-atlas`), a REST API, and an MCP server for AI agents.

The engine also holds a small supporting multi-modal substrate (patent text, clinical trials, proteins) used as **retrieval context, not predictors** — chemical similarity is the only relationship validated as predictive. Everything runs on Qdrant, CPU-served (no query-time GPU), ~74.5M vectors, reproducible from source.

> **Product vs engine:** the public product is the *Patent Target Atlas*; this repo is the data engine beneath it (prediction + provenance + substrate, exposed via REST + MCP). The web UI is a separate repo (`patent-atlas-web`) that talks to the engine only over HTTP. *(Internally the engine is named `bioyoda` — paths, scripts, and the `mcp_srv` server use it.)*

## What it does

- **Target prediction** — for any molecule (a pasted SMILES, or any of the 30M patent compounds): ranked protein targets with a Tanimoto **confidence** + a supporting-neighbour **support** count, by exact-Tanimoto k-NN over a 1.25M-ligand ChEMBL reference (FPSim2). Validated held-out; chemistry is the only validated predictor.
- **Patent provenance** — for any SureChEMBL compound: the patents that claim/disclose it (number, assignee, publication date, claimed flag), from a self-contained SureChEMBL parquet join.
- **Supporting context** (retrieval, not prediction): clinical trials (MedCPT) and proteins (ESM-2, for selectivity) relevant to a target; patent text (MedCPT).
- **Access** — a thin REST API + MCP server (`mcp_srv`) over three primitives (`query` / `predict` / `provenance`); the web atlas is a separate HTTP consumer.
- **Reproducible** — every collection rebuilds from source via `bioyoda.sh build <collection>` (orchestrated as bash build steps + Enju workflow DAGs; Snakemake is retired), with small-data fixture tests (`bioyoda.sh test [--atlas]`).

### Substrate (four modalities, ~74.5M vectors)

| Modality | Embedding | Vectors |
|---|---|---|
| Patent compounds | Morgan ECFP4 (2048-bit) | ~30.9M |
| Patent text | MedCPT (768-d) | ~38.7M |
| Clinical trials | MedCPT | ~4.3M |
| Proteins (UniProt/SwissProt) | ESM-2 (1280-d) | ~0.57M |

Chemistry (+ the 1.25M-ligand ChEMBL reference) powers prediction; trials and proteins are supporting context, explicitly not predictors.

> PubMed/literature was removed (commodity + maintenance debt); the engine is intentionally focused on patent chemistry + targets.

## Quick Start

### Prerequisites

```bash
# Create conda environment
conda env create -f environment.yml
conda activate bioyoda
```

Orchestration is `bioyoda.sh` (bash `build` steps + Enju workflow DAGs) — Snakemake is retired.

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

# Step 5: Stop insertion if needed
./bioyoda.sh qdrant stop-insert pubmed

# Step 6: Stop server when done
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
│  Patents Module (NEW)                                        │
│  ↓ Download (SureChEMBL + USPTO)                            │
│  ↓ Process (Text + Compounds)                               │
│  ↓ Create FAISS (768-dim text + 2048-bit fingerprints)      │
│                                                               │
│  Output: data/processed/pubmed/                              │
│          data/processed/clinical_trials/                     │
│          data/processed/patents/                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
                   (Data files ready)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Qdrant Vector Database                     │
│                      (Independent)                            │
├─────────────────────────────────────────────────────────────┤
│  Start Server           Insert Data                          │
│  (Local/Cluster)        (When ready)                         │
│                                                               │
│  Storage: data/qdrant/storage/                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    (Query via Sugi-Agent)
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
├── patents/                # Patents dataset module (SureChEMBL + USPTO)
│   ├── Snakefile
│   ├── README.md
│   └── scripts/
│       ├── download_and_prepare_patents.py
│       ├── process_patents.py      # Text embeddings
│       ├── process_compounds.py    # Chemical fingerprints
│       └── process_uspto_json.py   # USPTO enrichment
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

# Incremental update mode (PubMed only - downloads only new updatefiles)
./bioyoda.sh run pubmed --mode update --cluster --bg --jobs 50

# Process Clinical Trials with GPU (CUDA 12.4 nodes)
./bioyoda.sh run clinical_trials --cluster --bg --jobs 20 --config config/config_gpu.yaml

# Process with CUDA 11.4 nodes (scc116, scc117, scc066)
./bioyoda.sh run clinical_trials --cluster --bg --config config/config_gpu.yaml --cuda11.4

# Process Patents (SureChEMBL + USPTO enrichment)
./bioyoda.sh run patents --cluster --bg --jobs 50

# Process Protein Similarity with DIAMOND (sequence-based)
./bioyoda.sh run diamond --cluster --bg --jobs 100

# Process Protein Similarity with ESM-2 (embedding-based, requires GPU)
./bioyoda.sh run esm2 --cluster --bg --jobs 50 --config config/config_gpu.yaml

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

# Start with existing storage directory (restart from previous session)
./bioyoda.sh qdrant start --out-dir /localscratch/tgur/qdrant_scc140_20251029

# Restart with existing storage (convenience command with auto-detection)
./bioyoda.sh qdrant restart [storage_path]

# Check status
./bioyoda.sh qdrant status

# Build/insert collections (inserts moved from `qdrant insert` into `build`/`atlas`)
./bioyoda.sh build trials insert          # clinical_trials_medcpt
./bioyoda.sh build compounds all          # patent_compounds (chunk/predict/ingest/...)
./bioyoda.sh build reference chembl       # chembl
./bioyoda.sh atlas text insert            # patents_text (-> patents_text_medcpt)
./bioyoda.sh build proteins insert        # esm2
# GPU stages auto push/run/pull on a pod when POD_HOST/POD_PORT/POD_KEY are set.

# Trigger the HNSW index build after a bulk build
./bioyoda.sh qdrant reindex patent_compounds --monitor

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

# Stop running Qdrant insertion
./bioyoda.sh qdrant stop-insert pubmed

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
│   ├── patents/            # Patents module (SureChEMBL + USPTO)
│   └── qdrant/             # Qdrant operations (standalone)
├── out/                    # Production outputs (configurable via base_dir)
│   ├── raw_data/           # Downloaded raw data
│   │   ├── pubmed/
│   │   ├── clinical_trials/
│   │   └── patents/
│   ├── data/               # Generated/processed data
│   │   ├── processed/      # Per-file FAISS indices
│   │   ├── merged/         # Merged FAISS indices (optional)
│   │   └── qdrant/         # Qdrant storage & connection info
│   └── logs/               # Pipeline logs
│       ├── cluster/        # SGE job logs
│       ├── pubmed/
│       ├── clinical_trials/
│       ├── patents/
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

# 6. Stop insertion if needed
./bioyoda.sh qdrant stop-insert all

# 7. Stop server when done (after days/weeks)
./bioyoda.sh qdrant stop
```

### Workflow 3: Incremental Updates (PubMed Daily Updates)

```bash
# Qdrant server already running from previous session

# 1. Process new PubMed updatefiles (skips baseline, downloads only new files)
./bioyoda.sh run pubmed --mode update --cluster --bg --jobs 50

# 2. Insert new data (automatically skips already-inserted files)
./bioyoda.sh qdrant insert pubmed --cluster --jobs 10

# 3. Monitor insertion progress
tail -f out/logs/qdrant/insert_pubmed_main.log

# 4. Check tracking status
python modules/pubmed/scripts/tracking.py --tracking-file out/state/pubmed/processed_files.json stats

# 5. Verify collection
./bioyoda.sh qdrant status
```

**How It Works:**
- Tracking system remembers which files have been downloaded, processed, and inserted
- `--mode update` downloads only new PubMed updatefiles (not baseline)
- Qdrant insertion skips already-inserted files, processes only new ones
- PMID-based upsert ensures updated articles replace old versions
- No redundant work, no duplicates

### Workflow 4: Resume from Existing Storage

```bash
# Scenario: Server crashed or session ended, data exists on localscratch

# 1. Check available storage directories
ls -lhd /localscratch/$USER/qdrant_*

# 2. Restart with existing data (auto-detects latest for current host)
./bioyoda.sh qdrant restart

# 3. Or specify exact storage path
./bioyoda.sh qdrant restart /localscratch/tgur/qdrant_scc140_20251029

# 4. Verify collections are loaded
./bioyoda.sh qdrant status

# Server is now running with all previous data intact
```

## Documentation

- **This File**: Overview and quick start
- **Module READMEs**: Technical details for each module
  - `modules/pubmed/README.md` - PubMed processing details
  - `modules/clinical_trials/README.md` - Clinical trials processing
  - `modules/patents/README.md` - Patent and compound search (SureChEMBL, USPTO)
  - `modules/diamond/README.md` - DIAMOND BLASTP sequence similarity
  - `modules/esm2/README.md` - ESM-2 protein embeddings
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

# Stop a running insertion
./bioyoda.sh qdrant stop-insert pubmed

# Restart server (preserves existing data)
./bioyoda.sh qdrant restart

# Or manually stop and start
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
