# Qdrant Upsert Strategy for Incremental Updates

## Overview

The Qdrant insertion script (`insert_from_faiss.py`) now uses **document unique identifiers** as Qdrant point IDs instead of sequential IDs. This enables proper incremental updates using Qdrant's native `upsert` operation.

Additionally, the script integrates with the **tracking system** to avoid reprocessing FAISS indices that have already been inserted to Qdrant.

## Point ID Strategy

### PubMed (PMID)
- **Source field**: `metadata['pmid']`
- **Point ID**: Direct integer conversion of PMID
- **Example**: PMID `"12345678"` → Point ID `12345678`
- **Rationale**: PMIDs are already unique integers, use directly

### Clinical Trials (NCT ID)
- **Source field**: `metadata['nct_id']`
- **Point ID**: SHA256 hash of NCT ID (first 8 bytes as 63-bit integer)
- **Example**: NCT ID `"NCT01234567"` → Point ID `4523891047362819456` (deterministic hash)
- **Rationale**: NCT IDs are alphanumeric, need deterministic conversion to integer

### Fallback (Sequential)
- **Condition**: If neither `pmid` nor `nct_id` found in metadata
- **Point ID**: Sequential starting from `--start-id` parameter
- **Use case**: Backward compatibility with old data or custom datasets

## Tracking Integration

The insertion script integrates with the PubMed tracking system to avoid reprocessing files that have already been inserted to Qdrant.

### Tracking File Format

```json
{
  "files": {
    "baseline/pubmed25n0001.xml.gz": {
      "status": "completed",
      "vectors_count": 100,
      "processed_date": "2025-10-12T16:40:16",
      "qdrant_inserted": true,
      "qdrant_inserted_date": "2025-10-12T17:30:00"
    }
  }
}
```

### How Tracking Works

1. **Pass `--tracking-file` parameter** to insertion script
2. Script loads tracking data and identifies files with `qdrant_inserted: true`
3. **Skips already-inserted files** - doesn't reprocess their FAISS indices
4. After successful insertion, **marks file as inserted** with timestamp
5. Tracking file updated automatically with file locking (prevents race conditions)

### Benefits

✅ **Avoids redundant work**: Doesn't reprocess baseline files in update mode
✅ **Faster incremental updates**: Only inserts new FAISS indices
✅ **Resume capability**: Can restart insertion without duplicating work
✅ **Transparent**: Works seamlessly with existing upsert strategy

## How It Works

### Full Mode (Initial Load)
```bash
./bioyoda.sh run pubmed --local
# or
./bioyoda.sh run clinical_trials --local
```

**Behavior:**
1. Typically clears/recreates Qdrant collection (depending on workflow)
2. Processes all FAISS indices
3. Inserts vectors with PMID/NCT-based point IDs
4. Example PubMed point IDs: 12345678, 12345679, 87654321...
5. Example Clinical Trials point IDs: 4523891047362819456, 7821094563281945728...

### Update Mode (Incremental)
```bash
./bioyoda.sh run pubmed --mode update --local
./bioyoda.sh run clinical_trials --local  # Auto-detects updates (idempotent)
```

**Behavior:**
1. Keeps existing Qdrant collection intact
2. Processes only new/updated FAISS files
3. Uses `upsert` operation:
   - **New document** (new PMID/NCT) → Creates new point
   - **Existing document** (same PMID/NCT) → **Replaces** old vector
4. No duplicates, always latest version

**Clinical Trials**: The pipeline is **idempotent** - it automatically detects changes using a tracking database and processes only new/updated trials. No mode flag needed.

### Example Update Scenario

**Initial Load:**
```
Point ID 12345678: Vector from baseline file, created 2025-01-01
Point ID 12345679: Vector from baseline file, created 2025-01-01
```

**Update (e.g., revised PubMed article 12345678):**
```
Point ID 12345678: Vector from updatefile, REPLACED, now dated 2025-01-15 ✓
Point ID 12345679: Unchanged
Point ID 12345680: NEW vector from updatefile, created 2025-01-15
```

## Code Implementation

### Key Function: `get_point_id_from_metadata()`

```python
def get_point_id_from_metadata(meta: dict, fallback_id: int) -> int:
    """
    Extract point ID from metadata using document unique identifiers.

    Priority order:
    1. pmid (PubMed) - use directly as integer
    2. nct_id (Clinical Trials) - hash to integer
    3. fallback_id - sequential ID for backward compatibility
    """
    # Try PMID first (PubMed)
    if 'pmid' in meta:
        return int(meta['pmid'])

    # Try NCT ID (Clinical Trials)
    if 'nct_id' in meta:
        nct_id = str(meta['nct_id'])
        hash_bytes = hashlib.sha256(nct_id.encode()).digest()[:8]
        point_id = int.from_bytes(hash_bytes, byteorder='big', signed=False)
        return point_id & 0x7FFFFFFFFFFFFFFF  # 63-bit positive

    # Fallback
    return fallback_id
```

### Modified Insertion Logic

**Before (Sequential IDs):**
```python
point = PointStruct(
    id=global_point_id,  # 0, 1, 2, 3...
    vector=vectors[i].tolist(),
    payload=meta
)
global_point_id += 1
```

**After (Unique IDs):**
```python
point_id = get_point_id_from_metadata(meta, global_point_id)
point = PointStruct(
    id=point_id,  # PMID: 12345678, or hashed NCT ID
    vector=vectors[i].tolist(),
    payload=meta
)
```

## Benefits

✅ **Idempotent Updates**: Running insertion multiple times with same data won't create duplicates

✅ **Document-Centric**: Point ID directly tied to document identity (PMID/NCT)

✅ **Automatic Replacement**: Updated documents automatically replace old versions

✅ **Query Consistency**: Same document always has same point ID across updates

✅ **Backward Compatible**: Falls back to sequential IDs if unique identifiers missing

## Verification

### Check Point IDs
```python
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")

# Get a few points
points = client.scroll(
    collection_name="pubmed_biobert",
    limit=10
)[0]

for point in points:
    print(f"Point ID: {point.id}, PMID: {point.payload.get('pmid')}")
```

**Expected output:**
```
Point ID: 12345678, PMID: 12345678
Point ID: 87654321, PMID: 87654321
```

### Test Upsert
```bash
# Insert same file twice
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir test_out/data/processed/pubmed/baseline \
    --collection pubmed_test \
    --qdrant-url http://localhost:6333

# Check count (should not double)
```

## Impact on Existing Systems

### ✅ No Breaking Changes
- Script auto-detects ID strategy from metadata
- Falls back to sequential IDs for compatibility
- All existing parameters and workflows unchanged

### ⚠️ Migration Considerations
- **Existing collections with sequential IDs**: Will continue working, but can't leverage upsert
- **New collections**: Automatically use unique IDs
- **Recommendation**: For full benefit, recreate collection with new data

## Usage Examples

### Without Tracking (Basic)
```bash
# Insert all FAISS indices
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir test_out/data/processed/pubmed \
    --collection pubmed_biobert \
    --qdrant-url http://localhost:6333
```

### With Tracking (Incremental Updates)
```bash
# First insertion (full mode)
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir test_out/data/processed/pubmed \
    --collection pubmed_biobert \
    --qdrant-url http://localhost:6333 \
    --tracking-file test_out/state/pubmed/processed_files.json

# Result: Inserts all files, marks them as inserted in tracking

# Second insertion (update mode, after new updatefiles processed)
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir test_out/data/processed/pubmed \
    --collection pubmed_biobert \
    --qdrant-url http://localhost:6333 \
    --tracking-file test_out/state/pubmed/processed_files.json

# Result: Skips baseline files (already inserted), only inserts new updatefiles
```

### Check Tracking Status
```bash
# View tracking statistics
python modules/pubmed/scripts/tracking.py \
    --tracking-file test_out/state/pubmed/processed_files.json \
    stats

# Output shows:
# Qdrant Insertion:
#   - Inserted: 2
#   - Pending: 2
```

## Testing

### Test with PubMed
```bash
# Test mode (2 files)
./bioyoda.sh run pubmed --test --local

# Insert to Qdrant with tracking
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir test_out/data/processed/pubmed \
    --collection pubmed_test \
    --qdrant-url http://localhost:6333 \
    --tracking-file test_out/state/pubmed/processed_files.json

# Verify IDs match PMIDs and tracking is updated
python modules/pubmed/scripts/tracking.py \
    --tracking-file test_out/state/pubmed/processed_files.json \
    stats
```

### Test with Clinical Trials
```bash
# Idempotent - automatically detects updates
./bioyoda.sh run clinical_trials --test --local

# Insert to Qdrant with tracking
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir test_out/data/processed/clinical_trials \
    --collection clinical_trials_test \
    --qdrant-url http://localhost:6333 \
    --tracking-file test_out/state/clinical_trials/processed_chunks.json

# NCT IDs are hashed deterministically for upserts
```

## Clinical Trials Update Strategy

**Implemented**: Clinical trials now supports automatic incremental updates.

### How It Works

1. **Tracking Database**: SQLite DB (`trials_tracking.db`) stores trial content hashes
2. **Change Detection**: Compares new AACT snapshot with tracking DB
3. **Selective Processing**: Only new + updated trials are processed into update chunks
4. **Named Chunks**: Update chunks named with dates: `trials_update_20251013_chunk_0001.json`
5. **Upsert to Qdrant**: Updated trials automatically replace old vectors (same NCT ID = same point ID)

### Update Workflow

```bash
# Day 1: Initial load
./bioyoda.sh run clinical_trials --local
./bioyoda.sh qdrant insert clinical_trials
# → All trials in Qdrant

# Day 2+: Automatic incremental update
./bioyoda.sh run clinical_trials --local
# → Downloads new snapshot
# → Detects changed trials (hash comparison)
# → Creates: trials_update_20251013_chunk_*.json
./bioyoda.sh qdrant insert clinical_trials
# → Upserts changed trials (replaces old vectors)
```

### State Preservation

**Key benefit**: Metadata preserved across runs:
```json
{
  "chunks": {
    "trials_chunk_0001.json": {
      "status": "completed",
      "vectors_count": 259,
      "qdrant_inserted": true,
      "qdrant_inserted_date": "2025-10-13"
    },
    "trials_update_20251013_chunk_0001.json": {
      "status": "ready_to_process",
      "num_trials": 50
    }
  }
}
```

### Performance

**Example**: 554K trials total, 1K changed
- Initial load: ~4 hours
- Update detection: ~2 minutes
- Process 1K changed trials: ~3 minutes
- Insert to Qdrant: ~30 seconds
- **Total update time: ~6 minutes** (vs 4 hours full reprocess)

## Future Enhancements

- [ ] Add `--force-sequential` flag to override unique ID strategy
- [ ] Support custom ID field via `--id-field` parameter
- [ ] Add validation to detect ID collisions
- [ ] Performance metrics comparing sequential vs unique ID insertion
