# BioYoda Test Fixtures

This directory contains real data fixtures for deterministic testing of the BioYoda pipeline.

## Philosophy

Instead of dummy/fake data, we use **real data subsets** with **fixed IDs** for:
- ✅ Realistic testing with actual data quality
- ✅ Deterministic, reproducible tests
- ✅ Fast execution (small subsets)
- ✅ Version controlled (tiny ID lists)
- ✅ Easy to maintain and extend

## Directory Structure

```
tests/fixtures/
├── README.md                              # This file
├── pubmed/
│   ├── test_abstracts.xml.gz              # 50 real PubMed abstracts (68KB)
│   └── test_abstracts_pmids.txt           # List of PMIDs in fixture
└── clinical_trials/
    ├── test_nct_ids.txt                   # 50 NCT IDs for filtering (743B)
    └── sample_trials.json                 # 50 extracted trials (275KB)
```

## How It Works

### PubMed Testing
1. **Fixture**: `pubmed/test_abstracts.xml.gz` contains 50 real abstracts
2. **Setup**: `run_tests.sh` copies this file to `test_out/raw_data/pubmed/baseline/`
3. **Pipeline**: Processes this single file instead of downloading 1200+ files
4. **Result**: Fast, deterministic tests with real PubMed data

### Clinical Trials Testing
1. **ID List**: `clinical_trials/test_nct_ids.txt` contains 50 specific NCT IDs
2. **Filtering**: Extract scripts filter AACT database to only these IDs
3. **Config**: `test_config.yaml` references this file via `test_nct_ids_file`
4. **Result**: Processes only 50 specific trials from full AACT database

## Usage

### Running Tests

Simply use the test runner:
```bash
./run_tests.sh                    # All tests
./run_tests.sh unit               # Unit tests only
./run_tests.sh pubmed             # PubMed tests
./run_tests.sh clinical_trials    # Clinical trials tests
```

The `run_tests.sh` script automatically:
- ✅ Copies PubMed fixture to `test_out/raw_data/pubmed/baseline/`
- ✅ Verifies Clinical Trials NCT IDs file exists
- ✅ Runs tests with these fixtures

### Regenerating Fixtures

If you need to update fixtures with different data:

**PubMed Fixture:**
```bash
python tests/scripts/generate_pubmed_fixture.py \
    --source-dir /path/to/production/pubmed/raw_data \
    --output tests/fixtures/pubmed/test_abstracts.xml.gz \
    --num-abstracts 50 \
    --max-files 10
```

**Clinical Trials Fixture:**
```bash
# Extract different NCT IDs from production data
python3 -c "
import json
with open('out/data/processed/clinical_trials/trials_chunk_0001.json') as f:
    trials = json.load(f)
nct_ids = [trial['nct_id'] for trial in trials[:50]]
with open('tests/fixtures/clinical_trials/test_nct_ids.txt', 'w') as f:
    f.write('# Clinical Trials Test NCT IDs\n')
    for nct_id in nct_ids:
        f.write(f'{nct_id}\n')
"
```

## Adding New Test Cases

### To add edge cases for testing:

**PubMed:**
1. Find PMID with interesting characteristics (missing fields, special characters, etc.)
2. Re-run generation script with curated PMID list
3. Or manually add article to `test_abstracts.xml.gz`

**Clinical Trials:**
1. Find NCT ID with edge case characteristics
2. Add NCT ID to `test_nct_ids.txt`
3. Add comment explaining why (e.g., `# NCT12345678 - has missing interventions`)

## Configuration

**Test Config:** `config/test_config.yaml`

```yaml
pubmed:
  test_mode: true
  test_fixture_file: "test_out/raw_data/pubmed/baseline/test_abstracts.xml.gz"
  test_abstracts_limit: 100    # Fallback if fixture doesn't exist

clinical_trials:
  test_mode: true
  test_nct_ids_file: "tests/fixtures/clinical_trials/test_nct_ids.txt"
  test_trials_limit: 100       # Fallback if file doesn't exist
```

## Benefits Over Dummy Data

| Aspect | Dummy Data | Real Data Fixtures |
|--------|------------|-------------------|
| **Realism** | Artificial patterns | Actual data quality & edge cases |
| **Maintenance** | Must update when schema changes | Auto-validates schema compatibility |
| **Debugging** | Hard to trace issues | Can look up real PMID/NCT ID online |
| **Edge Cases** | Must manually craft | Real edge cases from production |
| **Trust** | "Will it work in prod?" | "It works with real data!" |

## File Sizes

- **PubMed fixture**: 68KB (50 abstracts in compressed XML)
- **Clinical Trials NCT IDs**: 743 bytes (50 IDs)
- **Clinical Trials sample JSON**: 275KB (50 extracted trials)
- **Total**: ~344KB for all fixtures

Compare to production:
- PubMed: 120GB+ (1200+ files)
- Clinical Trials: 2.2GB (AACT database)

## Notes

- **Version Control**: All fixtures are committed to git (tiny sizes)
- **Deterministic**: Same IDs every test run = reproducible results
- **No Downloads**: Tests run offline (fixtures already present)
- **Fast**: Process 50 items instead of 100,000+
- **Production Code Unchanged**: Filtering is test-mode only

## Future Enhancements

- Add more diverse edge cases as discovered
- Create category-based ID lists (e.g., `test_nct_ids_missing_fields.txt`)
- Add fixtures for specific bug reproductions
- Document rationale for each NCT ID / PMID selection
