#!/bin/bash
##############################################################################
#
#   BioYoda Sync Commands (push/pull)
#   Sync data to/from Google Drive for GPU processing on Colab
#
#   Usage:
#     ./bioyoda.sh push <module>   # Push data to Drive
#     ./bioyoda.sh pull <module>   # Pull results from Drive
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Get gdrive remote from config
get_gdrive_remote() {
    local config_file="${1:-$DEFAULT_CONFIG}"
    local value=""

    if [[ -f "$config_file" ]]; then
        # Extract remote value, handling comments correctly
        value=$(grep -A5 "^gdrive:" "$config_file" | grep "remote:" | head -1 | sed 's/#.*//' | sed 's/.*remote: *"\([^"]*\)".*/\1/')
    fi

    echo "${value:-gdrive:bioyoda}"
}

# Sync with rclone and logging
# Usage: rclone_sync <src> <dst> <description> <log_file> [dry_run]
rclone_sync() {
    local src="$1"
    local dst="$2"
    local desc="$3"
    local log_file="$4"
    local dry_run="${5:-}"

    local dry_run_flag=""
    if [[ "$dry_run" == "true" ]]; then
        dry_run_flag="--dry-run"
        log_info "[DRY-RUN] Would sync: $desc"
    else
        log_info "Syncing: $desc"
    fi

    echo "$(date '+%Y-%m-%d %H:%M:%S') - $desc" >> "$log_file"
    echo "  Source: $src" >> "$log_file"
    echo "  Destination: $dst" >> "$log_file"

    if rclone copy "$src" "$dst" --progress $dry_run_flag 2>&1 | tee -a "$log_file"; then
        echo "  Status: SUCCESS" >> "$log_file"
        return 0
    else
        echo "  Status: FAILED" >> "$log_file"
        log_error "Failed to sync: $desc"
        return 1
    fi
}

# Push PubMed data to Drive
push_pubmed() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"
    local code_only="${5:-false}"

    log_info "Pushing PubMed data to Google Drive..."

    if [[ "$code_only" != "true" ]]; then
        # Raw data (baseline + updatefiles)
        rclone_sync "${base_dir}/raw_data/pubmed/baseline" "${remote}/raw_data/pubmed/baseline" \
            "PubMed baseline XMLs" "$log_file" "$dry_run"

        rclone_sync "${base_dir}/raw_data/pubmed/updatefiles" "${remote}/raw_data/pubmed/updatefiles" \
            "PubMed update XMLs" "$log_file" "$dry_run"

        # Deleted PMIDs
        if [[ -f "${base_dir}/raw_data/pubmed/deleted.pmids.sorted.gz" ]]; then
            rclone_sync "${base_dir}/raw_data/pubmed/deleted.pmids.sorted.gz" "${remote}/raw_data/pubmed/" \
                "Deleted PMIDs" "$log_file" "$dry_run"
        fi

        # State files
        rclone_sync "${base_dir}/state/pubmed" "${remote}/state/pubmed" \
            "PubMed state files" "$log_file" "$dry_run"
    else
        log_info "Code-only mode: skipping data files"
    fi

    log_info "PubMed push complete!"
}

# Pull PubMed results from Drive
pull_pubmed() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"

    log_info "Pulling PubMed results from Google Drive..."

    # Processed indices
    rclone_sync "${remote}/processed/pubmed" "${base_dir}/data/processed/pubmed" \
        "PubMed processed indices" "$log_file" "$dry_run"

    # State files
    rclone_sync "${remote}/state/pubmed" "${base_dir}/state/pubmed" \
        "PubMed state files" "$log_file" "$dry_run"

    log_info "PubMed pull complete!"
}

# Push Patents data to Drive
push_patents() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"
    local code_only="${5:-false}"

    log_info "Pushing Patents data to Google Drive..."

    if [[ "$code_only" != "true" ]]; then
        # Chunked patent parquets
        rclone_sync "${base_dir}/raw_data/patents/chunked" "${remote}/raw_data/patents/chunked" \
            "Patent chunks (parquet)" "$log_file" "$dry_run"

        # USPTO historical data
        if [[ -f "${base_dir}/raw_data/patents/historical_uspto/uspto_historical.parquet" ]]; then
            rclone_sync "${base_dir}/raw_data/patents/historical_uspto/uspto_historical.parquet" \
                "${remote}/raw_data/patents/historical_uspto/" \
                "USPTO historical data" "$log_file" "$dry_run"
        fi

        # State files
        rclone_sync "${base_dir}/state/patents" "${remote}/state/patents" \
            "Patents state files" "$log_file" "$dry_run"
    else
        log_info "Code-only mode: skipping data files"
    fi

    log_info "Patents push complete!"
}

# Pull Patents results from Drive
pull_patents() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"

    log_info "Pulling Patents results from Google Drive..."

    # Processed text indices
    rclone_sync "${remote}/processed/patents/text" "${base_dir}/data/processed/patents/text" \
        "Patents text indices" "$log_file" "$dry_run"

    # State files
    rclone_sync "${remote}/state/patents" "${base_dir}/state/patents" \
        "Patents state files" "$log_file" "$dry_run"

    log_info "Patents pull complete!"
}

# Push Clinical Trials data to Drive
push_clinical_trials() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"
    local code_only="${5:-false}"

    log_info "Pushing Clinical Trials data to Google Drive..."

    if [[ "$code_only" != "true" ]]; then
        # Chunked clinical trials JSON files
        rclone_sync "${base_dir}/raw_data/clinical_trials/chunked" "${remote}/raw_data/clinical_trials/chunked" \
            "Clinical Trials chunks (JSON)" "$log_file" "$dry_run"

        # State files
        rclone_sync "${base_dir}/state/clinical_trials" "${remote}/state/clinical_trials" \
            "Clinical Trials state files" "$log_file" "$dry_run"
    else
        log_info "Code-only mode: skipping data files"
    fi

    log_info "Clinical Trials push complete!"
}

# Pull Clinical Trials results from Drive
pull_clinical_trials() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"

    log_info "Pulling Clinical Trials results from Google Drive..."

    # Processed text indices
    rclone_sync "${remote}/processed/clinical_trials/text" "${base_dir}/data/processed/clinical_trials/text" \
        "Clinical Trials text indices" "$log_file" "$dry_run"

    # State files
    rclone_sync "${remote}/state/clinical_trials" "${base_dir}/state/clinical_trials" \
        "Clinical Trials state files" "$log_file" "$dry_run"

    log_info "Clinical Trials pull complete!"
}

# Push ESM2 data to Drive
push_esm2() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"
    local code_only="${5:-false}"

    log_info "Pushing ESM2 data to Google Drive..."

    if [[ "$code_only" != "true" ]]; then
        # FASTA chunks
        rclone_sync "${base_dir}/raw_data/esm2/chunks" "${remote}/raw_data/esm2/chunks" \
            "ESM2 FASTA chunks" "$log_file" "$dry_run"

        # State files
        rclone_sync "${base_dir}/state/esm2" "${remote}/state/esm2" \
            "ESM2 state files" "$log_file" "$dry_run"
    else
        log_info "Code-only mode: skipping data files"
    fi

    # GPU scripts (always synced)
    local script_dir="${COMMANDS_DIR}/../../modules/esm2/scripts"
    rclone_sync "${script_dir}/batch_esm2_gpu.py" "${remote}/scripts/esm2/" \
        "ESM2 batch GPU script" "$log_file" "$dry_run"
    rclone_sync "${script_dir}/generate_embeddings.py" "${remote}/scripts/esm2/" \
        "ESM2 embeddings script" "$log_file" "$dry_run"
    rclone_sync "${script_dir}/h5_to_faiss.py" "${remote}/scripts/esm2/" \
        "ESM2 H5 to FAISS script" "$log_file" "$dry_run"

    log_info "ESM2 push complete!"
}

# Pull ESM2 results from Drive
pull_esm2() {
    local base_dir="$1"
    local remote="$2"
    local log_file="$3"
    local dry_run="$4"

    log_info "Pulling ESM2 results from Google Drive..."

    # Processed indices
    rclone_sync "${remote}/processed/esm2" "${base_dir}/data/processed/esm2" \
        "ESM2 FAISS indices" "$log_file" "$dry_run"

    # State files
    rclone_sync "${remote}/state/esm2" "${base_dir}/state/esm2" \
        "ESM2 state files" "$log_file" "$dry_run"

    log_info "ESM2 pull complete!"
}

# Run sync in background
# Usage: run_in_background <command> <log_file> <pid_file>
run_sync_background() {
    local cmd="$1"
    local log_file="$2"
    local pid_file="$3"

    nohup bash -c "$cmd" >> "$log_file" 2>&1 &
    local pid=$!
    echo $pid > "$pid_file"

    log_info "Running in background (PID: $pid)"
    log_info "Log: $log_file"
    log_info "Monitor: tail -f $log_file"
}

# Main push command
cmd_push() {
    local module=""
    local dry_run=false
    local background=false
    local code_only=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run|-n)
                dry_run=true
                shift
                ;;
            --bg|-b)
                background=true
                shift
                ;;
            --code-only|-c)
                code_only=true
                shift
                ;;
            --config)
                CUSTOM_CONFIG="$2"
                shift 2
                ;;
            *)
                if [[ -z "$module" ]]; then
                    module="$1"
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$module" ]]; then
        log_error "No module specified"
        echo "Usage: ./bioyoda.sh push <module> [--code-only] [--dry-run] [--bg]"
        echo "Modules: pubmed, patents, clinical_trials, esm2"
        echo ""
        echo "Options:"
        echo "  --code-only, -c   Only sync scripts (fast, for code changes)"
        echo "  --dry-run, -n     Show what would be synced without syncing"
        echo "  --bg, -b          Run in background"
        exit 1
    fi

    # Resolve config
    local config_file="${CUSTOM_CONFIG:-$DEFAULT_CONFIG}"
    local base_dir=$(get_base_dir "$config_file")
    local remote=$(get_gdrive_remote "$config_file")

    # Setup logging
    local log_dir="${base_dir}/logs/sync"
    mkdir -p "$log_dir"
    local log_file="${log_dir}/push_${module}_$(date '+%Y%m%d_%H%M%S').log"
    local pid_file="${log_dir}/push_${module}.pid"

    local mode_str=""
    if [[ "$code_only" == "true" ]]; then
        mode_str=" (code-only)"
    fi
    log_info "Push: module=${module}${mode_str}, base_dir=${base_dir}, remote=${remote}"

    # Check rclone
    if ! command -v rclone &> /dev/null; then
        log_error "rclone not found. Install with: sudo apt install rclone"
        exit 1
    fi

    # Build the sync command
    local sync_func=""
    case $module in
        pubmed)
            sync_func="push_pubmed"
            ;;
        patents)
            sync_func="push_patents"
            ;;
        clinical_trials)
            sync_func="push_clinical_trials"
            ;;
        esm2)
            sync_func="push_esm2"
            ;;
        *)
            log_error "Unknown module: $module"
            echo "Supported modules: pubmed, patents, clinical_trials, esm2"
            exit 1
            ;;
    esac

    if [[ "$background" == "true" ]]; then
        # Run in background
        local script_path="${COMMANDS_DIR}/sync.sh"
        local bg_cmd="source ${COMMANDS_DIR}/../lib/common.sh && source ${script_path} && echo '========== PUSH ${module} started at \$(date) ==========' >> ${log_file} && ${sync_func} '${base_dir}' '${remote}' '${log_file}' '${dry_run}' '${code_only}' && echo '========== PUSH ${module} completed at \$(date) ==========' >> ${log_file}"

        run_sync_background "$bg_cmd" "$log_file" "$pid_file"
    else
        # Run in foreground
        echo "========== PUSH ${module} started at $(date) ==========" > "$log_file"
        $sync_func "$base_dir" "$remote" "$log_file" "$dry_run" "$code_only"
        echo "========== PUSH ${module} completed at $(date) ==========" >> "$log_file"
        log_info "Log saved to: $log_file"
    fi
}

# Main pull command
cmd_pull() {
    local module=""
    local dry_run=false
    local background=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run|-n)
                dry_run=true
                shift
                ;;
            --bg|-b)
                background=true
                shift
                ;;
            --config)
                CUSTOM_CONFIG="$2"
                shift 2
                ;;
            *)
                if [[ -z "$module" ]]; then
                    module="$1"
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$module" ]]; then
        log_error "No module specified"
        echo "Usage: ./bioyoda.sh pull <module> [--dry-run] [--bg]"
        echo "Modules: pubmed, patents, clinical_trials, esm2"
        exit 1
    fi

    # Resolve config
    local config_file="${CUSTOM_CONFIG:-$DEFAULT_CONFIG}"
    local base_dir=$(get_base_dir "$config_file")
    local remote=$(get_gdrive_remote "$config_file")

    # Setup logging
    local log_dir="${base_dir}/logs/sync"
    mkdir -p "$log_dir"
    local log_file="${log_dir}/pull_${module}_$(date '+%Y%m%d_%H%M%S').log"
    local pid_file="${log_dir}/pull_${module}.pid"

    log_info "Pull: module=${module}, base_dir=${base_dir}, remote=${remote}"

    # Check rclone
    if ! command -v rclone &> /dev/null; then
        log_error "rclone not found. Install with: sudo apt install rclone"
        exit 1
    fi

    # Build the sync command
    local sync_func=""
    case $module in
        pubmed)
            sync_func="pull_pubmed"
            ;;
        patents)
            sync_func="pull_patents"
            ;;
        clinical_trials)
            sync_func="pull_clinical_trials"
            ;;
        esm2)
            sync_func="pull_esm2"
            ;;
        *)
            log_error "Unknown module: $module"
            echo "Supported modules: pubmed, patents, clinical_trials, esm2"
            exit 1
            ;;
    esac

    if [[ "$background" == "true" ]]; then
        # Run in background
        local script_path="${COMMANDS_DIR}/sync.sh"
        local bg_cmd="source ${COMMANDS_DIR}/../lib/common.sh && source ${script_path} && echo '========== PULL ${module} started at \$(date) ==========' >> ${log_file} && ${sync_func} '${base_dir}' '${remote}' '${log_file}' '${dry_run}' && echo '========== PULL ${module} completed at \$(date) ==========' >> ${log_file}"

        run_sync_background "$bg_cmd" "$log_file" "$pid_file"
    else
        # Run in foreground
        echo "========== PULL ${module} started at $(date) ==========" > "$log_file"
        $sync_func "$base_dir" "$remote" "$log_file" "$dry_run"
        echo "========== PULL ${module} completed at $(date) ==========" >> "$log_file"
        log_info "Log saved to: $log_file"
    fi
}
