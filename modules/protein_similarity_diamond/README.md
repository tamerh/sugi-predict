# Protein Similarity DIAMOND Module

Processes UniProt protein sequences into sequence-based similarity scores using DIAMOND BLASTP.

## Overview

This module performs all-vs-all protein sequence similarity searches using DIAMOND:
- **Source**: UniProt (SwissProt: 570K+ proteins, TrEMBL: 250M+ proteins)
- **Method**: DIAMOND BLASTP (10,000x faster than BLAST)
- **Output**: BioBTree JSON format for identifier mapping
- **Scale**: Configurable chunking for distributed processing

**Note**: This module creates JSON output **only** for BioBTree. It does not use Qdrant (no vector embeddings, just sequence alignment scores).

## Architecture

```
Download UniProt → Split FASTA → Create DIAMOND DB
                                         ↓
                     Parallel DIAMOND Search (all-vs-all per chunk)
                                         ↓
                     Merge Results → Filter Top-K → BioBTree JSON
```

## Quick Start

### Test Run (60 proteins)
```bash
# Process small test dataset
./bioyoda.sh run protein_similarity_diamond --test --local

# Result: BioBTree JSON with similarity scores
# test_out/data/processed/protein_similarity_diamond/protein_similarities_diamond.json
```

### Production Run - SwissProt (570K proteins)
```bash
# Process SwissProt proteins with parallel DIAMOND jobs
./bioyoda.sh run protein_similarity_diamond --cluster --jobs 100

# Result: BioBTree JSON ready for identifier mapping
# out/data/processed/protein_similarity_diamond/protein_similarities_diamond.json
```

### Production Run - TrEMBL (250M proteins)
```bash
# Configure for TrEMBL in config.yaml:
protein_similarity_diamond:
  dataset: "trembl"
  num_chunks: 1000  # More chunks for larger scale

# Process with many parallel CPU jobs
./bioyoda.sh run protein_similarity_diamond --cluster --jobs 500
```

## Pipeline Steps

### 1. Download UniProt (`download_uniprot.py`)
- Downloads FASTA file from UniProt FTP
- **SwissProt**: ~250MB (570K+ reviewed proteins)
- **TrEMBL**: ~100GB (250M+ unreviewed proteins)

```bash
# Output location
out/raw_data/protein_similarity_diamond/
└── uniprot_swissprot.fasta  (or uniprot_trembl.fasta)
```

### 2. Split FASTA (`split_fasta.py`) - CHECKPOINT
- Splits large FASTA into manageable chunks
- Each chunk processed in parallel DIAMOND job
- Enables distributed CPU processing

**Output**:
```bash
out/raw_data/protein_similarity_diamond/chunks/
├── chunk_001.fasta
├── chunk_002.fasta
├── ...
└── .split_complete  # Checkpoint marker
```

### 3. Create DIAMOND Database (`diamond makedb`)
- Builds DIAMOND database from complete FASTA
- Required for all searches (shared across chunks)

**Output**:
```bash
out/raw_data/protein_similarity_diamond/diamond_db/
└── uniprot_swissprot.dmnd  # DIAMOND database
```

### 4. DIAMOND Search (`diamond blastp`)
- **Parallel CPU processing**: Each chunk → separate job
- All proteins in chunk vs entire database
- Output: TSV with alignment scores

**DIAMOND Parameters**:
```bash
# Production settings (config.yaml)
--max-target-seqs 1000  # Max hits per query
--evalue 0.001          # E-value threshold
--sensitive             # Sensitivity mode
--threads 4             # Threads per job
```

**Output**:
```bash
out/data/processed/protein_similarity_diamond/results/
├── chunk_001.tsv  # TSV: query, target, identity, evalue, bitscore
├── chunk_002.tsv
└── ...
```

### 5. Merge Results (`merge_results`)
- Concatenates all chunk TSV files
- Creates single large TSV

**Output**:
```bash
out/data/processed/protein_similarity_diamond/merged/
└── merged_results.tsv  # All similarity pairs
```

### 6. Filter Top-K (`filter_top_k.py`)
- Keeps top-K hits per query protein
- Filters by minimum identity threshold
- Reduces data size dramatically

**Output**:
```bash
out/data/processed/protein_similarity_diamond/merged/
└── filtered_top100.tsv  # Top-K per protein
```

### 7. Convert to BioBTree JSON (`convert_to_biobtree_json.py`)
- Converts TSV to BioBTree JSON format
- Extracts UniProt accessions from IDs
- Groups by query protein

**Output**:
```bash
out/data/processed/protein_similarity_diamond/
└── protein_similarities_diamond.json  # BioBTree format
```

## Configuration

### Test Mode (`config/test_overrides.yaml`)
```yaml
protein_similarity_diamond:
  test_mode: true
  dataset: "test"           # Uses local test file (60 proteins)
  num_chunks: 3             # Create 3 chunks for testing

  diamond:
    max_target_seqs: 100    # Fewer targets for speed
    sensitivity: "fast"     # Fast mode for testing

  filter:
    top_k: 10              # Keep top-10 per protein
    min_identity: 0.0      # No filtering
```

### SwissProt Production (`config/config.yaml`)
```yaml
protein_similarity_diamond:
  dataset: "swissprot"           # 570K proteins
  num_chunks: 100                # 100 chunks for parallelism

  diamond:
    max_target_seqs: 1000        # Max 1000 hits per query
    evalue: 0.001                # E-value cutoff
    sensitivity: "sensitive"     # Good balance
    threads: 4                   # 4 threads per job

  filter:
    top_k: 100                   # Keep top-100 per protein
    min_identity: 30.0           # ≥30% identity
```
→ **Result**: Top-100 similarities per protein, ~30% identity cutoff

### TrEMBL Production (Large Scale)
```yaml
protein_similarity_diamond:
  dataset: "trembl"              # 250M proteins
  num_chunks: 1000               # More chunks for scale

  diamond:
    max_target_seqs: 500         # Fewer targets (data size)
    sensitivity: "sensitive"

  filter:
    top_k: 50                    # Keep top-50 per protein
    min_identity: 50.0           # Higher identity cutoff
```
→ **Result**: Top-50 high-confidence hits per protein

### Resource Settings
```yaml
protein_similarity_diamond:
  resources:
    download:
      memory_mb: 8192            # 8GB
      runtime_minutes: 10080     # 7 days

    create_db:
      memory_mb: 32768           # 32GB for DB creation
      runtime_minutes: 10080

    diamond_search:
      memory_mb: 32768           # 32GB per chunk search
      runtime_minutes: 10080
      threads: 4

    merge_results:
      memory_mb: 65536           # 64GB for merging
      runtime_minutes: 10080

    filter_top_k:
      memory_mb: 65536           # 64GB for filtering
      runtime_minutes: 10080
```

## DIAMOND Sensitivity Modes

| Mode | Speed | Sensitivity | Recommended For |
|------|-------|-------------|----------------|
| `fast` | Fastest | Lower | Testing |
| `mid-sensitive` | Fast | Medium | Quick production |
| **`sensitive`** | **Balanced** | **High** | **Default production** |
| `more-sensitive` | Slower | Higher | High accuracy |
| `very-sensitive` | Slowest | Highest | Maximum sensitivity |
| `ultra-sensitive` | Very slow | Maximum | Research |

**Configure in config.yaml**:
```yaml
protein_similarity_diamond:
  diamond:
    sensitivity: "sensitive"  # Default: balanced mode
```

## BioBTree JSON Format

Output format for BioBTree identifier mapping:

```json
{
  "protein_similarities": [
    {
      "query_id": "Q6GZX4",
      "dataset": "swissprot",
      "num_similar": 100,
      "similar_proteins": [
        {
          "target_id": "Q6GZX3",
          "identity": 98.5,
          "alignment_length": 256,
          "evalue": 1e-180,
          "bitscore": 512.3
        },
        {
          "target_id": "Q197F8",
          "identity": 45.2,
          "alignment_length": 198,
          "evalue": 1e-45,
          "bitscore": 156.7
        }
      ]
    }
  ]
}
```

## Performance

### Test Mode (60 proteins, 3 chunks)
- Runtime: ~2 minutes (CPU)
- Memory: 4GB per chunk
- Output: ~600 similarity pairs

### SwissProt Production (570K proteins, 100 chunks)
- **CPU**: ~12-24 hours (wall time with 100 parallel jobs)
- Memory: 32GB per chunk
- **Parallel**: 100 jobs × 4 cores each
- Storage: ~10GB merged TSV → ~500MB filtered JSON

### TrEMBL Production (250M proteins, 1000 chunks)
- **CPU**: ~5-7 days (wall time with 500 parallel jobs)
- Memory: 32GB per chunk
- **Parallel**: 500 jobs × 4 cores each
- Storage: ~500GB merged TSV → ~5GB filtered JSON

**DIAMOND Speedup**:
- DIAMOND is 10,000-20,000x faster than BLAST
- CPU-only (no GPU required)
- Highly parallelizable across chunks

## Output Structure

```
out/
├── raw_data/protein_similarity_diamond/
│   ├── uniprot_swissprot.fasta        # Downloaded FASTA
│   ├── chunks/
│   │   ├── chunk_001.fasta            # Split chunks
│   │   ├── chunk_002.fasta
│   │   └── .split_complete
│   └── diamond_db/
│       └── uniprot_swissprot.dmnd     # DIAMOND database
│
└── data/processed/protein_similarity_diamond/
    ├── results/
    │   ├── chunk_001.tsv              # Per-chunk results
    │   ├── chunk_002.tsv
    │   └── ...
    ├── merged/
    │   ├── merged_results.tsv         # All results merged
    │   └── filtered_top100.tsv        # Top-K filtered
    └── protein_similarities_diamond.json  # BioBTree JSON
```

## Workflow Examples

### Example 1: Standard SwissProt
```bash
# 1. Process proteins to BioBTree JSON (parallel CPU jobs)
./bioyoda.sh run protein_similarity_diamond --cluster --jobs 100

# 2. Use BioBTree for identifier mapping (external tool)
biobtree insert --input out/data/processed/protein_similarity_diamond/protein_similarities_diamond.json

# 3. Query BioBTree for protein relationships
biobtree query --protein Q6GZX4 --type similarity
```

### Example 2: TrEMBL (Large Scale)
```bash
# 1. Update config for TrEMBL
# Edit config/config.yaml:
#   dataset: "trembl"
#   num_chunks: 1000
#   filter.top_k: 50

# 2. Process with many parallel CPU jobs
./bioyoda.sh run protein_similarity_diamond --cluster --jobs 500

# 3. BioBTree integration
biobtree insert --input out/data/processed/protein_similarity_diamond/protein_similarities_diamond.json
```

## Troubleshooting

### Memory Issues During Merge
```bash
# Reduce number of chunks to reduce merge memory
protein_similarity_diamond:
  num_chunks: 50  # Fewer chunks = less merge memory
```

### Check Processing Status
```bash
# Count processed chunks
ls -lh out/data/processed/protein_similarity_diamond/results/chunk_*.tsv | wc -l

# Check merged results
wc -l out/data/processed/protein_similarity_diamond/merged/merged_results.tsv

# Check filtered results
wc -l out/data/processed/protein_similarity_diamond/merged/filtered_top100.tsv
```

### Inspect TSV Output
```bash
# View TSV format (DIAMOND blastp outfmt 6)
head out/data/processed/protein_similarity_diamond/results/chunk_001.tsv

# Columns:
# 1. query_id
# 2. target_id
# 3. identity (percent)
# 4. alignment_length
# 5. mismatches
# 6. gap_opens
# 7. q_start
# 8. q_end
# 9. s_start
# 10. s_end
# 11. evalue
# 12. bitscore
```

### Failed Chunks
```bash
# Rerun specific chunk
snakemake --snakefile modules/protein_similarity_diamond/Snakefile \
  out/data/processed/protein_similarity_diamond/results/chunk_005.tsv \
  --cores 4
```

## Key Design Points

### Why DIAMOND?
✅ **Fast**: 10,000-20,000x faster than BLAST
✅ **Accurate**: Maintains high sensitivity
✅ **Scalable**: Works for 250M+ proteins
✅ **CPU-only**: No GPU required
✅ **Standard format**: TSV output compatible with all tools

### Why BioBTree Integration?
✅ **Identifier mapping**: Link proteins across databases
✅ **Graph structure**: Build protein similarity networks
✅ **Efficient storage**: LMDB-based database
✅ **Query flexibility**: Complex relationship queries

### Why Not Qdrant?
- DIAMOND produces **pairwise similarities**, not embeddings
- Better suited for graph databases (BioBTree) than vector databases
- Top-K filtering reduces data size from billions to millions of pairs
- BioBTree handles identifier mapping more efficiently

### Chunking Strategy
✅ **Parallel execution**: 100-1000 independent CPU jobs
✅ **Memory efficient**: Process subset vs full database
✅ **Fault tolerance**: Retry individual chunks
✅ **Scalable**: Same workflow for SwissProt (570K) and TrEMBL (250M)

## Comparison: DIAMOND vs ESM-2

| Feature | DIAMOND | ESM-2 |
|---------|---------|-------|
| **Method** | Sequence alignment | Embeddings |
| **Output** | Similarity scores | 1280-dim vectors |
| **Compute** | CPU-only | GPU recommended |
| **Speed** | Fast (CPU) | Slow (CPU), Fast (GPU) |
| **Similarity** | Sequence identity | Functional similarity |
| **Storage** | Graph (BioBTree) | Vector DB (Qdrant) |
| **Use Case** | Homology, orthologs | Function prediction |

**Complementary approaches**: DIAMOND finds sequence-similar proteins, ESM-2 finds functionally-similar proteins.

## Related Documentation

- **Root README**: `../../README.md` - Overall system architecture
- **ESM-2 Module**: `../protein_similarity_esm2/README.md` - Vector-based similarity
- **BioBTree**: https://github.com/tamerh/biobtree - Identifier mapping tool
- **DIAMOND Paper**: https://www.nature.com/articles/nmeth.3176

---

**Module Version**: 1.0.0
**Last Updated**: January 2025
**Tool**: DIAMOND v2.1.8
