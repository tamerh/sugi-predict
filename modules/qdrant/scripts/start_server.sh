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
MOCK_CGROUPS="auto"         # auto, true, or false
OUT_DIR=""                  # Existing storage directory to use (restart mode)

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
        --mock-cgroups) MOCK_CGROUPS="true"; shift ;;
        --no-mock-cgroups) MOCK_CGROUPS="false"; shift ;;
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

# Storage mode detection
# Priority: 1. Restart mode (--out-dir), 2. Production mode (--scratch-base), 3. Development mode
if [ -n "$OUT_DIR" ]; then
    # ====== RESTART MODE: Use existing storage directory ======
    STORAGE_MODE="restart"

    echo "Restart mode: Using existing Qdrant storage"
    echo "  Storage directory: $OUT_DIR"

    # Verify structure
    if [ ! -d "$OUT_DIR/storage" ]; then
        echo "ERROR: Invalid storage directory structure - missing storage/ subdirectory"
        echo "Expected: $OUT_DIR/storage/"
        exit 1
    fi

    if [ ! -d "$OUT_DIR/snapshots" ]; then
        echo "ERROR: Invalid storage directory structure - missing snapshots/ subdirectory"
        echo "Expected: $OUT_DIR/snapshots/"
        exit 1
    fi

    # Set storage paths to existing directories (no mkdir!)
    ACTUAL_STORAGE="$OUT_DIR/storage"
    SNAPSHOTS_DIR="$OUT_DIR/snapshots"

    echo "  Verified: $ACTUAL_STORAGE"
    echo "  Verified: $SNAPSHOTS_DIR"

    # Check if there's a DEPLOYMENT_INFO.txt
    if [ -f "$OUT_DIR/DEPLOYMENT_INFO.txt" ]; then
        echo ""
        echo "Original deployment info:"
        cat "$OUT_DIR/DEPLOYMENT_INFO.txt" | sed 's/^/  /'
        echo ""
    fi

elif [ -n "$SCRATCH_BASE" ]; then
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

# ==============================================================================
# Mock cgroups setup (workaround for cgroups panic in Singularity/SGE)
# ==============================================================================
MOCK_CGROUPS_DIR=""
MOCK_CGROUPS_BIND=""

# Auto-detect: Enable mock cgroups for Singularity containers (file extension .sif)
if [ "$MOCK_CGROUPS" = "auto" ]; then
    if [[ "$CONTAINER" =~ \.sif$ ]]; then
        MOCK_CGROUPS="true"
        echo "Mock cgroups: auto-enabled (Singularity container detected)"
    else
        MOCK_CGROUPS="false"
        echo "Mock cgroups: auto-disabled (not a Singularity container)"
    fi
fi

if [ "$MOCK_CGROUPS" = "true" ]; then
    echo "================================================================================"
    echo "Mock cgroups workaround: ENABLED"
    echo "================================================================================"
    echo "This creates fake cgroup files to fix the cgroups panic in Singularity/SGE."
    echo "Qdrant will read memory limits from these mock files instead of real cgroups."
    echo ""

    # Create temporary directory for mock cgroups
    MOCK_CGROUPS_DIR="/tmp/qdrant_mock_cgroups_$$"
    mkdir -p "$MOCK_CGROUPS_DIR"

    # Get system memory to calculate realistic values
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MEM_BYTES=$((TOTAL_MEM_KB * 1024))

    # Set limits: 90% of total system memory as max
    MAX_MEM=$((TOTAL_MEM_BYTES * 90 / 100))
    HIGH_MEM=$((TOTAL_MEM_BYTES * 80 / 100))
    CURRENT_MEM=$((TOTAL_MEM_BYTES * 20 / 100))  # Assume 20% currently used

    echo "  System memory: $((TOTAL_MEM_KB / 1024 / 1024)) GB"
    echo "  Mock memory.max: $((MAX_MEM / 1024 / 1024 / 1024)) GB"
    echo "  Mock memory.high: $((HIGH_MEM / 1024 / 1024 / 1024)) GB"
    echo ""

    # Write realistic cgroup v2 memory files
    echo "$MAX_MEM" > "$MOCK_CGROUPS_DIR/memory.max"
    echo "$HIGH_MEM" > "$MOCK_CGROUPS_DIR/memory.high"
    echo "$CURRENT_MEM" > "$MOCK_CGROUPS_DIR/memory.current"
    echo "1073741824" > "$MOCK_CGROUPS_DIR/memory.low"     # 1GB
    echo "0" > "$MOCK_CGROUPS_DIR/memory.min"

    # Create memory.stat file (cgroups v2 format)
    cat > "$MOCK_CGROUPS_DIR/memory.stat" <<'MEMSTAT'
anon 21474836480
file 1073741824
kernel 536870912
slab 268435456
sock 0
shmem 0
file_mapped 0
file_dirty 0
file_writeback 0
anon_thp 0
MEMSTAT

    echo "  Mock cgroup directory: $MOCK_CGROUPS_DIR"
    echo "  Files created:"
    ls -lh "$MOCK_CGROUPS_DIR"
    echo ""
    echo "IMPORTANT: This directory will be automatically cleaned up when the server stops"
    echo "================================================================================"
    echo ""

    # Set bind mount for Singularity
    MOCK_CGROUPS_BIND="--bind $MOCK_CGROUPS_DIR:/sys/fs/cgroup/system.slice/sgeexecd.SCC.service"
else
    echo "Mock cgroups: disabled"
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

# Auto-detect storage mode
# Priority: 1. Restart mode (OUT_DIR), 2. Production mode (SCRATCH_BASE), 3. Development mode
OUT_DIR="$OUT_DIR"
SCRATCH_BASE="$SCRATCH_BASE"

if [ -n "\$OUT_DIR" ]; then
    # Restart mode: Use existing storage
    STORAGE_MODE="restart"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restart mode: Using existing Qdrant storage"
    echo "  Storage directory: \$OUT_DIR"

    # Verify structure
    if [ ! -d "\$OUT_DIR/storage" ] || [ ! -d "\$OUT_DIR/snapshots" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Invalid storage directory structure"
        exit 1
    fi

    ACTUAL_STORAGE="\$OUT_DIR/storage"
    SNAPSHOTS_DIR="\$OUT_DIR/snapshots"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Verified: \$ACTUAL_STORAGE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Verified: \$SNAPSHOTS_DIR"

elif [ -n "\$SCRATCH_BASE" ]; then
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
    # Clean up mock cgroups if created
    if [ -n "\$MOCK_CGROUPS_DIR" ] && [ -d "\$MOCK_CGROUPS_DIR" ]; then
        rm -rf "\$MOCK_CGROUPS_DIR"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaned up mock cgroups: \$MOCK_CGROUPS_DIR"
    fi
}
trap cleanup EXIT

# Mock cgroups setup (if enabled)
MOCK_CGROUPS_ENABLED="$MOCK_CGROUPS"
MOCK_CGROUPS_DIR=""
MOCK_CGROUPS_BIND=""

if [ "\$MOCK_CGROUPS_ENABLED" = "true" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting up mock cgroups..."

    # Create mock cgroups directory
    MOCK_CGROUPS_DIR="/tmp/qdrant_mock_cgroups_\$\$"
    mkdir -p "\$MOCK_CGROUPS_DIR"

    # Get system memory
    TOTAL_MEM_KB=\$(grep MemTotal /proc/meminfo | awk '{print \$2}')
    TOTAL_MEM_BYTES=\$((TOTAL_MEM_KB * 1024))
    MAX_MEM=\$((TOTAL_MEM_BYTES * 90 / 100))
    HIGH_MEM=\$((TOTAL_MEM_BYTES * 80 / 100))
    CURRENT_MEM=\$((TOTAL_MEM_BYTES * 20 / 100))

    # Write mock cgroup files
    echo "\$MAX_MEM" > "\$MOCK_CGROUPS_DIR/memory.max"
    echo "\$HIGH_MEM" > "\$MOCK_CGROUPS_DIR/memory.high"
    echo "\$CURRENT_MEM" > "\$MOCK_CGROUPS_DIR/memory.current"
    echo "1073741824" > "\$MOCK_CGROUPS_DIR/memory.low"
    echo "0" > "\$MOCK_CGROUPS_DIR/memory.min"
    cat > "\$MOCK_CGROUPS_DIR/memory.stat" <<'MEMSTAT'
anon 21474836480
file 1073741824
kernel 536870912
slab 268435456
sock 0
shmem 0
MEMSTAT

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Mock cgroups created: \$MOCK_CGROUPS_DIR"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] System memory: \$((TOTAL_MEM_KB / 1024 / 1024)) GB"

    MOCK_CGROUPS_BIND="--bind \$MOCK_CGROUPS_DIR:/sys/fs/cgroup/system.slice/sgeexecd.SCC.service"
fi

# Start Qdrant
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Singularity container..."
echo "  Storage: \$ACTUAL_STORAGE"
echo "  Snapshots: \$SNAPSHOTS_DIR"
if [ -n "\$MOCK_CGROUPS_BIND" ]; then
    echo "  Mock cgroups: ENABLED"
fi

singularity run \\
    --contain \\
    --pwd /qdrant \\
    --bind "\$ACTUAL_STORAGE:/qdrant/storage" \\
    --bind "\$SNAPSHOTS_DIR:/qdrant/snapshots" \\
    --bind $CONFIG_FILE:/opt/qdrant/config.yaml \\
    \$MOCK_CGROUPS_BIND \\
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

    # Display mock cgroups status
    if [ -n "$MOCK_CGROUPS_BIND" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Mock cgroups: ENABLED" | tee -a "$LOG_FILE"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Mock cgroup directory: $MOCK_CGROUPS_DIR" | tee -a "$LOG_FILE"
    fi

    # Start Qdrant in background
    singularity run \
        --contain \
        --pwd /qdrant \
        --bind "$ACTUAL_STORAGE:/qdrant/storage" \
        --bind "$SNAPSHOTS_DIR:/qdrant/snapshots" \
        --bind "$CONFIG_FILE:/opt/qdrant/config.yaml" \
        $MOCK_CGROUPS_BIND \
        "$CONTAINER" \
        --config-path /opt/qdrant/config.yaml \
        >> "$LOG_FILE" 2>&1 &

    QDRANT_PID=$!
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Qdrant server started (PID: $QDRANT_PID)" | tee -a "$LOG_FILE"

    # Save PID and mock cgroups path for cleanup
    echo $QDRANT_PID > "$STORAGE/qdrant.pid"
    if [ -n "$MOCK_CGROUPS_DIR" ]; then
        echo "$MOCK_CGROUPS_DIR" > "$STORAGE/mock_cgroups.path"
    fi

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
