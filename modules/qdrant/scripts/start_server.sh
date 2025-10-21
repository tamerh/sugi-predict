#!/bin/bash
#
# Start Qdrant Server Script
# Can run in local mode or cluster mode (SGE job)
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
SCRATCH_BASE=""             # Base path for local scratch (if set, use production mode)

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
        --scratch-base) SCRATCH_BASE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check if container exists
if [ ! -f "$CONTAINER" ]; then
    echo "ERROR: Qdrant container not found at $CONTAINER"
    echo "Please build it first"
    exit 1
fi

# Auto-detect storage mode based on whether scratch_base is provided
if [ -n "$SCRATCH_BASE" ]; then
    # Production mode: Use local scratch with hostname_date pattern
    STORAGE_MODE="production"
    HOSTNAME=$(hostname)
    DATE=$(date '+%Y%m%d')
    SCRATCH_DIR="${SCRATCH_BASE}/qdrant_${HOSTNAME}_${DATE}"

    echo "Production mode: Using local scratch storage (10-60x faster!)"
    echo "  Base: $SCRATCH_BASE"
    echo "  Storage directory: $SCRATCH_DIR"

    # Create scratch directory structure
    mkdir -p "$SCRATCH_DIR/storage"
    mkdir -p "$SCRATCH_DIR/snapshots"

    # Create deployment info file
    cat > "$SCRATCH_DIR/DEPLOYMENT_INFO.txt" <<EOF
Qdrant Deployment Information
==============================
Hostname: $HOSTNAME
Date: $(date '+%Y-%m-%d %H:%M:%S')
Storage Directory: $SCRATCH_DIR
Storage Mode: production (local scratch - 10-60x faster than NFS!)
NOTE: This is node-specific storage. Data is NOT accessible from other nodes.
      To access this data, connect to: $HOSTNAME
EOF

    # Override STORAGE to point to scratch directory
    ACTUAL_STORAGE="$SCRATCH_DIR/storage"
    SNAPSHOTS_DIR="$SCRATCH_DIR/snapshots"

    echo "  Created: $SCRATCH_DIR/DEPLOYMENT_INFO.txt"
else
    # Development/Test mode: Use NFS storage (accessible from all nodes)
    STORAGE_MODE="development"
    echo "Development mode: Using NFS storage (accessible from all nodes)"
    echo "  Storage directory: $STORAGE"
    ACTUAL_STORAGE="$STORAGE"
    SNAPSHOTS_DIR="$(dirname "$STORAGE")/snapshots"
    mkdir -p "$SNAPSHOTS_DIR"
fi

echo "Starting Qdrant server in $MODE mode..."

if [ "$MODE" = "cluster" ]; then
    # ====== CLUSTER MODE: Submit as job ======

    # Create job script (use original NFS STORAGE for scripts, not scratch)
    mkdir -p "$STORAGE"
    cat > "$STORAGE/start_server_job.sh" <<JOBSCRIPT
#!/bin/bash
#$ -N $JOB_NAME
#$ -q $QUEUE
#$ -l h_vmem=${MEMORY_MB}M
#$ -l h_rt=$RUNTIME
#$ -cwd
#$ -V
#$ -o $LOG_FILE
#$ -j y

set -e

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Qdrant server..."
echo "Job ID: \$JOB_ID"
echo "Hostname: \$(hostname)"

# Set variables
QDRANT_HOST=\$(hostname)
QDRANT_PORT=6333

# Auto-detect storage mode based on whether scratch_base is provided
SCRATCH_BASE="$SCRATCH_BASE"
if [ -n "\$SCRATCH_BASE" ]; then
    # Production mode: Use local scratch
    STORAGE_MODE="production"
    DATE=\$(date '+%Y%m%d')
    SCRATCH_DIR="\${SCRATCH_BASE}/qdrant_\${QDRANT_HOST}_\${DATE}"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Production mode: Using local scratch (10-60x faster!)"
    echo "  Storage directory: \$SCRATCH_DIR"

    # Create scratch directory structure
    mkdir -p "\$SCRATCH_DIR/storage"
    mkdir -p "\$SCRATCH_DIR/snapshots"

    # Create deployment info file
    cat > "\$SCRATCH_DIR/DEPLOYMENT_INFO.txt" <<INFOEOF
Qdrant Deployment Information
==============================
Job ID: \$JOB_ID
Hostname: \$QDRANT_HOST
Date: \$(date '+%Y-%m-%d %H:%M:%S')
Storage Directory: \$SCRATCH_DIR
Storage Mode: production (local scratch - 10-60x faster than NFS!)
NOTE: This is node-specific storage. Data is NOT accessible from other nodes.
      To access this data, connect to: \$QDRANT_HOST
INFOEOF

    ACTUAL_STORAGE="\$SCRATCH_DIR/storage"
    SNAPSHOTS_DIR="\$SCRATCH_DIR/snapshots"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Created: \$SCRATCH_DIR/DEPLOYMENT_INFO.txt"
else
    # Development/Test mode: Use NFS storage
    STORAGE_MODE="development"
    ACTUAL_STORAGE="$ACTUAL_STORAGE"
    SNAPSHOTS_DIR="$SNAPSHOTS_DIR"
fi

# Create connection info file
cat > $CONNECTION_INFO <<EOF
# Qdrant Connection Information
# Generated: \$(date)
# Job ID: \$JOB_ID
QDRANT_HOST=\$QDRANT_HOST
QDRANT_PORT=\$QDRANT_PORT
QDRANT_URL=http://\$QDRANT_HOST:\$QDRANT_PORT
QDRANT_STORAGE=\$ACTUAL_STORAGE
QDRANT_STORAGE_MODE=\$STORAGE_MODE
EOF

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Connection info: $CONNECTION_INFO"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Server URL: http://\$QDRANT_HOST:\$QDRANT_PORT"

# Cleanup on exit
cleanup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Shutting down Qdrant server..."
    rm -f $CONNECTION_INFO
}
trap cleanup EXIT

# Start Qdrant
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Singularity container..."
echo "  Storage: \$ACTUAL_STORAGE"
echo "  Snapshots: \$SNAPSHOTS_DIR"

singularity run \\
    --contain \\
    --pwd /qdrant \\
    --bind "\$ACTUAL_STORAGE:/qdrant/storage" \\
    --bind "\$SNAPSHOTS_DIR:/qdrant/snapshots" \\
    --bind $CONFIG_FILE:/opt/qdrant/config.yaml \\
    $CONTAINER \\
    --config-path /opt/qdrant/config.yaml

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Qdrant server stopped"
JOBSCRIPT

    chmod +x "$STORAGE/start_server_job.sh"

    # Check if a job is already running or waiting
    EXISTING_JOB=$(qstat -u $(whoami) 2>/dev/null | grep "$JOB_NAME" | awk '{print $1}' | head -1 || true)

    if [ -n "$EXISTING_JOB" ]; then
        echo "Qdrant server job already exists: $EXISTING_JOB"
        echo "Job status:"
        qstat -j $EXISTING_JOB 2>/dev/null | grep -E "(job_number|state)" || true

        # If connection info already exists, we're done
        if [ -f "$CONNECTION_INFO" ]; then
            echo "Connection info already exists, server is running"
            cat "$CONNECTION_INFO"
            exit 0
        fi

        echo "Waiting for job $EXISTING_JOB to start and create connection info..."
    else
        # Submit the job
        echo "Submitting Qdrant server job..."
        JOB_ID=$(qsub "$STORAGE/start_server_job.sh" | grep -oE '[0-9]+')
        echo "Submitted job: $JOB_ID"
    fi

    # Wait for connection_info.txt to appear (max 30 minutes for job to start + server to initialize)
    echo "Waiting for Qdrant server to start (this may take a while if job is queued)..."
    for i in {1..360}; do
        if [ -f "$CONNECTION_INFO" ]; then
            echo "Qdrant server started successfully!"
            cat "$CONNECTION_INFO"
            sleep 10  # Give it a bit more time to fully initialize
            exit 0
        fi
        if [ $((i % 12)) -eq 0 ]; then
            echo "  Still waiting... ($((i/12)) minutes elapsed)"
        fi
        sleep 5
    done

    echo "ERROR: Qdrant server did not start within 30 minutes"
    echo "Check logs: $LOG_FILE"
    echo "Check job status with: qstat -u $(whoami)"
    exit 1

else
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
QDRANT_STORAGE_MODE=$STORAGE_MODE
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
    echo $QDRANT_PID > "$STORAGE/qdrant.pid"

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
fi
