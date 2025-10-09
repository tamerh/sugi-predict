# Qdrant Module Tests

Tests for the Qdrant vector database module.

## Test Structure

```
tests/
├── unit/qdrant/              # Unit tests (no server required)
│   ├── test_insert.py        # Test insertion functions
│   └── test_server_scripts.py # Test server management
└── integration/              # Integration tests (requires server)
    └── test_qdrant_e2e.py    # End-to-end workflow tests
```

## Unit Tests

Unit tests can run without a Qdrant server. They test individual functions and components in isolation.

### Run All Unit Tests

```bash
pytest tests/unit/qdrant/ -v
```

### Run Specific Test Files

```bash
# Test insertion functions
pytest tests/unit/qdrant/test_insert.py -v

# Test server scripts
pytest tests/unit/qdrant/test_server_scripts.py -v
```

### Test Coverage

```bash
pytest tests/unit/qdrant/ --cov=modules/qdrant --cov-report=html
```

## Integration Tests (E2E)

Integration tests require:
- Qdrant Singularity container
- Test FAISS data (created automatically)
- Network access for Qdrant server

### Prerequisites

1. **Singularity Container**: Ensure Qdrant container is available:
   ```bash
   ls modules/qdrant/setup/singularity/qdrant.sif
   ```

2. **Test Configuration**: Use `test_config.yaml`:
   ```bash
   cat config/test_config.yaml
   ```

### Run E2E Tests

```bash
# Run all Qdrant E2E tests
pytest tests/integration/test_qdrant_e2e.py -m e2e -v

# Run with detailed output
pytest tests/integration/test_qdrant_e2e.py -m e2e -v -s

# Run specific test class
pytest tests/integration/test_qdrant_e2e.py::TestQdrantEndToEnd -m e2e -v

# Run single test
pytest tests/integration/test_qdrant_e2e.py::TestQdrantEndToEnd::test_server_is_running -m e2e -v
```

### E2E Test Workflow

The E2E tests execute this workflow:

1. **Setup**: Create minimal test FAISS indices (10 PubMed, 5 Clinical Trials)
2. **Start**: Launch Qdrant server in local mode
3. **Insert**: Insert PubMed and Clinical Trials data
4. **Verify**: Check collections, point counts, and metadata
5. **Teardown**: Stop server and clean up

### Expected Runtime

- Unit tests: < 1 minute
- E2E tests: 5-10 minutes (includes server startup/shutdown)

## Test Data

E2E tests create minimal test data automatically:

```
test_out/
└── data/
    ├── processed/
    │   ├── pubmed/baseline/
    │   │   ├── test_pubmed.index    # 10 vectors
    │   │   └── test_pubmed.json
    │   └── clinical_trials/
    │       ├── test_trials.index     # 5 vectors
    │       └── test_trials.json
    └── qdrant/
        ├── connection_info.txt        # Server URL
        ├── storage/                   # Qdrant data
        └── collections/
            ├── pubmed_abstracts.done
            └── clinical_trials.done
```

## Troubleshooting

### Server Won't Start

```bash
# Check Singularity container
ls -lh modules/qdrant/setup/singularity/qdrant.sif

# Check for port conflicts
lsof -i :6333

# Check logs
cat test_out/logs/qdrant/server_start.log
```

### Insertion Fails

```bash
# Verify server is running
./bioyoda.sh qdrant status --config config/test_config.yaml

# Check connection info
cat test_out/data/qdrant/connection_info.txt

# Check test data exists
ls -lh test_out/data/processed/pubmed/baseline/
ls -lh test_out/data/processed/clinical_trials/
```

### Tests Hang

```bash
# Kill any hanging Qdrant processes
pkill -f qdrant

# Clean test output
rm -rf test_out/

# Re-run tests
pytest tests/integration/test_qdrant_e2e.py -m e2e -v --tb=short
```

## CI/CD Integration

### Skip E2E Tests in CI

E2E tests are skipped by default in CI environments without Singularity:

```bash
# Run only unit tests (fast, no dependencies)
pytest tests/unit/qdrant/ -v

# Skip E2E tests explicitly
pytest tests/ -m "not e2e" -v
```

### Run in CI with Singularity

```bash
# Full test suite including E2E
pytest tests/unit/qdrant/ tests/integration/test_qdrant_e2e.py -m e2e -v
```

## Test Markers

```python
@pytest.mark.e2e           # End-to-end integration tests
@pytest.mark.slow          # Tests taking > 1 minute
@pytest.mark.requires_server  # Tests requiring Qdrant server
```

## Contributing

When adding new Qdrant features:

1. **Add unit tests** in `tests/unit/qdrant/` for new functions
2. **Add E2E tests** in `tests/integration/test_qdrant_e2e.py` for workflows
3. **Update this README** with new test cases
4. **Run full test suite** before submitting PR

```bash
# Run all tests
pytest tests/unit/qdrant/ tests/integration/test_qdrant_e2e.py -v

# Check coverage
pytest tests/unit/qdrant/ --cov=modules/qdrant --cov-report=term-missing
```
