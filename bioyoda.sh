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
#   # Quick start/stop Qdrant server
#   ./bioyoda.sh start
#   ./bioyoda.sh stop
#
#   # Data processing pipelines
#   ./bioyoda.sh enju pubmed                            # Run as an Enju DAG (preferred)
#   ./bioyoda.sh enju clinical_trials                   # Enju DAG: prepare -> fan-out -> merge
#   ./bioyoda.sh run pubmed --local                     # Run via local Snakemake
#   ./bioyoda.sh run pubmed --test --local              # Test with small dataset
#   (SGE/cluster execution retired — Enju distributes across citizens, not qsub)
#
#   # Qdrant vector database
#   ./bioyoda.sh qdrant start                                      # Start locally
#   ./bioyoda.sh qdrant start --mode cluster --queue gpu --runtime 168
#   ./bioyoda.sh qdrant start --out-dir /path/to/existing/storage  # Use existing data
#   ./bioyoda.sh qdrant restart                                    # Auto-detect and restart
#   ./bioyoda.sh qdrant insert pubmed                              # Insert data (local)
#   ./bioyoda.sh qdrant stop-insert pubmed                         # Stop insertion
#   ./bioyoda.sh qdrant status                                     # Check status
#   ./bioyoda.sh qdrant stop                                       # Stop server
#
#   # Testing
#   ./bioyoda.sh test                                   # Fast fixture mode
#   ./bioyoda.sh test --pipeline                        # Full E2E test
#
#   # Snapshots (isolated production copies)
#   ./bioyoda.sh snapshot --name prod_v1.0
#   cd snapshots/prod_v1.0/code && ./bioyoda.sh enju all
#
#   # Google Drive sync (for Colab GPU processing)
#   ./bioyoda.sh push patents                           # Push data + code to Drive
#   ./bioyoda.sh push patents --code-only              # Push only scripts (fast)
#   ./bioyoda.sh push clinical_trials --code-only      # Push clinical trials scripts
#   ./bioyoda.sh push pubmed --dry-run                 # Preview what would sync
#   ./bioyoda.sh pull patents                           # Pull processed results
#   ./bioyoda.sh pull clinical_trials                   # Pull clinical trials results
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
                echo "  bioyoda.sh start              # Start Qdrant server"
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

        # Data processing (Snakemake, local)
        run)
            source "${SCRIPT_DIR}/commands/run.sh"
            cmd_run "$@"
            ;;

        # Data processing (Enju DAG — distribution via citizens, not SGE)
        enju)
            source "${SCRIPT_DIR}/commands/enju.sh"
            cmd_enju "$@"
            ;;

        # Google Drive sync (for GPU processing)
        push)
            source "${SCRIPT_DIR}/commands/sync.sh"
            cmd_push "$@"
            ;;

        pull)
            source "${SCRIPT_DIR}/commands/sync.sh"
            cmd_pull "$@"
            ;;

        # Qdrant management
        qdrant)
            source "${SCRIPT_DIR}/commands/qdrant.sh"
            cmd_qdrant "$@"
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
