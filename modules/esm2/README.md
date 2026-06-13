# Protein Similarity ESM-2 Module

Processes UniProt protein sequences into ESM-2 embeddings for semantic similarity search.

## Overview

This module generates protein language model embeddings using Meta AI's ESM-2 (Evolutionary Scale Modeling):
- **Source**: UniProt (SwissProt: 570K+ proteins, TrEMBL: 250M+ proteins)
- **Model**: ESM-2 650M (`esm2_t33_650M_UR50D`) - 1280 dimensions
- **Output**: Individual FAISS chunk files + metadata for Qdrant insertion
- **Scale**: Configurable chunking for memory-efficient processing

**Note**: This module creates FAISS indices **only**. For Qdrant vector database insertion, see `modules/qdrant/README.md`.

## Architecture

```
Download UniProt → Split FASTA → Generate ESM-2 Embeddings (GPU) → H5 Files
                                                                      ↓
                                                        Convert H5 → FAISS chunks
                                                                      ↓
                                                                Insert to Qdrant
```

## Quick Start

### Test Run (60 proteins)
```bash
# Process small test dataset
./bioyoda.sh run esm2 --config config/test_config.yaml --local

# Result: 3 chunk files (20 proteins each)
# test_out/data/processed/esm2/embeddings/chunk_*.index
```

### Production Run - SwissProt (570K proteins)
```bash
# Process SwissProt proteins with GPU acceleration
./bioyoda.sh run esm2 --cluster --jobs 50 --config config/config_gpu.yaml

# Result: ~29 chunk files ready for Qdrant insertion
# work/data/processed/esm2/embeddings/chunk_*.index
```

### Production Run - TrEMBL (250M proteins)
```bash
# Configure for TrEMBL in config.yaml:
esm2:
  dataset: "trembl"
  proteins_per_chunk: 100000  # Larger chunks for efficiency

# Process with many parallel GPU jobs
./bioyoda.sh run esm2 --cluster --jobs 200 --config config/config_gpu.yaml

# Result: ~2500 chunk files
```

## Pipeline Steps

### 1. Download UniProt (`download_uniprot.py`)
- Downloads FASTA file from UniProt FTP
- **SwissProt**: ~250MB (570K+ reviewed proteins)
- **TrEMBL**: ~100GB (250M+ unreviewed proteins)

```bash
# Output location
work/raw_data/esm2/
└── uniprot_swissprot.fasta  (or uniprot_trembl.fasta)
```

### 2. Split FASTA (`split_fasta.py`) - CHECKPOINT
- Splits large FASTA into manageable chunks
- Each chunk contains N proteins (configurable)
- Enables parallel GPU processing

**Output**:
```bash
work/raw_data/esm2/chunks/
├── chunk_001.fasta
├── chunk_002.fasta
├── ...
└── .split_complete  # Checkpoint marker
```

### 3. Generate Embeddings (`generate_embeddings.py`)
- **Parallel GPU processing**: Each chunk → separate job
- Uses ESM-2 650M model (1280-dim embeddings)
- Extracts mean pooled embeddings from layer 33
- Supports mixed precision (FP16) for speed

**GPU Optimization**:
```bash
# Automatically detects GPU and uses optimal settings
- Batch size: 8-16 sequences (memory dependent)
- Mixed precision: FP16 for 2x speed
- Layer 33 extraction: 1280-dim per protein
```

**Output**:
```bash
work/data/processed/esm2/embeddings/
├── chunk_001.h5    # HDF5 with embeddings + IDs
├── chunk_002.h5
└── ...
```

### 4. Convert to FAISS (`h5_to_faiss.py`)
- Converts H5 embeddings to FAISS indices
- Creates metadata JSON for Qdrant insertion
- L2 distance metric for similarity search

**Output**:
```bash
work/data/processed/esm2/embeddings/
├── chunk_001.index  # FAISS index ← Insert to Qdrant
├── chunk_001.json   # Metadata with protein IDs
├── chunk_002.index
├── chunk_002.json
└── ...
```

## Configuration

### Test Mode (`config/test_overrides.yaml`)
```yaml
esm2:
  test_mode: true
  dataset: "test"           # Uses local test file (60 proteins)
  test_num_chunks: 3        # Create 3 chunks for testing
  proteins_per_chunk: 20    # 20 proteins per chunk
```

### SwissProt Production (`config/config.yaml`)
```yaml
esm2:
  dataset: "swissprot"           # 570K proteins
  proteins_per_chunk: 20000      # 20K proteins per chunk
  batch_size: 8                  # GPU batch size
  device: "cuda"                 # Use GPU
  model_name: "esm2_t33_650M_UR50D"
  vector_dimension: 1280
  repr_layer: 33
```
→ **Result**: ~29 chunks, ~2 hours on GPU

### TrEMBL Production (Large Scale)
```yaml
esm2:
  dataset: "trembl"              # 250M proteins
  proteins_per_chunk: 100000     # Larger chunks for efficiency
  batch_size: 16                 # Larger GPU batches
  device: "cuda"
```
→ **Result**: ~2500 chunks, distributed processing

### Resource Settings
```yaml
esm2:
  # Download
  download_memory_mb: 8192       # 8GB
  download_runtime: 120          # 2 hours

  # Split
  split_memory_mb: 4096          # 4GB
  split_runtime: 60              # 1 hour

  # Generate embeddings (per chunk, GPU)
  generate_memory_mb: 16384      # 16GB (8GB model + data)
  generate_runtime: 480          # 8 hours (conservative)

  # Convert H5 to FAISS
  h5_to_faiss_memory_mb: 8192    # 8GB
  h5_to_faiss_runtime: 60        # 1 hour
```

## Model Options

### ESM-2 Model Variants
BioYoda supports all ESM-2 models from Meta AI:

| Model | Parameters | Vector Dim | Speed | Quality | Recommended For |
|-------|-----------|------------|-------|---------|----------------|
| `esm2_t30_150M_UR50D` | 150M | 640 | Fast | Good | Testing, quick searches |
| **`esm2_t33_650M_UR50D`** | **650M** | **1280** | **Balanced** | **Excellent** | **Production (default)** |
| `esm2_t36_3B_UR50D` | 3B | 2560 | Slow | Best | Maximum accuracy |

**Configure in config.yaml**:
```yaml
esm2:
  model_name: "esm2_t33_650M_UR50D"  # Default: 650M balanced model
  vector_dimension: 1280              # Must match model
  repr_layer: 33                      # Must match model
```

## Similarity Search

### API Endpoint

```bash
# Search for similar proteins
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Q6GZX4",
    "collections": ["esm2"],
    "limit": 10
  }'
```

### How It Works

1. **Query by UniProt Accession**: Provide a UniProt accession (e.g., `Q6GZX4`)
2. **Vector Lookup**: System retrieves the protein's ESM-2 embedding from Qdrant
3. **Similarity Search**: Finds proteins with similar embeddings (cosine similarity)
4. **Results**: Returns proteins with similar:
   - Sequence homology
   - Structural properties
   - Functional annotations

### Use Cases

- **Homology detection**: Find evolutionarily related proteins
- **Function prediction**: Infer function from similar proteins
- **Drug target discovery**: Identify proteins with similar binding sites
- **Protein classification**: Group proteins by structural similarity

## Performance

### Test Mode (60 proteins, 3 chunks)
- Runtime: ~5 minutes (GPU)
- Memory: 8GB per chunk
- Output: 3 FAISS indices

### SwissProt Production (570K proteins, ~29 chunks)
- **GPU**: ~2 hours (wall time with parallel jobs)
- **CPU**: ~20 hours (not recommended)
- Memory: 16GB per chunk (GPU)
- **Parallel**: 29 jobs × 1 GPU each

### TrEMBL Production (250M proteins, ~2500 chunks)
- **GPU**: ~3-4 days (wall time with 200 parallel GPU jobs)
- Memory: 16GB per chunk (GPU)
- **Parallel**: 200 jobs × 1 GPU each
- Storage: ~800GB (embeddings + indices)

**GPU Speedup**:
- ESM-2 650M is highly optimized for GPU
- CPU processing is ~50-100x slower
- **Recommendation**: Always use GPU for production

## Metadata Format

Each protein in the FAISS index has associated metadata:

```json
{
  "0": {
    "protein_id": "Q6GZX4"
  },
  "1": {
    "protein_id": "Q6GZX3"
  }
}
```

## Output Structure

```
out/
├── raw_data/esm2/
│   ├── uniprot_swissprot.fasta        # Downloaded FASTA
│   └── chunks/
│       ├── chunk_001.fasta            # Split chunks
│       ├── chunk_002.fasta
│       └── .split_complete
│
└── data/processed/esm2/
    └── embeddings/
        ├── chunk_001.h5               # ESM-2 embeddings (H5)
        ├── chunk_001.index            # FAISS index ← Insert to Qdrant
        ├── chunk_001.json             # Metadata with protein IDs
        ├── chunk_002.h5
        ├── chunk_002.index
        ├── chunk_002.json
        └── ...
```

## Testing

### Validate Protein Search
```bash
# Run validation tests (requires Qdrant running)
python tests/fixtures/esm2/validate_protein_search.py

# Tests:
# 1. Collection configuration (1280-dim, Cosine)
# 2. All test proteins exist in Qdrant
# 3. Similarity search returns valid results
# 4. Vector quality checks (L2 norms, dimensions)
```

### Test Queries
Test protein IDs are in `tests/queries_protein_similarity.txt`:
```
Q6GZX4
Q6GZX3
Q197F8
Q197F7
Q6GZX2
```

## Workflow Examples

### Example 1: Standard SwissProt (GPU)
```bash
# 1. Process proteins to chunk files (parallel GPU jobs)
./bioyoda.sh run esm2 --cluster --jobs 50 --config config/config_gpu.yaml

# 2. Start Qdrant server
./bioyoda.sh qdrant start

# 3. Insert chunk files to Qdrant
./bioyoda.sh qdrant insert esm2

# 4. Test search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Q6GZX4", "collections": ["esm2"], "limit": 10}'
```

### Example 2: TrEMBL (Large Scale)
```bash
# 1. Update config for TrEMBL
# Edit config/config.yaml:
#   dataset: "trembl"
#   proteins_per_chunk: 100000

# 2. Process with many parallel GPU jobs
./bioyoda.sh run esm2 --cluster --jobs 200 --config config/config_gpu.yaml

# 3. Insert to Qdrant (can be done incrementally)
./bioyoda.sh qdrant insert esm2 --cluster --jobs 50
```

## Troubleshooting

### GPU Memory Issues
```bash
# Reduce batch size in config
esm2:
  batch_size: 4  # Smaller batches for GPUs with less memory
```

### Check Processing Status
```bash
# Count generated chunks
ls -lh work/data/processed/esm2/embeddings/chunk_*.index | wc -l

# Check chunk files exist
ls -lh work/raw_data/esm2/chunks/
```

### Check Embeddings
```bash
# Inspect H5 file
python -c "import h5py; f=h5py.File('work/data/processed/esm2/embeddings/chunk_001.h5'); print(f['embeddings'].shape, f['ids'][:][:5])"

# Expected output:
# (20, 1280) [b'sp|Q6GZX4|001R_FRG3G' b'sp|Q6GZX3|002L_FRG3G' ...]
```

### Failed Chunks
```bash
# Rerun specific chunk
snakemake --snakefile modules/esm2/Snakefile \
  work/data/processed/esm2/embeddings/chunk_005.index \
  --cores 1
```

## Key Design Points

### Why ESM-2?
✅ **State-of-the-art**: Meta AI's best protein language model
✅ **No alignment needed**: Works directly on sequences
✅ **Captures structure**: Embeddings encode 3D structure information
✅ **Pretrained**: Trained on 250M+ protein sequences
✅ **Fast**: GPU-optimized for production use

### Why Chunking?
✅ **Parallel GPU execution**: Many small jobs instead of 1 big job
✅ **Memory efficient**: Process 100K proteins per chunk
✅ **Fault tolerance**: Retry individual chunks
✅ **Scalable**: Works for SwissProt (570K) and TrEMBL (250M)

### Model Selection
- **t30 (150M)**: Fast testing, lower quality
- **t33 (650M)**: **Recommended** - best quality/speed tradeoff
- **t36 (3B)**: Maximum accuracy, requires more GPU memory

## GPU Processing (Google Colab)

For processing 570K+ proteins efficiently, use GPU acceleration on Google Colab.

### Prerequisites

1. **Push data to Google Drive:**
```bash
# Push ESM2 data and scripts
./bioyoda.sh push esm2

# Or manually with rclone:
rclone copy snapshots/esm2_latest/raw_data/esm2/chunks/ \
    gdrive:bioyoda/raw_data/esm2/chunks/ --progress

rclone copy modules/esm2/scripts/batch_esm2_gpu.py \
    gdrive:bioyoda/scripts/esm2/ --progress
```

2. **Data layout on Drive:**
```
MyDrive/bioyoda/
├── raw_data/esm2/
│   └── chunks/
│       ├── chunk_001.fasta   # 100 chunks × ~5.7K proteins
│       ├── chunk_002.fasta
│       └── ...
├── processed/esm2/            # Output directory (created)
├── state/esm2/                # State tracking
└── scripts/esm2/
    └── batch_esm2_gpu.py
```

### Step 1: Setup Colab Environment

```python
# Cell 1: Mount Drive and install dependencies
from google.colab import drive
drive.mount('/content/drive')

!pip install -q fair-esm biopython h5py faiss-cpu torch

# Verify GPU
import torch
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

# Copy scripts to Colab runtime
!cp "/content/drive/MyDrive/bioyoda/scripts/esm2/batch_esm2_gpu.py" .
!ls -la *.py
```

### Step 2: Check Progress and Create Directories

```python
# Cell 2: Setup directories and check progress
import os

# Create required directories
os.makedirs("/content/drive/MyDrive/bioyoda/processed/esm2", exist_ok=True)
os.makedirs("/content/drive/MyDrive/bioyoda/state/esm2", exist_ok=True)

# Check chunks
chunk_dir = "/content/drive/MyDrive/bioyoda/raw_data/esm2/chunks"
out_dir = "/content/drive/MyDrive/bioyoda/processed/esm2"

chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith('.fasta')])
done = len([f for f in os.listdir(out_dir) if f.endswith('.index')])
print(f"Total chunks: {len(chunks)}")
print(f"Already processed: {done}")
print(f"Remaining: {len(chunks) - done}")
```

### Step 3: Run Batch Processing (with nohup)

```python
# Cell 3: Start processing in background with logging to Drive
!nohup python batch_esm2_gpu.py \
    --input-dir "/content/drive/MyDrive/bioyoda/raw_data/esm2/chunks" \
    --output-dir "/content/drive/MyDrive/bioyoda/processed/esm2" \
    --state-file "/content/drive/MyDrive/bioyoda/state/esm2/gpu_progress.json" \
    --model esm2_t33_650M_UR50D \
    --skip-existing \
    > /content/drive/MyDrive/bioyoda/esm2_processing.log 2>&1 &

print("Processing started in background!")
print("Log: /content/drive/MyDrive/bioyoda/esm2_processing.log")
```

### Step 4: Monitor Progress

```python
# Cell 4: Monitor log file
!tail -f /content/drive/MyDrive/bioyoda/esm2_processing.log
```

Or check from local machine:
```bash
rclone cat gdrive:bioyoda/esm2_processing.log | tail -50
```

### Step 5: Pull Results Back

```bash
# Sync processed indices back to server
./bioyoda.sh pull esm2

# Or manually:
rclone copy gdrive:bioyoda/processed/esm2/ \
    snapshots/esm2_latest/data/processed/esm2/ --progress
```

### Resume After Disconnect

The batch script automatically resumes from where it left off:
- Checks existing `.index` files in output directory
- Skips completed chunks (use `--skip-existing`)
- Simply re-run the same command to continue

```python
# Just re-run - it will skip completed chunks
!nohup python batch_esm2_gpu.py \
    --input-dir "/content/drive/MyDrive/bioyoda/raw_data/esm2/chunks" \
    --output-dir "/content/drive/MyDrive/bioyoda/processed/esm2" \
    --state-file "/content/drive/MyDrive/bioyoda/state/esm2/gpu_progress.json" \
    --model esm2_t33_650M_UR50D \
    --skip-existing \
    > /content/drive/MyDrive/bioyoda/esm2_processing.log 2>&1 &
```

### Performance Estimates

| GPU Type | Speed | 100 Chunks Time |
|----------|-------|-----------------|
| T4 (free) | ~50 seq/sec | ~30 hours |
| A100 (Pro+) | ~200 seq/sec | ~8 hours |

**Note**: ESM-2 650M model requires ~2.5GB VRAM. A100 is strongly recommended for faster processing.

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **Qdrant Module**: `../qdrant/README.md` - Vector database operations
- **API Module**: `../api/README.md` - Search API usage
- **ESM-2 Paper**: https://www.biorxiv.org/content/10.1101/2022.07.20.500902v1

---

**Module Version**: 1.1.0
**Last Updated**: December 2025
**Model**: ESM-2 650M (esm2_t33_650M_UR50D)
**Major Changes**: Added GPU batch processing for Google Colab
