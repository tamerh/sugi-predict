#!/bin/bash
#$ -N qdser
#$ -q scc
#$ -l h_vmem=64G
#$ -l h_rt=24:00:00
#$ -cwd
#$ -V
#$ -pe smp 2

# Run Qdrant server using Singularity container
# This script starts a long-running Qdrant server on the HPC cluster

set -e

echo "Starting Qdrant server..."
echo "Job ID: $JOB_ID"
echo "Hostname: $(hostname)"
echo "Timestamp: $(date)"

# Configuration
CONTAINER_PATH="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/setup/singularity/qdrant.sif"
STORAGE_PATH="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/qdrant"
CONFIG_PATH="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/setup/singularity/config.yaml"

# Create storage directory if it doesn't exist
mkdir -p "$STORAGE_PATH"

# Check if container exists
if [ ! -f "$CONTAINER_PATH" ]; then
    echo "ERROR: Qdrant container not found at $CONTAINER_PATH"
    echo "Please build the container first using build_container.sh"
    exit 1
fi

# Display system information
echo "System Information:"
echo "  CPUs: $NSLOTS"
echo "  Memory: $(free -h | grep Mem | awk '{print $2}')"
echo "  Storage: $STORAGE_PATH"
echo "  Container: $CONTAINER_PATH"

# Set up port forwarding information
QDRANT_HOST=$(hostname)
QDRANT_HTTP_PORT=6333
QDRANT_GRPC_PORT=6334

echo "Qdrant will be accessible at:"
echo "  HTTP API: http://$QDRANT_HOST:$QDRANT_HTTP_PORT"
echo "  gRPC API: $QDRANT_HOST:$QDRANT_GRPC_PORT"

# Create a connection info file for other scripts
cat > "/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/connection_info.txt" <<EOF
# Qdrant Connection Information
# Generated: $(date)
# Job ID: $JOB_ID
QDRANT_HOST=$QDRANT_HOST
QDRANT_HTTP_PORT=$QDRANT_HTTP_PORT
QDRANT_GRPC_PORT=$QDRANT_GRPC_PORT
QDRANT_URL=http://$QDRANT_HOST:$QDRANT_HTTP_PORT
EOF

echo "Connection info saved to connection_info.txt"

# Trap to cleanup on exit
cleanup() {
    echo "Shutting down Qdrant server..."
    rm -f "/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant/connection_info.txt"
}
trap cleanup EXIT

# Start Qdrant server
echo "Starting Qdrant server with Singularity..."
singularity run \
    --bind "$STORAGE_PATH:/qdrant/storage" \
    --bind "$CONFIG_PATH:/opt/qdrant/config.yaml" \
    "$CONTAINER_PATH" \
    --config-path /opt/qdrant/config.yaml

echo "Qdrant server stopped."