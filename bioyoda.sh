#!/bin/bash
##############################################################################
# BioYoda - Minimal Pipeline Orchestrator
##############################################################################

set -euo pipefail

# Load configuration
source "$(dirname "$0")/bioyoda.env"

# Simple logging
log() { echo "[$(date '+%H:%M:%S')] $1"; }
error() { echo "[ERROR] $1" >&2; exit 1; }

# Usage
usage() {
    echo "Usage: $0 <command> [--debug]"
    echo "Commands: setup, download, process, merge, api, status"
    echo "Options: --debug (process only $DEBUG_SAMPLE_SIZE files)"
}

# Setup directories
setup() {
    log "Setting up directories..."
    mkdir -p "$PROJECT_ROOT/$LOGS_DIR"
    mkdir -p "$PROJECT_ROOT/$RAW_PUBMED_DIR"/{baseline,updatefiles}
    mkdir -p "$PROJECT_ROOT/$PROCESSED_PUBMED_DIR"/{baseline,updatefiles}
    mkdir -p "$PROJECT_ROOT/$FINAL_PUBMED_DIR"
    log "Setup complete"
}

# Download and create file list
download() {
    log "Starting download phase..."
    cd "$PROJECT_ROOT/scripts/pubmed"

    # Add config loading to data_download.py and run it
    python data_download.py

    # Create file list
    ./create_file_list.sh

    log "Download phase complete"
}

# Process files
process() {
    local debug_mode="$1"
    log "Starting processing phase..."
    cd "$PROJECT_ROOT/scripts/pubmed"

    # Get file count
    local total_files=$(wc -l < pubmed_files.txt)
    local num_tasks=$total_files

    if [[ "$debug_mode" == "true" ]]; then
        num_tasks=$DEBUG_SAMPLE_SIZE
        log "Debug mode: processing $num_tasks files out of $total_files"
    fi

    # Submit job array directly here
    log "Submitting $num_tasks processing jobs..."

    qsub -r y -q "$CLUSTER_QUEUE" \
         -l h_vmem="$PUBMED_MEMORY_PER_JOB" \
         -l h_rt="$DEFAULT_RUNTIME" \
         -o "$PROJECT_ROOT/$LOGS_DIR/pubmed_process.\$JOB_ID.\$TASK_ID.out" \
         -e "$PROJECT_ROOT/$LOGS_DIR/pubmed_process.\$JOB_ID.\$TASK_ID.err" \
         -t 1-${num_tasks} \
         run_job.sh

    # Wait for jobs
    log "Waiting for processing jobs..."
    while qstat -u "$USER" 2>/dev/null | grep -q pubmed_process; do
        sleep 30
    done

    log "Processing complete"
}

# Merge indices
merge() {
    log "Starting merge phase..."
    cd "$PROJECT_ROOT/scripts/pubmed"

    # Submit merge job
    qsub -N bioyoda_merge \
         -cwd -j y -V -S /bin/bash \
         -l h_vmem="$PUBMED_MERGE_MEMORY" \
         -l h_rt="$LARGE_RUNTIME" \
         -q "$CLUSTER_QUEUE" \
         -o "$PROJECT_ROOT/$LOGS_DIR/merge_\$JOB_ID.log" \
         << EOF
#!/bin/bash
eval "\$(conda shell.bash hook)"
conda activate $CONDA_ENV
python $PUBMED_MERGE_METHOD.py
EOF

    # Wait for merge
    log "Waiting for merge job..."
    while qstat -u "$USER" 2>/dev/null | grep -q bioyoda_merge; do
        sleep 30
    done

    log "Merge complete"
}

# Start API
api() {
    log "Starting API server..."
    cd "$PROJECT_ROOT/scripts/pubmed"
    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV"
    python -m uvicorn api:app --host "$API_HOST" --port "$API_PORT"
}

# Check status
status() {
    echo "BioYoda Status"
    echo "=============="
    echo "Environment: $ENVIRONMENT"

    # Count files
    raw_count=$(find "$PROJECT_ROOT/$RAW_PUBMED_DIR" -name "*.xml.gz" 2>/dev/null | wc -l)
    processed_count=$(find "$PROJECT_ROOT/$PROCESSED_PUBMED_DIR" -name "*.index" 2>/dev/null | wc -l)
    final_count=$(find "$PROJECT_ROOT/$FINAL_PUBMED_DIR" -name "*.index" 2>/dev/null | wc -l)

    echo "Raw files: $raw_count"
    echo "Processed: $processed_count"
    echo "Final indices: $final_count"

    # Running jobs
    if command -v qstat &> /dev/null; then
        running=$(qstat -u "$USER" 2>/dev/null | grep -c bioyoda || true)
        echo "Running jobs: $running"
    fi
}

# Parse arguments
DEBUG_MODE="false"
COMMAND=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug) DEBUG_MODE="true"; shift ;;
        setup|download|process|merge|api|status) COMMAND="$1"; shift ;;
        *) usage; exit 1 ;;
    esac
done

# Execute command
case "$COMMAND" in
    setup) setup ;;
    download) download ;;
    process) process "$DEBUG_MODE" ;;
    merge) merge ;;
    api) api ;;
    status) status ;;
    *) usage ;;
esac