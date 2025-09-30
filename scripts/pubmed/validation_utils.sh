#!/bin/bash
##############################################################################
# Validation Utilities for PubMed Pipeline
##############################################################################

# Validation functions to be sourced by pubmed.sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Validation logging
validate_log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%H:%M:%S')

    case $level in
        "INFO")  echo -e "[${timestamp}] ${GREEN}✓${NC} $message" ;;
        "WARN")  echo -e "[${timestamp}] ${YELLOW}⚠${NC} $message" ;;
        "ERROR") echo -e "[${timestamp}] ${RED}✗${NC} $message" ;;
    esac
}

# Check if index file has expected dimensions
validate_faiss_dimensions() {
    local index_file="$1"
    local expected_dim="$2"

    if [[ ! -f "$index_file" ]]; then
        validate_log "ERROR" "Index file not found: $index_file"
        return 1
    fi

    # Use Python to check FAISS index dimensions
    local actual_dim=$(python3 -c "
import faiss
import sys
try:
    index = faiss.read_index('$index_file')
    print(index.d)
except Exception as e:
    print('ERROR', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)

    if [[ "$actual_dim" == "ERROR" ]]; then
        validate_log "ERROR" "Failed to read index file: $index_file"
        return 1
    fi

    if [[ "$actual_dim" == "$expected_dim" ]]; then
        validate_log "INFO" "Index dimensions correct: $actual_dim"
        return 0
    else
        validate_log "ERROR" "Dimension mismatch: expected $expected_dim, got $actual_dim"
        return 1
    fi
}

# Validate index and metadata alignment
validate_index_metadata_alignment() {
    local index_file="$1"
    local metadata_file="$2"

    if [[ ! -f "$index_file" || ! -f "$metadata_file" ]]; then
        validate_log "ERROR" "Missing files for alignment check"
        return 1
    fi

    # Check vector count vs metadata count
    local vector_count=$(python3 -c "
import faiss
try:
    index = faiss.read_index('$index_file')
    print(index.ntotal)
except:
    print(0)
")

    local metadata_count=$(python3 -c "
import json
try:
    with open('$metadata_file', 'r') as f:
        data = json.load(f)
    print(len(data))
except:
    print(0)
")

    if [[ "$vector_count" == "$metadata_count" ]]; then
        validate_log "INFO" "Index-metadata alignment correct: $vector_count vectors"
        return 0
    else
        validate_log "WARN" "Index-metadata count mismatch: $vector_count vectors, $metadata_count metadata entries"
        return 1
    fi
}

# Check file integrity (basic size and permissions)
validate_file_integrity() {
    local file_path="$1"
    local min_size_mb="$2"  # Minimum expected size in MB

    if [[ ! -f "$file_path" ]]; then
        validate_log "ERROR" "File not found: $file_path"
        return 1
    fi

    if [[ ! -r "$file_path" ]]; then
        validate_log "ERROR" "File not readable: $file_path"
        return 1
    fi

    local file_size_mb=$(du -m "$file_path" | cut -f1)

    if [[ "$file_size_mb" -lt "$min_size_mb" ]]; then
        validate_log "WARN" "File smaller than expected: ${file_size_mb}MB (min: ${min_size_mb}MB)"
        return 1
    else
        validate_log "INFO" "File size OK: ${file_size_mb}MB"
        return 0
    fi
}

# Validate processed directory has expected number of files
validate_processed_files() {
    local expected_count="$1"
    local tolerance="$2"  # Allow some variance (e.g., 5% = 0.05)

    if [[ ! -d "$PROCESSED_DIR" ]]; then
        validate_log "ERROR" "Processed directory not found: $PROCESSED_DIR"
        return 1
    fi

    local actual_count=$(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | wc -l)
    local min_expected=$((expected_count - expected_count * tolerance / 100))
    local max_expected=$((expected_count + expected_count * tolerance / 100))

    if [[ "$actual_count" -ge "$min_expected" && "$actual_count" -le "$max_expected" ]]; then
        validate_log "INFO" "Processed file count OK: $actual_count (expected ~$expected_count)"
        return 0
    else
        validate_log "WARN" "Processed file count off: $actual_count (expected ~$expected_count ±${tolerance}%)"
        return 1
    fi
}

# Get model-specific directory
get_model_dir() {
    local model_name="$1"
    local vector_dim="$2"

    # Normalize model name for directory
    local model_dir_name=""
    case "$model_name" in
        *"S-BioBERT"*|*"s-biobert"*)
            model_dir_name="s-biobert-${vector_dim}d"
            ;;
        *"MiniLM"*|*"minilm"*)
            model_dir_name="minilm-${vector_dim}d"
            ;;
        *)
            # Generate safe directory name from model
            model_dir_name=$(echo "$model_name" | tr '/' '-' | tr '[:upper:]' '[:lower:]')-"${vector_dim}d"
            ;;
    esac

    echo "$model_dir_name"
}

# Create model-specific directories (SAFE - only for future runs)
create_model_directories() {
    local model_dir=$(get_model_dir "$MODEL_NAME" "$VECTOR_DIMENSION")
    local model_final_dir="$FINAL_DIR/$model_dir"

    # SAFETY: Only create if it doesn't exist and no migration is running
    if [[ ! -d "$model_final_dir" ]]; then
        validate_log "INFO" "Creating new model directory: $model_dir (safe for future runs)"
        mkdir -p "$model_final_dir"

        # Only create symlink if no migration is using current structure
        if [[ ! -L "$FINAL_DIR/current" ]]; then
            ln -sf "$model_dir" "$FINAL_DIR/current"
            validate_log "INFO" "Created current model symlink"
        else
            validate_log "INFO" "Preserving existing current symlink during active operations"
        fi
    else
        validate_log "INFO" "Model directory already exists: $model_dir"
    fi

    echo "$model_final_dir"
}

# Pre-flight checks before starting merge
validate_pre_merge() {
    validate_log "INFO" "Running pre-merge validation..."

    local errors=0

    # Check configuration
    if [[ -z "$MODEL_NAME" || -z "$VECTOR_DIMENSION" ]]; then
        validate_log "ERROR" "Model configuration missing"
        ((errors++))
    fi

    # Check if we have indexed files
    local indexed_count=$(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | wc -l)
    if [[ $indexed_count -eq 0 ]]; then
        validate_log "ERROR" "No indexed files found for merging"
        ((errors++))
    else
        validate_log "INFO" "Found $indexed_count files to merge"
    fi

    # Sample a few index files for dimension validation
    local sample_files=($(find "$PROCESSED_DIR" -name "*.index" 2>/dev/null | head -3))
    for sample_file in "${sample_files[@]}"; do
        if ! validate_faiss_dimensions "$sample_file" "$VECTOR_DIMENSION"; then
            ((errors++))
        fi
    done

    if [[ $errors -eq 0 ]]; then
        validate_log "INFO" "Pre-merge validation passed"
        return 0
    else
        validate_log "ERROR" "Pre-merge validation failed with $errors errors"
        return 1
    fi
}

# Post-merge validation
validate_post_merge() {
    local index_file="$1"
    local metadata_file="$2"

    validate_log "INFO" "Running post-merge validation..."

    local errors=0

    # Check files exist
    if [[ ! -f "$index_file" ]]; then
        validate_log "ERROR" "Final index not created: $index_file"
        ((errors++))
    fi

    if [[ ! -f "$metadata_file" ]]; then
        validate_log "ERROR" "Final metadata not created: $metadata_file"
        ((errors++))
    fi

    if [[ $errors -gt 0 ]]; then
        return 1
    fi

    # Validate dimensions
    if ! validate_faiss_dimensions "$index_file" "$VECTOR_DIMENSION"; then
        ((errors++))
    fi

    # Validate alignment
    if ! validate_index_metadata_alignment "$index_file" "$metadata_file"; then
        ((errors++))
    fi

    # Check file sizes (expect large files)
    if ! validate_file_integrity "$index_file" 1000; then  # At least 1GB
        ((errors++))
    fi

    if ! validate_file_integrity "$metadata_file" 100; then  # At least 100MB
        ((errors++))
    fi

    if [[ $errors -eq 0 ]]; then
        validate_log "INFO" "Post-merge validation passed"

        # Save validation info
        local validation_file="$(dirname "$index_file")/validation.log"
        {
            echo "Validation completed: $(date)"
            echo "Model: $MODEL_NAME"
            echo "Dimensions: $VECTOR_DIMENSION"
            echo "Index file: $(basename "$index_file")"
            echo "Metadata file: $(basename "$metadata_file")"
            echo "Index size: $(du -h "$index_file" | cut -f1)"
            echo "Metadata size: $(du -h "$metadata_file" | cut -f1)"
            echo "Vector count: $(python3 -c "import faiss; print(faiss.read_index('$index_file').ntotal)")"
        } > "$validation_file"

        validate_log "INFO" "Validation log saved: $validation_file"
        return 0
    else
        validate_log "ERROR" "Post-merge validation failed with $errors errors"
        return 1
    fi
}