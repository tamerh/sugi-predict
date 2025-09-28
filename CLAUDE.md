# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BioYoda is a biomedical AI-powered search and retrieval system that processes PubMed abstracts, PMC full-text articles, and preprint data to build semantic vector indices for intelligent query answering. The project implements a RAG (Retrieval-Augmented Generation) pipeline using FAISS for vector search and sentence transformers for embeddings.

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
4. **Data Merging**: `merge.py` - Combines individual indices into master index files

### Stage 1: API Backend
`scripts/pubmed/api.py` contains a FastAPI application that:
- Loads pre-built FAISS indices and metadata
- Provides semantic search endpoints
- Uses sentence-transformers model (all-MiniLM-L6-v2) for query embedding
- Implements adapter pattern for vector database abstraction

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
   python merge.py
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

- **Embedding Model**: `all-MiniLM-L6-v2` (384 dimensions)
- **Vector Dimension**: 384
- **Data Paths**: Relative paths from script locations to `../data/`
- **Conda Environment**: `bioyoda` as defined in `tamer.yml`

## HPC Cluster Integration

The project is designed for HPC environments using SGE:
- Job submission scripts in `scripts/pubmed/`
- Memory requirements: 8GB per processing job
- Parallel processing of individual PubMed XML files
- Extensive logging system in `logs/` directory

## Notes

- The project follows a modular architecture where new data sources can be added as plugins
- FAISS indices are built per file and then merged for efficiency
- The system implements deduplication using deleted PMID tracking
- Processing logs are extensive due to the large-scale data processing requirements