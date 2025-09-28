#!/bin/bash
##############################################################################
# PubMed Processing Pipeline
##############################################################################

set -euo pipefail

# Load configuration
source "$(dirname "$0")/pubmed.env"

# Simple logging
log() { echo "[$(date '+%H:%M:%S')] $1"; }

# Usage
usage() {
    echo "Usage: $0 <command> [--debug] [task_ids...]"
    echo "Commands:"
    echo "  download   - Download PubMed data and create file list"
    echo "  index      - Index XML files to FAISS indices"
    echo "  merge      - Merge all indices into master index"
    echo "  resubmit   - Resubmit stuck/failed indexing jobs"
    echo "  all        - Run complete pipeline (download + index + merge)"
    echo "  status     - Show indexing status"
    echo ""
    echo "Options:"
    echo "  --debug    - Index only $DEBUG_SAMPLE_SIZE files"
    echo ""
    echo "Examples:"
    echo "  $0 resubmit 98 99 100     # Resubmit specific task IDs"
    echo "  $0 resubmit               # Interactive mode to enter task IDs"
}

# Download and create file list
download() {
    log "Starting download phase..."

    # Run data download
    #python download.py

    # Create file list (moved from create_file_list.sh)
    log "Creating file list..."

    local baseline_dir="${BASE_DATA_DIR}/baseline"
    local updatefiles_dir="${BASE_DATA_DIR}/updatefiles"

    mkdir -p "$FINAL_DIR"
    # Clear the file list
    > "$FILE_LIST"

    # Find all .xml.gz files in baseline directory
    if [[ -d "$baseline_dir" ]]; then
        find "$baseline_dir" -name "*.xml.gz" | sort >> "$FILE_LIST"
        local baseline_count=$(find "$baseline_dir" -name "*.xml.gz" | wc -l)
        log "Added $baseline_count baseline files"
    fi

    # Find all .xml.gz files in updatefiles directory
    if [[ -d "$updatefiles_dir" ]]; then
        find "$updatefiles_dir" -name "*.xml.gz" | sort >> "$FILE_LIST"
        local update_count=$(find "$updatefiles_dir" -name "*.xml.gz" | wc -l)
        log "Added $update_count update files"
    fi

    local total_files=$(wc -l < "$FILE_LIST")
    log "Created file list with $total_files total files"

    log "Download complete"
}

# Index files
index() {
    local debug_mode="$1"
    log "Starting indexing phase..."

    # Check if file list exists
    if [[ ! -f "$FILE_LIST" ]]; then
        log "File list not found. Running download first..."
        download
    fi

    # Get total files
    local total_files=$(wc -l < "$FILE_LIST")
    local num_tasks=$total_files

    if [[ "$debug_mode" == "true" ]]; then
        num_tasks=$DEBUG_SAMPLE_SIZE
        log "Debug mode: indexing $num_tasks files out of $total_files"
    else
        log "Indexing all $total_files files"
    fi

    # Create log directory
    mkdir -p "$LOG_DIR"
    mkdir -p "${LOG_DIR}/index"
    # Submit job array (same as submit_jobs.sh)
    log "Submitting job array with $num_tasks tasks..."

    qsub -r y -q "$CLUSTER_QUEUE" \
         -l h_vmem="$PROCESS_MEMORY" \
         -l h_rt="$PROCESS_RUNTIME" \
         -o "${LOG_DIR}/index/index.\$JOB_ID.\$TASK_ID.out" \
         -e "${LOG_DIR}/index/index.\$JOB_ID.\$TASK_ID.err" \
         -t 1-${num_tasks} \
         run_index.sh

    log "Jobs submitted. Monitor with: qstat -u $USER"
}

# Wait for indexing jobs to complete
wait_indexing() {
    log "Waiting for indexing jobs to complete..."

    while qstat -u "$USER" 2>/dev/null | grep -q "pubmed_process"; do
        local running_jobs=$(qstat -u "$USER" 2>/dev/null | grep "pubmed_process" | wc -l)
        log "Waiting... $running_jobs jobs still running"
        sleep 30
    done

    log "All indexing jobs completed"
}

# Merge indices
merge() {
    log "Starting merge phase..."

    # Check if we have indexed files
    local indexed_count=$(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | wc -l)
    if [[ $indexed_count -eq 0 ]]; then
        log "No indexed files found. Run indexing first."
        return 1
    fi

    log "Found $indexed_count indexed files"

    # Create merge log directory
    local merge_log_dir="${LOG_DIR}/pubmed/merge"
    mkdir -p "$merge_log_dir"

    # Submit merge job (same style as submit_merge.sh)
    log "Submitting merge job..."

    qsub -r y -q "$CLUSTER_QUEUE" -N merge_bioyoda \
         -l h_vmem="$MERGE_MEMORY" \
         -l h_rt="$MERGE_RUNTIME" \
         -o "${merge_log_dir}/pubmed_merge_process.\$JOB_ID.\$TASK_ID.out" \
         -e "${merge_log_dir}/pubmed_merge_process.\$JOB_ID.\$TASK_ID.err" \
         run_merge.sh

    log "Merge job submitted"
}

# Resubmit stuck/failed jobs
resubmit() {
    local task_ids="$*"

    log "Starting resubmission of stuck/failed jobs..."

    # If no task IDs provided, ask for input
    if [[ -z "$task_ids" ]]; then
        echo "Enter task IDs to resubmit (space-separated): "
        read -r task_ids

        if [[ -z "$task_ids" ]]; then
            log "No task IDs provided. Exiting."
            return 1
        fi
    fi

    log "Resubmitting task IDs: $task_ids"

    # Create log directory
    mkdir -p "$LOG_DIR"

    # Resubmit each task ID
    for task_id in $task_ids; do
        log "Resubmitting task ID: $task_id"

        qsub -r y -q "$CLUSTER_QUEUE" \
             -l h_vmem="$PROCESS_MEMORY" \
             -l h_rt="$PROCESS_RUNTIME" \
             -o "${LOG_DIR}/pubmed_process.\$JOB_ID.${task_id}.out" \
             -e "${LOG_DIR}/pubmed_process.\$JOB_ID.${task_id}.err" \
             -t "$task_id" \
             run_job.sh
    done

    log "All stuck jobs have been resubmitted"
    log "Monitor with: qstat -u $USER"
}

# Wait for merge to complete
wait_merge() {
    log "Waiting for merge to complete..."

    while qstat -u "$USER" 2>/dev/null | grep -q "pubmed_merge"; do
        log "Merge job still running..."
        sleep 30
    done

    log "Merge completed"

    # Check if outputs were created
    local final_index="${FINAL_DIR}/master_pubmed_${MERGE_METHOD}.index"
    local final_metadata="${FINAL_DIR}/master_metadata_${MERGE_METHOD}.json"

    if [[ -f "$final_index" && -f "$final_metadata" ]]; then
        log "Merge outputs created successfully:"
        log "  Index: $final_index"
        log "  Metadata: $final_metadata"
    else
        log "Warning: Expected merge outputs not found"
    fi
}

# Show status
status() {
    echo "PubMed Indexing Status"
    echo "======================"

    # Raw files
    if [[ -d "$BASE_DATA_DIR" ]]; then
        local raw_count=$(find "$BASE_DATA_DIR" -name "*.xml.gz" 2>/dev/null | wc -l)
        echo "Raw XML files: $raw_count"
    else
        echo "Raw XML files: 0 (directory missing)"
    fi

    # File list
    if [[ -f "$FILE_LIST" ]]; then
        local list_count=$(wc -l < "$FILE_LIST")
        echo "Files to index: $list_count"
    else
        echo "File list: not created"
    fi

    # Indexed files
    if [[ -d "$PROCESSED_DIR" ]]; then
        local indexed_count=$(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | wc -l)
        echo "Indexed files: $indexed_count"
    else
        echo "Indexed files: 0 (directory missing)"
    fi

    # Final files
    if [[ -d "$FINAL_DIR" ]]; then
        local final_count=$(find "$FINAL_DIR" -name "*.index" 2>/dev/null | wc -l)
        echo "Final indices: $final_count"
    else
        echo "Final indices: 0 (directory missing)"
    fi

    # Running jobs
    if command -v qstat &> /dev/null; then
        local running_jobs=$(qstat -u "$USER" 2>/dev/null | grep -E "(pubmed_process|pubmed_merge)" | wc -l)
        echo "Running jobs: $running_jobs"

        if [[ $running_jobs -gt 0 ]]; then
            echo ""
            echo "Active jobs:"
            qstat -u "$USER" 2>/dev/null | grep -E "(pubmed_process|pubmed_merge)" || true
        fi
    fi
}

# Run complete pipeline
run_all() {
    local debug_mode="$1"
    log "Running complete PubMed pipeline..."

    # Download
    download

    # Index
    index "$debug_mode"
    wait_indexing

    # Merge
    merge
    wait_merge

    log "Complete pipeline finished!"
}

# Parse arguments
DEBUG_MODE="false"
COMMAND=""
TASK_IDS=""

source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug) DEBUG_MODE="true"; shift ;;
        download|index|merge|resubmit|all|status) COMMAND="$1"; shift ;;
        [0-9]*) TASK_IDS="$TASK_IDS $1"; shift ;;  # Collect numeric task IDs
        *) usage; exit 1 ;;
    esac
done

# Execute command
case "$COMMAND" in
    download)
        download
        ;;
    index)
        index "$DEBUG_MODE"
        ;;
    merge)
        merge
        ;;
    resubmit)
        resubmit $TASK_IDS
        ;;
    all)
        run_all "$DEBUG_MODE"
        ;;
    status)
        status
        ;;
    *)
        usage
        ;;
esac