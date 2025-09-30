# Qdrant Migration Performance Optimization

## Key Finding: Local Storage Performance

During our migration testing, we discovered **significant performance improvements** when using local `/tmp` storage vs NFS storage.

## Performance Comparison

| Storage Type | Performance | Issues |
|--------------|-------------|---------|
| **NFS** `/data/scc/` | Baseline | Data corruption warnings, slower I/O |
| **Local** `/tmp/` | **30-50% faster** | Clean operation, no corruption warnings |

## Future Migration Strategy

For any future FAISS to Qdrant migrations:

### 1. Copy FAISS Index to Local Storage First

```bash
# Before starting migration, copy FAISS files to /tmp
FAISS_INDEX="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/final/pubmed/master_pubmed2.index"
METADATA="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/final/pubmed/master_metadata2.json"

LOCAL_FAISS="/tmp/faiss_migration_$$/"
mkdir -p "$LOCAL_FAISS"

echo "Copying FAISS index to local storage for better performance..."
cp "$FAISS_INDEX" "$LOCAL_FAISS/"
cp "$METADATA" "$LOCAL_FAISS/"

# Then run migration using local copies
python migrate_faiss_to_qdrant.py \
    --index "$LOCAL_FAISS/master_pubmed2.index" \
    --metadata "$LOCAL_FAISS/master_metadata2.json" \
    # ... other args
```

### 2. Benefits

- **Faster I/O**: Local SSD vs NFS network latency
- **No corruption warnings**: Qdrant works cleanly with local storage
- **Better batch processing**: ~1.2-1.5 batches/second vs slower NFS rate
- **Cleaner logs**: No NFS-related warnings or errors

### 3. Disk Space Considerations

- FAISS index: ~90GB
- Metadata: ~19GB
- **Total**: ~110GB temporary space needed in `/tmp`
- Check available space: `df -h /tmp`

### 4. Current Migration Status

The current migration (started Sep 29, 2024) is running successfully with local storage:
- **Progress**: 4,024/31,521 batches (~12.7% complete)
- **Performance**: ~90 batches/minute
- **Memory**: Stable at ~144GB
- **ETA**: ~6-7 hours total

## Implementation for Next Time

Add this check to migration scripts:

```bash
# Check /tmp space before copying
REQUIRED_SPACE_GB=120
AVAILABLE_SPACE_GB=$(df /tmp | tail -1 | awk '{print int($4/1024/1024)}')

if [[ $AVAILABLE_SPACE_GB -lt $REQUIRED_SPACE_GB ]]; then
    echo "ERROR: Need ${REQUIRED_SPACE_GB}GB in /tmp, only ${AVAILABLE_SPACE_GB}GB available"
    exit 1
fi

echo "✓ Sufficient space in /tmp: ${AVAILABLE_SPACE_GB}GB available"
```

This optimization should be standard procedure for large-scale data migrations.