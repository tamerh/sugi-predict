# Incremental Updates Implementation Plan

**Version**: 1.0
**Date**: 2025-01-15
**Status**: Planning → Implementation

## Overview

This document outlines the implementation plan for incremental dataset updates in BioYoda. The goal is to efficiently update existing data in Qdrant without reprocessing everything from scratch.

**Design Philosophy**: Keep it simple - minimum viable solution for a solo developer.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   INITIAL FULL LOAD (Once)                   │
├─────────────────────────────────────────────────────────────┤
│  Download All Data → Process → Create FAISS → Insert Qdrant │
│  Track: What was processed (state tracking)                 │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                  INCREMENTAL UPDATE (Regular)                │
├─────────────────────────────────────────────────────────────┤
│  1. Download NEW data only                                   │
│  2. Compare with tracking state                              │
│  3. Process NEW/UPDATED items only                           │
│  4. Upsert to Qdrant (delete old + insert new)               │
│  5. Update tracking state                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Dataset-Specific Strategies

### 1. PubMed (Simpler - File-Based Tracking)

**Current State**:
- Downloads from `baseline/` (static) + `updatefiles/` (daily new publications)
- Processes each XML file independently
- Creates FAISS indices per file

**Update Strategy**:

```yaml
# State tracking (JSON file)
out/state/pubmed/processed_files.json:
  {
    "baseline/pubmed25n0001.xml.gz": {
      "processed_date": "2025-01-10T10:30:00",
      "vectors_count": 50000
    },
    "updatefiles/pubmed25n1234.xml.gz": {
      "processed_date": "2025-01-15T08:15:00",
      "vectors_count": 1500
    }
  }
```

**Implementation**:
1. Track which files have been processed
2. Download only NEW updatefiles not in tracking
3. Process new files only
4. Insert new FAISS indices to Qdrant
5. Update tracking JSON

**Commands**:
```bash
# Full load (first time)
./bioyoda.sh run pubmed --mode full

# Daily updates
./bioyoda.sh run pubmed --mode update
./bioyoda.sh qdrant insert pubmed --mode update
```

---

### 2. Clinical Trials (Complex - Record-Based Tracking)

**Current State**:
- Downloads full AACT snapshot (~554K trials, 14GB)
- Processes all trials every time
- No way to know which trials changed

**Update Strategy**:

```sql
-- Minimal tracking database (SQLite)
CREATE TABLE trials (
    nct_id TEXT PRIMARY KEY,
    last_update_date TEXT,      -- From AACT data
    content_hash TEXT,           -- To detect actual changes
    last_processed_date TEXT     -- When we last processed it
);
```

**Change Detection Logic**:
```python
for trial in new_aact_snapshot:
    db_record = get_from_db(trial.nct_id)

    if not db_record:
        # NEW trial: process and insert
        process_and_insert(trial)
        add_to_db(trial)

    elif trial.hash != db_record.content_hash:
        # UPDATED trial: reprocess and upsert
        delete_from_qdrant(trial.nct_id)  # Remove old vectors
        process_and_insert(trial)         # Add new vectors
        update_db(trial)

    else:
        # UNCHANGED: skip
        continue
```

**Implementation**:
1. Create SQLite database for tracking
2. During full load: populate tracking DB
3. During update: compare new snapshot with DB
4. Process only NEW + UPDATED trials
5. Upsert to Qdrant (delete old trial vectors + insert new)
6. Update tracking DB

**Commands**:
```bash
# Full load (first time)
./bioyoda.sh run clinical_trials --mode full

# Weekly/monthly updates
./bioyoda.sh run clinical_trials --mode update
./bioyoda.sh qdrant insert clinical_trials --mode update
```

---

## Qdrant Update Strategy

### For PubMed (Append-Only)
- PubMed abstracts don't change
- Just insert new vectors
- No deletion needed

### For Clinical Trials (Upsert with Deletion)
```python
def update_trial_in_qdrant(nct_id, new_vectors, metadata):
    # Step 1: Delete all existing vectors for this trial
    client.delete(
        collection_name="clinical_trials",
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="nct_id",
                        match=models.MatchValue(value=nct_id)
                    )
                ]
            )
        )
    )

    # Step 2: Insert new vectors
    client.upsert(
        collection_name="clinical_trials",
        points=new_vectors
    )
```

---

## File Structure

```
bioyoda/
├── out/state/                              # Tracking data
│   ├── pubmed/
│   │   └── processed_files.json            # Simple JSON tracking
│   └── clinical_trials/
│       └── trials_tracking.db              # SQLite database
│
├── out/data/processed/
│   ├── pubmed/
│   │   ├── baseline/*.index                # Full load files
│   │   └── updatefiles/*.index             # Update files
│   └── clinical_trials/
│       ├── trials_chunk_*.index            # Full load chunks
│       └── trials_update_YYYYMMDD_*.index  # Update chunks (dated)
│
├── modules/
│   ├── pubmed/scripts/
│   │   ├── download.py                     # Modify: skip existing files
│   │   └── index.py                        # Modify: add --update-mode
│   │
│   ├── clinical_trials/scripts/
│   │   ├── download_aact.py                # Existing (downloads full snapshot)
│   │   ├── process_trials_update.py        # NEW: update mode processing
│   │   └── tracking_db.py                  # NEW: SQLite utilities
│   │
│   └── qdrant/scripts/
│       └── insert_from_faiss.py            # Modify: add --update-mode with deletion
│
└── config/
    └── config.yaml                         # Add update settings
```

---

## Implementation Phases

### Phase 1: PubMed Updates (Quick Win - 2-3 days)

**Files to modify:**
1. `modules/pubmed/scripts/download.py`
   - Add `--update-mode` flag
   - Load tracking JSON
   - Skip already-processed files

2. Create `modules/pubmed/scripts/tracking.py`
   - Simple functions to read/write tracking JSON
   - `get_processed_files()`, `mark_file_processed()`

3. Modify `modules/pubmed/Snakefile`
   - Add `pubmed_update` rule
   - Use different output directory for updates

4. Update `bioyoda.sh`
   - Add `--mode update` parameter
   - Pass to Snakemake

**Testing:**
```bash
# Test with fixture
./bioyoda.sh test --pipeline --mode update
```

---

### Phase 2: Clinical Trials Tracking DB (3-4 days)

**New files:**
1. `modules/clinical_trials/scripts/tracking_db.py`
```python
import sqlite3
from pathlib import Path

class TrialsTracker:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Create tracking table if not exists"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trials (
                    nct_id TEXT PRIMARY KEY,
                    last_update_date TEXT,
                    content_hash TEXT,
                    last_processed_date TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nct ON trials(nct_id)")

    def get_trial(self, nct_id):
        """Get trial info from DB"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM trials WHERE nct_id = ?",
                (nct_id,)
            )
            return cursor.fetchone()

    def add_or_update_trial(self, nct_id, last_update_date, content_hash):
        """Add or update trial record"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trials
                (nct_id, last_update_date, content_hash, last_processed_date)
                VALUES (?, ?, ?, datetime('now'))
            """, (nct_id, last_update_date, content_hash))

    def get_all_nct_ids(self):
        """Get all tracked NCT IDs"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT nct_id FROM trials")
            return [row[0] for row in cursor.fetchall()]
```

2. Modify `modules/clinical_trials/scripts/extract_text_optimized.py`
   - Add `--populate-tracking` flag for initial load
   - Store trial ID + hash in tracking DB

---

### Phase 3: Clinical Trials Update Processing (4-5 days)

**New file:** `modules/clinical_trials/scripts/process_trials_update.py`
```python
# Pseudo-code structure

def main(args):
    # 1. Load tracking database
    tracker = TrialsTracker(args.tracking_db)
    known_nct_ids = set(tracker.get_all_nct_ids())

    # 2. Load new AACT snapshot
    new_trials = load_aact_snapshot(args.aact_dir)

    # 3. Identify changes
    new_trials_list = []
    updated_trials_list = []

    for trial in new_trials:
        nct_id = trial['nct_id']
        trial_hash = compute_hash(trial)

        if nct_id not in known_nct_ids:
            new_trials_list.append(trial)
        else:
            db_record = tracker.get_trial(nct_id)
            if trial_hash != db_record['content_hash']:
                updated_trials_list.append(trial)

    print(f"Found {len(new_trials_list)} new trials")
    print(f"Found {len(updated_trials_list)} updated trials")

    # 4. Process only changed trials
    trials_to_process = new_trials_list + updated_trials_list

    if not trials_to_process:
        print("No changes detected, nothing to process")
        return

    # 5. Create update chunk files
    process_trials_to_faiss(
        trials_to_process,
        output_dir=args.output_dir,
        chunk_prefix=f"trials_update_{datetime.now().strftime('%Y%m%d')}"
    )

    # 6. Update tracking database
    for trial in trials_to_process:
        tracker.add_or_update_trial(
            nct_id=trial['nct_id'],
            last_update_date=trial['last_update_date'],
            content_hash=compute_hash(trial)
        )
```

---

### Phase 4: Qdrant Upsert Operations (2-3 days)

**Modify:** `modules/qdrant/scripts/insert_from_faiss.py`

Add deletion logic for clinical trials updates:

```python
def insert_from_faiss(faiss_dir, collection_name, qdrant_url,
                      batch_size=500, update_mode=False):

    # ... existing code ...

    for index_path in index_files:
        index, metadata = load_faiss_and_metadata(index_path)

        # If update mode for clinical_trials, delete old data first
        if update_mode and collection_name == "clinical_trials":
            # Get unique NCT IDs from this chunk
            nct_ids_in_chunk = set()
            for meta_key in metadata:
                nct_id = metadata[meta_key].get('nct_id')
                if nct_id:
                    nct_ids_in_chunk.add(nct_id)

            # Delete old vectors for these trials
            for nct_id in nct_ids_in_chunk:
                log_with_timestamp(f"  Deleting old vectors for {nct_id}")
                client.delete(
                    collection_name=collection_name,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[models.FieldCondition(
                                key="nct_id",
                                match=models.MatchValue(value=nct_id)
                            )]
                        )
                    )
                )

        # Insert new vectors (same as before)
        # ... existing insertion code ...
```

---

### Phase 5: Configuration & CLI Integration (1-2 days)

**Update:** `config/config.yaml`
```yaml
# Update settings
update:
  enabled: true
  state_dir: "out/state"

pubmed:
  update:
    state_file: "out/state/pubmed/processed_files.json"
    download_updates_only: true  # Skip baseline in update mode

clinical_trials:
  update:
    tracking_db: "out/state/clinical_trials/trials_tracking.db"
    chunk_prefix: "trials_update"
    keep_update_chunks: true
```

**Update:** `bioyoda.sh`
```bash
# Add --mode parameter
run() {
    local mode="full"  # or "update"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --mode)
                mode="$2"
                shift 2
                ;;
            # ... other args ...
        esac
    done

    # Pass mode to Snakemake
    snakemake_cmd="${snakemake_cmd} --config update_mode=${mode}"

    # ... rest of function ...
}
```

---

## Testing Strategy

### Unit Tests
- Test tracking JSON read/write
- Test SQLite operations
- Test hash computation
- Test change detection logic

### Integration Tests

**Add to existing test suite:**

```bash
# New test mode: test --pipeline --with-updates
test() {
    local pipeline_mode=false
    local test_updates=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --pipeline) pipeline_mode=true; shift ;;
            --with-updates) test_updates=true; shift ;;
            *) shift ;;
        esac
    done

    # ... existing test steps ...

    # NEW: Test incremental updates
    if [[ "$test_updates" == true ]]; then
        log_info "Step 7/7: Testing incremental updates"

        # Simulate update: add new fixtures
        cp tests/fixtures/pubmed/update_test.xml.gz test_out/raw_data/pubmed/updatefiles/

        # Run update
        ./bioyoda.sh run pubmed --mode update --test --local
        ./bioyoda.sh qdrant insert pubmed --mode update --test --local

        # Verify update worked
        python tests/validate_updates.py

        log_success "Update test passed"
    fi
}
```

**Test Commands:**
```bash
# Quick test (fixtures only)
./bioyoda.sh test

# Full pipeline test
./bioyoda.sh test --pipeline

# Full test with updates
./bioyoda.sh test --pipeline --with-updates
```

---

## Example Workflows

### Daily PubMed Updates
```bash
#!/bin/bash
# cron job: daily at 2 AM

cd /path/to/bioyoda

# Download and process new updatefiles
./bioyoda.sh run pubmed --mode update --cluster --bg --jobs 20

# Wait for processing to complete (or check in next run)
# ...

# Insert new data to Qdrant
./bioyoda.sh qdrant insert pubmed --mode update --cluster --jobs 5 --bg
```

### Weekly Clinical Trials Updates
```bash
#!/bin/bash
# cron job: weekly on Sunday at 3 AM

cd /path/to/bioyoda

# Download new AACT snapshot
./bioyoda.sh run clinical_trials --mode update --cluster --bg --jobs 10

# Wait for processing...

# Upsert to Qdrant (with deletion of old data)
./bioyoda.sh qdrant insert clinical_trials --mode update --cluster --jobs 5 --bg
```

---

## Status & Monitoring

**New commands:**
```bash
# Show update status
./bioyoda.sh status --updates

# Output:
# PubMed:
#   Last update: 2025-01-15 08:30:00
#   Files processed: 1234 baseline + 567 updates
#   Last update file: pubmed25n1234.xml.gz
#
# Clinical Trials:
#   Last update: 2025-01-10 03:00:00
#   Trials tracked: 554,123
#   New trials (last run): 1,234
#   Updated trials (last run): 5,678

# Show tracking database stats
./bioyoda.sh tracking stats clinical_trials

# Output:
# Tracking Database: out/state/clinical_trials/trials_tracking.db
# Total trials: 554,123
# Oldest processed: 2020-01-15
# Newest processed: 2025-01-15
# Database size: 45 MB
```

---

## Rollback Strategy

If an update fails or corrupts data:

```bash
# 1. Stop any running updates
./bioyoda.sh qdrant stop-insert all

# 2. Restore Qdrant from backup (manual)
# - Stop Qdrant server
# - Restore out/data/qdrant/storage from backup
# - Restart Qdrant server

# 3. Reset tracking state
./bioyoda.sh tracking reset pubmed           # Remove last update entry
./bioyoda.sh tracking reset clinical_trials  # Restore DB from backup

# 4. Retry update
./bioyoda.sh run pubmed --mode update --cluster --bg
```

---

## Future Enhancements (Not in Initial Implementation)

1. **Change History Tracking** (for user notifications)
   - Add `change_log` column to trials table
   - Track which fields changed

2. **Incremental Deletion** (for removed trials)
   - Track trials that disappeared from AACT
   - Remove from Qdrant

3. **Update Verification**
   - Compare vector counts before/after
   - Validate data integrity

4. **Performance Optimization**
   - Parallel processing of updates
   - Bulk deletion in Qdrant

5. **Monitoring Dashboard**
   - Web UI to view update status
   - Graphs of growth over time

---

## Timeline Estimate

| Phase | Task | Duration | Status |
|-------|------|----------|--------|
| 1 | PubMed Updates | 2-3 days | Pending |
| 2 | Clinical Trials Tracking DB | 3-4 days | Pending |
| 3 | Clinical Trials Update Processing | 4-5 days | Pending |
| 4 | Qdrant Upsert Operations | 2-3 days | Pending |
| 5 | Configuration & CLI | 1-2 days | Pending |
| 6 | Testing & Documentation | 2-3 days | Pending |
| **Total** | | **14-20 days** | |

---

## Success Criteria

✅ PubMed daily updates complete in <30 minutes
✅ Clinical trials updates complete in <2 hours
✅ No data loss or corruption
✅ Tracking state is reliable
✅ Updates integrate with existing test suite
✅ Clear documentation for maintenance

---

## Questions & Decisions

### Resolved:
- ✅ Use 1 table for tracking (simple approach)
- ✅ Use SQLite for clinical trials (not JSON)
- ✅ Upsert strategy: delete old + insert new

### Open:
- ⏳ Update frequency: Daily for PubMed, Weekly for Clinical Trials?
- ⏳ Keep dated update chunks or overwrite?
- ⏳ Backup strategy for tracking DB?
- ⏳ Notification system for failed updates?

---

**Next Steps:**
1. Review this plan with stakeholders
2. Set up development environment
3. Start with Phase 1 (PubMed Updates)
4. Iterate based on feedback

**Contact:** Solo developer - update as needed!

---

_Last updated: 2025-01-15_
