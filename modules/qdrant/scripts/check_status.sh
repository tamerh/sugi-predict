#!/bin/bash

##############################################################################
#
#   Check Qdrant Server Status
#   Reports on server status, collections, and data
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
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================"
echo "Qdrant Server Status"
echo "========================================"
echo ""

# Check if server is running
SERVER_RUNNING=false
QDRANT_URL=""

# Check local PID
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Local server running (PID: $PID)${NC}"
        SERVER_RUNNING=true
    else
        echo -e "${YELLOW}⚠ Stale PID file found (process not running)${NC}"
    fi
else
    echo -e "${YELLOW}✗ No local PID file${NC}"
fi

# Check cluster job
if command -v qstat &> /dev/null; then
    QDRANT_JOBS=$(qstat -u $(whoami) 2>/dev/null | grep "$JOB_NAME" | awk '{print $1, $5}' || true)

    if [ -n "$QDRANT_JOBS" ]; then
        echo -e "${GREEN}✓ Cluster job(s) found:${NC}"
        echo "$QDRANT_JOBS" | while read JOB_ID STATE; do
            if [ "$STATE" = "r" ]; then
                echo -e "  Job $JOB_ID: ${GREEN}running${NC}"
                SERVER_RUNNING=true
            elif [ "$STATE" = "qw" ]; then
                echo -e "  Job $JOB_ID: ${YELLOW}queued (waiting)${NC}"
            else
                echo -e "  Job $JOB_ID: $STATE"
            fi
        done
    else
        echo -e "${YELLOW}✗ No cluster jobs found${NC}"
    fi
fi

echo ""
echo "========================================"
echo "Connection Info"
echo "========================================"
echo ""

# Check connection info
if [ -f "$CONNECTION_INFO" ]; then
    echo -e "${GREEN}✓ Connection info file exists${NC}"
    echo ""
    cat "$CONNECTION_INFO"
    echo ""

    # Extract URL
    source "$CONNECTION_INFO"

    if [ -n "$QDRANT_URL" ]; then
        echo "Testing connection to $QDRANT_URL..."

        # Try to connect to Qdrant API
        if command -v curl &> /dev/null; then
            if curl -s --max-time 5 "$QDRANT_URL" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ Server is responding${NC}"

                # Get collections info
                echo ""
                echo "========================================"
                echo "Collections"
                echo "========================================"
                echo ""

                COLLECTIONS=$(curl -s --max-time 5 "$QDRANT_URL/collections" 2>/dev/null || echo "")

                if [ -n "$COLLECTIONS" ]; then
                    echo "$COLLECTIONS" | python3 -m json.tool 2>/dev/null || echo "$COLLECTIONS"
                else
                    echo -e "${YELLOW}Could not retrieve collections${NC}"
                fi
            else
                echo -e "${RED}✗ Server not responding${NC}"
            fi
        else
            echo -e "${YELLOW}⚠ curl not available, cannot test connection${NC}"
        fi
    fi
else
    echo -e "${RED}✗ No connection info file${NC}"
    echo "Server may not be started yet"
fi

echo ""
echo "========================================"
echo "Storage Info"
echo "========================================"
echo ""

if [ -d "${STORAGE}/storage" ]; then
    STORAGE_SIZE=$(du -sh "${STORAGE}/storage" 2>/dev/null | cut -f1)
    echo "Storage directory: ${STORAGE}/storage"
    echo "Size: ${STORAGE_SIZE}"
else
    echo -e "${YELLOW}No storage directory found${NC}"
fi

echo ""
echo "========================================"
echo "Collection Markers"
echo "========================================"
echo ""

if [ -d "${STORAGE}/collections" ]; then
    MARKERS=$(ls -1 "${STORAGE}/collections"/*.done 2>/dev/null || true)
    if [ -n "$MARKERS" ]; then
        for MARKER in $MARKERS; do
            COLLECTION=$(basename "$MARKER" .done)
            echo -e "${GREEN}✓ $COLLECTION${NC}"
            if [ -f "$MARKER" ]; then
                echo "  $(head -n 1 "$MARKER")"
            fi
        done
    else
        echo -e "${YELLOW}No insertion markers found${NC}"
    fi
else
    echo -e "${YELLOW}No collections directory${NC}"
fi

echo ""
echo "========================================"
