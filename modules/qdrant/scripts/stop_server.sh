#!/bin/bash

##############################################################################
#
#   Stop Qdrant Server
#   Stops both local and cluster-based Qdrant servers
#
##############################################################################

set -e

# Default paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Use environment variable if set, otherwise default to PROJECT_ROOT
if [ -n "$QDRANT_STORAGE_PATH" ]; then
    STORAGE="$QDRANT_STORAGE_PATH"
else
    STORAGE="${PROJECT_ROOT}/out/data/qdrant"
fi

PID_FILE="${STORAGE}/qdrant.pid"
CONNECTION_INFO="${STORAGE}/connection_info.txt"
JOB_NAME="q_server"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Stopping Qdrant Server"
echo "========================================"

FOUND_SOMETHING=false

# Check for local PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo -e "${YELLOW}Found local PID file: $PID${NC}"

    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping Qdrant server (PID: $PID)..."
        kill $PID 2>/dev/null || true
        sleep 2

        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            echo "Force killing..."
            kill -9 $PID 2>/dev/null || true
        fi

        echo -e "${GREEN}✓ Qdrant server stopped${NC}"
        FOUND_SOMETHING=true
    else
        echo -e "${YELLOW}Process $PID not running (stale PID file)${NC}"
    fi

    rm -f "$PID_FILE"
fi

# Check for cluster job
if command -v qstat &> /dev/null; then
    QDRANT_JOBS=$(qstat -u $(whoami) 2>/dev/null | grep "$JOB_NAME" | awk '{print $1}' || true)

    if [ -n "$QDRANT_JOBS" ]; then
        echo -e "${YELLOW}Found Qdrant cluster job(s)${NC}"
        for JOB_ID in $QDRANT_JOBS; do
            echo "Cancelling job: $JOB_ID"
            qdel $JOB_ID 2>/dev/null || true
        done
        echo -e "${GREEN}✓ Qdrant cluster job(s) cancelled${NC}"
        FOUND_SOMETHING=true
    fi
fi

# Clean up connection info
if [ -f "$CONNECTION_INFO" ]; then
    rm -f "$CONNECTION_INFO"
    echo "✓ Removed connection info file"
    FOUND_SOMETHING=true
fi

# Clean up .qdrant-initialized marker if exists
if [ -f "${PROJECT_ROOT}/.qdrant-initialized" ]; then
    rm -f "${PROJECT_ROOT}/.qdrant-initialized"
fi

if [ "$FOUND_SOMETHING" = false ]; then
    echo -e "${YELLOW}No running Qdrant server found${NC}"
else
    echo ""
    echo -e "${GREEN}Qdrant server stopped successfully${NC}"
fi

echo "========================================"
