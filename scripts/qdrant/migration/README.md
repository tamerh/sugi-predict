# Qdrant Migration Scripts

## Storage Options

The migration script now supports two storage modes:

### 1. NFS Storage (Default - Reliable)
```bash
# Uses reliable NFS storage directly
./local_qdrant_migration.sh
```

### 2. Temporary Storage (Optional - Performance)
```bash
# Uses /tmp for performance, then copies to NFS
USE_TMP_STORAGE=true ./local_qdrant_migration.sh
```

## Improved Features

### Enhanced Error Checking
- ✅ Verifies Qdrant responses
- ✅ Periodic point count verification (every 50 batches)
- ✅ Better error reporting with collection state info

### Flexible Storage
- ✅ Configurable storage location
- ✅ Automatic data preservation
- ✅ Intelligent cleanup based on storage type

### Migration Verification
- ✅ Real-time point count verification
- ✅ Collection state monitoring
- ✅ Response status checking

## Usage Examples

```bash
# Reliable NFS storage (recommended)
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/migration
./local_qdrant_migration.sh

# High-performance /tmp storage
cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/migration
USE_TMP_STORAGE=true ./local_qdrant_migration.sh

# Check available space first
df -h /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/qdrant
```

## Troubleshooting

If migration shows successful uploads but no files in storage:
1. Check the migration logs for point count verification messages
2. Verify Qdrant is actually receiving and storing data
3. Use NFS storage mode for guaranteed reliability
4. Monitor the periodic verification messages every 50 batches