# Running Qdrant E2E Tests

This guide explains how to run the Qdrant end-to-end tests with test configuration.

## Quick Start

### Option 1: Let Tests Manage Server (Recommended)

The E2E tests automatically start and stop the server:

```bash
pytest tests/integration/test_qdrant_e2e.py -m e2e -v
```

The tests will:
1. Automatically create test FAISS data in `test_out/`
2. Start Qdrant server using test config
3. Run all insertion and verification tests
4. Stop server and clean up

### Option 2: Manual Server Management

If you prefer to manage the server yourself:

**Step 1: Start Qdrant server with test config**
```bash
./bioyoda.sh qdrant start --test
```

This will:
- Use `config/test_config.yaml` (points to `test_out/`)
- Start server in local mode
- Create `test_out/data/qdrant/connection_info.txt`

**Step 2: Run E2E tests**
```bash
pytest tests/integration/test_qdrant_e2e.py -m e2e -v
```

**Step 3: Stop server when done**
```bash
./bioyoda.sh qdrant stop --test
```

## Understanding Test Modes

### Test Configuration (`--test` flag)

When you use `--test`:
- Config: `config/test_config.yaml`
- Base dir: `test_out/` (instead of `out/`)
- Data: Minimal test datasets (10 vectors for PubMed, 5 for Clinical Trials)
- Runtime: Fast (5-10 minutes total)

### Production Configuration (default)

Without `--test`:
- Config: `config/config.yaml`
- Base dir: `out/`
- Data: Full production datasets (30M+ vectors)
- Runtime: Hours

## Test Data Location

With `--test` flag, everything goes to `test_out/`:

```
test_out/
├── data/
│   ├── processed/
│   │   ├── pubmed/baseline/
│   │   │   ├── test_pubmed.index      # Created by tests
│   │   │   └── test_pubmed.json
│   │   └── clinical_trials/
│   │       ├── test_trials.index      # Created by tests
│   │       └── test_trials.json
│   └── qdrant/
│       ├── connection_info.txt         # Server URL
│       ├── storage/                    # Qdrant database
│       └── collections/
│           ├── pubmed_abstracts.done   # Insertion markers
│           └── clinical_trials.done
└── logs/
    └── qdrant/
        ├── server.log
        ├── insert_pubmed.log
        └── insert_clinical_trials.log
```

## Common Commands

### Check if server is running
```bash
./bioyoda.sh qdrant status --test
```

### Start server in cluster mode
```bash
./bioyoda.sh qdrant start --test --mode cluster --queue scc
```

### Insert only PubMed data
```bash
./bioyoda.sh qdrant insert pubmed --test --local
```

### Insert all data
```bash
./bioyoda.sh qdrant insert all --test --local
```

### Clean test output
```bash
rm -rf test_out/
```

## Troubleshooting

### Tests are skipped

**Problem:** Tests show "SKIPPED (Could not start Qdrant server)"

**Solutions:**
1. Check Singularity container exists:
   ```bash
   ls -lh modules/qdrant/setup/singularity/qdrant.sif
   ```

2. Check for port conflicts:
   ```bash
   lsof -i :6333
   ```

3. Check server logs:
   ```bash
   cat test_out/logs/qdrant/server.log
   ```

### Server won't start

**Problem:** `./bioyoda.sh qdrant start --test` fails

**Solutions:**
1. Ensure Singularity is installed:
   ```bash
   which singularity
   ```

2. Check permissions on container:
   ```bash
   ls -l modules/qdrant/setup/singularity/qdrant.sif
   ```

3. Try starting manually:
   ```bash
   singularity instance list
   singularity run modules/qdrant/setup/singularity/qdrant.sif
   ```

### Insertion fails

**Problem:** Tests fail during data insertion

**Solutions:**
1. Verify server is running:
   ```bash
   ./bioyoda.sh qdrant status --test
   ```

2. Check connection info:
   ```bash
   cat test_out/data/qdrant/connection_info.txt
   ```

3. Verify test data exists:
   ```bash
   ls -lh test_out/data/processed/pubmed/baseline/
   ls -lh test_out/data/processed/clinical_trials/
   ```

4. Check insertion logs:
   ```bash
   tail -f test_out/logs/qdrant/insert_pubmed.log
   ```

### Tests hang

**Problem:** Tests seem stuck

**Solutions:**
1. Kill hanging processes:
   ```bash
   pkill -f qdrant
   singularity instance stop qdrant_server
   ```

2. Clean everything:
   ```bash
   rm -rf test_out/
   singularity instance list  # Check for orphaned instances
   ```

3. Re-run with more verbose output:
   ```bash
   pytest tests/integration/test_qdrant_e2e.py -m e2e -v -s --tb=long
   ```

## CI/CD Integration

### Skip E2E tests in CI (fast)
```bash
pytest tests/unit/qdrant/ -v
```

### Run full suite in CI with Singularity
```bash
pytest tests/unit/qdrant/ tests/integration/test_qdrant_e2e.py -m e2e -v
```

## Performance Expectations

| Test Type | Time | Requirements |
|-----------|------|--------------|
| Unit tests | < 1 min | None |
| E2E tests (auto server) | 5-10 min | Singularity |
| E2E tests (manual server) | 3-5 min | Running server |

## Summary

✅ **Recommended workflow:**
```bash
# Let tests handle everything
pytest tests/integration/test_qdrant_e2e.py -m e2e -v
```

✅ **Manual control:**
```bash
# 1. Start server
./bioyoda.sh qdrant start --test

# 2. Run tests
pytest tests/integration/test_qdrant_e2e.py -m e2e -v

# 3. Stop server
./bioyoda.sh qdrant stop --test
```

✅ **All outputs go to `test_out/` directory**

✅ **Clean separation from production data in `out/`**
