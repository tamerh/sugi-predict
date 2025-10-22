# Patents Module

**Status**: ✅ **WORKING** - SureChEMBL + USPTO-Chem Enrichment
**Last Updated**: October 21, 2025
**Version**: 2.0

## Overview

This module processes patent data from SureChEMBL to create searchable embeddings for the BioYoda knowledge graph. It produces two types of search indices:

1. **Patent Text Search**: Semantic search using S-BioBERT embeddings (768-dimensional)
2. **Chemical Structure Search**: Similarity search using Morgan fingerprints (2048-bit)

Both indices are stored in FAISS format and can be inserted into Qdrant for vector search.

## Data Source: SureChEMBL

**What is SureChEMBL?**
- Patent chemistry database from EMBL-EBI
- 43M+ patent records from USPTO, EPO, WIPO
- 30M+ extracted chemical compounds
- Bi-weekly updates via FTP

**Download**: `https://ftp.ebi.ac.uk/pub/databases/chembl/SureChEMBL/bulk_data/`

**What SureChEMBL Provides:**
- ✅ Patent titles, IPC/CPC codes, assignees, publication dates
- ✅ Extracted chemical structures (SMILES, InChI)
- ✅ Compound-to-patent mappings
- ❌ **NO full text** (no abstracts, descriptions, or claims)

**Data Files** (4 Parquet files per release):

```
compounds.parquet (3.9GB, 30M rows)
├── id: SureChEMBL compound ID
├── smiles: Chemical structure
├── inchi: InChI identifier
└── mol_weight: Molecular weight

patents.parquet (5.7GB, 43M rows)
├── id: Internal patent ID
├── patent_number: Patent number (e.g., US-5153197-A)
├── country: Patent country code
├── publication_date: Publication date
├── family_id: Patent family ID
├── title: Patent title (ONLY text field!)
├── ipc, cpc: Classification codes
└── asignee: Assignees (note: typo in field name)

patent_compound_map.parquet (4.7GB, 1.5B rows)
├── patent_id: Links to patents.parquet
├── compound_id: Links to compounds.parquet
└── field_id: Where compound appeared (1=desc, 2=claims, etc.)

fields.parquet (1.7KB)
└── Field ID descriptions
```

## USPTO-Chem Enrichment

**Problem**: SureChEMBL only has patent titles, not full text.

**Solution**: Enrich US patents with abstracts from USPTO-Chem historical data.

**Coverage**:
- 493K US patents (2001-2025) with title + abstract
- Source: https://eloyfelix.github.io/uspto-chem/
- Format: Pre-processed JSON converted to single parquet file (137MB)

**How It Works**:
1. Download USPTO-Chem historical JSON files (~3,400 files, one-time)
2. Convert to `uspto_historical.parquet` using `process_uspto_json.py`
3. During processing, load USPTO parquet into memory
4. Join by `patent_number` to add abstracts to matching US patents
5. Mark enriched patents: `has_full_text=True`, `text_source='surechembl+uspto'`

**Expected Enrichment Rates**:
- **Production**: ~5-10% of US patents (only 2001+ patents match)
- **Test (first 500)**: ~0% (mostly 1980s-1990s patents - temporal mismatch)
- **Test with fixture**: ~100% (using guaranteed matches)

**Why Low Enrichment?**
- SureChEMBL: 9.4M US patents (1970s-present)
- USPTO-Chem: 493K US patents (2001-2025 only)
- Gap: ~90% of US patents are pre-2001 → cannot be enriched
- **This is expected**, not a bug

**Enrichment Distribution** (Production Run):
- Chunks with 2001+ patents: 4-6% enrichment rate (20K-35K patents enriched per 1M chunk)
- Chunks with pre-2001 patents: 0% enrichment (no matches in USPTO data)
- Total enriched: ~490K US patents out of 9.4M (~5.2% overall)
- **Uneven distribution is normal** - depends on temporal overlap with USPTO dataset

**Testing Enrichment**:

To test with guaranteed matches, uncomment in `config/test_overrides.yaml`:
```yaml
patents:
  test_patent_ids_file: "tests/fixtures/patents/test_patent_ids_with_uspto.txt"
```

This file contains 100 patent IDs (2001+ US patents) that match USPTO data, giving ~100% enrichment.

## Pipeline Steps

### 1. Download Data

Downloads latest SureChEMBL release:

```bash
./bioyoda.sh run patents --cluster
```

Script: `modules/patents/scripts/download_and_prepare_patents.py`

Output:
```
raw_data/patents/surechembl/2025-10-01/
├── compounds.parquet
├── patents.parquet
├── patent_compound_map.parquet
└── fields.parquet
```

### 2. Process Patent Text

Generates semantic embeddings for text search:

Script: `modules/patents/scripts/process_patents.py`

**Steps**:
1. Load patents from parquet
2. Enrich US patents with USPTO abstracts (if enabled)
3. Generate S-BioBERT embeddings (768-dim) from title + abstract
4. Create FAISS index + metadata JSON

**Output**:
```
data/processed/patents/text/
├── patents_text.index    # FAISS vectors (768-dim)
└── patents_text.json     # Metadata
```

**Metadata Format**:
```json
{
  "0": {
    "patent_id": "US-20110053848-A1",
    "title": "EGFR inhibitors...",
    "has_full_text": true,
    "text_source": "surechembl+uspto",
    "family_id": "12345",
    "pub_date": "2011-03-03",
    "ipc_codes": ["A61K31/517"],
    "assignees": ["AstraZeneca"]
  }
}
```

### 3. Process Compounds

Generates chemical fingerprints for structure search:

Script: `modules/patents/scripts/process_compounds.py`

**Steps**:
1. Load compounds from parquet
2. Load patent-compound mappings
3. Generate Morgan fingerprints (2048-bit, radius=2) using RDKit
4. Create FAISS index + metadata JSON

**Output**:
```
data/processed/patents/compounds/
├── compounds.index       # FAISS vectors (2048-bit)
└── compounds.json        # Metadata
```

**Metadata Format**:
```json
{
  "0": {
    "surechembl_id": "SCHEMBL123",
    "smiles": "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O",
    "molecular_weight": 206.28,
    "patent_ids": ["US-20110053848-A1", "EP-2023-789012-B1"],
    "patent_count": 2
  }
}
```

### 4. Convert to Biobtree JSON

Converts parquet files to JSON format for biobtree ingestion:

Script: `modules/patents/scripts/convert_to_biobtree_json.py`

**Purpose**: Biobtree uses its jsparser to load JSON data for cross-reference mapping.

**Converts**:
- `patents.parquet` → `patents.json` (wrapped as `{"patents": [...]}`)
- `compounds.parquet` → `compounds.json` (wrapped as `{"compounds": [...]}`)
- `patent_compound_map.parquet` → `mapping.json` (wrapped as `{"mappings": [...]}`)

**Output**:
```
data/processed/patents/biobtree/
├── patents.json
├── compounds.json
├── mapping.json
└── conversion_summary.json
```

**Usage**:
```bash
python modules/patents/scripts/convert_to_biobtree_json.py \
  --input raw_data/patents/surechembl/2025-10-01 \
  --output data/processed/patents/biobtree \
  --verbose
```

These JSON files are then loaded by biobtree for cross-reference queries.

## Memory-Efficient Processing

**Challenge**: Cannot load 43M patents or 1.5B mappings into RAM

**Solution**: Streaming with PyArrow

### Patents Processing
```python
import pyarrow.parquet as pq

parquet_file = pq.ParquetFile('patents.parquet')
for batch in parquet_file.iter_batches(batch_size=100000):
    df = batch.to_pandas()
    # Process 100K patents at a time
    process_batch(df)
```

### Compounds Processing (3-Step Streaming)

**Step 1**: Collect compound IDs only (~2GB)
```python
compound_ids = set()
for batch in iter_batches('compounds.parquet'):
    compound_ids.update(batch['id'])
```

**Step 2**: Load mappings filtered by IDs (~5GB)
```python
compound_to_patents = {}
for batch in iter_batches('patent_compound_map.parquet'):
    filtered = batch[batch['compound_id'].isin(compound_ids)]
    # Build mapping dictionary
```

**Step 3**: Process compounds with mappings
```python
for batch in iter_batches('compounds.parquet'):
    # Generate fingerprints
    # Add patent IDs from mapping dict
    # Accumulate results
```

**Memory Usage**:
- Test mode: ~2GB peak
- Production: ~12GB peak

## Configuration

### Test Mode (`config/test_overrides.yaml`)

```yaml
patents:
  test_mode: true
  test_limit_compounds: 1000        # First 1K compounds
  test_limit_patents: 500           # First 500 patents (fallback)
  #test_patent_ids_file: "tests/fixtures/patents/test_patent_ids_with_uspto.txt"
  max_mapping_rows: 10000000        # Scan 10M mapping rows (vs 1.5B)

  # USPTO enrichment
  enable_uspto: true
  uspto_historical_json_dir: "snapshots/raw_data/patents/historical_uspto"

  # Resources
  encode_batch_size: 32
  num_workers: 1
  process_memory_mb: 12288          # 12GB (for USPTO data)
```

### Production Mode (`config/config.yaml`)

```yaml
patents:
  test_mode: false
  # No limits - process all data

  # USPTO enrichment
  enable_uspto: true
  uspto_historical_json_dir: "snapshots/raw_data/patents/historical_uspto"

  # Resources
  encode_batch_size: 128
  num_workers: 8
  process_memory_mb: 20480          # 20GB
```

## Usage

### Quick Test
```bash
# Test with 500 patents + 1000 compounds
./bioyoda.sh run patents --config config/test_overrides.yaml --local
```

### Test with USPTO Enrichment
```bash
# Uncomment test_patent_ids_file in config/test_overrides.yaml first
./bioyoda.sh run patents --config config/test_overrides.yaml --local
```

### Production Run
```bash
# Process all 43M patents + 30M compounds
./bioyoda.sh run patents --cluster --bg --jobs 50
```

### Monitor Progress
```bash
# Check logs
tail -f test_out/logs/patents/process_text_*.log
tail -f test_out/logs/patents/process_compounds_*.log
```

## Output Files

```
test_out/
├── raw_data/patents/surechembl/2025-10-01/
│   ├── compounds.parquet
│   ├── patents.parquet
│   ├── patent_compound_map.parquet
│   └── fields.parquet
│
├── data/processed/patents/
│   ├── text/
│   │   ├── patents_text.index
│   │   └── patents_text.json
│   ├── compounds/
│   │   ├── compounds.index
│   │   └── compounds.json
│   └── biobtree/
│       ├── patents.json
│       ├── compounds.json
│       ├── mapping.json
│       └── conversion_summary.json
│
└── logs/patents/
    ├── download_*.log
    ├── process_text_*.log
    └── process_compounds_*.log
```

## Next Steps

After processing, insert to Qdrant for vector search:

```bash
# Start Qdrant server
./bioyoda.sh qdrant start

# Insert patent text
./bioyoda.sh qdrant insert patents_text

# Insert compounds
./bioyoda.sh qdrant insert patents_compounds
```

## Search Examples

### Text Search (via Qdrant)
```python
# Find patents about EGFR inhibitors
results = qdrant.search(
    collection_name="patents_text",
    query_vector=encode("EGFR tyrosine kinase inhibitors lung cancer"),
    limit=50
)
```

### Chemical Search (via Qdrant)
```python
# Find similar structures to aspirin
results = qdrant.search(
    collection_name="patents_compounds",
    query_vector=morgan_fingerprint("CC(=O)Oc1ccccc1C(=O)O"),
    limit=50
)
```

## Performance

### Test Mode
- **Data**: 500 patents, 1K compounds
- **Time**: 2-3 minutes
- **Memory**: 2GB peak

### Production Mode
- **Data**: 43M patents, 30M compounds
- **Time**: 6-8 hours (parallel on cluster)
- **Memory**: 12-20GB per job
- **Storage**: ~200GB total

## Troubleshooting

### Check Downloads
```bash
ls -lh test_out/raw_data/patents/surechembl/2025-10-01/
```

### Verify Parquet Files
```bash
conda run -n bioyoda python3 -c "
import pandas as pd
df = pd.read_parquet('test_out/raw_data/patents/surechembl/2025-10-01/patents.parquet')
print(f'Patents: {len(df):,}')
print(df.columns.tolist())
"
```

### Check Processing Logs
```bash
tail -f test_out/logs/patents/process_text_*.log
```

### Test Processing Directly
```bash
conda run -n bioyoda python3 modules/patents/scripts/process_patents.py \
  --input test_out/raw_data/patents/surechembl/2025-10-01/patents.parquet \
  --output-index test_out/data/processed/patents/text/test.index \
  --output-metadata test_out/data/processed/patents/text/test.json \
  --limit 10 \
  --uspto-data snapshots/raw_data/patents/historical_uspto/uspto_historical.parquet
```

## Key Scripts

```
modules/patents/scripts/
├── download_and_prepare_patents.py    # Unified download pipeline
├── process_patents.py                 # Text processing + embeddings
├── process_compounds.py               # Chemical fingerprints
├── process_uspto_json.py              # Convert USPTO JSON to parquet
└── convert_to_biobtree_json.py        # Convert parquet to JSON for biobtree

tests/
└── generate_patents_fixture.py        # Generate test fixture with USPTO matches
```

## Related Documentation

- **Qdrant Module**: `../qdrant/README.md` - Vector database insertion
- **SureChEMBL Docs**: https://chembl.gitbook.io/surechembl
- **USPTO-Chem**: https://eloyfelix.github.io/uspto-chem/

---

**Last Updated**: October 21, 2025
