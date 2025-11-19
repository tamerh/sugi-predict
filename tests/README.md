# BioYoda Test Suite (v2)

Simple, result-oriented testing system for BioYoda with fixture-based data and query validation.

## Philosophy

This testing system focuses on **practical, result-oriented testing** rather than complex unit tests:

- ✅ **Real queries** against real (fixture) data
- ✅ **End-to-end validation** of search and RAG functionality
- ✅ **Fast feedback** with fixture mode (2-3 minutes)
- ✅ **Full E2E testing** with pipeline mode (15-20 minutes)
- ✅ **Simple maintenance** - no complex pytest fixtures or mocking
- ✅ **Iterative improvement** - add queries, run tests, fix issues

## Quick Start

```bash
# Run tests with fixtures (fast - recommended for development)
./bioyoda.sh test

# Run full pipeline test (slower - for comprehensive validation)
./bioyoda.sh test --pipeline
```

## Directory Structure

```
tests/
├── README.md                              # This file
├── validate_queries.py                     # Query validation script (executable)
├── queries.txt                             # Clinical trials test queries (10 queries)
├── queries_pubmed.txt                      # PubMed test queries (10 queries)
└── fixtures/                               # Test data fixtures
    ├── README.md                           # Fixture documentation
    ├── pubmed/
    │   ├── test_abstracts.xml.gz           # 50 real PubMed abstracts (68KB)
    │   └── test_abstracts_pmids.txt        # List of PMIDs in fixture
    ├── clinical_trials/
    │   ├── test_nct_ids.txt                # 50 NCT IDs for filtering (743B)
    │   └── sample_trials.json              # 50 extracted trials (275KB)
    └── patents/
        ├── test_patent_ids_with_uspto.txt  # 100 patent IDs (113 lines with header)
        ├── patents_text.json               # 100 patent text entries (184KB)
        └── compounds.json                  # 1000 compound entries (249KB)
```

## Test Modes

### Fixture Mode (Default - Fast)

Uses pre-existing fixture data and runs minimal processing:

```bash
./bioyoda.sh test
```

**Steps:**
1. Setup test environment (copy fixtures to test_out/)
2. Run minimal data processing for all modules (~1-2 min):
   - PubMed: 50 abstracts
   - Clinical Trials: 50 trials
   - Patents: 100 patents + 1000 compounds
3. Start Qdrant server
4. Insert data to Qdrant (5 collections total)
5. Start API server
6. Validate queries from queries.txt and queries_pubmed.txt
7. Cleanup

**Duration:** ~2-3 minutes
**Use when:** Developing features, testing query performance, rapid iteration

### Pipeline Mode (Full E2E)

Runs the complete data processing pipeline from scratch:

```bash
./bioyoda.sh test --pipeline
```

**Steps:**
1. Clean test_out/ directory
2. Run full pipeline for all modules (~15-20 min):
   - PubMed processing
   - Clinical Trials processing
   - Patents processing (text + compounds)
3. Start Qdrant server
4. Insert data to Qdrant (5 collections)
5. Start API server
6. Validate queries from queries.txt and queries_pubmed.txt
7. Cleanup

**Duration:** ~15-20 minutes
**Use when:** Testing pipeline changes, validating full E2E workflow, pre-release testing

## Query Validation

The test suite validates two types of queries:

### 1. Search Queries

Tests the `/search` endpoint with queries from query files:
- **Clinical Trials**: `queries.txt` (10 queries testing clinical_trials collection)
- **PubMed**: `queries_pubmed.txt` (10 queries testing pubmed_abstracts collection)
- **Patents**: Currently NOT validated (see Patents section below)
- Verifies API returns results
- Checks result count > 0
- Shows top matching documents with scores
- Reports PMID/NCT IDs of top matches

### 2. RAG Queries (Optional)

Tests the `/ask` endpoint by generating questions from search queries:
- Verifies answer generation works
- Checks source citations are included
- Validates answer quality warnings
- Skips gracefully if RAG not configured

## Test Output

The validation script provides color-coded output:

```
================================================================================
SEARCH QUERY VALIDATION
================================================================================

Clinical Trials Queries (10 queries)
----------------------------------------

1. Query: What are the eligibility criteria for studies using vagal nerve stimulation?
   Collections: clinical_trials
   ✓ PASS: 15 results
     Top: NCT:NCT04484285 (score: 0.876)

...

----------------------------------------
Clinical Trials: 10/10 passed ✓
----------------------------------------

PubMed Queries (10 queries)
----------------------------------------

1. Query: How does pregnancy affect bone density and osteoporosis recovery?
   Collections: pubmed_abstracts
   ✓ PASS: 8 results
     Top: PMID:12345678 (score: 0.734)

...

----------------------------------------
PubMed: 10/10 passed ✓
----------------------------------------

================================================================================
Overall Search Results: 20/20 passed ✓
================================================================================

================================================================================
RAG QUERY VALIDATION
================================================================================

1. Question: What are the eligibility criteria for studies on vagal nerve stimulation?
   ✓ Generated answer (1234 chars)
     Sources: 3
     Citations: NCT04484285, NCT05417490, NCT03990558

...

--------------------------------------------------------------------------------
RAG Results: 5/5 passed ✓
--------------------------------------------------------------------------------

================================================================================
FINAL RESULTS
================================================================================
Clinical Trials Search: 10/10 passed
PubMed Search:          10/10 passed
Total Search:           20/20 passed
RAG:                    5/5 passed

NOTE: Patents collections are processed but NOT query-validated
      (patents_text: 100 docs, patents_compounds: 1000 docs)

================================================================================
TOTAL: 25/25 passed

✓ All tests passed!
================================================================================
```

## Adding New Queries

To add new test queries:

### For Clinical Trials

1. **Edit queries.txt:**
   ```bash
   vim tests/queries.txt
   ```

2. **Add your query** (one per line, with or without quotes):
   ```
   "Find studies on CRISPR gene editing in cancer"
   ```

### For PubMed

1. **Edit queries_pubmed.txt:**
   ```bash
   vim tests/queries_pubmed.txt
   ```

2. **Add your query** (one per line, with or without quotes):
   ```
   "What is the mechanism of action of mRNA vaccines?"
   ```

### Run Tests

3. **Run tests:**
   ```bash
   ./bioyoda.sh test
   ```

4. **Review results** - queries should match fixture data

**Tips:**
- Queries are designed to match fixture data (50 clinical trials, 50 PubMed abstracts)
- **Clinical trials queries**: Focus on trial-specific concepts (eligibility, interventions, outcomes)
- **PubMed queries**: Focus on research topics, mechanisms, treatments covered in literature
- Avoid overly specific queries that won't match any fixture data
- Test both broad and specific query types

## Protein Similarity ESM-2 Testing

### Current Status (✓ Implemented)

Protein similarity ESM-2 module has been fully integrated into the test framework:

**Test Fixtures:**
- ✓ Test protein sequences: `tests/fixtures/esm2/test_proteins.fasta` (1000 proteins)
- ✓ Metadata file: `tests/fixtures/esm2/test_proteins.fasta.metadata.txt`

**Test Configuration:**
```yaml
esm2:
  test_mode: true
  test_limit_proteins: 1000     # Download first 1000 proteins from SwissProt
  test_num_chunks: 10           # Split into 10 chunks (100 proteins each)
```

**Test Behavior:**
1. Downloads SwissProt FASTA from UniProt
2. Limits to first 1000 sequences during decompression
3. Splits into 10 chunks for parallel processing
4. Generates ESM-2 embeddings for all chunks (1280 dimensions)
5. Merges into single HDF5 file
6. Ready for Qdrant insertion

**Expected Runtime:** ~10-15 minutes (depending on GPU availability)

**Regenerating Fixtures:**
```bash
# Clean and regenerate test data
./bioyoda.sh stop esm2 --test --clean
./bioyoda.sh run esm2 --test

# Copy to fixtures
cp test_out/raw_data/esm2/uniprot_test.fasta \
   tests/fixtures/esm2/test_proteins.fasta
```

## Patents Testing

### Current Status

The test suite includes patents data processing but **does NOT** include query validation for patents. Here's the current state:

#### ✅ What's Implemented

**Data Processing:**
- **Fixtures exist**: 100 patent text entries + 1000 compound entries
- **Test config**: `config/test_config.yaml` includes patents configuration
- **Pipeline integration**: `./bioyoda.sh test` processes patents data
- **Qdrant collections**: Both collections are created and populated:
  - `patents_text` - 100 patent text entries (S-BioBERT 768-dim embeddings)
  - `patents_compounds` - 1000 compound entries (Morgan/ECFP4 2048-bit fingerprints)

**Test Configuration (`config/test_config.yaml`):**
```yaml
patents:
  test_mode: true
  test_limit_files: 4
  test_limit_patents: 500           # Limit patents to process
  test_limit_compounds: 1000        # Limit compounds to process
  test_patent_ids_file: "tests/fixtures/patents/test_patent_ids_with_uspto.txt"
  patents_per_chunk: 100
  compounds_per_chunk: 100
  enable_uspto: true                # Enable USPTO enrichment
```

#### ❌ What's Missing

**Query Validation:**
- No `queries_patents.txt` file (for patent text search)
- No `queries_compounds.txt` file (for chemical similarity search)
- `validate_queries.py` does NOT test patents collections
- No automated validation of patents search results

#### ⚠️ API Integration Limitations

**patents_text Collection (Semantic Search):**
- ✅ **CAN be searched via API** `/search` endpoint
- Uses S-BioBERT model (same as PubMed/Clinical Trials)
- Supports semantic search for patent concepts/keywords
- Example query: `"CRISPR gene editing applications"`

**patents_compounds Collection (Chemical Similarity):**
- ❌ **CANNOT be searched via current API** `/search` endpoint
- Uses RDKit Morgan fingerprints, NOT a neural network model
- API's `encode_query()` uses SentenceTransformer (incompatible with chemical fingerprints)
- Requires direct Qdrant API access or custom chemical search endpoint

### Testing Patents Collections

While automated query validation is not implemented, you can manually test patents collections:

#### Test Patent Text Search (via API)

```bash
# Example patent text search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "CRISPR gene editing",
    "collections": ["patents_text"],
    "limit": 5
  }' | jq
```

#### Test Chemical Similarity Search (via Qdrant API)

Chemical similarity requires direct Qdrant access with pre-computed Morgan fingerprints:

```python
#!/usr/bin/env python3
"""Test chemical similarity search in patents_compounds collection."""

import requests
from rdkit import Chem
from rdkit.Chem import AllChem

QDRANT_URL = "http://localhost:6333"

# 1. Get a sample compound vector from the collection
scroll_response = requests.post(
    f"{QDRANT_URL}/collections/patents_compounds/points/scroll",
    json={"limit": 1, "with_vector": True}
)
query_vector = scroll_response.json()['result']['points'][0]['vector']

# 2. Search for similar compounds
search_response = requests.post(
    f"{QDRANT_URL}/collections/patents_compounds/points/search",
    json={"vector": query_vector, "limit": 5, "with_payload": True}
)

# 3. Display results
for i, result in enumerate(search_response.json()['result'], 1):
    print(f"{i}. Score: {result['score']:.4f}")
    print(f"   SureChEMBL ID: {result['payload']['surechembl_id']}")
    print(f"   SMILES: {result['payload']['smiles'][:60]}...")
    print()
```

**Note:** To search by a specific SMILES string, you need to:
1. Install RDKit (`conda install -c conda-forge rdkit`)
2. Generate Morgan fingerprint from SMILES
3. Convert to 2048-bit vector
4. Search with that vector

### Collections Created During Testing

When you run `./bioyoda.sh test`, the following collections are created:

| Collection | Type | Documents | Vector Dimension | Purpose |
|------------|------|-----------|------------------|---------|
| `pubmed_abstracts` | Text | 50 | 768 | PubMed semantic search |
| `clinical_trials` | Text | 50 | 768 | Clinical trials search |
| `patents_text` | Text | 100 | 768 | Patent semantic search |
| `patents_compounds` | Chemical | 1000 | 2048 | Chemical similarity |
| `esm2` | Protein | 1000 | 1280 | Protein similarity search |

**Total: 5 collections, 2,200 documents**

### Fixture Details

**Patent Text Fixture (`fixtures/patents/patents_text.json`):**
- 100 patent entries (184KB)
- Fields: `patent_id`, `title`, `abstract`, `text`, `chunk_type`
- Includes USPTO enrichment (full text for US patents)
- Suitable for semantic search testing

**Compounds Fixture (`fixtures/patents/compounds.json`):**
- 1000 compound entries (249KB)
- Fields: `surechembl_id`, `smiles`, `molecular_weight`, `patent_id`
- 2048-bit Morgan fingerprints (ECFP4)
- Suitable for chemical similarity testing

**Patent IDs File (`fixtures/patents/test_patent_ids_with_uspto.txt`):**
- 100 patent IDs (113 lines with header)
- Used to filter patents during processing
- Includes mix of US and international patents

### Future Enhancements

To achieve full patents query validation:

1. **Add Chemical Search API Endpoint:**
   - Implement `/search/chemical` endpoint with RDKit support
   - Accept SMILES strings and generate fingerprints on-the-fly
   - Return similar compounds from patents_compounds collection

2. **Create Query Files:**
   - `queries_patents.txt` - Semantic queries for patent text
   - Add to `validate_queries.py` for automated testing

3. **Chemical Query Validation:**
   - Would require either:
     - Custom endpoint (option 1 above)
     - Or separate validation script with RDKit dependency

4. **Patent-Specific Metrics:**
   - Patent ID format validation
   - SMILES string validity checks
   - Molecular weight range checks

## Configuration

Tests use `config/test_config.yaml` which specifies:

```yaml
base_dir: test_out/  # All test outputs go here

pubmed:
  test_mode: true
  test_fixture_file: "test_out/raw_data/pubmed/baseline/test_abstracts.xml.gz"

clinical_trials:
  test_mode: true
  test_nct_ids_file: "tests/fixtures/clinical_trials/test_nct_ids.txt"

patents:
  test_mode: true
  test_limit_patents: 500
  test_limit_compounds: 1000
  test_patent_ids_file: "tests/fixtures/patents/test_patent_ids_with_uspto.txt"
  enable_uspto: true

# Model must match what was used during indexing
pubmed:
  model_name: "pritamdeka/S-BioBERT-snli-multinli-stsb"
clinical_trials:
  model_name: "pritamdeka/S-BioBERT-snli-multinli-stsb"
patents:
  model_name: "pritamdeka/S-BioBERT-snli-multinli-stsb"  # For patents_text only
```

## Troubleshooting

### Tests fail with "No results found"

**Possible causes:**
- Model mismatch (indexing with one model, querying with another)
- Fixture data not properly loaded
- Qdrant collections empty

**Solution:**
```bash
# Check Qdrant status
./bioyoda.sh qdrant status --test

# Verify collections exist
curl http://localhost:6333/collections

# Re-run with clean state
rm -rf test_out/
./bioyoda.sh test
```

### API server not starting

**Possible causes:**
- Qdrant server not running
- Port 8000 already in use
- Missing dependencies

**Solution:**
```bash
# Check Qdrant is running
curl http://localhost:6333/healthz

# Check if port is in use
lsof -i :8000

# Check API logs
tail -f test_out/logs/api/server.log
```

### "Model mismatch" warning

**Cause:** Embedding model used during indexing doesn't match the model specified in config.

**Solution:**
1. Verify `config/test_config.yaml` has correct model
2. Clean and rebuild indices:
   ```bash
   rm -rf test_out/
   ./bioyoda.sh test
   ```

### RAG queries fail but search works

**Possible causes:**
- RAG model not configured (this is OK - RAG tests will skip)
- RAG endpoint error (check API logs)

**Solution:**
```bash
# Check API health endpoint
curl http://localhost:8000/health | jq

# Test RAG endpoint directly
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test question", "collections": ["clinical_trials"]}'
```

## Advanced Usage

### Run validation script directly

```bash
# Basic run
python tests2/validate_queries.py

# Verbose output (show full results)
python tests2/validate_queries.py --verbose

# Only test search (skip RAG)
python tests2/validate_queries.py --search-only

# Only test RAG (skip search)
python tests2/validate_queries.py --rag-only

# Custom API URL
python tests2/validate_queries.py --api-url http://localhost:8001
```

### Manual test workflow

```bash
# 1. Start servers manually
./bioyoda.sh run all --test --local --cores 2
./bioyoda.sh qdrant start --mode local --test
./bioyoda.sh qdrant insert all --test --local --cores 2
./bioyoda.sh api start --test

# 2. Run validation
python tests2/validate_queries.py --verbose

# 3. Cleanup
./bioyoda.sh api stop --test
./bioyoda.sh qdrant stop --test
```

### Inspect fixture data

```bash
# View PubMed fixture
zcat tests2/fixtures/pubmed/test_abstracts.xml.gz | less

# View Clinical Trials NCT IDs
cat tests2/fixtures/clinical_trials/test_nct_ids.txt

# View Clinical Trials sample data
jq '.[0]' tests2/fixtures/clinical_trials/sample_trials.json | less
```

## Continuous Integration

The test suite is designed for CI/CD integration:

```bash
# Run tests and capture exit code
./bioyoda.sh test
EXIT_CODE=$?

# Exit code 0 = all tests passed
# Exit code 1 = some tests failed

if [ $EXIT_CODE -eq 0 ]; then
  echo "Tests passed - ready to deploy"
else
  echo "Tests failed - check logs"
  exit 1
fi
```

## Differences from Old Test System (tests/)

| Aspect | Old System (tests/) | New System (tests2/) |
|--------|---------------------|----------------------|
| **Framework** | pytest with complex fixtures | Simple Python script |
| **Focus** | Unit tests + E2E tests | Result validation only |
| **Queries** | Not validated | Validated every run |
| **Maintenance** | High (mocking, fixtures) | Low (just add queries) |
| **Speed** | Varies | Fast (fixture mode) |
| **CI/CD** | Complex setup | Simple exit codes |
| **Documentation** | Detailed but complex | Simple and practical |

## Future Enhancements

Potential improvements to consider:

- [ ] **Patents query validation** - Add `queries_patents.txt` and test patents_text search
- [ ] **Chemical search API** - Implement RDKit-based `/search/chemical` endpoint
- [ ] Add query performance benchmarks (latency, throughput)
- [ ] Compare results across different embedding models
- [ ] Add visual diff for result changes between runs
- [ ] Create category-based query lists (easy, medium, hard)
- [ ] Add regression test mode (compare to baseline results)
- [ ] Generate test reports in HTML/JSON format
- [ ] Add query-level debugging mode

## Getting Help

- **Test failures:** Check logs in `test_out/logs/`
- **API issues:** Review `test_out/logs/api/server.log`
- **Qdrant issues:** Review `test_out/logs/qdrant/`
- **General help:** `./bioyoda.sh help`
- **Report bugs:** Create issue with test output and logs

## Credits

Designed for solo developer workflow with focus on simplicity and fast iteration.
