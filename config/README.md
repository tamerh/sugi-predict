# BioYoda Configuration Files

This directory contains configuration files for the BioYoda pipeline.

## Available Configurations

### 1. `config.yaml` - Production Configuration (CPU)
**Purpose**: Full-scale processing for production use (CPU optimized)

**Key Settings**:
- Downloads all PubMed baseline + update files (~1200 files)
- Processes complete abstracts from each file (~30k abstracts per file)
- Memory: 12GB per process job, 256GB for merge
- Batch size: 128 for encoding
- Runtime: Up to 7 days per job
- Output: `data/merged/pubmed/`

**Usage**:
```bash
./bioyoda.sh run pubmed --cluster --jobs 100
```

**Expected Duration**: Several days (depending on cluster load)

---

### 2. `config_gpu.yaml` - GPU Configuration
**Purpose**: GPU-accelerated processing for faster performance

**Key Settings**:
- Same data processing as production config
- Memory: 16GB per process job (GPU nodes have more RAM)
- Batch size: 256 for encoding (larger for GPU)
- Worker count: 4 (GPU handles parallelism)
- Queue: `gpu` by default
- Max jobs: 50 (limited GPU slots)
- Conda env: `bioyoda_gpu` or `bioyoda_gpu_cuda11`

**Usage**:
```bash
# Default CUDA 12.4 nodes (scc213, scc192, spiderman, hulk, scc195-199)
./bioyoda.sh run pubmed --cluster --jobs 50 --config config/config_gpu.yaml

# CUDA 11.4 nodes (scc116, scc117, scc066)
./bioyoda.sh run clinical_trials --cluster --config config/config_gpu.yaml --cuda11.4
```

**Expected Duration**: Faster than CPU mode (depends on GPU availability)

**Benefits**:
- 2-4x faster embedding generation
- Larger batch processing
- Better for large datasets

---

### 3. `test_config.yaml` - Test Configuration
**Purpose**: Fast end-to-end pipeline testing

**Key Settings**:
- Downloads only 2 sample files (debug mode)
- Processes only first 1000 abstracts per file (test mode)
- Memory: 4GB per process job, 8GB for merge
- Runtime: 1 hour per job, 30 min for merge
- Output: `test_out/data/merged/pubmed/`

**Usage**:
```bash
./bioyoda.sh run pubmed --config config/test_config.yaml --cluster --jobs 5
```

**Expected Duration**: ~5-10 minutes total

---

## When to Use Each Configuration

### Use `config.yaml` (Production CPU) When:
- ✓ Running final production pipeline on CPU nodes
- ✓ Building complete PubMed index
- ✓ Need full dataset for research/production
- ✓ GPU nodes are unavailable or busy

### Use `config_gpu.yaml` (Production GPU) When:
- ✓ GPU nodes are available
- ✓ Need faster processing times
- ✓ Processing large embedding batches
- ✓ Want to optimize resource usage with GPU acceleration

### Use `test_config.yaml` (Test) When:
- ✓ Testing pipeline changes
- ✓ Verifying Snakemake workflow logic
- ✓ Debugging processing scripts
- ✓ Learning the pipeline
- ✓ Before running expensive full pipeline

---

## Configuration Parameters Explained

### Test Mode Settings
```yaml
test_mode: true              # Enables test optimizations
test_abstracts_limit: 1000   # Process only first N abstracts per file
debug_mode: true             # Download limited files
debug_sample_size: 2         # Number of files to download
```

### Resource Settings
Adjust based on your cluster capabilities:
```yaml
process_memory_mb: 4096      # Memory per indexing job
merge_memory_mb: 8192        # Memory for merge job
process_runtime: 60          # Max runtime in minutes
```

---

## Creating Custom Configurations

To create a custom configuration:

1. Copy test_config.yaml or config.yaml:
   ```bash
   cp config/test_config.yaml config/my_config.yaml
   ```

2. Adjust parameters as needed

3. Run with custom config:
   ```bash
   ./bioyoda.sh run pubmed --config config/my_config.yaml --cluster
   ```

---

## Tips

1. **Always test first**: Run test config before production
2. **Separate outputs**: Test and production use different data directories
3. **Check resources**: Ensure cluster has enough memory for your settings
4. **Monitor logs**: Check `logs/test/` or `logs/pubmed/` for progress

---

## GPU Environment Setup

BioYoda supports two CUDA versions for different GPU node sets:

### CUDA 12.4 (Default)
**Environment**: `config/tamer_gpu.yml`
**Nodes**: scc213, scc192, spiderman, hulk, scc195-scc199

```bash
conda env create -f config/tamer_gpu.yml
conda activate bioyoda_gpu
```

### CUDA 11.8 (Older Nodes)
**Environment**: `config/tamer_gpu_cuda11.yml`
**Nodes**: scc116, scc117, scc066

```bash
conda env create -f config/tamer_gpu_cuda11.yml
conda activate bioyoda_gpu_cuda11
```

**Usage**:
```bash
# Use CUDA 11.4 nodes with --cuda11.4 flag
./bioyoda.sh run clinical_trials --cluster --config config/config_gpu.yaml --cuda11.4
```

---

## Example Workflows

### Workflow 1: Test First
```bash
# 1. Test the pipeline (fast)
./bioyoda.sh run pubmed --config config/test_config.yaml --cluster --jobs 5

# 2. Check test results
ls -lh test_out/data/merged/pubmed/

# 3. If tests pass, run production with GPU
./bioyoda.sh run pubmed --cluster --jobs 50 --config config/config_gpu.yaml
```

### Workflow 2: GPU Processing with Different CUDA Versions
```bash
# Process with default CUDA 12.4 nodes
./bioyoda.sh run pubmed --cluster --bg --jobs 50 --config config/config_gpu.yaml

# Process with CUDA 11.4 nodes (if 12.4 nodes are busy)
./bioyoda.sh run clinical_trials --cluster --bg --config config/config_gpu.yaml --cuda11.4
```

### Workflow 3: Mixed CPU/GPU
```bash
# Heavy processing on GPU
./bioyoda.sh run clinical_trials --cluster --config config/config_gpu.yaml --cuda11.4

# Other tasks on CPU
./bioyoda.sh run pubmed --cluster --config config/config.yaml
```
