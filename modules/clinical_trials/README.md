# Clinical Trials Module

Snakemake workflow for processing ClinicalTrials.gov AACT database for semantic search.

## Overview

This module builds a semantic search index from clinical trials using:
- **Source**: AACT database (Clinical Trials Transformation Initiative)
- **Model**: S-BioBERT (`pritamdeka/S-BioBERT-snli-multinli-stsb`) - 768 dimensions
- **Vector DB**: FAISS (FlatL2 index)
- **Scale**: 554K+ trials, 49 tables, 14GB raw data

## Quick Start

### Production Run
```bash
# Full dataset processing (554K trials, takes days)
./bioyoda.sh run clinical_trials --cluster --bg --jobs 10
```

### Test Run
```bash
# Fast test with 100 trials (~10 minutes)
./bioyoda.sh run clinical_trials --config config/test_config.yaml --local
```

## Pipeline Steps

1. **Download** (`download_aact.py`)
   - Downloads latest AACT snapshot from CTTI
   - Extracts 49 pipe-delimited tables
   - Output: ~14GB of flat files

2. **Extract** (`extract_text.py`)
   - Reads and joins AACT tables by NCT ID
   - Extracts 6 core text fields per trial
   - Filters withdrawn/incomplete studies
   - Output: Single JSON file with all trials

3. **Process** (`process_trials.py`)
   - Parses trial JSON
   - Creates multiple chunks per trial (summary, description, outcomes, eligibility, interventions)
   - Generates embeddings using S-BioBERT
   - Output: `.index` (FAISS) + `.json` (metadata)

**Note**: No merge step needed! All trials processed into single index.

## Directory Structure

```
modules/clinical_trials/
├── Snakefile              # Workflow definition (3 rules + validate)
├── scripts/
│   ├── download_aact.py   # Download AACT database
│   ├── extract_text.py    # Extract text from tables
│   ├── process_trials.py  # Create embeddings
│   ├── merge_trials.py    # (Unused - kept for future batching)
│   └── clinical_trials.env # Script-level settings
└── README.md              # This file
```

## Configuration

### Production (`config/config.yaml`)
- Downloads full AACT database
- Processes all 554K trials
- Memory: 16GB/download, 16GB/extract, 20GB/process
- Runtime: Days

### Test (`config/test_config.yaml`)
- Downloads full database (one-time)
- Processes only 100 trials
- Memory: 8GB each step
- Runtime: ~10 minutes

## Output

```
data/
├── raw/clinical_trials/
│   ├── aact_snapshot.zip              # Downloaded snapshot
│   └── extracted/
│       ├── studies.txt                # 49 pipe-delimited tables
│       ├── brief_summaries.txt
│       ├── detailed_descriptions.txt
│       └── ... (46 more tables)
├── processed/clinical_trials/
│   ├── trials_data.json               # All trials in JSON
│   └── trials_data.csv                # Summary CSV
└── final/clinical_trials/
    ├── clinical_trials.index          # FAISS index
    └── clinical_trials_metadata.json  # Metadata
```

## Text Fields Extracted

Per trial, the following fields are extracted and chunked:

1. **Brief Summary** - Lay-friendly study overview (weight: 1.0)
2. **Detailed Description** - Technical study details (weight: 0.8)
3. **Primary Outcomes** - Main study endpoints (weight: 0.9)
4. **Secondary Outcomes** - Additional endpoints (weight: 0.9)
5. **Eligibility Criteria** - Inclusion/exclusion criteria (weight: 0.7)
6. **Interventions** - Treatment/procedure descriptions (weight: 0.8)

Expected: **8-12 chunks per trial** = ~5-6M total chunks

## Key Features

### Multi-Field Chunking
Each trial creates multiple embeddings for different content types, enabling:
- Granular search (find by outcome, eligibility, intervention)
- Weighted ranking (summaries ranked higher than descriptions)
- Comprehensive coverage (all trial aspects indexed)

### Data Quality Filters
- Excludes withdrawn studies
- Requires minimum summary length (100 chars)
- Validates text fields present
- Handles missing optional fields gracefully

### Test Mode Support
- `test_mode: true` - Fast pipeline testing
- `test_trials_limit: 100` - Limit trials processed
- Separate test config for safe experimentation

## AACT Database Tables

### Tier 1: Core Text (Used in MVP)
- `studies` - Core metadata (NCT ID, title, status, phase)
- `brief_summaries` - Study summaries
- `detailed_descriptions` - Technical descriptions
- `design_outcomes` - Outcome measures
- `eligibilities` - Patient criteria
- `interventions` - Treatments

### Tier 2: Structured Metadata (Future Phase 2)
- `conditions` - Disease conditions
- `keywords` - Study keywords
- `sponsors` - Funding organizations
- `facilities` - Trial locations
- `study_references` - PubMed cross-links ⭐

### Tier 3: Results Data (Future Phase 3)
- `outcome_measurements` - Study results
- `reported_events` - Adverse events (50M+ events!)
- `baseline_measurements` - Demographics
- Other analytics tables

## Monitoring

```bash
# Watch main pipeline log
tail -f logs/bioyoda_clinical_trials_main.log

# Check individual step logs
ls -lh logs/clinical_trials/

# Monitor cluster jobs
qstat | grep clinical
```

## Stopping Pipeline

```bash
# Stop running pipeline
./bioyoda.sh stop clinical_trials

# Stop and clean intermediate files
./bioyoda.sh stop clinical_trials --clean
```

## Performance

**Test Mode** (100 trials):
- Download: ~30 min (one-time, downloads full database)
- Extract: ~2 min
- Process: ~5 min
- **Total: ~10 minutes** (after first download)

**Production** (554K trials):
- Download: ~1 hour (one-time)
- Extract: ~2-3 hours
- Process: ~12-18 hours
- **Total: ~20 hours**

## Troubleshooting

**Issue**: Download fails
- **Check**: Network connection, AACT site status
- **Log**: `logs/clinical_trials/download.log`
- **Solution**: AACT updates daily, try again later

**Issue**: Out of memory during processing
- **Check**: Current memory setting in config
- **Solution**: Increase `process_memory_mb` to 32GB
- **Note**: 554K trials with chunking needs ~20GB minimum

**Issue**: Extraction fails on table join
- **Check**: `logs/clinical_trials/extract.log`
- **Common**: Missing NCT IDs in some tables
- **Solution**: Script handles gracefully, check log for details

## Scripts Reference

### `download_aact.py`
```bash
python download_aact.py \
    --download-dir data/raw/clinical_trials \
    --extract-dir data/raw/clinical_trials/extracted
```

### `extract_text.py`
```bash
python extract_text.py \
    --extract-dir data/raw/clinical_trials/extracted \
    --output-json trials_data.json \
    --limit 100  # Test mode
```

### `process_trials.py`
```bash
python process_trials.py \
    --input-json trials_data.json \
    --output-index clinical_trials.index \
    --output-metadata metadata.json \
    --limit 100  # Test mode
```

## Phased Implementation

This module implements **Phase 1 (MVP)** - Core semantic search.

**Future Phases** (see `vibe/clinical.md` for details):
- **Phase 2**: Enhanced filters + PubMed cross-references
- **Phase 3**: Adverse events database (50M+ events)
- **Phase 4**: AI-powered patient-trial matching

## Model Details

**S-BioBERT** - Same as PubMed for consistency:
- Pre-trained on biomedical literature
- Fine-tuned for semantic similarity
- 768-dimensional embeddings
- Optimized for clinical/biomedical text

This ensures **unified search** across PubMed literature + clinical trials using the same vector space!

## Cross-Reference with PubMed

Future enhancement (Phase 2):
```python
# Link trials to related publications
trial_nct = "NCT12345678"
related_pmids = get_trial_publications(trial_nct)  # From study_references table

# Unified search
results = search(
    query="CRISPR therapy",
    sources=["pubmed", "clinical_trials"]
)
```

## Data Freshness & Updates

AACT database updates **daily** with new trials from ClinicalTrials.gov.

### Current Approach (Full Rebuild)

```bash
# Re-run entire pipeline to get latest snapshot
./bioyoda.sh run clinical_trials --cluster --bg
```

**Limitations:**
- Downloads entire database (~14GB) daily
- Reprocesses all 554K trials (~20 hours)
- High compute cost for incremental changes
- Rebuilds entire FAISS index from scratch

### Future Enhancement: Incremental Updates (Phase 2)

**Goal:** Process only new/changed trials for faster daily updates

**Proposed Strategy:**

```python
# Incremental update workflow
def incremental_update():
    """
    Smart update system using SQLite change tracking

    1. Download latest AACT snapshot (~30 min)
    2. Load SQLite tracking database
    3. Compare trial NCT IDs + last_update_date
    4. Identify: new trials, modified trials, deleted trials
    5. Process only changes (~1-2 hours vs 20 hours)
    6. Merge changes into existing FAISS index
    7. Update SQLite tracking database
    """
```

**SQLite Change Tracking Schema:**

```sql
CREATE TABLE trial_tracking (
    nct_id TEXT PRIMARY KEY,
    last_update_date TEXT,      -- From AACT studies.last_update_posted_date
    data_hash TEXT,              -- Hash of trial content for change detection
    index_position INTEGER,      -- Position in FAISS index
    chunk_count INTEGER,         -- Number of embeddings for this trial
    processed_date TEXT,         -- When we last processed this trial
    status TEXT                  -- 'active', 'deleted', 'modified'
);

CREATE INDEX idx_last_update ON trial_tracking(last_update_date);
CREATE INDEX idx_status ON trial_tracking(status);
```

**Implementation Components:**

1. **Change Detection:**
```python
def detect_changes(aact_snapshot_path, tracking_db_path):
    """
    Compare AACT snapshot with tracking DB
    Returns: (new_trials, modified_trials, deleted_trials)
    """
    # Load current AACT trial list with update dates
    current_trials = load_aact_studies(aact_snapshot_path)

    # Load tracking database
    tracked_trials = load_tracking_db(tracking_db_path)

    # Identify changes
    new_trials = [t for t in current_trials if t['nct_id'] not in tracked_trials]

    modified_trials = [
        t for t in current_trials
        if t['nct_id'] in tracked_trials
        and t['last_update_date'] > tracked_trials[t['nct_id']]['last_update_date']
    ]

    deleted_trials = [
        nct_id for nct_id in tracked_trials
        if nct_id not in {t['nct_id'] for t in current_trials}
    ]

    return new_trials, modified_trials, deleted_trials
```

2. **Incremental Index Update:**
```python
def update_faiss_index(index_path, metadata_path, changes):
    """
    Update FAISS index with changes without full rebuild
    """
    # Load existing index
    index = faiss.read_index(index_path)
    metadata = load_metadata(metadata_path)

    # Remove deleted/modified trials
    for nct_id in changes['deleted'] + changes['modified']:
        # Mark vectors as deleted using IDMap
        positions = find_trial_positions(metadata, nct_id)
        index.remove_ids(positions)
        metadata = remove_metadata(metadata, nct_id)

    # Add new/modified trials
    for trial in changes['new'] + changes['modified']:
        # Process trial to get embeddings
        vectors, trial_metadata = process_trial(trial)

        # Add to index
        index.add(vectors)
        metadata.extend(trial_metadata)

    # Save updated index
    faiss.write_index(index, index_path)
    save_metadata(metadata, metadata_path)
```

3. **Daily Update Workflow:**
```bash
#!/bin/bash
# daily_update.sh - Smart incremental update

# Download latest snapshot
python download_aact.py --extract-dir data/raw/clinical_trials/extracted

# Detect changes
python detect_changes.py \
    --snapshot-dir data/raw/clinical_trials/extracted \
    --tracking-db data/final/clinical_trials/tracking.db \
    --output-changes data/temp/changes.json

# Process only changes
python process_changes.py \
    --changes data/temp/changes.json \
    --index data/final/clinical_trials/clinical_trials.index \
    --metadata data/final/clinical_trials/clinical_trials_metadata.json

# Update tracking database
python update_tracking.py \
    --changes data/temp/changes.json \
    --tracking-db data/final/clinical_trials/tracking.db
```

**Benefits:**

| Metric | Full Rebuild | Incremental Update |
|--------|--------------|-------------------|
| **Time** | ~20 hours | ~1-2 hours |
| **Data Transfer** | 14GB | 14GB (one-time) |
| **Processing** | 554K trials | ~500-2000 trials/day |
| **Compute Cost** | High | Low (90% reduction) |
| **Downtime** | Yes (during rebuild) | No (live updates) |

**Typical Daily Changes:**
- New trials: ~200-500/day
- Modified trials: ~500-1000/day
- Deleted/withdrawn: ~50-100/day
- **Total:** ~750-1600 changes/day (0.3% of corpus)

**Implementation Priority:** Phase 2 (after MVP stabilizes)

**References:** See `vibe/clinical_trials_integration_plan.md` (line 496-518) for detailed specifications

## History

- **Sep 2024**: Initial implementation, AACT download
- **Sep 2024**: Text extraction pipeline
- **Sep 2024**: Embedding generation with S-BioBERT
- **Oct 2024**: Snakemake integration (3-rule pipeline)

## Next Steps

See `vibe/clinical.md` and `vibe/clinical_trials_integration_plan.md` for:
- Phase 2 planning (filters + cross-references)
- Phase 3 planning (results database)
- Batch processing strategy (if needed for parallelization)
