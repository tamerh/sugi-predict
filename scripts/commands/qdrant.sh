#!/bin/bash
##############################################################################
#
#   BioYoda Qdrant Commands
#   Manages Qdrant vector database (start/stop/insert/status)
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"
source "${COMMANDS_DIR}/../lib/snakemake.sh"

# Show qdrant help
qdrant_help() {
    cat << 'EOF'
Qdrant Vector Database Management

Usage: bioyoda.sh qdrant <subcommand> [options]

Subcommands:
    start         Start Qdrant server (local or cluster)
    stop          Stop Qdrant server
    restart       Restart with existing storage directory
    status        Check Qdrant server status and collections
    insert        Insert data to Qdrant
    stop-insert   Stop a running insertion job

Start Options:
    --mode local              Run mode (only local supported)
    --runtime <hours>         Runtime in hours (default: 48)
    --memory <mb>             Memory in MB (default: 32000)
    --out-dir <path>          Use specific storage directory
    --test                    Use test configuration
    --config <file>           Use custom config file

Insert Options:
    --cluster                 Submit insertion jobs to cluster
    --local                   Run insertion locally (default)
    --bg, -b                  Run in background
    --jobs N                  Max parallel jobs (for cluster mode)
    --cores N                 Number of cores (for local mode)
    --test                    Use test configuration

Datasets:
    pubmed              PubMed abstracts
    clinical_trials     Clinical trials data
    patents             All patents data (text + compounds)
    patents_text        Patents text only
    patents_compounds   Patents compounds only
    esm2                Protein embeddings (ESM-2)
    all                 All datasets

Examples:
    bioyoda.sh qdrant start
    bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168
    bioyoda.sh qdrant start --out-dir /path/to/existing/qdrant  # Restart with existing storage
    bioyoda.sh qdrant restart                                   # Auto-detect and restart
    bioyoda.sh qdrant insert pubmed --cluster --jobs 10 --bg
    bioyoda.sh qdrant stop-insert pubmed
    bioyoda.sh qdrant status
    bioyoda.sh qdrant stop
EOF
}

# Main qdrant dispatcher
cmd_qdrant() {
    if [[ $# -eq 0 ]]; then
        qdrant_help
        exit 1
    fi

    local subcommand=$1
    shift

    case $subcommand in
        start)       qdrant_start "$@" ;;
        stop)        qdrant_stop "$@" ;;
        restart)     qdrant_restart "$@" ;;
        status)      qdrant_status "$@" ;;
        insert)      qdrant_insert "$@" ;;
        stop-insert) qdrant_stop_insert "$@" ;;
        help|--help|-h) qdrant_help ;;
        *)
            log_error "Unknown qdrant subcommand: $subcommand"
            qdrant_help
            exit 1
            ;;
    esac
}

# Start Qdrant server
qdrant_start() {
    local mode="local"
    local runtime_hours=48
    local memory_mb=32000
    local out_dir=""

    # Parse arguments
    parse_common_args "$@"

    # Parse qdrant-specific arguments from REMAINING_ARGS
    local i=0
    while [[ $i -lt ${#REMAINING_ARGS[@]} ]]; do
        case ${REMAINING_ARGS[$i]} in
            --mode)
                mode="${REMAINING_ARGS[$((i+1))]}"
                ((i+=2))
                ;;
            --runtime)
                runtime_hours="${REMAINING_ARGS[$((i+1))]}"
                ((i+=2))
                ;;
            --memory)
                memory_mb="${REMAINING_ARGS[$((i+1))]}"
                ((i+=2))
                ;;
            --out-dir)
                out_dir="${REMAINING_ARGS[$((i+1))]}"
                ((i+=2))
                ;;
            *)
                ((i++))
                ;;
        esac
    done

    # Resolve config
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")

    # Validate/prepare out_dir if provided
    if [[ -n "$out_dir" ]]; then
        # Make absolute path
        if [[ ! "$out_dir" = /* ]]; then
            out_dir="$(pwd)/$out_dir"
        fi

        # Handle existing directory with subdirectories
        if [[ -d "$out_dir/storage" ]] && [[ -d "$out_dir/snapshots" ]]; then
            log_info "Using existing Qdrant storage: $out_dir"
        elif [[ "$(basename $out_dir)" == "storage" ]]; then
            out_dir="$(dirname $out_dir)"
            log_info "Adjusted path to parent directory: $out_dir"
        else
            # Create directory structure for new storage
            log_info "Creating Qdrant storage directory: $out_dir"
            mkdir -p "$out_dir/storage"
            mkdir -p "$out_dir/snapshots"
        fi
    fi

    log_info "Starting Qdrant server (mode=${mode})"

    local base_dir=$(get_base_dir "$active_config")
    ensure_directories "$active_config"

    local timestamp=$(get_timestamp)

    # Get storage path from config (or use --out-dir if provided)
    local storage_path
    if [[ -n "$out_dir" ]]; then
        storage_path="$out_dir"
        log_info "Using specified storage: ${storage_path}"
    else
        storage_path=$(get_qdrant_storage_path "$active_config")
        log_info "Using configured storage: ${storage_path}"
    fi

    # Call start_server.sh
    bash modules/qdrant/scripts/start_server.sh \
        --container modules/qdrant/setup/singularity/qdrant.sif \
        --config config/qdrant_config.yaml \
        --storage "${storage_path}" \
        --memory-mb "${memory_mb}" \
        --runtime "$((runtime_hours * 3600))" \
        --job-name q_server \
        --mode "${mode}" \
        --connection-info "${storage_path}/connection_info.txt" \
        --log "${base_dir}/logs/qdrant/server_${timestamp}.log" \
        --out-dir "${storage_path}"

    if [[ $? -eq 0 ]]; then
        log_success "Qdrant server started successfully"
        if [[ -f "${storage_path}/connection_info.txt" ]]; then
            echo ""
            cat "${storage_path}/connection_info.txt"
        fi
    else
        log_error "Failed to start Qdrant server"
        exit 1
    fi
}

# Stop Qdrant server
qdrant_stop() {
    parse_common_args "$@"
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")
    local storage_path=$(get_qdrant_storage_path "$active_config")

    log_info "Stopping Qdrant server (storage=${storage_path})..."

    QDRANT_STORAGE_PATH="${storage_path}" \
    bash modules/qdrant/scripts/stop_server.sh
}

# Restart Qdrant with existing storage
qdrant_restart() {
    local storage_path="$1"

    # Use configured path if not provided
    if [[ -z "$storage_path" ]]; then
        storage_path=$(get_qdrant_storage_path)
        log_info "Using configured storage: $storage_path"
    fi

    # Validate path exists
    if [[ ! -d "$storage_path" ]]; then
        log_error "Storage directory not found: $storage_path"
        log_error "Run './bioyoda.sh qdrant start' first to create it"
        exit 1
    fi

    log_info "Restarting Qdrant with storage: $storage_path"

    # Stop current instance
    log_info "Stopping current Qdrant instance (if any)..."
    qdrant_stop 2>/dev/null || true
    sleep 2

    # Start with existing storage
    qdrant_start --out-dir "$storage_path"
}

# Check Qdrant status
qdrant_status() {
    parse_common_args "$@"
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")
    local storage_path=$(get_qdrant_storage_path "$active_config")

    QDRANT_STORAGE_PATH="${storage_path}" \
    bash modules/qdrant/scripts/check_status.sh
}

# Insert data to Qdrant
qdrant_insert() {
    if [[ $# -eq 0 ]]; then
        log_error "No dataset specified for insertion"
        echo ""
        echo "Available datasets:"
        echo "  pubmed              PubMed abstracts"
        echo "  clinical_trials     Clinical trials data"
        echo "  patents             All patents (text + compounds)"
        echo "  patents_text        Patents text only"
        echo "  patents_compounds   Patents compounds only"
        echo "  esm2                Protein embeddings"
        echo "  all                 All datasets"
        exit 1
    fi

    local dataset=$1
    shift

    # Parse arguments
    parse_common_args "$@"

    log_info "Inserting ${dataset} to Qdrant (mode=${EXECUTION_MODE})"

    check_snakemake || exit 1

    # Resolve config
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")

    # Auto-select GPU config if on cluster
    if [[ "$USE_TEST" != "true" ]] && [[ "$EXECUTION_MODE" == "cluster" ]]; then
        active_config=$(auto_select_gpu_config "$active_config" "$EXECUTION_MODE")
        if [[ "$active_config" == "config/config_gpu.yaml" ]]; then
            log_info "Auto-selected GPU config: config_gpu.yaml"
        fi
    fi

    local base_dir=$(get_base_dir "$active_config")
    ensure_directories "$active_config"

    local pid_dir="${base_dir}/logs/pids"
    local pid_base="${pid_dir}/qdrant_insert_${dataset}"
    local main_log="${base_dir}/logs/qdrant/insert_${dataset}_main.log"

    # Check if already running
    if ! check_not_running "${pid_base}.${EXECUTION_MODE}.pid" "Qdrant insertion ${dataset}"; then
        log_info "Use './bioyoda.sh qdrant stop-insert ${dataset}' to stop it first"
        exit 1
    fi

    # Log execution info
    local queue=$(get_queue_from_config "$active_config")
    if [[ "$EXECUTION_MODE" == "cluster" ]]; then
        log_cluster_info "$queue" "$JOBS"
    else
        log_local_info "$CORES"
    fi

    # Build Snakemake command
    local snakemake_cmd=$(build_qdrant_insert_command \
        "$active_config" \
        "$EXECUTION_MODE" \
        "$JOBS" \
        "$CORES" \
        "$USE_TEST" \
        "$dataset"
    )

    if [[ -z "$snakemake_cmd" ]]; then
        exit 1
    fi

    # Execute with tracking
    run_with_tracking \
        "$snakemake_cmd" \
        "$pid_base" \
        "$main_log" \
        "$BACKGROUND" \
        "$EXECUTION_MODE"

    if [[ "$BACKGROUND" == "true" ]]; then
        log_info "To stop: ./bioyoda.sh qdrant stop-insert ${dataset}"
        log_info "Rule logs directory: ${base_dir}/logs/qdrant/"
    fi
}

# Stop Qdrant insertion
qdrant_stop_insert() {
    if [[ $# -eq 0 ]]; then
        log_error "No dataset specified"
        echo ""
        echo "Available datasets:"
        echo "  pubmed, clinical_trials, patents, patents_text,"
        echo "  patents_compounds, esm2, all"
        exit 1
    fi

    local dataset=$1
    shift

    parse_common_args "$@"

    log_info "Stopping Qdrant insertion for ${dataset}..."

    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")
    local base_dir=$(get_base_dir "$active_config")
    local pid_base="${base_dir}/logs/pids/qdrant_insert_${dataset}"

    stop_process "$pid_base" "qdrant_insert_${dataset}" "$base_dir" "true"

    # Also clean Qdrant-specific locks
    rm -rf modules/qdrant/.snakemake/locks/ 2>/dev/null || true

    log_success "Stop completed"
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_qdrant "$@"
fi
