# Clinical Trials Module

Processes ClinicalTrials.gov data into FAISS vector indices for semantic search.

## Overview

This module downloads and processes clinical trials to create semantic search indices:
- **Source**: AACT database (Clinical Trials Transformation Initiative)
- **Model**: S-BioBERT (`pritamdeka/S-BioBERT-snli-multinli-stsb`) - 768 dimensions
- **Output**: FAISS indices (FlatL2) with metadata
- **Scale**: 554K+ trials, 49 tables, 14GB raw data

**Note**: This module creates FAISS indices **only**. For Qdrant vector database insertion, see `modules/qdrant/README.md`.

## Quick Start

### Production Run
```bash
# Process all clinical trials
./bioyoda.sh run clinical_trials --cluster --bg --jobs 20

# Monitor progress
tail -f logs/bioyoda_clinical_trials_main.log
```

### Test Run
```bash
# Process small sample (100 trials)
./bioyoda.sh run clinical_trials --config config/test_config.yaml --local
```

## Pipeline Steps

### 1. Download (`download_aact.py`)
- Downloads latest AACT snapshot from CTTI
- Extracts 49 pipe-delimited tables
- File size: ~14GB compressed

```bash
# Output location
raw_data/clinical_trials/
├── aact_snapshot.zip
└── extracted/
    ├── studies.txt
    ├── brief_summaries.txt
    ├── interventions.txt
    └── ... (46 more tables)
```

### 2. Extract (`extract_text.py`)
- Joins AACT tables by NCT ID
- Extracts core text fields:
  - Brief title
  - Brief summary
  - Detailed description
  - Primary/secondary outcomes
  - Eligibility criteria
  - Interventions
- Filters withdrawn/incomplete studies

```bash
# Output
data/processed/clinical_trials/trials_data.json
```

### 3. Process (`process_trials.py`)
- Creates multiple text chunks per trial
- Generates embeddings using S-BioBERT
- Supports GPU acceleration (auto-detect)

**Key Parameters**:
- `--limit N`: Process only first N trials (for testing)
- `--batch-size`: Embedding batch size (default: 128)
- `--encode-batch-size`: Model encoding batch size
- `--num-workers`: CPU workers for parallel encoding

**GPU Optimization**:
```bash
# On GPU nodes, use larger batch sizes
--encode-batch-size 256 --batch-size 5000
```

```bash
# Output
data/final/clinical_trials/
├── clinical_trials.index      # FAISS vectors
└── clinical_trials.json       # Metadata
```

## Configuration

### Production Mode (`config/config.yaml`)
```yaml
clinical_trials:
  test_mode: false
  test_trials_limit: null          # All trials
  download_memory_mb: 16384        # 16GB
  extract_memory_mb: 16384         # 16GB
  process_memory_mb: 20480         # 20GB
```

### Test Mode (`config/test_config.yaml`)
```yaml
clinical_trials:
  test_mode: true
  test_trials_limit: 100           # First 100 trials
  download_memory_mb: 4096
  extract_memory_mb: 4096
  process_memory_mb: 8192
```

## Output Structure

```
raw_data/clinical_trials/
├── aact_snapshot.zip
└── extracted/
    ├── studies.txt (554K trials)
    ├── brief_summaries.txt
    ├── detailed_descriptions.txt
    ├── interventions.txt
    ├── outcomes.txt
    ├── eligibility.txt
    └── ... (43 more tables)

data/
├── processed/clinical_trials/
│   └── trials_data.json          # Extracted text per trial
│
└── final/clinical_trials/
    ├── clinical_trials.index     # FAISS vectors (all chunks)
    └── clinical_trials.json      # Metadata per chunk
```

## Metadata Format

Each trial generates multiple chunks. Metadata format:

```json
{
  "0": {
    "nct_id": "NCT12345678",
    "chunk_type": "summary",
    "chunk_id": 0,
    "text": "Title: ... Summary: ...",
    "brief_title": "Study title",
    "overall_status": "Completed",
    "phase": "Phase 3",
    "study_type": "Interventional",
    "conditions": ["Diabetes", "..."],
    "interventions": ["Drug A", "..."]
  },
  "1": {
    "nct_id": "NCT12345678",
    "chunk_type": "description",
    "chunk_id": 0,
    ...
  }
}
```

## Performance

### Test Mode
- Trials: 100
- Chunks: ~500
- Runtime: 10-20 minutes
- Memory: 4-8GB

### Production Mode
- Trials: 554K+
- Chunks: ~3M+
- Runtime: 4-6 hours (with GPU)
- Memory: 16-20GB

**GPU vs CPU**:
- GPU: 4-6 hours with large batches
- CPU: 12-16 hours with small batches

## Next Steps

After processing clinical trials data, you can:

1. **Insert to Qdrant** (for vector search):
   ```bash
   ./bioyoda.sh qdrant start
   ./bioyoda.sh qdrant insert clinical_trials
   ```

2. **Validate outputs**:
   ```bash
   ./bioyoda.sh validate clinical_trials
   ```

3. **Check status**:
   ```bash
   ./bioyoda.sh status
   ```

## Troubleshooting

### Download Issues
```bash
# Check download
ls -lh raw_data/clinical_trials/

# Re-run download
snakemake --snakefile modules/clinical_trials/Snakefile clinical_trials_download
```

### Processing Issues (GPU)
```bash
# Check GPU availability
python -c "import torch; print(torch.cuda.is_available())"

# Test processing locally with small sample
python modules/clinical_trials/scripts/process_trials.py \
  --input-json data/processed/clinical_trials/trials_data.json \
  --output-index test.index \
  --output-metadata test.json \
  --limit 10
```

### Memory Issues
- Use test mode for development
- Increase memory allocation in config
- For GPU nodes: use larger batch sizes (faster, more memory efficient)

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **Qdrant Module**: `../qdrant/README.md` - Vector database operations
- **Configuration**: `../../config/README.md` - Config options

---

**Module Version**: 0.2.0
**Last Updated**: October 2025
