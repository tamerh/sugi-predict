# Clinical Trials Processing Pipeline for BioYoda

A comprehensive pipeline for processing clinical trials data from AACT database to create semantic embeddings for the BioYoda search system.

## Overview

This pipeline downloads clinical trials data from the AACT (Aggregate Analysis of ClinicalTrials.gov) database, processes the text content using S-BioBERT embeddings, and creates FAISS indices for semantic search - following the same architecture as the PubMed pipeline.

## Key Features

- **AACT Database Integration**: Downloads daily PostgreSQL snapshots
- **Rich Text Processing**: Extracts summaries, descriptions, outcomes, eligibility criteria
- **Chunking Strategy**: Splits trials into multiple searchable text segments
- **S-BioBERT Embeddings**: 768-dimensional vectors for biomedical semantic search
- **HPC Cluster Ready**: SGE job integration with memory optimization
- **Resume Support**: Can restart from interruptions
- **Comprehensive Validation**: Data quality checks throughout pipeline

## Architecture

### Data Flow
```
AACT Database → Text Extraction → Text Processing → FAISS Index
     ↓              ↓                  ↓              ↓
PostgreSQL → JSON/CSV files → Embeddings → Searchable Index
```

### Directory Structure
```
scripts/clinical_trials/
├── clinical_trials.sh          # Main pipeline script
├── clinical_trials.env         # Configuration
├── download_aact.py            # AACT database download
├── extract_text.py             # SQL-based text extraction
├── process_trials.py           # Embedding generation
├── merge_trials.py             # Index merging
├── jobs/                       # HPC job scripts
│   ├── download_aact.sh        # Download job
│   └── process_trials.sh       # Processing job
└── README.md                   # This file
```

## Quick Start

### 1. Test AACT Access (5 minutes)
```bash
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/clinical_trials

# Check status
./clinical_trials.sh status

# Test download (debug mode)
./clinical_trials.sh download
```

### 2. Debug Run (30 minutes)
```bash
# Process only 100 trials for testing
./clinical_trials.sh all --debug
```

### 3. Full Production Run
```bash
# Submit complete pipeline job
qsub jobs/process_trials.sh

# Or run interactively
./clinical_trials.sh all
```

## Commands Reference

### Main Pipeline Commands
```bash
./clinical_trials.sh download [--recreate]    # Download AACT database
./clinical_trials.sh extract [--debug]        # Extract text from database
./clinical_trials.sh process [--debug]        # Create embeddings
./clinical_trials.sh merge                    # Merge into master index
./clinical_trials.sh all [--debug]           # Run complete pipeline
./clinical_trials.sh status                   # Show pipeline status
./clinical_trials.sh validate                 # Validate data integrity
```

### Individual Script Usage
```bash
# Download AACT snapshot
python download_aact.py --database-name aact_clinical_trials --recreate

# Extract text with custom parameters
python extract_text.py \
  --database-url "postgresql://user@localhost:5432/aact" \
  --output-json trials_data.json \
  --limit 1000

# Process trials to embeddings
python process_trials.py \
  --input-json trials_data.json \
  --output-index trials.index \
  --output-metadata trials_metadata.json

# Merge indices
python merge_trials.py \
  --processed-dir /path/to/processed \
  --output-index master_trials.index \
  --output-metadata master_metadata.json
```

## Configuration

### Key Settings (clinical_trials.env)
```bash
# Model settings (same as PubMed for consistency)
MODEL_NAME="pritamdeka/S-BioBERT-snli-multinli-stsb"
VECTOR_DIMENSION=768

# Processing parameters
BATCH_SIZE=1000
MAX_CHUNK_LENGTH=500
MIN_TEXT_LENGTH=50

# Text inclusion flags
INCLUDE_DETAILED_DESCRIPTION=true
INCLUDE_OUTCOMES=true
INCLUDE_ELIGIBILITY=true
INCLUDE_INTERVENTIONS=true

# Quality filters
MIN_BRIEF_SUMMARY_LENGTH=100
EXCLUDE_WITHDRAWN_STUDIES=true
```

### Resource Requirements
```bash
# Download job
DOWNLOAD_MEMORY="16G"
DOWNLOAD_RUNTIME="4:00:00"

# Processing job
PROCESS_MEMORY="64G"
PROCESS_RUNTIME="24:00:00"

# Merge job
MERGE_MEMORY="256G"
MERGE_RUNTIME="168:00:00"
```

## Data Processing Details

### Text Chunking Strategy

Each clinical trial is split into multiple searchable chunks:

1. **Summary Chunk**: `"Title: [title]. Summary: [brief_summary]"`
2. **Description Chunks**: Long detailed descriptions split at sentence boundaries
3. **Outcome Chunks**: `"Primary Outcomes: [measures and descriptions]"`
4. **Eligibility Chunks**: `"Eligibility: [criteria] Demographics: [age, gender]"`

### AACT Database Schema

Key tables used for text extraction:
- `studies`: Main trial information, brief_summary, detailed_description
- `design_outcomes`: Primary/secondary outcome measures
- `eligibilities`: Inclusion/exclusion criteria, demographics
- `conditions`: Disease conditions studied
- `interventions`: Treatments and procedures

### Expected Output

```
data/final/clinical_trials/
├── master_clinical_trials.index           # FAISS index (~50-100GB)
├── master_clinical_trials_metadata.json   # Metadata (~2-5GB)
└── master_clinical_trials_metadata_report.json  # Processing report
```

## Performance Estimates

### Data Volume (400K+ trials)
- **Raw AACT database**: ~10-15GB
- **Extracted text**: ~2-3GB JSON
- **Final FAISS index**: ~50-100GB
- **Processing time**: ~12-16 hours total

### Chunk Generation
- **Average chunks per trial**: 3-8 chunks
- **Total embeddings**: ~1-3M vectors
- **Typical chunk types**:
  - Summary: 100% of trials
  - Description: ~60% of trials
  - Outcomes: ~90% of trials
  - Eligibility: ~95% of trials

## Integration with BioYoda

### Unified Search
```python
# Search across PubMed + Clinical Trials
def search_bioyoda(query, corpora=['pubmed', 'clinical_trials']):
    results = []

    if 'clinical_trials' in corpora:
        ct_results = search_faiss_index(
            query,
            'data/final/clinical_trials/master_clinical_trials.index',
            'data/final/clinical_trials/master_clinical_trials_metadata.json'
        )
        results.extend([(r, 'clinical_trials') for r in ct_results])

    return rerank_combined_results(results, query)
```

### Metadata Structure
```json
{
  "nct_id": "NCT12345678",
  "chunk_type": "summary",
  "chunk_id": 0,
  "text": "Title: Study of ABC drug. Summary: This trial...",
  "brief_title": "Study of ABC drug for cancer",
  "overall_status": "Recruiting",
  "phase": "Phase 2",
  "study_type": "Interventional",
  "conditions": ["Cancer", "Breast Neoplasms"],
  "interventions": ["Drug: ABC123"]
}
```

## Troubleshooting

### Common Issues

1. **PostgreSQL Connection Failed**
   ```bash
   # Check if PostgreSQL is running
   sudo systemctl status postgresql

   # Check connection
   psql -h localhost -U $USER postgres
   ```

2. **AACT Download Timeout**
   ```bash
   # Resume download
   ./clinical_trials.sh download
   ```

3. **Memory Issues During Processing**
   ```bash
   # Reduce batch size in clinical_trials.env
   BATCH_SIZE=500

   # Or request more memory
   qsub -l h_vmem=128G jobs/process_trials.sh
   ```

4. **Dimension Mismatch**
   ```bash
   # Validate model configuration
   python -c "
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer('pritamdeka/S-BioBERT-snli-multinli-stsb')
   print('Dimension:', len(model.encode('test')))
   "
   ```

### Validation Commands
```bash
# Check database connection
python extract_text.py --database-url $AACT_DATABASE_URL --stats-only

# Validate FAISS index
python -c "
import faiss
index = faiss.read_index('path/to/index.index')
print(f'Vectors: {index.ntotal}, Dimensions: {index.d}')
"

# Run full validation
./clinical_trials.sh validate
```

## Maintenance

### Regular Updates
```bash
# Weekly AACT database update
qsub jobs/download_aact.sh

# Check for new data and reprocess if needed
./clinical_trials.sh status
```

### Monitoring
- Check job logs in `/data/.../logs/clinical_trials/`
- Monitor disk usage for large index files
- Validate data integrity after updates

## Development Notes

### Adding New Text Fields
1. Modify `extract_text.py` SQL queries
2. Update `process_trials.py` chunking logic
3. Test with debug mode: `--debug`

### Performance Tuning
- Adjust `BATCH_SIZE` for memory/speed trade-off
- Modify `MAX_CHUNK_LENGTH` for embedding quality
- Use `MIN_TEXT_LENGTH` to filter low-quality text

### Integration Testing
```bash
# Test with small dataset
./clinical_trials.sh all --debug

# Validate against PubMed pipeline
./clinical_trials.sh validate
```

This pipeline provides a robust, scalable foundation for clinical trials semantic search within the BioYoda ecosystem.