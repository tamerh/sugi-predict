# Patents Module - Incremental Update Strategies

## Current Situation

**SureChEMBL releases are full snapshots**, not deltas:
- Each release contains ALL patents (~43M) and compounds (~30M)
- Releases are bi-weekly
- No built-in way to identify what changed between releases

**Current behavior:**
- New release detected → chunks exist → **skips re-chunking** (uses stale data)
- No release version tracking in state files
- No change detection mechanism

## Problem Statement

```
Release 2025-12-15: 43M patents, 30M compounds (processed)
Release 2025-12-29: 43.1M patents, 30.2M compounds (new release)
                    └── ~100K new patents, ~200K compounds, some updates

Without incremental updates:
  Full reprocess: ~12 hours (cluster) every 2 weeks

With incremental updates:
  Process only changes: ~30 min every 2 weeks
```

---

## Solution Options

### Option 1: Release-Level Invalidation (Simple)

**Description:** Track release version in state file. When new release detected, invalidate all chunks and reprocess everything.

**Implementation:**
```python
# processed_chunks.json
{
    "release_version": "2025-12-15",  # ADD THIS
    "last_update": "...",
    "chunks": {...}
}

# In download_and_prepare_patents.py:
if state['release_version'] != current_release:
    log("New release detected, invalidating old chunks...")
    delete_old_chunks()
    delete_old_indices()
    # Proceed to re-chunk and reprocess
```

**Pros:**
- Simple to implement
- Reliable, no stale data
- No additional storage

**Cons:**
- Not truly incremental
- Full reprocess every 2 weeks (~12 hours)

**When to use:** Acceptable if compute resources are available and 12h processing time is OK.

---

### Option 2: SQLite Hash Tracking (True Incremental)

**Description:** Store patent/compound IDs with content hashes in SQLite. On new release, stream through data and compare hashes to detect changes.

**Implementation:**
```python
# patents_tracking.db schema:
CREATE TABLE patents (
    patent_id TEXT PRIMARY KEY,
    content_hash TEXT,
    release_version TEXT,
    last_processed TEXT
);

# Processing flow:
for row in stream_parquet(new_release):
    stored_hash = sqlite.get(row.patent_id)
    current_hash = compute_hash(row)

    if stored_hash is None:
        process(row)  # NEW
    elif stored_hash != current_hash:
        process(row)  # CHANGED
    else:
        skip(row)     # UNCHANGED
```

**Pros:**
- True incremental (process only ~1% of data)
- Low memory (streaming)
- Detects both new and changed records

**Cons:**
- Complex implementation
- Requires SQLite DB maintenance (~2GB for patents, ~1.5GB for compounds)
- Initial full processing still required

**Existing infrastructure:** `modules/patents/scripts/tracking.py` has `PatentsSQLiteTracker` class (not currently wired up).

---

### Option 3: DuckDB Parquet Diff (Recommended)

**Description:** Use DuckDB to query old and new parquet files directly, identifying new and changed records without loading into memory.

**Implementation:**
```python
import duckdb

# Keep both releases temporarily
old_release = 'surechembl/2025-12-15/patents.parquet'
new_release = 'surechembl/2025-12-29/patents.parquet'

# Find NEW patents (in new, not in old)
new_patents = duckdb.sql(f"""
    SELECT n.*
    FROM '{new_release}' n
    LEFT JOIN '{old_release}' o ON n.patent_id = o.patent_id
    WHERE o.patent_id IS NULL
""").fetchdf()

# Find CHANGED patents (same ID, different content)
changed_patents = duckdb.sql(f"""
    SELECT n.*
    FROM '{new_release}' n
    JOIN '{old_release}' o ON n.patent_id = o.patent_id
    WHERE md5(COALESCE(n.title,'') || COALESCE(n.abstract,''))
       != md5(COALESCE(o.title,'') || COALESCE(o.abstract,''))
""").fetchdf()

# Find DELETED patents
deleted_ids = duckdb.sql(f"""
    SELECT o.patent_id
    FROM '{old_release}' o
    LEFT JOIN '{new_release}' n ON o.patent_id = n.patent_id
    WHERE n.patent_id IS NULL
""").fetchdf()

# Create delta parquet for processing
delta = pd.concat([new_patents, changed_patents])
delta.to_parquet('delta_patents.parquet')
```

**Pros:**
- Queries parquet directly on disk (low memory)
- Detects both new IDs and content changes
- No persistent DB to maintain
- Fast (columnar, vectorized operations)
- SQL syntax (familiar, readable)

**Cons:**
- Requires keeping 2 releases temporarily (~12GB extra disk)
- DuckDB dependency
- More complex than Option 1

**When to use:** Best balance of efficiency and simplicity for bi-weekly batch updates.

---

### Option 4: Qdrant Upsert Only (Simplest)

**Description:** Always reprocess everything, rely on Qdrant's upsert to handle duplicates by ID.

**Implementation:**
```python
# Process all patents (or all chunks)
for chunk in chunks:
    vectors = embed(chunk)
    qdrant.upsert(
        collection="patents",
        points=vectors,
        ids=patent_ids  # Qdrant replaces existing by ID
    )
```

**Pros:**
- Simplest implementation
- No diff logic needed
- Always consistent

**Cons:**
- Wastes compute on unchanged records
- Full embedding cost every time
- Network overhead to Qdrant

**When to use:** If compute is cheap and simplicity is priority.

---

## Recommended Approach

### Phase 1: Release Tracking (Immediate)
Add `release_version` to state files to prevent stale data.

### Phase 2: Evaluate Full Processing Time
Run full processing with GPU acceleration. If acceptable (<2 hours), use Option 1.

### Phase 3: DuckDB Delta Detection (If Needed)
If full processing is too slow, implement Option 3 (DuckDB diff).

---

## Applies To

Both data types need incremental handling:

| Data | File | Records | Embedding |
|------|------|---------|-----------|
| Patents | patents.parquet | ~43M | S-BioBERT text embeddings |
| Compounds | compounds.parquet | ~30M | Morgan fingerprints |

---

## Related Files

- `scripts/tracking.py` - Has SQLite tracker (not wired up)
- `scripts/download_and_prepare_patents.py` - Chunking logic
- `Snakefile` - Pipeline rules
- `processed_chunks.json` - State file (needs release_version)

---

## Future Considerations

1. **SureChEMBL API:** If EMBL-EBI provides delta endpoint, use that instead
2. **USPTO-Chem:** Already incremental (weekly JSON files with tracking)
3. **Content hashing:** Consider which fields to include in hash (title, abstract, claims?)
4. **Qdrant delete:** Need to handle deleted patents (remove from vector DB)

---

**Last Updated:** December 2025
