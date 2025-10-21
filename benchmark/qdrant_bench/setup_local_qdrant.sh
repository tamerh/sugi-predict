#!/bin/bash
#
# Setup Qdrant on Local Storage
# Uses /localscratch/tgur for fast disk access (not NFS!)
#
# Usage:
#   ./setup_local_qdrant.sh <config_name>
#   config_name: base | balanced | optimized
#

set -e

# Configuration
LOCAL_STORAGE="/localscratch/tgur/qdrant_test"
QDRANT_BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$QDRANT_BENCH_DIR/server_config.yaml"
QDRANT_PORT="${QDRANT_PORT:-6333}"
PROJECT_DIR="$(cd "$QDRANT_BENCH_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "Qdrant Local Storage Setup"
echo "============================================"

# Check if we're on a node with local storage
if [ ! -d "/localscratch/tgur" ]; then
    echo -e "${RED}ERROR: /localscratch/tgur not found!${NC}"
    echo "You must run this on an SGE interactive node with local storage:"
    echo "  qrsh -l h_vmem=64G,h_rt=24:00:00"
    echo "Then /localscratch/\$USER will be available"
    exit 1
fi

# Check config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}ERROR: Config file not found: $CONFIG_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Local storage available${NC}"
echo "  Location: $LOCAL_STORAGE"
echo "  Config: $CONFIG_FILE"

# Create local storage directory
mkdir -p "$LOCAL_STORAGE"
mkdir -p "$LOCAL_STORAGE/storage"
mkdir -p "$LOCAL_STORAGE/logs"
mkdir -p "$LOCAL_STORAGE/snapshots"

# Copy config to local storage
cp "$CONFIG_FILE" "$LOCAL_STORAGE/qdrant_config.yaml"

echo -e "${GREEN}✓ Local storage initialized${NC}"
echo "  Storage dir: $LOCAL_STORAGE/storage"
echo "  Config: $LOCAL_STORAGE/qdrant_config.yaml"

# Check if Qdrant container exists
CONTAINER_PATH="$PROJECT_DIR/modules/qdrant/setup/singularity/qdrant.sif"
if [ ! -f "$CONTAINER_PATH" ]; then
    echo -e "${RED}ERROR: Qdrant container not found: $CONTAINER_PATH${NC}"
    echo "Please build the container first"
    exit 1
fi

# Check if Qdrant is already running
if curl -s "http://localhost:$QDRANT_PORT" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠  Qdrant already running on port $QDRANT_PORT${NC}"
    echo "Stop it first with: ./stop_local_qdrant.sh"
    exit 1
fi

# Start Qdrant with local storage
echo ""
echo "Starting Qdrant server..."
echo "  Port: $QDRANT_PORT"
echo "  Storage: $LOCAL_STORAGE/storage"
echo "  Logs: $LOCAL_STORAGE/logs/qdrant.log"

# Start in background
# Use --contain to prevent auto-binding current directory
# Use --pwd to set working directory inside container
nohup singularity run \
    --contain \
    --pwd /qdrant \
    --bind "$LOCAL_STORAGE/storage:/qdrant/storage" \
    --bind "$LOCAL_STORAGE/snapshots:/qdrant/snapshots" \
    --bind "$LOCAL_STORAGE/qdrant_config.yaml:/qdrant/config/config.yaml" \
    "$CONTAINER_PATH" \
    > "$LOCAL_STORAGE/logs/qdrant.log" 2>&1 &

QDRANT_PID=$!
echo $QDRANT_PID > "$LOCAL_STORAGE/qdrant.pid"

echo -e "${GREEN}✓ Qdrant started (PID: $QDRANT_PID)${NC}"

# Wait for Qdrant to be ready
echo "Waiting for Qdrant to start..."
for i in {1..30}; do
    if curl -s "http://localhost:$QDRANT_PORT" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Qdrant is ready!${NC}"
        echo ""
        echo "Server URL: http://$(hostname):$QDRANT_PORT"
        echo "PID file: $LOCAL_STORAGE/qdrant.pid"
        echo "Logs: tail -f $LOCAL_STORAGE/logs/qdrant.log"
        echo ""
        echo "To stop: ./stop_local_qdrant.sh"
        exit 0
    fi
    sleep 1
done

echo -e "${RED}ERROR: Qdrant failed to start${NC}"
echo "Check logs: tail -f $LOCAL_STORAGE/logs/qdrant.log"
exit 1
