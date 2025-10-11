# BioYoda Test Workflow Guide

## Overview
The e2e tests now preserve processed data across test runs, allowing you to reuse expensive pipeline results without re-processing.

## Workflow

### First Run (Full Pipeline)
```bash
# Clean everything and run full tests
rm -rf test_out/
./run_tests.sh
```

This will:
1. Run PubMed e2e → Creates fixture data and processed FAISS indices
2. Run Clinical Trials e2e → Creates fixture data and processed FAISS indices
3. Run Qdrant tests → Uses the processed data from steps 1 & 2
4. All processed data is preserved in `test_out/`

### Subsequent Runs (Reuse Data)
```bash
# Run all tests again - will REUSE existing processed data
./run_tests.sh
```

This will:
1. PubMed e2e → **SKIPS pipeline**, reuses existing processed data
2. Clinical Trials e2e → **SKIPS pipeline**, reuses existing processed data
3. Qdrant tests → Uses the same processed data
4. Tests complete in ~1-2 minutes instead of ~15-20 minutes

## What Gets Preserved

After first run, `test_out/` contains:
```
test_out/
├── raw_data/              # Raw data (fixtures or downloads)
│   ├── pubmed/baseline/test_abstracts.xml.gz
│   └── clinical_trials/chunked/trials_chunk_0001.json
├── data/processed/        # Processed FAISS indices (REUSED!)
│   ├── pubmed/baseline/pubmed_baseline_*.index
│   └── clinical_trials/trials_chunk_*.index
└── logs/                  # Pipeline logs
```

## Force Re-processing

To force re-running the pipelines:
```bash
# Option 1: Clean only processed data
rm -rf test_out/data test_out/logs

# Option 2: Clean everything (including raw data)
rm -rf test_out/

# Then run tests
./run_tests.sh
```

## Test Output Messages

### When Reusing Data:
```
================================================================================
REUSING existing processed data from previous test run
Found processed indices in: test_out/data/processed/pubmed/baseline
To force re-processing, delete: test_out
================================================================================
Skipping pipeline execution - reusing existing data
```

### When Running Fresh:
```
================================================================================
Cleaning test output: test_out/data and test_out/logs
Preserving: test_out/raw_data (fixture or downloads)
================================================================================
Running E2E Pipeline: ./bioyoda.sh run pubmed ...
```

## Benefits

1. **Fast iteration**: Subsequent test runs complete in ~1-2 minutes
2. **Consistent data**: Qdrant tests always use same processed data
3. **Easy debugging**: Processed data remains available for inspection
4. **Flexible**: Can force re-processing anytime by deleting `test_out/data`

## Data Flow

```
First Run:
  Fixtures → [PubMed Pipeline] → processed/pubmed/*.index
  Fixtures → [CT Pipeline] → processed/clinical_trials/*.index
  Both → [Qdrant Tests] → Validates insertion

Subsequent Runs:
  Skip Pipelines → Use existing *.index files
  → [Qdrant Tests] → Validates insertion
```
