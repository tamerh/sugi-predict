# BioYoda Test Suite

Comprehensive test suite for BioYoda biomedical search pipeline.

## Quick Start

```bash
# Install test dependencies
pip install pytest pytest-cov pyyaml requests

# Run unit tests only (fast - seconds)
./run_tests.sh unit

# Run PubMed tests (unit + e2e pipeline test - ~10-15 min)
./run_tests.sh pubmed
```

## Directory Structure

After reorganization, all outputs are organized under dedicated directories:

```
bioyoda_dev2/
├── out/                    # Production pipeline outputs
│   ├── raw_data/          # Downloaded data
│   ├── data/              # Processed data
│   └── logs/              # Pipeline logs
├── test_out/              # Test pipeline outputs (cleaned on each test run)
│   ├── raw_data/
│   ├── data/
│   └── logs/
├── tests/
│   ├── unit/              # Fast unit tests
│   └── integration/       # E2E pipeline tests
└── config/
    ├── config.yaml        # Production (outputs to out/)
    └── test_config.yaml   # Testing (outputs to test_out/)
```

## Test Types

### 1. Unit Tests (Fast - seconds)
Test individual functions in isolation with mock data.

```bash
# Run all unit tests
./run_tests.sh unit

# Run specific module
pytest tests/unit/pubmed/ -v
pytest tests/unit/clinical_trials/ -v
pytest tests/unit/qdrant/ -v
```

**What they test**: Individual functions like `merge_all_parts()`, `prepare_points()`, etc.

### 2. End-to-End (E2E) Tests (~15-25 minutes)
Actually run the full Snakemake pipeline with test config and validate output.

```bash
# Run PubMed E2E test (~10-15 min)
./run_tests.sh pubmed

# Run Clinical Trials E2E test (~5-10 min)
./run_tests.sh clinical_trials

# Run all E2E tests (~15-25 min)
./run_tests.sh e2e

# Or directly
pytest tests/integration/test_pubmed_e2e.py -m e2e -v
pytest tests/integration/test_clinical_trials_e2e.py -m e2e -v
```

**What happens (PubMed)**:
1. Cleans `test_out/` directory (fresh start)
2. Runs full pipeline: `./bioyoda.sh run pubmed --config test_config.yaml --local`
3. Downloads 2 PubMed files (debug mode)
4. Processes 100 abstracts per file (test mode)
5. Creates FAISS indices
6. Validates all outputs (merge is optional)
7. Leaves results in `test_out/` for inspection

**What happens (Clinical Trials)**:
1. Cleans `test_out/` directory (fresh start)
2. Runs full pipeline: `./bioyoda.sh run clinical_trials --config test_config.yaml --local`
3. Downloads clinical trials data
4. Processes 100 trials (test mode)
5. Creates FAISS indices with chunks
6. Validates all outputs
7. Leaves results in `test_out/` for inspection

**Test config settings**:
- PubMed: `debug_mode: true` (2 files), `test_abstracts_limit: 100`
- Clinical Trials: `test_mode: true`, `test_trials_limit: 100`
- `base_dir: ./test_out` → All outputs go here

## Test Structure

```
tests/
├── unit/                           # Fast unit tests (~1-5 min)
│   ├── pubmed/                     # PubMed module tests
│   │   ├── test_index.py          # Index creation tests
│   │   └── test_merge.py          # Merge function tests
│   ├── clinical_trials/            # Clinical trials module tests
│   │   └── test_process_trials.py # Processing & chunking tests
│   ├── qdrant/                     # Qdrant module tests
│   │   └── test_insert.py         # Insertion logic tests
│   └── common/                     # Shared/common tests
│       └── test_config.py         # Configuration validation
│
├── integration/                    # End-to-end pipeline tests (~10-30 min)
│   ├── test_pubmed_pipeline.py           # Full PubMed workflow
│   ├── test_clinical_trials_pipeline.py  # Full CT workflow
│   └── test_qdrant_integration.py        # Qdrant server & insertion
│
├── fixtures/                       # Test data and fixtures
├── conftest.py                     # Shared fixtures
├── pytest.ini                      # Pytest configuration
└── README.md                       # This file
```

## Test Categories

### Unit Tests (`tests/unit/`)

**Fast, isolated tests for individual functions:**

#### PubMed Tests
- `test_merge.py` - Merge function validation (CRITICAL for data integrity)
  - Verifies all vectors are preserved
  - Checks metadata-vector alignment
  - Tests dimension consistency
  - Validates metadata re-indexing

- `test_index.py` - Index creation validation
  - Tests deleted PMID filtering (CRITICAL)
  - Validates FAISS index creation
  - Checks vector dimensions
  - Tests metadata structure

#### Clinical Trials Tests
- `test_process_trials.py` - Text processing validation
  - Tests text cleaning (whitespace, HTML, URLs)
  - Validates chunking logic
  - Checks trial-to-chunks conversion
  - Tests minimum length enforcement

#### Qdrant Tests
- `test_insert.py` - Insertion logic validation
  - Tests batch creation
  - Validates point preparation
  - Checks vector-payload alignment
  - Tests checkpoint tracking

#### Common Tests
- `test_config.py` - Configuration validation
  - Validates YAML structure
  - Checks required fields
  - Tests model configuration
  - Validates resource settings

### E2E Tests (`tests/integration/`)

**Slow, end-to-end workflow tests that actually run the full pipeline:**

#### PubMed E2E Test (`test_pubmed_e2e.py`)
Tests complete workflow: download → process → index
- Downloads 2 PubMed files (debug mode)
- Processes 100 abstracts per file (test mode)
- Creates FAISS indices
- Validates all outputs in test_out/
- **Runtime**: ~10-15 minutes

#### Clinical Trials E2E Test (`test_clinical_trials_e2e.py`)
Tests complete workflow: download → process → index
- Downloads clinical trials data
- Processes 100 trials (test mode)
- Creates FAISS indices with chunks
- Validates metadata structure
- **Runtime**: ~5-10 minutes

## Running Tests

### Quick Commands

```bash
# All tests (unit + integration)
pytest -v

# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests only (slow)
pytest tests/integration/ -v -m integration

# Specific module
pytest tests/unit/pubmed/ -v           # PubMed unit tests
pytest tests/integration/test_pubmed_pipeline.py  # PubMed integration

# Skip slow tests
pytest -m "not slow"

# With coverage
pytest --cov=modules --cov-report=html
```

### Test Markers

```bash
# By marker
pytest -m unit           # Unit tests
pytest -m integration    # Integration tests
pytest -m slow           # Slow tests only
pytest -m qdrant         # Qdrant-specific tests
pytest -m "not slow"     # Skip slow tests

# Combined markers
pytest -m "integration and not slow"  # Fast integration tests
```

### Using run_tests.sh

```bash
./run_tests.sh              # All tests
./run_tests.sh unit         # Unit tests only
./run_tests.sh integration  # Integration tests only
./run_tests.sh pubmed       # PubMed tests (unit + integration)
./run_tests.sh ct           # Clinical trials tests
./run_tests.sh qdrant       # Qdrant tests
./run_tests.sh coverage     # With coverage report
```

## What Tests Catch

### 🔴 CRITICAL Issues (Data Loss Prevention)
1. **Vector-Metadata Misalignment** - Prevents data corruption
2. **Deleted PMID Filtering** - Ensures exclusions work
3. **Merge Data Loss** - Verifies all vectors preserved
4. **Dimension Mismatches** - Catches incompatible configs

### 🟡 Important Issues (Quality & Correctness)
1. **Config Validation** - Catches errors before jobs start
2. **Text Processing** - Ensures chunking works correctly
3. **Insertion Logic** - Validates batch processing
4. **Collection Structure** - Ensures Qdrant schema correct

### 🟢 Integration Issues (End-to-End)
1. **Pipeline Completion** - Verifies workflows finish
2. **File Creation** - Checks all outputs exist
3. **Idempotency** - Ensures re-runs are safe
4. **Search Functionality** - Validates Qdrant works

## E2E Test Workflow

E2E tests use test_config.yaml which outputs to test_out/ directory:

### 1. PubMed E2E Test
```bash
pytest tests/integration/test_pubmed_e2e.py -m e2e -v
```

**What it does:**
- Cleans test_out/ directory (fresh start)
- Runs: `./bioyoda.sh run pubmed --config test_config.yaml --local`
- Downloads 2 PubMed XML files (debug mode)
- Processes 100 abstracts per file (test mode)
- Creates FAISS indices
- Validates all outputs
- Leaves results in test_out/ for inspection

### 2. Clinical Trials E2E Test
```bash
pytest tests/integration/test_clinical_trials_e2e.py -m e2e -v
```

**What it does:**
- Cleans test_out/ directory (fresh start)
- Runs: `./bioyoda.sh run clinical_trials --config test_config.yaml --local`
- Downloads clinical trials data
- Processes 100 trials (test mode)
- Creates chunked FAISS indices
- Validates chunk structure
- Leaves results in test_out/ for inspection

**Run all E2E tests in sequence:**
```bash
pytest tests/integration/ -v -m e2e
# Or use the helper script
./run_tests.sh e2e
```

## Test Data & Fixtures

### Shared Fixtures (`conftest.py`)

- `temp_dir` - Temporary directory for test outputs
- `sample_faiss_index` - Pre-built FAISS index (100 vectors, 768d)
- `sample_metadata` - Matching metadata
- `sample_index_files` - Multiple index files for merge testing
- `sample_pubmed_xml` - Minimal PubMed XML
- `sample_deleted_pmids` - Deleted PMID list
- `mock_config` - Mock configuration

### Creating Test Data

```python
def test_my_function(temp_dir, sample_faiss_index):
    index, vectors = sample_faiss_index
    # Your test code here
```

## Coverage Reports

```bash
# Generate coverage report
pytest --cov=modules --cov-report=term-missing

# HTML coverage report
pytest --cov=modules --cov-report=html
# Open: htmlcov/index.html

# Focus on specific module
pytest --cov=modules/pubmed --cov-report=term
```

## Continuous Testing

```bash
# Watch for changes and re-run
pytest-watch

# Parallel execution
pip install pytest-xdist
pytest -n auto  # Use all cores

# Run only failed tests
pytest --lf -v
```

## Writing New Tests

### Test Naming Convention

```python
class TestFeatureName:
    """Test suite for feature"""

    def test_feature_does_something(self):
        """Test that feature does X"""
        # Arrange
        data = setup_test_data()

        # Act
        result = function_to_test(data)

        # Assert
        assert result.is_valid()
```

### Adding Markers

```python
@pytest.mark.slow
@pytest.mark.integration
def test_full_workflow():
    """Test complete workflow (slow)"""
    # ...

@pytest.mark.unit
def test_individual_function():
    """Test single function (fast)"""
    # ...
```

## Troubleshooting

### Import Errors
```bash
# Ensure you're in project root
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2

# Install dependencies
pip install pytest pytest-cov pyyaml requests
```

### Model Download Issues
First run downloads models (~90MB):
```bash
python -c "from sentence_transformers import SentenceTransformer; \
           SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

### Integration Test Failures

**Pipeline not completing:**
- Check logs in test output directory
- Increase timeout values
- Run manually: `./bioyoda.sh run pubmed --config config/test_config.yaml --local`

**Qdrant not starting:**
- Ensure no other Qdrant instance running
- Check port 6333 is available
- Review Qdrant logs

**Data not found:**
- Run pipeline tests before Qdrant test
- Check `/tmp/bioyoda_integration_test_*` directories
- Uncomment cleanup to inspect outputs

## Test Execution Order

Recommended order for testing:

1. **Unit tests** (fast, no dependencies)
   ```bash
   ./run_tests.sh unit
   ```

2. **PubMed E2E** (independent, creates test data in test_out/)
   ```bash
   ./run_tests.sh pubmed
   ```

3. **Clinical Trials E2E** (independent, creates test data in test_out/)
   ```bash
   ./run_tests.sh clinical_trials
   ```

Or run all at once:
```bash
./run_tests.sh all  # Unit + E2E tests
pytest tests/ -v    # Same via pytest
```

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: BioYoda Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest tests/unit/ -v
      - run: pytest tests/integration/ -v -m "not slow"
```

## Performance Benchmarks

**Unit Tests:**
- `tests/unit/`: ~1-5 minutes total
- Individual test files: ~10-60 seconds

**E2E Tests:**
- `test_pubmed_e2e.py`: ~10-15 minutes
- `test_clinical_trials_e2e.py`: ~5-10 minutes
- **Total**: ~15-25 minutes

**Coverage:**
- Target: >80% for core modules
- Current: Run `pytest --cov` to check

---

## Testing Philosophy

**These tests are designed to:**
1. 🔴 **Prevent data loss** (critical assertions)
2. 🟡 **Catch errors early** (config validation)
3. 🟢 **Ensure correctness** (output validation)
4. 🔵 **Enable confidence** (integration workflows)

**Run tests before:**
- Committing code changes
- Deploying to production
- Processing large datasets
- Making configuration changes

**Happy testing! 🧪**
