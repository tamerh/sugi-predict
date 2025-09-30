#!/bin/bash
##############################################################################
# PubMed Processing Pipeline
##############################################################################

set -euo pipefail

# Load configuration
source "$(dirname "$0")/pubmed.env"

# Load validation utilities
source "$(dirname "$0")/validation_utils.sh"

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
    echo "  status     - Show indexing status with validation"
    echo "  validate   - Run validation checks on existing data"
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
    local debug_mode="$1"
    log "Starting download phase..."

    # Run data download
    if [[ "$debug_mode" == "true" ]]; then
        log "Running download in DEBUG mode (3 files only)..."
        python download.py --debug 3
    else
        log "Running full download..."
        python download.py
    fi

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
        # In debug mode, use actual file count (don't exceed available files)
        if [[ $total_files -lt $DEBUG_SAMPLE_SIZE ]]; then
            num_tasks=$total_files
        else
            num_tasks=$DEBUG_SAMPLE_SIZE
        fi
        log "Debug mode: indexing $num_tasks files out of $total_files"
    else
        log "Indexing all $total_files files"
    fi

    # Create log directory
    mkdir -p "$LOG_DIR"
    mkdir -p "${LOG_DIR}/index"
    # Submit job array (same as submit_jobs.sh)
    log "Submitting job array with $num_tasks tasks..."

    qsub -r y -q "$CLUSTER_QUEUE" -N pubmed_process \
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

    # Wait a moment for jobs to appear in queue
    sleep 2

    while qstat -u "$USER" 2>/dev/null | grep -q "pubmed_pro"; do
        local running_jobs=$(qstat -u "$USER" 2>/dev/null | grep "pubmed_pro" | wc -l)
        log "Waiting... $running_jobs jobs still running"
        sleep 10
    done

    log "All indexing jobs completed"

    # Give filesystem a moment to sync
    sleep 2
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

    # Run pre-merge validation
    if ! validate_pre_merge; then
        log "Pre-merge validation failed. Aborting merge."
        return 1
    fi

    # Create model-specific directories
    local model_final_dir=$(create_model_directories)
    export MODEL_FINAL_DIR="$model_final_dir"
    log "Using model directory: $model_final_dir"

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

    # Wait a moment for job to appear in queue
    sleep 2

    while qstat -u "$USER" 2>/dev/null | grep -q "merge_bioy"; do
        log "Merge job still running..."
        sleep 30
    done

    log "Merge completed"

    # Give filesystem a moment to sync
    sleep 2

    # Determine output paths (check model-specific dir first, fallback to standard)
    local model_dir=$(get_model_dir "$MODEL_NAME" "$VECTOR_DIMENSION")
    local model_final_dir="$FINAL_DIR/$model_dir"

    local final_index=""
    local final_metadata=""

    if [[ -d "$model_final_dir" ]]; then
        final_index="${model_final_dir}/master_pubmed.index"
        final_metadata="${model_final_dir}/master_metadata.json"
    else
        # Fallback to old paths
        final_index="${FINAL_DIR}/master_pubmed.index"
        final_metadata="${FINAL_DIR}/master_metadata.json"
    fi

    if [[ -f "$final_index" && -f "$final_metadata" ]]; then
        log "Merge outputs created successfully:"
        log "  Index: $final_index"
        log "  Metadata: $final_metadata"

        # Run post-merge validation
        if validate_post_merge "$final_index" "$final_metadata"; then
            log "Post-merge validation passed ✓"
        else
            log "Warning: Post-merge validation failed"
            return 1
        fi
    else
        log "Warning: Expected merge outputs not found"
        log "  Expected index: $final_index"
        log "  Expected metadata: $final_metadata"
        return 1
    fi
}

# Show status
status() {
    echo "PubMed Indexing Status"
    echo "======================"
    echo "Model: $MODEL_NAME"
    echo "Dimensions: $VECTOR_DIMENSION"
    echo ""

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

        # Sample validation on processed files
        if [[ $indexed_count -gt 0 ]]; then
            echo -n "Processing validation: "
            local sample_files=($(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | head -3))
            local validation_passed=0
            for sample_file in "${sample_files[@]}"; do
                if validate_faiss_dimensions "$sample_file" "$VECTOR_DIMENSION" 2>/dev/null; then
                    ((validation_passed++))
                fi
            done
            if [[ $validation_passed -eq ${#sample_files[@]} ]]; then
                echo -e "${GREEN}✓ OK${NC} (sampled ${#sample_files[@]} files)"
            else
                echo -e "${RED}✗ ISSUES${NC} ($validation_passed/${#sample_files[@]} valid)"
            fi
        fi
    else
        echo "Indexed files: 0 (directory missing)"
    fi

    # Final files
    echo ""
    echo "Final files:"
    if [[ -d "$FINAL_DIR" ]]; then
        local model_dir=$(get_model_dir "$MODEL_NAME" "$VECTOR_DIMENSION")
        local model_final_dir="$FINAL_DIR/$model_dir"

        # Check for model-specific directory first
        if [[ -d "$model_final_dir" ]]; then
            echo "  Model directory: $model_dir"
            local final_count=$(find "$model_final_dir" -name "*.index" 2>/dev/null | wc -l)
            echo "  Total indices: $final_count"

            # List files with sizes
            find "$model_final_dir" -name "*.index" -exec basename {} \; 2>/dev/null | while read index_name; do
                local full_path="$model_final_dir/$index_name"
                local size=$(du -h "$full_path" | cut -f1)
                echo "    $index_name ($size)"
            done
        else
            # Fallback to old structure
            local final_count=$(find "$FINAL_DIR" -maxdepth 1 -name "*.index" 2>/dev/null | wc -l)
            echo "  Total indices: $final_count (legacy structure)"

            # List actual files with sizes
            find "$FINAL_DIR" -maxdepth 1 -name "*.index" -exec basename {} \; 2>/dev/null | while read index_name; do
                local full_path="$FINAL_DIR/$index_name"
                local size=$(du -h "$full_path" | cut -f1)
                echo "    $index_name ($size)"
            done
        fi
    else
        echo "  Directory: Not created"
    fi

    # Running jobs
    echo ""
    if command -v qstat &> /dev/null; then
        local running_jobs=$(qstat -u "$USER" 2>/dev/null | grep -E "(pubmed_pro|merge_bioy)" | wc -l)
        echo "Running jobs: $running_jobs"

        if [[ $running_jobs -gt 0 ]]; then
            echo ""
            echo "Active jobs:"
            qstat -u "$USER" 2>/dev/null | grep -E "(pubmed_pro|merge_bioy)" || true
        fi
    fi
}

# Standalone validation command
validate() {
    log "Running comprehensive validation..."

    local errors=0

    # Validate configuration
    log "Checking configuration..."
    if [[ -z "$MODEL_NAME" || -z "$VECTOR_DIMENSION" ]]; then
        validate_log "ERROR" "Model configuration missing"
        errors=$((errors + 1))
    else
        validate_log "INFO" "Model: $MODEL_NAME ($VECTOR_DIMENSION dimensions)"
    fi

    # Validate processed files (sample)
    if [[ -d "$PROCESSED_DIR" ]]; then
        log "Validating processed files..."
        local sample_files=($(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | head -10))

        if [[ ${#sample_files[@]} -gt 0 ]]; then
            local valid_count=0
            for sample_file in "${sample_files[@]}"; do
                if validate_faiss_dimensions "$sample_file" "$VECTOR_DIMENSION"; then
                    valid_count=$((valid_count + 1))
                else
                    errors=$((errors + 1))
                fi
            done
            validate_log "INFO" "Processed validation: $valid_count/${#sample_files[@]} files valid"
        else
            validate_log "WARN" "No processed files to validate"
        fi
    fi

    # Validate final outputs
    if [[ -d "$FINAL_DIR" ]]; then
        log "Validating final outputs..."
        local final_files=($(find "$FINAL_DIR" -name "*.index" 2>/dev/null))

        for index_file in "${final_files[@]}"; do
            # Metadata file is in same directory, just replace pubmed with metadata in filename
            local metadata_file="$(dirname "$index_file")/$(basename "$index_file" .index | sed 's/pubmed/metadata/').json"

            validate_log "INFO" "Validating $(basename "$index_file")..."

            if ! validate_faiss_dimensions "$index_file" "$VECTOR_DIMENSION"; then
                errors=$((errors + 1))
            fi

            if [[ -f "$metadata_file" ]]; then
                if ! validate_index_metadata_alignment "$index_file" "$metadata_file"; then
                    errors=$((errors + 1))
                fi
            else
                validate_log "WARN" "Metadata file not found: $(basename "$metadata_file")"
            fi
        done
    else
        validate_log "WARN" "No final directory found: $FINAL_DIR"
    fi

    # Summary
    echo ""
    if [[ $errors -eq 0 ]]; then
        validate_log "INFO" "All validations passed! ✓"
        return 0
    else
        validate_log "ERROR" "Validation completed with $errors errors ✗"
        return 1
    fi
}

# Run complete pipeline
run_all() {
    local debug_mode="$1"
    log "Running complete PubMed pipeline..."

    # Download
    download "$debug_mode"

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
        download|index|merge|resubmit|all|status|validate) COMMAND="$1"; shift ;;
        [0-9]*) TASK_IDS="$TASK_IDS $1"; shift ;;  # Collect numeric task IDs
        *) usage; exit 1 ;;
    esac
done

# Execute command
case "$COMMAND" in
    download)
        download "$j"
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
    validate)
        validate
        ;;
    *)
        usage
        ;;
esac