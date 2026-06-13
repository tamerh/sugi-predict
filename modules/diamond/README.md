# Protein Similarity DIAMOND Module

Processes UniProt protein sequences into sequence-based similarity scores using DIAMOND BLASTP.

## Overview

This module performs all-vs-all protein sequence similarity searches using DIAMOND:
- **Source**: UniProt (SwissProt: 570K+ proteins, TrEMBL: 250M+ proteins)
- **Method**: DIAMOND BLASTP (10,000x faster than BLAST)
- **Output**: Filtered TSV format for BioBTree identifier mapping
- **Scale**: Configurable chunking for distributed processing

**Note**: This module creates TSV output for BioBTree. It does not use Qdrant (no vector embeddings, just sequence alignment scores).

## Architecture

```
Download UniProt → Split FASTA → Create DIAMOND DB
                                         ↓
                     Parallel DIAMOND Search (all-vs-all per chunk)
                                         ↓
                     Merge Results → Filter Top-K → TSV Output (for BioBTree)
```

## Quick Start

### Test Run (20 globin proteins)
```bash
# Process small test dataset
./bioyoda.sh run protein_similarity_diamond --test --local

# Result: Filtered TSV ready for BioBTree
# test_out/data/processed/protein_similarity_diamond/merged/filtered_top10.tsv
```

### Production Run - SwissProt (570K proteins)
```bash
# Process SwissProt proteins with parallel DIAMOND jobs
./bioyoda.sh run protein_similarity_diamond --cluster --jobs 100

# Result: Filtered TSV ready for BioBTree identifier mapping
# work/data/processed/protein_similarity_diamond/merged/filtered_top100.tsv
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
work/raw_data/protein_similarity_diamond/
└── uniprot_swissprot.fasta  (or uniprot_trembl.fasta)
```

### 2. Split FASTA (`split_fasta.py`) - CHECKPOINT
- Splits large FASTA into manageable chunks
- Each chunk processed in parallel DIAMOND job
- Enables distributed CPU processing

**Output**:
```bash
work/raw_data/protein_similarity_diamond/chunks/
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
work/raw_data/protein_similarity_diamond/diamond_db/
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
work/data/processed/protein_similarity_diamond/results/
├── chunk_001.tsv  # TSV: query, target, identity, evalue, bitscore
├── chunk_002.tsv
└── ...
```

### 5. Merge Results (`merge_results`)
- Concatenates all chunk TSV files
- Creates single large TSV

**Output**:
```bash
work/data/processed/protein_similarity_diamond/merged/
└── merged_results.tsv  # All similarity pairs
```

### 6. Filter Top-K (`filter_top_k.py`) - FINAL OUTPUT
- Keeps top-K hits per query protein
- Filters by minimum identity threshold
- Reduces data size dramatically
- **TSV output ready for BioBTree parsing**

**Output**:
```bash
work/data/processed/protein_similarity_diamond/merged/
└── filtered_top100.tsv  # Top-K per protein (BioBTree-ready)
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

## BioBTree TSV Format

Output format for BioBTree identifier mapping (TSV with tab-separated columns):

```tsv
query_id	target_id	identity	alignment_length	mismatches	gap_opens	q_start	q_end	s_start	s_end	evalue	bitscore
sp|Q6GZX4|...	sp|Q6GZX3|...	98.5	256	3	1	1	256	1	256	1e-180	512.3
sp|Q6GZX4|...	sp|Q197F8|...	45.2	198	95	5	12	205	8	201	1e-45	156.7
sp|Q6GZX4|...	sp|P12345|...	42.1	187	89	3	15	198	10	192	3e-42	148.9
```

**TSV Columns** (DIAMOND BLASTP outfmt 6):
1. `query_id` - Query protein ID (full sp|accession|name format)
2. `target_id` - Target protein ID
3. `identity` - Percent sequence identity
4. `alignment_length` - Length of alignment
5. `mismatches` - Number of mismatches
6. `gap_opens` - Number of gap openings
7. `q_start` - Query alignment start
8. `q_end` - Query alignment end
9. `s_start` - Subject alignment start
10. `s_end` - Subject alignment end
11. `evalue` - Expectation value
12. `bitscore` - Bit score

BioBTree can parse this TSV format directly for identifier mapping and graph queries.

## Performance

### Test Mode (20 globin proteins, 3 chunks)
- Runtime: ~2 minutes (CPU)
- Memory: 4GB per chunk
- Output: ~184 similarity pairs (filtered top-10)

### SwissProt Production (570K proteins, 100 chunks)
- **CPU**: ~12-24 hours (wall time with 100 parallel jobs)
- Memory: 32GB per chunk
- **Parallel**: 100 jobs × 4 cores each
- Storage: ~10GB merged TSV → ~500MB filtered TSV

### TrEMBL Production (250M proteins, 1000 chunks)
- **CPU**: ~5-7 days (wall time with 500 parallel jobs)
- Memory: 32GB per chunk
- **Parallel**: 500 jobs × 4 cores each
- Storage: ~500GB merged TSV → ~5GB filtered TSV

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
    └── merged/
        ├── merged_results.tsv         # All results merged
        └── filtered_top100.tsv        # Top-K filtered (BioBTree-ready)
```

## Workflow Examples

### Example 1: Standard SwissProt
```bash
# 1. Process proteins to filtered TSV (parallel CPU jobs)
./bioyoda.sh run protein_similarity_diamond --cluster --jobs 100

# 2. Use BioBTree for identifier mapping (external tool)
# BioBTree can parse the TSV directly
biobtree insert --input work/data/processed/protein_similarity_diamond/merged/filtered_top100.tsv

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

# 3. BioBTree integration (TSV input)
biobtree insert --input work/data/processed/protein_similarity_diamond/merged/filtered_top50.tsv
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
ls -lh work/data/processed/protein_similarity_diamond/results/chunk_*.tsv | wc -l

# Check merged results
wc -l work/data/processed/protein_similarity_diamond/merged/merged_results.tsv

# Check filtered results
wc -l work/data/processed/protein_similarity_diamond/merged/filtered_top100.tsv
```

### Inspect TSV Output
```bash
# View TSV format (DIAMOND blastp outfmt 6)
head work/data/processed/protein_similarity_diamond/results/chunk_001.tsv

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
  work/data/processed/protein_similarity_diamond/results/chunk_005.tsv \
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
