# BioYoda Configuration Files

This directory contains configuration files for the BioYoda pipeline.

## Available Configurations

### 1. `config.yaml` - Production Configuration
**Purpose**: Full-scale PubMed processing for production use

**Key Settings**:
- Downloads all PubMed baseline + update files (~1200 files)
- Processes complete abstracts from each file (~30k abstracts per file)
- Memory: 12GB per process job, 256GB for merge
- Runtime: Up to 7 days per job
- Output: `data/final/pubmed/`

**Usage**:
```bash
./bioyoda.sh run pubmed --cluster --jobs 100
```

**Expected Duration**: Several days (depending on cluster load)

---

### 2. `test_config.yaml` - Test Configuration
**Purpose**: Fast end-to-end pipeline testing

**Key Settings**:
- Downloads only 2 sample files (debug mode)
- Processes only first 1000 abstracts per file (test mode)
- Memory: 4GB per process job, 8GB for merge
- Runtime: 1 hour per job, 30 min for merge
- Output: `data/test/final/pubmed/`

**Usage**:
```bash
./bioyoda.sh run pubmed --config config/test_config.yaml --cluster --jobs 5
```

**Expected Duration**: ~5-10 minutes total

---

## When to Use Each Configuration

### Use `config.yaml` (Production) When:
- ✓ Running final production pipeline
- ✓ Building complete PubMed index
- ✓ Need full dataset for research/production

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

## Example Workflow

```bash
# 1. Test the pipeline (fast)
./bioyoda.sh run pubmed --config config/test_config.yaml --cluster --jobs 5

# 2. Check test results
ls -lh data/test/final/pubmed/

# 3. If tests pass, run production
./bioyoda.sh run pubmed --cluster --jobs 100
```
