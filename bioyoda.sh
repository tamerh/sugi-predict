#!/bin/bash
##############################################################################
#
#   BioYoda Main Entry Point
#   AI-powered biomedical search system
#
#   This is the main orchestration script that dispatches commands to
#   modular command handlers in scripts/commands/
#
##############################################################################
#
# EXAMPLES:
#
#   # Quick start/stop servers (Qdrant + API)
#   ./bioyoda.sh start
#   ./bioyoda.sh stop
#
#   # Data processing pipelines
#   ./bioyoda.sh run pubmed --local                     # Run locally
#   ./bioyoda.sh run pubmed --cluster --bg --jobs 50    # Run on cluster in background
#   ./bioyoda.sh run all --cluster --bg --jobs 100      # Run all modules
#   ./bioyoda.sh run pubmed --test --local              # Test with small dataset
#   ./bioyoda.sh run pubmed --cluster --bg --cuda11.4   # GPU cluster with CUDA 11.4
#
#   # Qdrant vector database
#   ./bioyoda.sh qdrant start                                      # Start locally
#   ./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168
#   ./bioyoda.sh qdrant start --out-dir /path/to/existing/storage  # Use existing data
#   ./bioyoda.sh qdrant restart                                    # Auto-detect and restart
#   ./bioyoda.sh qdrant insert pubmed --cluster --jobs 10 --bg     # Insert data
#   ./bioyoda.sh qdrant stop-insert pubmed                         # Stop insertion
#   ./bioyoda.sh qdrant status                                     # Check status
#   ./bioyoda.sh qdrant stop                                       # Stop server
#
#   # API server
#   ./bioyoda.sh api start --bg                         # Start in background
#   ./bioyoda.sh api start --port 8080 --reload         # Dev mode with auto-reload
#   ./bioyoda.sh api status                             # Check status
#   ./bioyoda.sh api stop                               # Stop server
#
#   # Search
#   ./bioyoda.sh search "CRISPR gene editing"           # Quick search
#   ./bioyoda.sh search                                 # Interactive mode
#
#   # Testing
#   ./bioyoda.sh test                                   # Fast fixture mode
#   ./bioyoda.sh test --pipeline                        # Full E2E test
#
#   # Snapshots (isolated production copies)
#   ./bioyoda.sh snapshot --name prod_v1.0
#   cd snapshots/prod_v1.0/code && ./bioyoda.sh run all --cluster --bg
#
#   # Maintenance
#   ./bioyoda.sh status                                 # Pipeline status
#   ./bioyoda.sh validate pubmed                        # Validate outputs
#   ./bioyoda.sh clean pubmed                           # Clean intermediate files
#   ./bioyoda.sh stop pubmed --clean                    # Stop and clean
#   ./bioyoda.sh dryrun pubmed                          # Show what would run
#   ./bioyoda.sh dag pubmed                             # Generate workflow DAG
#   ./bioyoda.sh unlock                                 # Unlock after crash
#
#   # Help
#   ./bioyoda.sh help                                   # Show full help
#   ./bioyoda.sh qdrant help                            # Qdrant-specific help
#   ./bioyoda.sh api help                               # API-specific help
#
##############################################################################

set -eo pipefail

# Capture working directory and determine script location
USER_DIR="$PWD"
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SCRIPT_DIR="${PIPELINE_DIR}/scripts"
export PIPELINE_DIR SCRIPT_DIR USER_DIR

# Conda/Mamba setup - ensure conda command is available in non-interactive shells
# Clear any stale conda environment state from previous sessions
unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER
export CONDA_SHLVL=0
# Remove any stale micromamba paths from PATH
export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v '/data/micromamba' | tr '\n' ':' | sed 's/:$//')
if [[ -d "/data/miniconda3/bin" ]]; then
    export PATH="/data/miniconda3/bin:$PATH"
    # Source conda initialization for proper environment handling
    if [[ -f "/data/miniconda3/etc/profile.d/conda.sh" ]]; then
        source "/data/miniconda3/etc/profile.d/conda.sh"
        # Activate the bioyoda environment
        conda activate bioyoda 2>/dev/null || true
    fi
fi

# Change to pipeline directory for consistent relative paths
cd "$PIPELINE_DIR"

# Cleanup handler - return to user directory on exit
cleanup() {
    local rc=$?
    cd "$USER_DIR"
    exit $rc
}
trap cleanup SIGINT EXIT

# Source common libraries
source "${SCRIPT_DIR}/lib/common.sh"

##############################################################################
# Main Command Dispatcher
##############################################################################

main() {
    if [[ $# -eq 0 ]]; then
        log_error "No command specified"
        echo ""
        cat "${SCRIPT_DIR}/help/usage.txt"
        exit 1
    fi

    local command="$1"
    shift

    case "$command" in
        # Quick start/stop for servers
        start)
            if [[ $# -gt 0 ]] && [[ "$1" != "--"* ]]; then
                log_error "Unknown module: $1"
                echo ""
                echo "Did you mean:"
                echo "  bioyoda.sh start              # Start Qdrant and API servers"
                echo "  bioyoda.sh run $1             # Run data processing pipeline"
                exit 1
            fi
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_start_all "$@"
            ;;

        stop)
            if [[ $# -gt 0 ]] && [[ "$1" != "--"* ]]; then
                # Stopping a pipeline module
                source "${SCRIPT_DIR}/commands/maintenance.sh"
                cmd_stop "$@"
            else
                # Stop servers
                source "${SCRIPT_DIR}/commands/maintenance.sh"
                cmd_stop_all "$@"
            fi
            ;;

        # Data processing
        run)
            source "${SCRIPT_DIR}/commands/run.sh"
            cmd_run "$@"
            ;;

        # Qdrant management
        qdrant)
            source "${SCRIPT_DIR}/commands/qdrant.sh"
            cmd_qdrant "$@"
            ;;

        # API management
        api)
            source "${SCRIPT_DIR}/commands/api.sh"
            cmd_api "$@"
            ;;

        # Quick search (alias for api search)
        search)
            if [[ $# -eq 0 ]]; then
                python "${PIPELINE_DIR}/modules/api/scripts/bioyoda_search.py" --interactive
            else
                python "${PIPELINE_DIR}/modules/api/scripts/bioyoda_search.py" "$@"
            fi
            ;;

        # Testing
        test)
            source "${SCRIPT_DIR}/commands/test.sh"
            cmd_test "$@"
            ;;

        # Snapshot creation
        snapshot)
            source "${SCRIPT_DIR}/commands/snapshot.sh"
            cmd_snapshot "$@"
            ;;

        # Maintenance commands
        status)
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_status "$@"
            ;;

        validate)
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_validate "$@"
            ;;

        clean)
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_clean "$@"
            ;;

        dryrun)
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_dryrun "$@"
            ;;

        dag)
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_dag "$@"
            ;;

        unlock)
            source "${SCRIPT_DIR}/commands/maintenance.sh"
            cmd_unlock "$@"
            ;;

        # Help and version
        help|--help|-h)
            cat "${SCRIPT_DIR}/help/usage.txt"
            ;;

        version|--version|-v)
            print_version
            ;;

        *)
            log_error "Unknown command: $command"
            echo ""
            cat "${SCRIPT_DIR}/help/usage.txt"
            exit 1
            ;;
    esac
}

main "$@"
