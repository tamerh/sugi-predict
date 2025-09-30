#!/bin/bash
# Local Qdrant Migration Script
# Migrates FAISS indices to Qdrant using local /tmp storage for performance
# Data is automatically copied to permanent storage after completion

set -e

echo "=== Qdrant Migration ==="
echo "Storage type: $STORAGE_TYPE"
echo "Working directory: $LOCAL_STORAGE"

# Configuration
CONTAINER_PATH="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/setup/singularity/qdrant.sif"
CONFIG_PATH="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/setup/singularity/config.yaml"
PERMANENT_STORAGE="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/qdrant"  # Final storage location
MIGRATION_SCRIPT="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/migration/migrate_faiss_to_qdrant.py"

# Storage options - choose between tmp (performance) or NFS (reliability)
USE_TMP_STORAGE="${USE_TMP_STORAGE:-false}"  # Set to true to use /tmp

if [ "$USE_TMP_STORAGE" = "true" ]; then
    LOCAL_STORAGE="/tmp/qdrant_migration_$$"
    STORAGE_TYPE="temporary (/tmp)"
else
    LOCAL_STORAGE="$PERMANENT_STORAGE/migration_$$"
    STORAGE_TYPE="NFS (reliable)"
fi

# Create local storage directory
mkdir -p "$LOCAL_STORAGE"
echo "Created local storage: $LOCAL_STORAGE"

# Check available space
echo "Available space in storage location:"
df -h "$(dirname "$LOCAL_STORAGE")"

# Start Qdrant in background
echo "Starting Qdrant server locally..."
nohup singularity run \
    --bind "$LOCAL_STORAGE:/qdrant/storage" \
    --bind "$CONFIG_PATH:/opt/qdrant/config.yaml" \
    "$CONTAINER_PATH" \
    --config-path /opt/qdrant/config.yaml > qdrant_local.log 2>&1 &

QDRANT_PID=$!
echo "Qdrant started with PID: $QDRANT_PID"

# Wait for Qdrant to be ready
echo "Waiting for Qdrant to start..."
for i in {1..30}; do
    if curl -s http://localhost:6333/collections > /dev/null 2>&1; then
        echo "✓ Qdrant is ready!"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

# Test connection and verify configuration
echo "Testing Qdrant connection:"
curl -s http://localhost:6333/collections | head -100

# Verify configuration is loaded by creating a test collection
echo ""
echo "Verifying configuration is loaded correctly..."
curl -X PUT 'http://localhost:6333/collections/config_verify' \
    -H 'Content-Type: application/json' \
    --data-raw '{"vectors": {"size": 768, "distance": "Cosine"}}' \
    -s > /dev/null

# Check if our S-BioBERT configuration is applied
CONFIG_CHECK=$(curl -s 'http://localhost:6333/collections/config_verify' | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    config = data['result']['config']

    # Check key settings
    vector_size = config['params']['vectors']['size']
    hnsw_m = config['hnsw_config']['m']
    hnsw_ef = config['hnsw_config']['ef_construct']
    deleted_threshold = config['optimizer_config']['deleted_threshold']
    wal_capacity = config['wal_config']['wal_capacity_mb']

    print(f'Vector size: {vector_size} (expected: 768)')
    print(f'HNSW m: {hnsw_m} (expected: 16)')
    print(f'HNSW ef_construct: {hnsw_ef} (expected: 100)')
    print(f'Deleted threshold: {deleted_threshold} (expected: 0.2)')
    print(f'WAL capacity: {wal_capacity} (expected: 32)')

    # Verify our critical settings
    if vector_size == 768 and hnsw_m == 16 and wal_capacity == 32:
        print('✓ Configuration verified - custom settings are active')
    else:
        print('✗ Configuration issue detected')

except Exception as e:
    print(f'Config verification failed: {e}')
")

echo "$CONFIG_CHECK"

# Clean up test collection
curl -X DELETE 'http://localhost:6333/collections/config_verify' -s > /dev/null

# Check if previous migration exists and resume
echo ""
echo "Checking for existing migration data..."
if curl -s http://localhost:6333/collections/pubmed_abstracts > /dev/null 2>&1; then
    CURRENT_POINTS=$(curl -s http://localhost:6333/collections/pubmed_abstracts | python -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['result']['points_count'])
except:
    print('0')
")
    echo "Found existing collection with $CURRENT_POINTS points"
    echo "Will resume migration..."
    RESUME_FLAG="--resume"
else
    echo "No existing collection found - starting fresh"
    RESUME_FLAG=""
fi

# Activate conda environment
echo "Activating conda environment..."
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda

# Run migration
echo ""
echo "=== Starting Migration ==="
python "$MIGRATION_SCRIPT" \
    --index /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/final/pubmed/master_pubmed2.index \
    --metadata /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/final/pubmed/master_metadata2.json \
    --collection pubmed_abstracts \
    --qdrant-url http://localhost:6333 \
    --batch-size 1000 \
    $RESUME_FLAG

# Cleanup function
cleanup() {
    echo ""
    echo "=== Migration Completed - Processing Results ==="

    # Stop Qdrant server first
    echo "Stopping Qdrant server (PID: $QDRANT_PID)..."
    kill $QDRANT_PID 2>/dev/null || true
    sleep 3  # Give it time to shut down gracefully

    # Check local storage size
    if [ -d "$LOCAL_STORAGE" ]; then
        LOCAL_SIZE=$(du -sh "$LOCAL_STORAGE" 2>/dev/null | cut -f1)
        echo "Local storage used: $LOCAL_SIZE"

        if [ "$USE_TMP_STORAGE" = "true" ]; then
            # Copy from /tmp to permanent storage
            mkdir -p "$PERMANENT_STORAGE"

            echo "Copying Qdrant data to permanent storage..."
            echo "  From: $LOCAL_STORAGE"
            echo "  To: $PERMANENT_STORAGE"

            if cp -r "$LOCAL_STORAGE"/* "$PERMANENT_STORAGE/" 2>/dev/null; then
                FINAL_SIZE=$(du -sh "$PERMANENT_STORAGE" 2>/dev/null | cut -f1)
                echo "✓ Data successfully copied to permanent storage ($FINAL_SIZE)"

                # Verify data integrity
                echo "Verifying data integrity..."
                if [ -f "$PERMANENT_STORAGE/raft_state.json" ] && [ -d "$PERMANENT_STORAGE/collections" ]; then
                    echo "✓ Data integrity verified - core files present"

                    # Clean up temporary storage
                    echo "Cleaning up temporary storage: $LOCAL_STORAGE"
                    rm -rf "$LOCAL_STORAGE"
                    echo "✓ Temporary storage cleaned up"
                else
                    echo "✗ Data integrity check failed - keeping temporary storage for investigation"
                    echo "  Temporary storage preserved at: $LOCAL_STORAGE"
                fi
            else
                echo "✗ Failed to copy data to permanent storage"
                echo "  Temporary storage preserved at: $LOCAL_STORAGE"
                echo "  Manual intervention required"
            fi
        else
            # Data is already in NFS location, just rename
            echo "Data already in permanent NFS storage location"
            FINAL_DIR="$PERMANENT_STORAGE/$(date +%Y%m%d_%H%M%S)"

            if mv "$LOCAL_STORAGE" "$FINAL_DIR" 2>/dev/null; then
                FINAL_SIZE=$(du -sh "$FINAL_DIR" 2>/dev/null | cut -f1)
                echo "✓ Data moved to final location: $FINAL_DIR ($FINAL_SIZE)"
                LOCAL_STORAGE="$FINAL_DIR"  # Update for final reporting
            else
                echo "✗ Failed to move data to final location"
                echo "  Data remains at: $LOCAL_STORAGE"
            fi
        fi
    else
        echo "No local storage found to clean up"
    fi

    echo ""
    echo "Final locations:"
    if [ "$USE_TMP_STORAGE" = "true" ]; then
        echo "  Permanent storage: $PERMANENT_STORAGE"
        echo "  Size: $(du -sh "$PERMANENT_STORAGE" 2>/dev/null | cut -f1 || echo 'Unknown')"
    else
        echo "  Final storage: $LOCAL_STORAGE"
        echo "  Size: $(du -sh "$LOCAL_STORAGE" 2>/dev/null | cut -f1 || echo 'Unknown')"
    fi
    echo "=== Cleanup complete ==="
}

# Set up cleanup on exit
trap cleanup EXIT

echo ""
echo "Migration completed! Check the logs above for results."
echo "Local storage will be cleaned up automatically."