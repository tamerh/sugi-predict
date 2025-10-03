# PubMed Module

Snakemake workflow for downloading, processing, and indexing PubMed literature for semantic search.

## Overview

This module builds a semantic search index from PubMed abstracts using:
- **Model**: S-BioBERT (`pritamdeka/S-BioBERT-snli-multinli-stsb`) - 768 dimensions
- **Vector DB**: FAISS (FlatL2 index) + Qdrant (automatic)
- **Source**: PubMed baseline + update files from NCBI FTP
- **Scale**: ~1200+ files, ~30M abstracts

**Note**: This module creates FAISS indices only. Qdrant vector database insertion happens automatically via the infrastructure module.

## Quick Start

### Production Run
```bash
# Full PubMed processing + automatic Qdrant insertion
./bioyoda.sh run pubmed --cluster --bg --jobs 100

# What happens:
# 1. Downloads ~1200 PubMed XML files
# 2. Processes in parallel → creates FAISS indices
# 3. Auto-starts Qdrant server
# 4. Sequentially inserts FAISS data to Qdrant
```

### Test Run
```bash
# Fast test: 2 files × 1000 abstracts + Qdrant insertion
./bioyoda.sh run pubmed --config config/test_config.yaml --cluster --bg --jobs 5

# Monitor
tail -f logs/bioyoda_pubmed_main.log
tail -f logs/qdrant/insert_pubmed.log
```

## Pipeline Steps (This Module)

1. **Download** (`download.py`)
   - Fetches PubMed XML files from NCBI FTP
   - Downloads deleted PMIDs list
   - Supports debug mode (limited files)

2. **Process** (`index.py`) - **Parallel on cluster**
   - Parses XML to extract titles + abstracts
   - Skips deleted PMIDs
   - Creates embeddings using S-BioBERT
   - Outputs: `*.index` (FAISS) + `*_metadata.pkl` (metadata)
   - Supports `--limit N` for testing (processes first N abstracts)

3. **Merge** (`merge0.py`) - **Optional**
   - Combines all individual indices into master index
   - Memory-efficient streaming approach
   - **Performance**: ~700s for full dataset, 180MB RAM
   - **Note**: Not required for Qdrant insertion (inserts from unmerged files)

4. **Qdrant Insertion** (Automatic) - **See `modules/qdrant/` for details**
   - Auto-started after FAISS creation completes
   - Sequentially reads unmerged FAISS files
   - Inserts to Qdrant `pubmed_abstracts` collection
   - Creates searchable vector database

## Directory Structure

```
modules/pubmed/
├── Snakefile              # Workflow definition (4 rules)
├── scripts/
│   ├── download.py        # FTP download + deleted PMIDs
│   ├── index.py           # XML parsing + FAISS indexing
│   ├── merge0.py          # Index merging (fastest)
│   ├── config_loader.py   # Config helper
│   └── pubmed.env         # Script-level settings
└── README.md              # This file
```

## Configuration

### Production (`config/config.yaml`)
- Downloads all files (~1200)
- Processes all abstracts per file
- Memory: 12GB/process, 256GB/merge
- Runtime: Days

### Test (`config/test_config.yaml`)
- Downloads 2 files only
- Processes first 1000 abstracts/file
- Memory: 4GB/process, 8GB/merge
- Runtime: ~5 minutes

## Output

```
data/
├── raw/pubmed/
│   ├── baseline/*.xml.gz           # Downloaded files
│   ├── updatefiles/*.xml.gz
│   └── deleted.pmids.sorted.gz     # Deleted PMIDs
├── processed/pubmed/
│   ├── baseline/*.index + *.json   # Per-file indices
│   └── updatefiles/*.index + *.json
└── final/pubmed/
    ├── master_pubmed.index         # Merged FAISS index
    └── master_metadata.json        # Merged metadata
```

## Key Features

### Deduplication
- Tracks deleted PMIDs from NCBI
- Skips deleted articles during indexing
- Maintains data integrity

### Testing Support
- `test_mode: true` - Fast pipeline testing
- `test_abstracts_limit: 1000` - Limit abstracts/file
- Separate test config for safe experimentation

### HPC Optimization
- Checkpoint-based workflow (download → process → merge)
- Dynamic file discovery (handles variable FTP content)
- SGE cluster integration
- Parallel file processing

## Monitoring

```bash
# Watch main pipeline log
tail -f logs/bioyoda_pubmed_main.log

# Check individual file processing
ls -lh logs/pubmed/process/baseline/

# Monitor cluster jobs
qstat | grep pubmed
```

## Stopping Pipeline

```bash
# Stop running pipeline
./bioyoda.sh stop pubmed

# Stop and clean intermediate files
./bioyoda.sh stop pubmed --clean
```

## Performance

**Test Mode** (2 files × 1000 abstracts):
- Download: ~30s
- Process: ~2-3 min
- Merge: <10s
- **Total: ~5 minutes**

**Production** (full dataset):
- Download: Hours
- Process: Days (parallel on cluster)
- Merge: ~12 minutes
- **Total: Days (cluster-dependent)**

## Troubleshooting

**Issue**: Pipeline stuck at download
- **Check**: Network/FTP connection
- **Log**: `logs/pubmed/download.log`

**Issue**: Out of memory during merge
- **Solution**: Increase `merge_memory_mb` in config
- **Current**: 256GB for production, 8GB for test

**Issue**: Process fails on specific file
- **Check**: `logs/pubmed/process/baseline/<filename>.log`
- **Action**: File may be corrupted, re-download

## Scripts Reference

### `download.py`
```bash
python download.py                 # Full download
python download.py --debug 5       # Download 5 files only
```

### `index.py`
```bash
python index.py input.xml.gz output_dir/           # Full file
python index.py input.xml.gz output_dir/ --limit 100  # First 100 abstracts
```

### `merge0.py`
```bash
python merge0.py --processed-dir data/processed/pubmed \
                 --output-dir data/final/pubmed
```

## Model Details

**S-BioBERT** (`pritamdeka/S-BioBERT-snli-multinli-stsb`):
- Pre-trained on biomedical literature
- Fine-tuned for semantic similarity
- 768-dimensional embeddings
- Optimized for PubMed abstracts

**Alternatives tested**:
- `all-MiniLM-L6-v2` (384d) - General purpose, smaller
- `dmis-lab/biobert-base-cased-v1.1` (768d) - Pure BioBERT

## History

- **Sep 2024**: Initial implementation with bash scripts
- **Sep 2024**: Merge script optimization (merge0.py 57% faster)
- **Oct 2024**: Snakemake integration
- **Oct 2024**: Test mode implementation
- **Oct 2024**: Background execution + stop functionality

## Next Steps

See `vibe/clinical_trials_integration_plan.md` for planned ClinicalTrials.gov integration.
