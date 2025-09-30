#!/bin/bash
##############################################################################
# Clinical Trials Processing Pipeline
##############################################################################

set -euo pipefail

# Load configuration
source "$(dirname "$0")/clinical_trials.env"

# Simple logging
log() { echo "[$(date '+%H:%M:%S')] $1"; }

# Usage
usage() {
    echo "Usage: $0 <command> [--debug] [options...]"
    echo "Commands:"
    echo "  download   - Download AACT database snapshot"
    echo "  extract    - Extract text from AACT database"
    echo "  process    - Process trials to create FAISS embeddings"
    echo "  merge      - Merge all indices into master index"
    echo "  all        - Run complete pipeline (download + extract + process + merge)"
    echo "  status     - Show processing status"
    echo "  validate   - Run validation checks on data"
    echo ""
    echo "Options:"
    echo "  --debug    - Process only $DEBUG_SAMPLE_SIZE trials"
    echo "  --recreate - Recreate database (for download command)"
    echo ""
    echo "Examples:"
    echo "  $0 download --recreate    # Download and recreate AACT database"
    echo "  $0 extract --debug        # Extract limited data for testing"
    echo "  $0 all                    # Run complete pipeline"
}

# Download AACT database
download() {
    local recreate_flag="$1"
    log "Starting AACT database download..."

    local download_args=""
    if [[ "$recreate_flag" == "true" ]]; then
        download_args="--recreate"
    fi

    python download_aact.py \
        --download-dir "$BASE_DATA_DIR" \
        --database-name "$AACT_DATABASE_NAME" \
        $download_args

    if [[ $? -eq 0 ]]; then
        log "AACT database download completed successfully"
        # Create connection info file for other scripts
        local conn_file="$SCRIPTS_DIR/aact_connection.env"
        cat > "$conn_file" << EOF
AACT_DATABASE_URL="postgresql://$POSTGRES_USER@$POSTGRES_HOST:$POSTGRES_PORT/$AACT_DATABASE_NAME"
EOF
        log "Database connection info saved to $conn_file"
    else
        log "ERROR: AACT database download failed"
        return 1
    fi
}

# Extract text from AACT database
extract() {
    local debug_mode="$1"
    log "Starting text extraction from AACT database..."

    # Check if connection info exists
    local conn_file="$SCRIPTS_DIR/aact_connection.env"
    if [[ ! -f "$conn_file" ]]; then
        log "Database connection info not found. Running download first..."
        download "false"
    fi

    source "$conn_file"

    # Prepare output files
    local output_json="${PROCESSED_DIR}/trials_data.json"
    local output_csv="${PROCESSED_DIR}/trials_data.csv"

    mkdir -p "$PROCESSED_DIR"

    # Set extraction parameters
    local extract_args=""
    if [[ "$debug_mode" == "true" ]]; then
        extract_args="--limit $DEBUG_SAMPLE_SIZE"
        output_json="${PROCESSED_DIR}/trials_data_debug.json"
        output_csv="${PROCESSED_DIR}/trials_data_debug.csv"
        log "Debug mode: extracting $DEBUG_SAMPLE_SIZE trials"
    fi

    if [[ "$INCLUDE_DETAILED_DESCRIPTION" == "true" ]]; then
        extract_args="$extract_args --include-detailed-description"
    fi

    if [[ "$INCLUDE_OUTCOMES" == "true" ]]; then
        extract_args="$extract_args --include-outcomes"
    fi

    if [[ "$INCLUDE_ELIGIBILITY" == "true" ]]; then
        extract_args="$extract_args --include-eligibility"
    fi

    if [[ "$INCLUDE_INTERVENTIONS" == "true" ]]; then
        extract_args="$extract_args --include-interventions"
    fi

    if [[ "$EXCLUDE_WITHDRAWN_STUDIES" == "true" ]]; then
        extract_args="$extract_args --exclude-withdrawn"
    fi

    python extract_text.py \
        --database-url "$AACT_DATABASE_URL" \
        --output-json "$output_json" \
        --output-csv "$output_csv" \
        --min-summary-length "$MIN_BRIEF_SUMMARY_LENGTH" \
        $extract_args

    if [[ $? -eq 0 ]]; then
        log "Text extraction completed successfully"
        log "  JSON output: $output_json"
        log "  CSV output: $output_csv"

        # Save extraction info for next steps
        echo "EXTRACTED_JSON=\"$output_json\"" > "$SCRIPTS_DIR/extraction_info.env"
    else
        log "ERROR: Text extraction failed"
        return 1
    fi
}

# Process trials to create embeddings
process() {
    local debug_mode="$1"
    log "Starting trial processing..."

    # Check if extraction data exists
    local extract_info="$SCRIPTS_DIR/extraction_info.env"
    if [[ ! -f "$extract_info" ]]; then
        log "Extraction info not found. Running extraction first..."
        extract "$debug_mode"
    fi

    source "$extract_info"

    if [[ ! -f "$EXTRACTED_JSON" ]]; then
        log "ERROR: Extracted JSON file not found: $EXTRACTED_JSON"
        return 1
    fi

    # Prepare output files
    local base_name="clinical_trials"
    if [[ "$debug_mode" == "true" ]]; then
        base_name="clinical_trials_debug"
    fi

    local output_index="${PROCESSED_DIR}/${base_name}.index"
    local output_metadata="${PROCESSED_DIR}/${base_name}_metadata.json"

    mkdir -p "$PROCESSED_DIR"

    # Set processing parameters
    local process_args=""
    if [[ "$debug_mode" == "true" ]]; then
        process_args="--limit $DEBUG_SAMPLE_SIZE"
        log "Debug mode: processing $DEBUG_SAMPLE_SIZE trials"
    fi

    python process_trials.py \
        --input-json "$EXTRACTED_JSON" \
        --output-index "$output_index" \
        --output-metadata "$output_metadata" \
        --model-name "$MODEL_NAME" \
        --vector-dimension "$VECTOR_DIMENSION" \
        --batch-size "$BATCH_SIZE" \
        --max-chunk-length "$MAX_CHUNK_LENGTH" \
        --min-text-length "$MIN_TEXT_LENGTH" \
        $process_args

    if [[ $? -eq 0 ]]; then
        log "Trial processing completed successfully"
        log "  Index: $output_index"
        log "  Metadata: $output_metadata"
    else
        log "ERROR: Trial processing failed"
        return 1
    fi
}

# Merge all indices
merge() {
    log "Starting merge phase..."

    # Check if we have processed files
    local processed_count=$(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | wc -l)
    if [[ $processed_count -eq 0 ]]; then
        log "No processed index files found. Run processing first."
        return 1
    fi

    log "Found $processed_count index files to merge"

    # Prepare output files
    local final_index="${FINAL_DIR}/master_clinical_trials.index"
    local final_metadata="${FINAL_DIR}/master_clinical_trials_metadata.json"

    mkdir -p "$FINAL_DIR"

    python merge_trials.py \
        --processed-dir "$PROCESSED_DIR" \
        --output-index "$final_index" \
        --output-metadata "$final_metadata" \
        --vector-dimension "$VECTOR_DIMENSION"

    if [[ $? -eq 0 ]]; then
        log "Merge completed successfully"
        log "  Final index: $final_index"
        log "  Final metadata: $final_metadata"
    else
        log "ERROR: Merge failed"
        return 1
    fi
}

# Show status
status() {
    echo "Clinical Trials Processing Status"
    echo "================================="
    echo "Model: $MODEL_NAME"
    echo "Dimensions: $VECTOR_DIMENSION"
    echo ""

    # AACT Database
    local conn_file="$SCRIPTS_DIR/aact_connection.env"
    if [[ -f "$conn_file" ]]; then
        echo "AACT Database: ✓ Downloaded and configured"

        # Try to get database stats
        source "$conn_file"
        echo "Database URL: $AACT_DATABASE_URL"

        # Test database connection
        if python extract_text.py --database-url "$AACT_DATABASE_URL" --stats-only >/dev/null 2>&1; then
            echo "Database connection: ✓ Working"
        else
            echo "Database connection: ✗ Failed"
        fi
    else
        echo "AACT Database: ✗ Not downloaded"
    fi

    # Extracted data
    local extract_info="$SCRIPTS_DIR/extraction_info.env"
    if [[ -f "$extract_info" ]]; then
        source "$extract_info"
        if [[ -f "$EXTRACTED_JSON" ]]; then
            local file_size=$(du -h "$EXTRACTED_JSON" | cut -f1)
            echo "Extracted data: ✓ Available ($file_size)"
        else
            echo "Extracted data: ✗ File missing"
        fi
    else
        echo "Extracted data: ✗ Not extracted"
    fi

    # Processed files
    if [[ -d "$PROCESSED_DIR" ]]; then
        local processed_count=$(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | wc -l)
        echo "Processed indices: $processed_count"

        if [[ $processed_count -gt 0 ]]; then
            # Show recent processed files
            echo "Recent processed files:"
            find "$PROCESSED_DIR" -name "*.index" -exec basename {} \; 2>/dev/null | head -3 | while read filename; do
                local full_path="$PROCESSED_DIR/$filename"
                local size=$(du -h "$full_path" | cut -f1)
                echo "  $filename ($size)"
            done
        fi
    else
        echo "Processed indices: 0 (directory missing)"
    fi

    # Final files
    echo ""
    echo "Final files:"
    if [[ -d "$FINAL_DIR" ]]; then
        local final_count=$(find "$FINAL_DIR" -name "*.index" 2>/dev/null | wc -l)
        echo "  Final indices: $final_count"

        # List final files with sizes
        find "$FINAL_DIR" -name "*.index" -exec basename {} \; 2>/dev/null | while read index_name; do
            local full_path="$FINAL_DIR/$index_name"
            local size=$(du -h "$full_path" | cut -f1)
            echo "    $index_name ($size)"
        done

        # Check for report files
        local report_count=$(find "$FINAL_DIR" -name "*_report.json" 2>/dev/null | wc -l)
        if [[ $report_count -gt 0 ]]; then
            echo "  Merge reports: ✓ Available"
        fi
    else
        echo "  Directory: Not created"
    fi

    # Running jobs
    echo ""
    if command -v qstat &> /dev/null; then
        local running_jobs=$(qstat -u "$USER" 2>/dev/null | grep -E "(clinical_trials|ct_)" | wc -l)
        echo "Running jobs: $running_jobs"

        if [[ $running_jobs -gt 0 ]]; then
            echo ""
            echo "Active jobs:"
            qstat -u "$USER" 2>/dev/null | grep -E "(clinical_trials|ct_)" || true
        fi
    fi
}

# Validate data
validate() {
    log "Running clinical trials validation..."

    local errors=0

    # Check configuration
    log "Checking configuration..."
    if [[ -z "$MODEL_NAME" || -z "$VECTOR_DIMENSION" ]]; then
        log "ERROR: Model configuration missing"
        ((errors++))
    else
        log "✓ Model: $MODEL_NAME ($VECTOR_DIMENSION dimensions)"
    fi

    # Check AACT database
    local conn_file="$SCRIPTS_DIR/aact_connection.env"
    if [[ -f "$conn_file" ]]; then
        source "$conn_file"
        log "Testing AACT database connection..."
        if python extract_text.py --database-url "$AACT_DATABASE_URL" --stats-only >/dev/null 2>&1; then
            log "✓ AACT database connection working"
        else
            log "✗ AACT database connection failed"
            ((errors++))
        fi
    else
        log "✗ AACT database not configured"
        ((errors++))
    fi

    # Validate final files if they exist
    if [[ -d "$FINAL_DIR" ]]; then
        log "Validating final outputs..."
        local final_files=($(find "$FINAL_DIR" -name "*.index" 2>/dev/null))

        for index_file in "${final_files[@]}"; do
            local basename_index=$(basename "$index_file")
            local metadata_file="${index_file%.index}_metadata.json"

            echo -n "  $basename_index: "
            if python -c "
import faiss
import json
try:
    index = faiss.read_index('$index_file')
    if index.d != $VECTOR_DIMENSION:
        print('✗ Dimension mismatch')
        exit(1)
    if '$metadata_file' and open('$metadata_file').read():
        metadata = json.load(open('$metadata_file'))
        if len(metadata) != index.ntotal:
            print('✗ Metadata mismatch')
            exit(1)
    print(f'✓ Valid ({index.ntotal} vectors)')
except Exception as e:
    print(f'✗ Error: {e}')
    exit(1)
" 2>/dev/null; then
                :  # Success, message already printed by Python
            else
                ((errors++))
            fi
        done
    else
        log "No final directory found for validation"
    fi

    # Summary
    echo ""
    if [[ $errors -eq 0 ]]; then
        log "✓ All validations passed!"
        return 0
    else
        log "✗ Validation completed with $errors errors"
        return 1
    fi
}

# Run complete pipeline
run_all() {
    local debug_mode="$1"
    log "Running complete clinical trials pipeline..."

    # Download
    download "false"

    # Extract
    extract "$debug_mode"

    # Process
    process "$debug_mode"

    # Merge
    merge

    log "Complete clinical trials pipeline finished!"
}

# Parse arguments
DEBUG_MODE="false"
RECREATE="false"
COMMAND=""

source /home/scc/tgur/programs/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug) DEBUG_MODE="true"; shift ;;
        --recreate) RECREATE="true"; shift ;;
        download|extract|process|merge|all|status|validate) COMMAND="$1"; shift ;;
        *) usage; exit 1 ;;
    esac
done

# Execute command
case "$COMMAND" in
    download)
        download "$RECREATE"
        ;;
    extract)
        extract "$DEBUG_MODE"
        ;;
    process)
        process "$DEBUG_MODE"
        ;;
    merge)
        merge
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