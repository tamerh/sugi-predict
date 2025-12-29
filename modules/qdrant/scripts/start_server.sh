#!/bin/bash
#
# Start Qdrant Server Script
# Runs Qdrant in local mode using Singularity/Apptainer container
#
set -euo pipefail

# Parse arguments
CONTAINER=""
CONFIG_FILE=""
STORAGE=""
MEMORY_MB=""
RUNTIME=""
JOB_NAME=""
MODE=""
CONNECTION_INFO=""
LOG_FILE=""
QUEUE="scc"
OUT_DIR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --container) CONTAINER="$2"; shift 2 ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        --storage) STORAGE="$2"; shift 2 ;;
        --memory-mb) MEMORY_MB="$2"; shift 2 ;;
        --runtime) RUNTIME="$2"; shift 2 ;;
        --job-name) JOB_NAME="$2"; shift 2 ;;
        --mode) MODE="$2"; shift 2 ;;
        --connection-info) CONNECTION_INFO="$2"; shift 2 ;;
        --log) LOG_FILE="$2"; shift 2 ;;
        --queue) QUEUE="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check if container exists
if [ ! -f "$CONTAINER" ]; then
    echo "ERROR: Qdrant container not found at $CONTAINER"
    echo "Please build it first"
    exit 1
fi

# Storage directory setup
if [ -n "$OUT_DIR" ]; then
    echo "Using Qdrant storage: $OUT_DIR"

    # Ensure directory structure exists
    if [ ! -d "$OUT_DIR/storage" ]; then
        echo "Creating storage directory: $OUT_DIR/storage"
        mkdir -p "$OUT_DIR/storage"
    fi

    if [ ! -d "$OUT_DIR/snapshots" ]; then
        echo "Creating snapshots directory: $OUT_DIR/snapshots"
        mkdir -p "$OUT_DIR/snapshots"
    fi

    ACTUAL_STORAGE="$OUT_DIR/storage"
    SNAPSHOTS_DIR="$OUT_DIR/snapshots"

    echo "  Storage: $ACTUAL_STORAGE"
    echo "  Snapshots: $SNAPSHOTS_DIR"
else
    # Fallback to --storage parameter
    echo "Using storage directory: $STORAGE"
    ACTUAL_STORAGE="$STORAGE"
    SNAPSHOTS_DIR="$(dirname "$STORAGE")/snapshots"
    mkdir -p "$ACTUAL_STORAGE"
    mkdir -p "$SNAPSHOTS_DIR"
fi

echo "Starting Qdrant server in $MODE mode..."

if [ "$MODE" = "local" ]; then
    # ====== LOCAL MODE: Start in background ======

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Qdrant server locally..." | tee "$LOG_FILE"

    # Set variables
    QDRANT_HOST="localhost"
    QDRANT_PORT=6333

    # Create connection info file
    cat > "$CONNECTION_INFO" <<EOF
# Qdrant Connection Information (Local Mode)
# Generated: $(date)
QDRANT_HOST=$QDRANT_HOST
QDRANT_PORT=$QDRANT_PORT
QDRANT_URL=http://$QDRANT_HOST:$QDRANT_PORT
QDRANT_STORAGE=$ACTUAL_STORAGE
EOF

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Connection info: $CONNECTION_INFO" | tee -a "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Server URL: http://$QDRANT_HOST:$QDRANT_PORT" | tee -a "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Storage: $ACTUAL_STORAGE" | tee -a "$LOG_FILE"

    # Start Qdrant in background
    singularity run \
        --contain \
        --pwd /qdrant \
        --bind "$ACTUAL_STORAGE:/qdrant/storage" \
        --bind "$SNAPSHOTS_DIR:/qdrant/snapshots" \
        --bind "$CONFIG_FILE:/opt/qdrant/config.yaml" \
        "$CONTAINER" \
        --config-path /opt/qdrant/config.yaml \
        >> "$LOG_FILE" 2>&1 &

    QDRANT_PID=$!
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Qdrant server started (PID: $QDRANT_PID)" | tee -a "$LOG_FILE"

    # Save PID for cleanup
    echo $QDRANT_PID > "$OUT_DIR/qdrant.pid"

    # Wait for server to be ready
    echo "Waiting for Qdrant to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:6333/health > /dev/null 2>&1; then
            echo "Qdrant server is ready!"
            exit 0
        fi
        echo "  Waiting... ($i/30)"
        sleep 2
    done

    echo "WARNING: Qdrant may not be fully ready yet, but continuing..."
    echo "Check logs: $LOG_FILE"
else
    echo "ERROR: Only local mode is supported. Use --mode local"
    exit 1
fi
