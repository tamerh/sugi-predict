#!/bin/bash
##############################################################################
#
#   BioYoda Run Command
#   Executes data processing pipelines (PubMed, Clinical Trials, etc.)
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"
source "${COMMANDS_DIR}/../lib/snakemake.sh"

# Main run function
# Usage: cmd_run [module] [options]
cmd_run() {
    local module="all"

    # Parse arguments
    parse_common_args "$@"

    # Get module from remaining args
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
        module="${REMAINING_ARGS[0]}"
    fi

    # Resolve configuration
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")

    # Auto-select GPU config if on cluster and not test mode
    if [[ "$USE_TEST" != "true" ]] && [[ "$EXECUTION_MODE" == "cluster" ]]; then
        active_config=$(auto_select_gpu_config "$active_config" "$EXECUTION_MODE")
        if [[ "$active_config" == "config/config_gpu.yaml" ]]; then
            log_info "Auto-selected GPU config: config_gpu.yaml (queue=gpu detected)"
        fi
    fi

    log_info "Running BioYoda pipeline: module=${module}, mode=${EXECUTION_MODE}, update_mode=${UPDATE_MODE}, config=${active_config}"

    # Check prerequisites
    check_conda_env || exit 1
    check_snakemake || exit 1

    # Get base_dir and ensure directories exist
    local base_dir=$(get_base_dir "$active_config")
    ensure_directories "$active_config"

    local pid_dir="${base_dir}/logs/pids"
    local pid_base="${pid_dir}/${module}"
    local main_log="${base_dir}/logs/bioyoda_${module}_main.log"

    # Check if already running
    if ! check_not_running "${pid_base}.${EXECUTION_MODE}.pid" "Pipeline ${module}"; then
        log_info "Use './bioyoda.sh stop ${module}' to stop it first"
        exit 1
    fi

    # Delete checkpoint markers for clinical_trials to force re-evaluation
    if [[ "$module" == "clinical_trials" ]] || [[ "$module" == "all" ]]; then
        local state_dir="${base_dir}/state/clinical_trials"
        mkdir -p "${state_dir}"
        rm -f "${state_dir}/.download_extract_done"
        log_info "Deleted checkpoint marker to force re-evaluation..."
    fi

    # Log execution info
    local queue=$(get_queue_from_config "$active_config")
    if [[ "$EXECUTION_MODE" == "cluster" ]]; then
        log_cluster_info "$queue" "$CUDA_VERSION" "$JOBS"
    else
        log_local_info "$CORES"
    fi

    # Build Snakemake command
    local snakemake_cmd=$(build_pipeline_command \
        "$DEFAULT_SNAKEFILE" \
        "$active_config" \
        "$EXECUTION_MODE" \
        "$JOBS" \
        "$CORES" \
        "$CUDA_VERSION" \
        "$USE_TEST" \
        "$UPDATE_MODE" \
        "$DRYRUN" \
        "$module"
    )

    # Execute with tracking
    run_with_tracking \
        "$snakemake_cmd" \
        "$pid_base" \
        "$main_log" \
        "$BACKGROUND" \
        "$EXECUTION_MODE"
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_run "$@"
fi
