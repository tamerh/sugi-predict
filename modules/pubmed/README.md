# PubMed Module

Processes PubMed literature into FAISS vector indices for semantic search.

## Overview

This module downloads and processes PubMed abstracts to create semantic search indices:
- **Model**: S-BioBERT (`pritamdeka/S-BioBERT-snli-multinli-stsb`) - 768 dimensions
- **Output**: FAISS indices (FlatL2) with metadata
- **Source**: PubMed baseline + update files from NCBI FTP
- **Scale**: ~1200+ files, ~30M abstracts

**Note**: This module creates FAISS indices **only**. For Qdrant vector database insertion, see `modules/qdrant/README.md`.

## Quick Start

### Production Run
```bash
# Process all PubMed data
./bioyoda.sh run pubmed --cluster --bg --jobs 100

# Monitor progress
tail -f logs/bioyoda_pubmed_main.log
```

### Test Run
```bash
# Process small sample (2 files, 1000 abstracts each)
./bioyoda.sh run pubmed --config config/test_config.yaml --local

# Faster local testing
./bioyoda.sh run pubmed --config config/test_config.yaml --cores 4
```

## Pipeline Steps

### 1. Download (`download.py`)
- Fetches PubMed XML files from NCBI FTP
- Downloads deleted PMIDs list
- Supports debug mode (limited files for testing)

```bash
# Output location
raw_data/pubmed/
├── baseline/*.xml.gz
├── updatefiles/*.xml.gz
└── deleted.pmids.sorted.gz
```

### 2. Process (`index.py`) - Parallel on Cluster
- Parses XML to extract titles + abstracts
- Filters out deleted PMIDs
- Generates embeddings using S-BioBERT
- Creates FAISS indices + metadata files

**Key Parameters**:
- `--limit N`: Process only first N abstracts (for testing)
- `--batch-size`: Embedding batch size (default: 128)

```bash
# Output per file
data/processed/pubmed/baseline/
├── pubmed25n0001.index          # FAISS vectors
├── pubmed25n0001.json           # Metadata
├── pubmed25n0002.index
└── pubmed25n0002.json
```

### 3. Merge (Optional)
Combines individual indices into master index. **Not required** - Qdrant inserts from unmerged files.

```bash
# Optional: create master index
# Output: data/final/pubmed/master_pubmed.index
```

## Configuration

### Production Mode (`config/config.yaml`)
```yaml
pubmed:
  download_debug_mode: false          # All files
  limit_abstracts_per_file: null      # All abstracts
  batch_size: 128
  memory_mb: 12000                    # 12GB per job
```

### Test Mode (`config/test_config.yaml`)
```yaml
pubmed:
  download_debug_mode: true           # 2 files only
  limit_abstracts_per_file: 1000      # First 1000 abstracts
  batch_size: 32
  memory_mb: 4000                     # 4GB per job
```

## Output Structure

```
raw_data/pubmed/
├── baseline/
│   ├── pubmed25n0001.xml.gz
│   └── pubmed25n0002.xml.gz
├── updatefiles/
└── deleted.pmids.sorted.gz

data/
├── processed/pubmed/
│   ├── baseline/
│   │   ├── pubmed25n0001.index      # FAISS vectors
│   │   ├── pubmed25n0001.json       # Metadata (PMID, title, etc.)
│   │   ├── pubmed25n0002.index
│   │   └── pubmed25n0002.json
│   └── updatefiles/
│
└── final/pubmed/                     # Optional merged index
    ├── master_pubmed.index
    └── master_pubmed.json
```

## Metadata Format

Each `.json` file contains metadata for vectors:

```json
{
  "0": {
    "pmid": "12345678",
    "title": "Study title...",
    "abstract": "Full abstract text...",
    "journal": "Journal Name",
    "pub_date": "2024-01-15",
    "authors": ["Author A", "Author B"],
    "mesh_terms": ["Term1", "Term2"]
  },
  "1": { ... }
}
```

## Performance

### Test Mode
- Files: 2
- Abstracts: ~2000
- Runtime: 10-20 minutes
- Memory: 4-8GB

### Production Mode
- Files: ~1200
- Abstracts: ~30M
- Runtime: 10-12 hours (parallel on cluster)
- Memory: 8-12GB per job

## Next Steps

After processing PubMed data, you can:

1. **Insert to Qdrant** (for vector search):
   ```bash
   ./bioyoda.sh qdrant start
   ./bioyoda.sh qdrant insert pubmed
   ```

2. **Validate outputs**:
   ```bash
   ./bioyoda.sh validate pubmed
   ```

3. **Check status**:
   ```bash
   ./bioyoda.sh status
   ```

## Troubleshooting

### Download Issues
```bash
# Check raw directory
ls -lh raw_data/pubmed/baseline/

# Re-run download only
snakemake --snakefile modules/pubmed/Snakefile pubmed_download
```

### Processing Issues
```bash
# Check individual job logs
tail -f logs/cluster/index_pubmed*.log

# Test with single file locally
python modules/pubmed/scripts/index.py \
  --input raw_data/pubmed/baseline/pubmed25n0001.xml.gz \
  --output data/processed/pubmed/baseline/pubmed25n0001 \
  --limit 100
```

### Memory Issues
- Reduce batch size in config
- Increase `mem_mb` for cluster jobs
- Use test config for development

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **Qdrant Module**: `../qdrant/README.md` - Vector database operations
- **Configuration**: `../../config/README.md` - Config options

---

**Module Version**: 0.2.0
**Last Updated**: October 2025
