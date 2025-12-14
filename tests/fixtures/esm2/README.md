# Protein Similarity ESM-2 Test Fixtures

This directory contains test fixtures for the esm2 module.

## Files

### test_proteins.fasta
- **Description**: Small subset of UniProt SwissProt sequences for testing
- **Source**: First 1000 sequences from SwissProt
- **Generation**: Run `./bioyoda.sh run esm2 --test` to regenerate
- **Usage**: Test mode automatically uses this dataset
- **Size**: ~1000 protein sequences

## Regenerating Fixtures

To regenerate test fixtures from scratch:

```bash
# 1. Clean previous test outputs
./bioyoda.sh stop esm2 --test --clean

# 2. Run ESM-2 in test mode (processes first 1000 SwissProt proteins)
./bioyoda.sh run esm2 --test

# 3. Copy generated test data to fixtures
cp test_out/raw_data/esm2/uniprot_test.fasta tests/fixtures/esm2/test_proteins.fasta
cp test_out/raw_data/esm2/uniprot_test.fasta.metadata.txt tests/fixtures/esm2/test_proteins.fasta.metadata.txt
```

## Test Mode Behavior

When `test_mode: true` in `config/test_config.yaml`:
- Downloads SwissProt FASTA
- Limits to first 1000 sequences
- Splits into 10 chunks (100 proteins each)
- Generates embeddings for all chunks
- Fast test run (~10-15 minutes total)

## Validation

After test run completes, you should have:
- `test_out/raw_data/esm2/uniprot_test.fasta` - Input sequences
- `test_out/raw_data/esm2/chunks/chunk_*.fasta` - 10 chunk files
- `test_out/data/processed/esm2/embeddings/chunk_*.h5` - 10 embedding files
- `test_out/data/processed/esm2/merged/all_embeddings.h5` - Merged file

Total embeddings: ~1000 proteins × 1280 dimensions (ESM-2 650M model)
