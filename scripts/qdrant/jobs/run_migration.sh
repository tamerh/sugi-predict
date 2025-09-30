#!/bin/bash
#$ -N fs_migration
#$ -q scc
#$ -l h_vmem=256G
#$ -l h_rt=12:00:00
#$ -cwd
#$ -V
#$ -pe smp 4

# Migrate FAISS index to Qdrant database
# This script runs the migration process on the HPC cluster

set -e

echo "Starting FAISS to Qdrant migration..."
echo "Job ID: $JOB_ID"
echo "Hostname: $(hostname)"
echo "Timestamp: $(date)"

# Activate conda environment
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda

# Install qdrant-client if not already installed
pip install qdrant-client --quiet

# Configuration
SCRIPT_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant"
MIGRATION_SCRIPT="$SCRIPT_DIR/migration/migrate_faiss_to_qdrant.py"
CONNECTION_INFO="$SCRIPT_DIR/connection_info.txt"

# Default paths (can be overridden with environment variables)
FAISS_INDEX_PATH="${FAISS_INDEX_PATH:-/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/final/pubmed/current/master_pubmed.index}"
METADATA_PATH="${METADATA_PATH:-/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/final/pubmed/current/master_metadata.json}"
COLLECTION_NAME="${COLLECTION_NAME:-pubmed_abstracts}"
BATCH_SIZE="${BATCH_SIZE:-1000}"

# Check if Qdrant server is running
if [ ! -f "$CONNECTION_INFO" ]; then
    echo "ERROR: Qdrant connection info not found."
    echo "Please start the Qdrant server first using run_qdrant_server.sh"
    exit 1
fi

# Load connection information
source "$CONNECTION_INFO"

echo "Migration Configuration:"
echo "  FAISS Index: $FAISS_INDEX_PATH"
echo "  Metadata: $METADATA_PATH"
echo "  Collection: $COLLECTION_NAME"
echo "  Qdrant URL: $QDRANT_URL"
echo "  Batch Size: $BATCH_SIZE"

# Verify input files exist
if [ ! -f "$FAISS_INDEX_PATH" ]; then
    echo "ERROR: FAISS index file not found: $FAISS_INDEX_PATH"
    exit 1
fi

if [ ! -f "$METADATA_PATH" ]; then
    echo "ERROR: Metadata file not found: $METADATA_PATH"
    exit 1
fi

# Check Qdrant server connectivity
echo "Testing Qdrant connectivity..."
if ! curl -s "$QDRANT_URL/collections" > /dev/null; then
    echo "ERROR: Cannot connect to Qdrant server at $QDRANT_URL"
    echo "Please ensure the Qdrant server is running."
    exit 1
fi

echo "✓ Qdrant server is accessible"

# Display file sizes
echo "Input Data Information:"
echo "  FAISS Index: $(du -h "$FAISS_INDEX_PATH" | cut -f1)"
echo "  Metadata: $(du -h "$METADATA_PATH" | cut -f1)"

# System information
echo "System Resources:"
echo "  CPUs: $NSLOTS"
echo "  Memory: $(free -h | grep Mem | awk '{print $2}')"

# Run migration
echo "Starting migration process..."
python "$MIGRATION_SCRIPT" \
    --index "$FAISS_INDEX_PATH" \
    --metadata "$METADATA_PATH" \
    --collection "$COLLECTION_NAME" \
    --qdrant-url "$QDRANT_URL" \
    --batch-size "$BATCH_SIZE" \
    --resume

# Verify migration success
echo "Verifying migration..."
COLLECTION_INFO=$(curl -s "$QDRANT_URL/collections/$COLLECTION_NAME" | python -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Points: {data['result']['points_count']:,}\")
print(f\"Status: {data['result']['status']}\")
")

echo "Migration completed successfully!"
echo "Collection '$COLLECTION_NAME' information:"
echo "$COLLECTION_INFO"

echo "Migration job finished: $(date)"