# Clinical Trials Module

Processes ClinicalTrials.gov data into FAISS vector indices for semantic search.

## Overview

This module downloads and processes clinical trials to create semantic search indices:
- **Source**: AACT database (Clinical Trials Transformation Initiative)
- **Model**: S-BioBERT (`pritamdeka/S-BioBERT-snli-multinli-stsb`) - 768 dimensions
- **Output**: Individual FAISS chunk files (like PubMed) + optional merge
- **Scale**: 554K+ trials, 49 tables, 14GB raw data

**Note**: This module creates FAISS indices **only**. For Qdrant vector database insertion, see `modules/qdrant/README.md`.

## Architecture

**Similar to PubMed**: Default output is **individual chunk files** (NOT merged).

```
Download AACT → Extract (chunks) → Process (parallel) → Individual .index files
                                                         ↓
                                                    Insert to Qdrant

Optional: Merge chunks → Single master index (for analysis/export)
```

## Quick Start

### Production Run (Chunked Mode - Recommended)
```bash
# Process all clinical trials to individual chunk files
./bioyoda.sh run clinical_trials --cluster --bg --jobs 30

# Result: ~25 chunk files ready for Qdrant insertion
# out/data/processed/clinical_trials/trials_chunk_*.index
```

### Test Run
```bash
# Process small sample (400 trials → 8 chunks)
./bioyoda.sh test --modules clinical_trials

# Or manually with test config
./bioyoda.sh run clinical_trials --config config/test_config.yaml --local
```

**Test Reference Data**: The test suite uses a fixed set of 400 trials (controlled by `test_trials_limit: 400` in `config/test_overrides.yaml`). These 400 trials are deterministic (always the same first 400 from AACT) and serve as reference data for:
- Query validation in `tests/validate_queries.py`
- Reference fixtures in `tests/fixtures/clinical_trials/sample_trials.json` (all 400 trials)
- Tier 1 field coverage validation (sponsors, facilities, study_arms)

To update test reference fixtures after code changes:
```bash
# 1. Run test to generate new data
./bioyoda.sh test --modules clinical_trials

# 2. Update fixtures from test_out
python3 tests/update_clinical_trials_fixtures.py

# Result: tests/fixtures/clinical_trials/sample_trials.json updated with all 400 trials
```

### Optional: Merge Chunks
```bash
# Only if you need a single merged index
snakemake --cores 1 \
  --snakefile modules/clinical_trials/Snakefile \
  --configfile config/config.yaml \
  clinical_trials_merge

# Output: out/data/merged/clinical_trials/master_clinical_trials.index
```

## Incremental Updates

**New Feature**: The pipeline now supports **idempotent incremental updates** - automatically detecting and processing only changed trials.

### How It Works

The system uses:
- **State File** (`processed_chunks.json`): Tracks processed chunks and their metadata
- **Tracking Database** (`trials_tracking.db`): SQLite database tracking trial content hashes
- **Combined Script** (`download_and_extract.py`): Handles download → extract → change detection → chunking

**Auto-detection**:
```bash
# Just run the pipeline - it automatically determines what to do
./bioyoda.sh run clinical_trials --cluster --jobs 30

# System checks:
# 1. No state file → Fresh run (process everything)
# 2. State file exists, last_update == today → Skip (already processed today)
# 3. State file exists, last_update != today → Update (process only changes)
```

### Update Workflow

```bash
# Day 1: Initial load
./bioyoda.sh run clinical_trials --cluster --jobs 30
# → Creates: trials_chunk_0001.index, trials_chunk_0002.index, ...
# → State: processed_chunks.json + trials_tracking.db

# Day 2+: Automatic incremental update
./bioyoda.sh run clinical_trials --cluster --jobs 30
# → Compares new AACT snapshot with tracking DB
# → Identifies new + updated trials
# → Creates: trials_update_20251013_chunk_0001.index, ...
# → Preserves existing chunks and metadata

# Insert updates to Qdrant (upserts automatically)
./bioyoda.sh qdrant insert clinical_trials --cluster --jobs 10
# → New trials: inserted as new points
# → Updated trials: old vectors replaced (using NCT ID)
```

### Change Detection

The system tracks content changes using **SHA256 hashes**:

```python
# Tracked for each trial:
{
  "nct_id": "NCT01234567",
  "last_update_date": "2025-01-15",
  "content_hash": "a3f5e9...",  # Hash of trial content
  "last_processed_date": "2025-01-15T10:30:00"
}
```

**Only processes trials when**:
1. **New trial**: NCT ID not in tracking DB
2. **Content changed**: Hash differs from tracking DB
3. **Unchanged trials**: Skipped (saves processing time)

### State Preservation

**Key Feature**: State file metadata is preserved across runs:

```json
{
  "last_update": "2025-10-13T12:57:34",
  "no_changes": false,
  "chunks": {
    "trials_chunk_0001.json": {
      "status": "completed",
      "processed_date": "2025-10-12",
      "vectors_count": 259,
      "qdrant_inserted": true,
      "qdrant_inserted_date": "2025-10-13"
    },
    "trials_update_20251013_chunk_0001.json": {
      "status": "ready_to_process",
      "num_trials": 50,
      "size_mb": 0.3
    }
  }
}
```

✅ **Qdrant metadata** (`qdrant_inserted`, `qdrant_inserted_date`) preserved
✅ **Vector counts** (`vectors_count`) preserved
✅ **Processing dates** tracked for all chunks
✅ **Update chunks** named with dates for tracking

### Performance Benefits

**Example**: 554K trials, 1K trials changed

| Mode | Initial Load | Update (1K changed) | Time Savings |
|------|--------------|---------------------|--------------|
| **Full** | 4 hours | 4 hours | 0% |
| **Incremental** | 4 hours | ~10 minutes | 96% |

**Update costs**:
- Download: ~5 minutes (14GB snapshot)
- Change detection: ~2 minutes (hash comparison)
- Process changed trials: ~3 minutes (1K trials)
- Total: ~10 minutes vs 4 hours

### Monitoring Updates

Check state file for update status:
```bash
# View state file
cat out/state/clinical_trials/processed_chunks.json

# Check tracking database
sqlite3 out/state/clinical_trials/trials_tracking.db "SELECT COUNT(*) FROM trials"

# List update chunks (dated)
ls -lh out/raw_data/clinical_trials/chunked/trials_update_*.json
```

## Pipeline Steps

### 1. Download (`download_aact.py`)
- Downloads latest AACT snapshot from CTTI
- Extracts 49 pipe-delimited tables
- File size: ~14GB compressed

```bash
# Output location
out/raw_data/clinical_trials/
├── aact_snapshot.zip
└── extracted/
    ├── studies.txt (554K trials)
    ├── brief_summaries.txt
    ├── interventions.txt
    └── ... (46 more tables)
```

### 2. Extract (`extract_text_optimized.py`) - CHECKPOINT
- Joins AACT tables by NCT ID using pandas merge
- **NEW**: Creates chunks based on `trials_per_chunk` config
- Extracts core text fields:
  - Brief title & summary
  - Detailed description
  - Primary/secondary outcomes
  - Eligibility criteria
  - Interventions
- Filters withdrawn/incomplete studies

**Chunking Options**:
```bash
# Chunked mode (default)
--chunk-size 20000    # Creates trials_chunk_0001.json, trials_chunk_0002.json, ...

# Single file mode
--chunk-size 0        # Creates trials_data.json
```

**Output**:
```bash
out/data/processed/clinical_trials/
├── trials_chunk_0001.json
├── trials_chunk_0002.json
├── ...
└── chunk_manifest.json    # Discovery metadata
```

### 3. Process Chunks (`process_trials_chunk.py`)
- **Parallel processing**: Each chunk → separate job
- Creates multiple text chunks per trial
- Generates embeddings using S-BioBERT
- Supports GPU acceleration (auto-detect)

**Key Parameters**:
- `--encode-batch-size`: Model encoding batch size (CPU: 64, GPU: 256)
- `--num-workers`: CPU workers (1 for chunked mode)
- `--max-chunk-length`: Text chunk size (default: 500)
- `--min-text-length`: Min text length (default: 50)

**GPU Optimization**:
```bash
# On GPU nodes, use larger batch sizes and chunks
config_gpu.yaml:
  trials_per_chunk: 100000    # Larger chunks for GPU
  encode_batch_size: 256
```

**Output**:
```bash
out/data/processed/clinical_trials/
├── trials_chunk_0001.index + _metadata.json  ← Insert to Qdrant
├── trials_chunk_0002.index + _metadata.json  ← Insert to Qdrant
├── trials_chunk_0003.index + _metadata.json  ← Insert to Qdrant
└── ...
```

### 4. Optional: Merge (`merge_trials.py`)
- **NOT run by default** (like PubMed)
- Combines all chunk indices into single master index
- Only needed for full-index analysis/exports

**Output**:
```bash
out/data/merged/clinical_trials/
├── master_clinical_trials.index
└── master_clinical_trials.json
```

## Configuration

### Chunking Strategy

**CPU Production Mode** (`config/config.yaml`):
```yaml
clinical_trials:
  enable_chunking: true
  trials_per_chunk: 20000      # 20K trials per chunk
  num_workers: 1               # 1 CPU per chunk job
  encode_batch_size: 64        # CPU-optimized

  process_memory_mb: 12288     # 12GB per chunk
  process_runtime: 480         # 8 hours per chunk
```
→ **Result**: ~25 parallel jobs × 1 CPU = Easy to schedule

**GPU Production Mode** (`config/config_gpu.yaml`):
```yaml
clinical_trials:
  enable_chunking: true
  trials_per_chunk: 100000     # 100K trials per chunk (larger for GPU)
  num_workers: 1               # GPU handles parallelism
  encode_batch_size: 256       # GPU-optimized

  process_memory_mb: 16384     # 16GB per chunk
  process_runtime: 480         # 8 hours per chunk
```
→ **Result**: ~5 parallel jobs × 1 GPU = Utilize multiple GPU nodes

**Single File Mode** (disable chunking):
```yaml
clinical_trials:
  enable_chunking: false       # Single large file
  num_workers: 1               # GPU parallelism
  encode_batch_size: 256
```
→ **Result**: 1 job × 1 GPU = Maximum batch efficiency

**Test Mode** (`config/test_overrides.yaml`):
```yaml
clinical_trials:
  test_mode: true
  test_trials_limit: 400       # 400 trials (deterministic reference set)
  enable_chunking: true
  trials_per_chunk: 50         # Small chunks for testing
```
→ **Result**: 8 chunks for testing (fixtures in `tests/fixtures/clinical_trials/`)

### Resource Settings

```yaml
clinical_trials:
  # Download & extraction
  download_memory_mb: 16384    # 16GB
  download_runtime: 240        # 4 hours
  extract_memory_mb: 16384     # 16GB

  # Processing (per chunk)
  process_memory_mb: 12288     # 12GB (CPU) or 16GB (GPU)
  process_runtime: 480         # 8 hours

  # Merge (optional)
  merge_memory_mb: 32768       # 32GB
  merge_runtime: 240           # 4 hours
```

## Output Structure

```
out/
├── raw_data/clinical_trials/
│   ├── aact_snapshot.zip
│   └── extracted/
│       ├── studies.txt (554K trials)
│       └── ... (48 more tables)
│
├── data/processed/clinical_trials/
│   ├── trials_chunk_0001.json              # Extracted text (input)
│   ├── trials_chunk_0001.index             # FAISS vectors ← Insert to Qdrant
│   ├── trials_chunk_0001_metadata.json     # Processed metadata
│   ├── trials_chunk_0002.json              # Extracted text (input)
│   ├── trials_chunk_0002.index             # FAISS vectors ← Insert to Qdrant
│   ├── trials_chunk_0002_metadata.json     # Processed metadata
│   ├── ...
│   └── chunk_manifest.json                 # Discovery info
│
└── data/merged/clinical_trials/             # Only if merge run
    ├── master_clinical_trials.index        # Optional merged index
    └── master_clinical_trials.json         # Optional merged metadata
```

## Metadata Format

Each trial generates multiple chunks. Metadata format per chunk:

```json
{
  "0": {
    "nct_id": "NCT12345678",
    "chunk_type": "summary",
    "chunk_id": 0,
    "global_chunk_id": 0,
    "text": "Title: ... Summary: ...",
    "brief_title": "Study title",
    "overall_status": "Completed",
    "phase": "Phase 3",
    "study_type": "Interventional",
    "conditions": ["Diabetes"],
    "interventions": [{"intervention_type": "Drug", "name": "Drug A"}],
    "sponsors": [{"name": "NIH", "agency_class": "NIH", "role": "lead"}],
    "facilities": [{"name": "Hospital", "city": "Boston", "state": "MA", "country": "USA", "status": "RECRUITING"}],
    "study_arms": [{"title": "Experimental", "type": "EXPERIMENTAL", "description": "..."}]
  }
}
```

**Tier 1 Fields** (added for enhanced filtering):
- **sponsors**: Funding organizations with agency class and role
- **facilities**: Study locations with geographic details
- **study_arms**: Treatment groups and study design

## Performance

### Test Mode (400 trials)
- Chunks created: 8 (50 trials each)
- Text chunks: ~2000
- Runtime: 10-20 minutes
- Memory: 8GB per chunk job
- **Parallel**: 8 jobs can run simultaneously
- **Reference**: All 400 trials saved in `tests/fixtures/clinical_trials/sample_trials.json`

### CPU Production Mode (554K trials)
- Chunks created: ~25 (20K trials each)
- Text chunks: ~3M+
- Runtime: ~4 hours (wall time with 25 parallel jobs)
- Memory: 12GB per chunk job
- **Parallel**: 25 jobs × 1 CPU each

### GPU Production Mode (554K trials)
- Chunks created: ~5 (100K trials each)
- Text chunks: ~3M+
- Runtime: ~1 hour (wall time with 5 parallel jobs)
- Memory: 16GB per chunk job
- **Parallel**: 5 jobs × 1 GPU each

**CPU vs GPU**:
- **CPU Chunked**: ~4 hours (25 parallel × 1 CPU)
- **GPU Chunked**: ~1 hour (5 parallel × 1 GPU)
- **GPU Single**: ~2 hours (1 job × 1 GPU, max batch size)

### Comparison to Old Architecture

| Mode | Before | After (Chunked) |
|------|--------|-----------------|
| **CPU** | 1 job × 16 CPUs × 7 days | 25 jobs × 1 CPU × 4 hours |
| **GPU** | Hard to parallelize | 5 jobs × 1 GPU × 1 hour |
| **Scheduling** | Hard (need 16 CPUs) | Easy (need 1 CPU/GPU) |
| **Fault Tolerance** | Restart everything | Retry failed chunks only |

## Workflow Examples

### Example 1: Standard Production (CPU Chunked)
```bash
# 1. Process trials to chunk files (parallel)
./bioyoda.sh run clinical_trials --cluster --jobs 30

# 2. Start Qdrant server
./bioyoda.sh qdrant start

# 3. Insert chunk files to Qdrant (no merge needed!)
./bioyoda.sh qdrant insert clinical_trials

# DONE! Chunks are in Qdrant, ready for search
```

### Example 2: GPU Production
```bash
# 1. Process with GPU acceleration
./bioyoda.sh run clinical_trials --cluster --jobs 10 --config config/config_gpu.yaml

# 2. Insert to Qdrant
./bioyoda.sh qdrant insert clinical_trials --config config/config_gpu.yaml
```

### Example 3: With Optional Merge
```bash
# 1. Process to chunks (default)
./bioyoda.sh run clinical_trials --cluster --jobs 30

# 2. Optional: Merge for full-index analysis
snakemake --snakefile modules/clinical_trials/Snakefile clinical_trials_merge

# 3. Insert to Qdrant (still uses chunks, not merged file)
./bioyoda.sh qdrant insert clinical_trials
```

## Next Steps

After processing clinical trials data:

1. **Insert to Qdrant** (most common use case):
   ```bash
   ./bioyoda.sh qdrant start
   ./bioyoda.sh qdrant insert clinical_trials
   ```
   → Inserts directly from chunk files (no merge needed)

2. **Check chunk files**:
   ```bash
   ls -lh out/data/processed/clinical_trials/trials_chunk_*.index
   cat out/data/processed/clinical_trials/chunk_manifest.json
   ```

3. **Optional: Merge for analysis**:
   ```bash
   snakemake --snakefile modules/clinical_trials/Snakefile clinical_trials_merge
   ```

## Troubleshooting

### Check Chunking Status
```bash
# Check manifest
cat out/data/processed/clinical_trials/chunk_manifest.json

# Example output:
# {
#   "chunked": true,
#   "total_trials": 554000,
#   "num_chunks": 28,
#   "trials_per_chunk": 20000,
#   "chunks": [...]
# }
```

### List Chunk Files
```bash
# List generated chunks
ls -lh out/data/processed/clinical_trials/trials_chunk_*.json

# Count index files
find out/data/processed/clinical_trials -name "*.index" | wc -l
```

### Check Processing Logs
```bash
# Main log
tail -f out/logs/clinical_trials/extract.log

# Individual chunk logs
tail -f out/logs/clinical_trials/process_chunk_0001.log
tail -f out/logs/clinical_trials/process_chunk_0002.log
```

### Memory Issues
```bash
# Reduce chunk size in config
clinical_trials:
  trials_per_chunk: 10000    # Smaller chunks = less memory per job

# Or disable chunking for single large job
clinical_trials:
  enable_chunking: false
  num_workers: 16            # Multi-threaded single job
```

### Failed Chunks
```bash
# Rerun just the failed chunk
snakemake --snakefile modules/clinical_trials/Snakefile \
  out/data/processed/clinical_trials/trials_chunk_0005.index \
  --cores 1
```

## Key Design Points

### Why Chunking?
✅ **Parallel execution**: Many small jobs instead of 1 big job
✅ **Easy scheduling**: 1 CPU per job (vs 16 CPUs)
✅ **Fault tolerance**: Retry individual chunks
✅ **GPU support**: Flexible chunk sizes for batch efficiency
✅ **Like PubMed**: Proven architecture pattern

### Why No Default Merge?
✅ **Most use case**: Qdrant inserts from chunks (like PubMed)
✅ **Merge overhead**: Memory + time intensive
✅ **Flexibility**: Keep chunks for incremental updates
✅ **Optional**: Merge only when you need single index for analysis

### Configuration Flexibility
- **CPU mode**: Small chunks (20K) → many parallel jobs
- **GPU mode**: Large chunks (100K) → fewer GPU jobs
- **Single file**: Disable chunking → maximum batch size
- **Test mode**: Tiny chunks (50) → fast validation

## GPU Processing (Google Colab)

For processing 554K+ trials efficiently, use GPU acceleration on Google Colab.

### Prerequisites

1. **Push data to Google Drive:**
```bash
# Push clinical trials data and scripts
./bioyoda.sh push clinical_trials

# Or manually with rclone:
rclone copy snapshots/ct_latest/raw_data/clinical_trials/chunked/ \
    gdrive:bioyoda/raw_data/clinical_trials/chunked/ --progress

rclone copy modules/clinical_trials/scripts/process_trials_gpu.py \
    gdrive:bioyoda/scripts/clinical_trials/ --progress
rclone copy modules/clinical_trials/scripts/batch_trials_gpu.py \
    gdrive:bioyoda/scripts/clinical_trials/ --progress
```

2. **Data layout on Drive:**
```
MyDrive/bioyoda/
├── raw_data/clinical_trials/
│   └── chunked/
│       ├── trials_chunk_0001.json   # 111 chunks × 5K trials
│       ├── trials_chunk_0002.json
│       └── ...
├── processed/clinical_trials/text/   # Output directory (created)
└── scripts/clinical_trials/
    ├── process_trials_gpu.py
    └── batch_trials_gpu.py
```

### Step 1: Setup Colab Environment

```python
# Cell 1: Mount Drive and install dependencies
from google.colab import drive
drive.mount('/content/drive')

!pip install -q sentence-transformers faiss-cpu torch

# Verify GPU
import torch
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

# Copy scripts to Colab runtime
!cp "/content/drive/MyDrive/bioyoda/scripts/clinical_trials/batch_trials_gpu.py" .
!cp "/content/drive/MyDrive/bioyoda/scripts/clinical_trials/process_trials_gpu.py" .
!ls -la *.py
```

### Step 2: Check Progress and Create Directories

```python
# Cell 2: Setup directories and check progress
import os

# Create required directories
os.makedirs("/content/drive/MyDrive/bioyoda/processed/clinical_trials/text", exist_ok=True)
os.makedirs("/content/drive/MyDrive/bioyoda/state/clinical_trials", exist_ok=True)

# Check chunks
chunk_dir = "/content/drive/MyDrive/bioyoda/raw_data/clinical_trials/chunked"
out_dir = "/content/drive/MyDrive/bioyoda/processed/clinical_trials/text"

chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith('.json')])
done = len([f for f in os.listdir(out_dir) if f.endswith('.index')])
print(f"Total chunks: {len(chunks)}")
print(f"Already processed: {done}")
print(f"Remaining: {len(chunks) - done}")
```

### Step 3: Run Batch Processing (with nohup)

```python
# Cell 3: Start processing in background with logging to Drive
!nohup python batch_trials_gpu.py \
    --input-dir "/content/drive/MyDrive/bioyoda/raw_data/clinical_trials/chunked" \
    --output-dir "/content/drive/MyDrive/bioyoda/processed/clinical_trials/text" \
    --state-file "/content/drive/MyDrive/bioyoda/state/clinical_trials/gpu_progress.json" \
    --model-name pritamdeka/S-BioBERT-snli-multinli-stsb \
    > /content/drive/MyDrive/bioyoda/clinical_trials_processing.log 2>&1 &

print("Processing started in background!")
print("Log: /content/drive/MyDrive/bioyoda/clinical_trials_processing.log")
```

If model loading hangs, add `--no-fp16`:
```python
!nohup python batch_trials_gpu.py \
    --input-dir "/content/drive/MyDrive/bioyoda/raw_data/clinical_trials/chunked" \
    --output-dir "/content/drive/MyDrive/bioyoda/processed/clinical_trials/text" \
    --state-file "/content/drive/MyDrive/bioyoda/state/clinical_trials/gpu_progress.json" \
    --model-name pritamdeka/S-BioBERT-snli-multinli-stsb \
    --no-fp16 \
    > /content/drive/MyDrive/bioyoda/clinical_trials_processing.log 2>&1 &
```

### Step 4: Monitor Progress

```python
# Cell 4: Monitor log file
!tail -f /content/drive/MyDrive/bioyoda/clinical_trials_processing.log
```

Or check from local machine:
```bash
rclone cat gdrive:bioyoda/clinical_trials_processing.log | tail -50
```

### Step 5: Pull Results Back

```bash
# Sync processed indices back to server
./bioyoda.sh pull clinical_trials

# Or manually:
rclone copy gdrive:bioyoda/processed/clinical_trials/text/ \
    snapshots/ct_latest/data/processed/clinical_trials/text/ --progress
```

### Resume After Disconnect

The batch script automatically resumes from where it left off:
- Checks existing `.index` files in output directory
- Skips completed chunks
- Simply re-run the same command to continue

```python
# Just re-run - it will skip completed chunks
!nohup python batch_trials_gpu.py \
    --input-dir "/content/drive/MyDrive/bioyoda/raw_data/clinical_trials/chunked" \
    --output-dir "/content/drive/MyDrive/bioyoda/processed/clinical_trials/text" \
    --state-file "/content/drive/MyDrive/bioyoda/state/clinical_trials/gpu_progress.json" \
    --model-name pritamdeka/S-BioBERT-snli-multinli-stsb \
    > /content/drive/MyDrive/bioyoda/clinical_trials_processing.log 2>&1 &
```

### Performance Estimates

| GPU Type | Speed | 111 Chunks Time |
|----------|-------|-----------------|
| T4 (free) | ~800 texts/sec | ~4-6 hours |
| A100 (Pro+) | ~2000 texts/sec | ~1-2 hours |

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **PubMed Module**: `../pubmed/README.md` - Similar chunking pattern
- **Qdrant Module**: `../qdrant/README.md` - Vector database operations
- **Configuration**: `../../config/README.md` - Config options

---

**Module Version**: 0.4.0
**Last Updated**: December 2025
**Major Changes**: Added GPU processing support for Google Colab
