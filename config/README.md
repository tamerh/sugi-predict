# BioYoda Configuration Files

## Configurations

| File | Purpose |
|------|---------|
| `config.yaml` | Production settings |
| `test_config.yaml` | Fast testing (small dataset) |
| `tamer.yml` | Conda environment |

## Usage

```bash
# Production
./bioyoda.sh run pubmed --local --cores 8

# Testing
./bioyoda.sh run pubmed --test --local
```

## GPU Processing

GPU processing is done via Google Colab. See module READMEs:
- `modules/pubmed/README.md`
- `modules/patents/README.md`
- `modules/clinical_trials/README.md`
- `modules/esm2/README.md`
