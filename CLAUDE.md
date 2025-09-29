# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BioYoda is a biomedical AI-powered search and retrieval system that processes PubMed abstracts to build semantic vector indices for intelligent query answering. The project implements a RAG (Retrieval-Augmented Generation) pipeline using FAISS for vector search and biomedical sentence transformers for embeddings.

**Current Status**: Successfully processing PubMed abstracts using S-BioBERT model on HPC cluster with optimized merge pipelines.

## Environment Setup

The project uses conda for environment management. The main environment is defined in `tamer.yml`:

```bash
# Create and activate the bioyoda environment
conda env create -f tamer.yml
conda activate bioyoda
```

Key dependencies include:
- Python 3.12
- PyTorch ecosystem (pytorch, torchvision, torchaudio)
- FAISS for vector search
- sentence-transformers for embeddings
- Standard data processing libraries (pandas, lxml, requests, tqdm)

## Data Pipeline Architecture

### Stage 0: Data Processing Pipeline
The core data processing pipeline is located in `scripts/pubmed/`:

1. **Data Download**: `data_download.py` - Downloads PubMed baseline and update files
2. **Single File Processing**: `process_single_file.py` - Processes individual XML files to create FAISS indices and metadata
3. **Batch Processing**: Job submission system using SGE (Sun Grid Engine) for HPC clusters
4. **Data Merging**: Multiple merge scripts available:
   - `merge0.py` - **Recommended**: Simple, memory-efficient, fastest (57% faster than alternatives)
   - `merge.py` - FAISS native approach (higher memory usage)
   - `merge2.py` - Streaming batch approach (medium complexity)

### Stage 1: API Backend & Search Testing
- `api.py` - FastAPI application for production deployment
- `test_search.py` - **Terminal-based search client** for testing and development:
  - Interactive search interface with memory monitoring
  - Direct FAISS index testing without web server
  - Supports single queries and interactive mode
  - Memory usage reporting and system statistics

## Data Organization

```
data/
├── raw/pubmed/          # Downloaded PubMed XML files
├── processed/pubmed/    # Individual FAISS indices and metadata
│   ├── baseline/        # Baseline file processing results
│   └── updatefiles/     # Update file processing results
├── test/                # Test data
└── final/               # Master indices and metadata
```

## Development Workflows

### Processing PubMed Data

1. **Setup file list for processing**:
   ```bash
   cd scripts/pubmed
   ./create_file_list.sh
   ```

2. **Submit batch jobs** (on HPC cluster):
   ```bash
   ./submit_jobs.sh
   ```

3. **Monitor job progress**:
   ```bash
   # Check logs in ../../logs/ directory
   ls -la ../../logs/
   ```

4. **Merge processed files**:
   ```bash
   python merge0.py  # Recommended: fastest and most memory-efficient
   ```

### Testing Search Results

```bash
cd scripts/pubmed
python test_search.py --query "CRISPR gene editing" --top-k 10
# Or interactive mode:
python test_search.py
```

### Running the API Server

```bash
cd scripts/pubmed
python -m uvicorn api:app --reload
```

### Claude Code CLI

The repository includes Claude Code CLI setup:
```bash
cd scripts
npm install  # Installs @anthropic-ai/claude-code
./claude     # Run Claude Code CLI
```

## Key Configuration Constants

**Current Production Configuration (pubmed.env):**
- **Embedding Model**: `pritamdeka/S-BioBERT-snli-multinli-stsb` (768 dimensions)
- **Vector Dimension**: 768
- **Configuration File**: `scripts/pubmed/pubmed.env` (replaces bioyoda.env)
- **Conda Environment**: `bioyoda` as defined in `tamer.yml`

**Alternative Models Tested:**
- `all-MiniLM-L6-v2` (384 dimensions) - General purpose
- `dmis-lab/biobert-base-cased-v1.1` (768 dimensions) - Biomedical focus

## HPC Cluster Integration

The project is designed for HPC environments using SGE:
- Job submission scripts in `scripts/pubmed/`
- Memory requirements: 8GB per processing job
- Parallel processing of individual PubMed XML files
- Extensive logging system in `logs/` directory

## Performance Benchmarks

**Merge Script Performance (verified on HPC cluster):**
- `merge0.py`: 695s runtime, 180MB peak memory, 249GB I/O ⭐ **Recommended**
- `merge.py`: 1091s runtime, 264MB peak memory, 340GB I/O (57% slower)
- All scripts produce identical 90GB index files

**Memory Monitoring:** All scripts now include psutil-based memory logging for optimization.

## Notes

- The project follows a modular architecture where new data sources can be added as plugins
- FAISS indices are built per file and then merged for efficiency
- The system implements deduplication using deleted PMID tracking
- Processing logs are extensive due to the large-scale data processing requirements
- Configuration moved from `bioyoda.env` to `scripts/pubmed/pubmed.env` for modularity