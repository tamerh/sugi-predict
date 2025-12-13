#!/bin/bash
##############################################################################
#
#   BioYoda Maintenance Commands
#   Status, clean, validate, dryrun, dag, unlock, and stop commands
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Default snakefile for operations
DEFAULT_SNAKEFILE="modules/Snakefile"

# Show pipeline status
cmd_status() {
    log_info "Checking BioYoda pipeline status..."

    local base_dir=$(get_base_dir)

    # PubMed status
    log_section "PubMed Module"
    if [[ -f "${base_dir}/data/merged/pubmed/master_pubmed.index" ]]; then
        local size=$(du -h "${base_dir}/data/merged/pubmed/master_pubmed.index" | cut -f1)
        log_success "Merged index exists (${size})"
    else
        log_warning "Merged index not found"
    fi

    local processed_count=$(find "${base_dir}/data/processed/pubmed" -name "*.index" 2>/dev/null | wc -l)
    log_info "Processed files: ${processed_count}"

    # Check for running cluster jobs
    if command -v qstat &> /dev/null; then
        local running_jobs
        running_jobs=$(qstat 2>/dev/null | grep -c bioyoda 2>/dev/null || true)
        running_jobs=${running_jobs:-0}
        if [[ "$running_jobs" =~ ^[0-9]+$ ]] && [[ "$running_jobs" -gt 0 ]]; then
            log_info "Running cluster jobs: ${running_jobs}"
        fi
    fi

    # Clinical Trials status
    log_section "Clinical Trials Module"
    if [[ -f "${base_dir}/data/processed/clinical_trials/trials_data.json" ]]; then
        local size=$(du -h "${base_dir}/data/processed/clinical_trials/trials_data.json" | cut -f1)
        log_success "Trials data exists (${size})"
    else
        log_warning "Trials data not found"
    fi

    # Qdrant status
    log_section "Qdrant Module"
    if [[ -f "${base_dir}/data/qdrant/connection_info.txt" ]]; then
        log_success "Qdrant server connection info found"
        grep QDRANT_URL "${base_dir}/data/qdrant/connection_info.txt" || true
    else
        log_info "Qdrant server not running"
    fi

    # Check collections
    for collection in pubmed_abstracts clinical_trials; do
        if [[ -f "${base_dir}/data/qdrant/collections/${collection}.done" ]]; then
            log_success "${collection} collection complete"
        else
            log_info "${collection} collection not completed"
        fi
    done

    # Storage size
    if [[ -d "${base_dir}/data/qdrant/storage" ]]; then
        local qdrant_size=$(du -sh "${base_dir}/data/qdrant/storage" 2>/dev/null | cut -f1)
        log_info "Qdrant storage size: ${qdrant_size}"
    fi
}

# Validate module outputs
cmd_validate() {
    local module="${1:-pubmed}"
    local base_dir=$(get_base_dir)

    log_info "Validating module: ${module}"

    case $module in
        pubmed)
            if [[ ! -f "${base_dir}/data/merged/pubmed/master_pubmed.index" ]]; then
                log_error "PubMed index not found. Run pipeline first."
                exit 1
            fi

            snakemake --snakefile "$DEFAULT_SNAKEFILE" --configfile "$DEFAULT_CONFIG" \
                pubmed_validate --cores 1 --use-conda

            if [[ -f "${base_dir}/data/merged/pubmed/validation_report.txt" ]]; then
                echo ""
                cat "${base_dir}/data/merged/pubmed/validation_report.txt"
            fi
            ;;
        qdrant)
            if [[ ! -f "${base_dir}/data/qdrant/connection_info.txt" ]]; then
                log_error "Qdrant server not running or connection info not found."
                exit 1
            fi

            log_info "Checking Qdrant collections..."
            source "${base_dir}/data/qdrant/connection_info.txt"

            log_info "Querying Qdrant at: $QDRANT_URL"
            curl -s "$QDRANT_URL/collections" | python -m json.tool 2>/dev/null || log_warning "Failed to connect to Qdrant"

            # Check specific collections
            for collection in pubmed_abstracts clinical_trials; do
                if curl -s "$QDRANT_URL/collections/${collection}" >/dev/null 2>&1; then
                    log_success "${collection} collection accessible"
                    curl -s "$QDRANT_URL/collections/${collection}" | python -m json.tool 2>/dev/null | grep -E "(points_count|status)" || true
                fi
            done
            ;;
        *)
            log_error "Unknown module: ${module}"
            exit 1
            ;;
    esac
}

# Clean intermediate files
cmd_clean() {
    local module="${1:-all}"
    local base_dir=$(get_base_dir)

    if ! confirm_action "This will remove intermediate files. Continue?"; then
        log_info "Cancelled"
        exit 0
    fi

    case $module in
        pubmed)
            log_info "Cleaning PubMed processed files..."
            rm -rf "${base_dir}/data/processed/pubmed/"*
            log_success "PubMed cleaned"
            ;;
        clinical_trials)
            log_info "Cleaning Clinical Trials processed files..."
            rm -rf "${base_dir}/data/processed/clinical_trials/"*
            log_success "Clinical Trials cleaned"
            ;;
        qdrant)
            log_info "Cleaning Qdrant storage and collections..."
            rm -rf "${base_dir}/data/qdrant/storage/"*
            rm -f "${base_dir}/data/qdrant/connection_info.txt"
            rm -f "${base_dir}/data/qdrant/collections/"*.done
            log_success "Qdrant cleaned"
            ;;
        all)
            log_info "Cleaning all processed files..."
            rm -rf "${base_dir}/data/processed/"*
            rm -rf "${base_dir}/data/qdrant/storage/"*
            rm -f "${base_dir}/data/qdrant/connection_info.txt"
            rm -f "${base_dir}/data/qdrant/collections/"*.done
            log_success "All modules cleaned"
            ;;
        *)
            log_error "Unknown module: ${module}"
            exit 1
            ;;
    esac
}

# Dry run to see what would execute
cmd_dryrun() {
    local module="${1:-all}"

    log_info "Performing dry run for module: ${module}"

    check_snakemake || exit 1

    local target=""
    if [[ "$module" != "all" ]]; then
        target="-- ${module}"
    fi

    snakemake --snakefile "$DEFAULT_SNAKEFILE" --configfile "$DEFAULT_CONFIG" \
        --dryrun --printshellcmds $target
}

# Generate workflow DAG
cmd_dag() {
    local module="${1:-all}"
    local output_file="workflow_dag.pdf"

    log_info "Generating DAG for module: ${module}"

    check_snakemake || exit 1
    check_graphviz || exit 1

    local target=""
    if [[ "$module" != "all" ]]; then
        target="-- ${module}"
    fi

    snakemake --snakefile "$DEFAULT_SNAKEFILE" --configfile "$DEFAULT_CONFIG" \
        --dag $target | dot -Tpdf > "$output_file"

    log_success "DAG saved to: ${output_file}"
}

# Unlock working directory
cmd_unlock() {
    log_info "Unlocking working directory..."

    snakemake --snakefile "$DEFAULT_SNAKEFILE" --configfile "$DEFAULT_CONFIG" --unlock

    log_success "Directory unlocked"
}

# Stop a running pipeline
cmd_stop() {
    local module=""
    local clean=false

    # Parse arguments
    parse_common_args "$@"

    # Get module from remaining args
    if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
        module="${REMAINING_ARGS[0]}"
    fi

    # Check for --clean in remaining args
    for arg in "${REMAINING_ARGS[@]}"; do
        if [[ "$arg" == "--clean" ]] || [[ "$arg" == "-c" ]]; then
            clean=true
        fi
    done

    # Default to pubmed if no module specified
    if [[ -z "$module" ]] || [[ "$module" == "--clean" ]] || [[ "$module" == "-c" ]]; then
        module="pubmed"
    fi

    log_info "Stopping BioYoda pipeline: module=${module}"

    # Determine base_dir
    local base_dir
    if [[ "$USE_TEST" == "true" ]]; then
        base_dir="test_out"
    else
        base_dir=$(get_base_dir)
    fi

    local pid_base="${base_dir}/logs/pids/${module}"

    stop_process "$pid_base" "$module" "$base_dir" "true"

    # Optional: clean intermediate files
    if [[ "$clean" == "true" ]]; then
        log_warning "Cleaning intermediate files for ${module}..."
        rm -rf "${base_dir}/data/processed/${module}/"* 2>/dev/null || true
        log_success "Intermediate files cleaned"
    fi

    log_success "Stop completed"
}

# Quick start: start both Qdrant and API
cmd_start_all() {
    parse_common_args "$@"

    log_divider
    log_info "Starting BioYoda servers (Qdrant + API)"
    log_divider
    echo ""

    # Step 1: Start Qdrant
    log_info "Step 1/2: Starting Qdrant server"
    source "${COMMANDS_DIR}/qdrant.sh"
    qdrant_start --mode local $(if [[ "$USE_TEST" == "true" ]]; then echo "--test"; fi) || {
        log_error "Failed to start Qdrant server"
        exit 1
    }

    # Wait for Qdrant
    log_info "  Waiting for Qdrant to be ready..."
    if ! wait_for_url "http://localhost:6333/healthz" 10; then
        log_error "Qdrant server not responding"
        exit 1
    fi
    log_success "Qdrant server ready"
    echo ""

    # Step 2: Start API
    log_info "Step 2/2: Starting API server"
    source "${COMMANDS_DIR}/api.sh"
    api_start --bg $(if [[ "$USE_TEST" == "true" ]]; then echo "--test"; fi) || {
        log_error "Failed to start API server"
        log_warning "Cleaning up: stopping Qdrant..."
        qdrant_stop 2>/dev/null || true
        exit 1
    }

    echo ""
    log_divider
    log_success "BioYoda servers started successfully!"
    log_divider
    echo ""
    log_info "Services:"
    log_info "  - Qdrant: http://localhost:6333"
    log_info "  - API: http://localhost:8000"
    log_info "  - API Docs: http://localhost:8000/docs"
    echo ""
    log_info "To stop: ./bioyoda.sh stop"
}

# Quick stop: stop both API and Qdrant
cmd_stop_all() {
    parse_common_args "$@"

    log_divider
    log_info "Stopping BioYoda servers (API + Qdrant)"
    log_divider
    echo ""

    # Step 1: Stop API first (it depends on Qdrant)
    log_info "Step 1/2: Stopping API server"
    source "${COMMANDS_DIR}/api.sh"
    api_stop $(if [[ "$USE_TEST" == "true" ]]; then echo "--test"; fi) 2>/dev/null || true
    sleep 1
    echo ""

    # Step 2: Stop Qdrant
    log_info "Step 2/2: Stopping Qdrant server"
    source "${COMMANDS_DIR}/qdrant.sh"
    qdrant_stop $(if [[ "$USE_TEST" == "true" ]]; then echo "--test"; fi) 2>/dev/null || true
    sleep 1

    echo ""
    log_divider
    log_success "BioYoda servers stopped"
    log_divider
}
