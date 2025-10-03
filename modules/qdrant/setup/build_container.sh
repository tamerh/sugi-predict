#!/bin/bash
# Build Qdrant Singularity container for HPC cluster
# This is a one-time setup script

set -e

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Building Qdrant Singularity container..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/singularity"

# Build the container
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Building container from qdrant.def..."
singularity build qdrant.sif qdrant.def

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Container built: $(pwd)/qdrant.sif"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Container size: $(du -h qdrant.sif | cut -f1)"

# Test the container
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Testing container..."
singularity exec qdrant.sif /qdrant/qdrant --help

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ Build completed successfully!"
echo ""
echo "Container location: $SCRIPT_DIR/singularity/qdrant.sif"
