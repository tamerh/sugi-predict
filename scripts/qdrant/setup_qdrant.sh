#!/bin/bash
# Setup script for Qdrant on HPC cluster

set -e

echo "=== BioYoda Qdrant Setup ==="
echo "Setting up Qdrant vector database for HPC cluster"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Script directory: $SCRIPT_DIR"

# Step 1: Install Python dependencies
echo "Step 1: Installing Python dependencies..."
source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
pip install qdrant-client

# Step 2: Create data directory
echo "Step 2: Creating data directory..."
QDRANT_DATA_DIR="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/qdrant"
mkdir -p "$QDRANT_DATA_DIR"
echo "Created: $QDRANT_DATA_DIR"

# Step 3: Build Singularity container
echo "Step 3: Building Singularity container..."
cd "$SCRIPT_DIR/setup"
if [ ! -f "singularity/qdrant.sif" ]; then
    echo "Submitting container build job..."
    qsub build_container.sh
    echo "Container build job submitted. Check 'qstat' for progress."
    echo "Wait for build to complete before proceeding to next steps."
else
    echo "Container already exists: singularity/qdrant.sif"
fi

echo ""
echo "=== Setup Instructions ==="
echo "1. Wait for container build to complete (if submitted)"
echo "2. Start Qdrant server:"
echo "   cd $SCRIPT_DIR"
echo "   qsub jobs/run_qdrant_server.sh"
echo ""
echo "3. Run migration (after server is running):"
echo "   qsub jobs/run_migration.sh"
echo ""
echo "4. Check job status with: qstat"
echo "5. View logs in the script directory"
echo ""
echo "=== Next Steps ==="
echo "- The Qdrant server will run on a cluster node"
echo "- Connection info will be saved to connection_info.txt"
echo "- Migration will import your FAISS data to Qdrant"
echo "- You can then build new search interfaces using the Qdrant API"