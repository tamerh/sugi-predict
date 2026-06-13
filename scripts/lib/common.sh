#!/bin/bash
##############################################################################
#
#   BioYoda Common Utilities
#   Shared functions, argument parsing, and prerequisite checks
#
##############################################################################

# Determine script directory (where this file lives)
if [[ -z "${LIB_DIR:-}" ]]; then
    LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Source other library files
source "${LIB_DIR}/logging.sh"
source "${LIB_DIR}/config.sh"
source "${LIB_DIR}/process.sh"

# Delete-guard: refuse to rm a path that is empty, a filesystem/repo root, or that
# resolves inside a PROTECTED root (raw_data/, qdrant/, snapshots/). Catches the
# classic misfire where an unset base_dir turns `rm -rf "$base_dir/data/.."` into
# `rm -rf "/data/.."`, and stops any clean target from ever reaching the
# irreplaceable raw_data, the live qdrant DB, or the published snapshots.
# Usage: assert_deletable "<path-to-be-deleted>"   (call BEFORE the rm)
assert_deletable() {
    local target="$1"
    local repo_root="${PIPELINE_DIR:-$(pwd)}"
    if [[ -z "$target" || "$target" == "/" || "$target" == "/data" \
          || "$target" == "$repo_root" || "$target" == "$repo_root/" ]]; then
        log_error "DELETE-GUARD: refusing unsafe delete target: '${target}'"
        exit 1
    fi
    local abs; abs="$(readlink -f "$target" 2>/dev/null || echo "$target")"
    local prot
    for prot in raw_data qdrant snapshots; do
        local pabs; pabs="$(readlink -f "${repo_root}/${prot}" 2>/dev/null || echo "${repo_root}/${prot}")"
        if [[ "$abs" == "$pabs" || "$abs" == "$pabs/"* ]]; then
            log_error "DELETE-GUARD: refusing to delete PROTECTED path '${target}' (resolves under ${prot}/)"
            exit 1
        fi
    done
}

# Global variables set by argument parsing
declare -g EXECUTION_MODE="local"
declare -g CORES=1
declare -g JOBS=100
declare -g CUSTOM_CONFIG=""
declare -g USE_TEST=false
declare -g BACKGROUND=false
declare -g UPDATE_MODE="full"
declare -g DRYRUN=""
declare -g REMAINING_ARGS=()

# Parse common arguments used across multiple commands
# Usage: parse_common_args "$@"
# Sets global variables: EXECUTION_MODE, CORES, JOBS, CUSTOM_CONFIG, USE_TEST, BACKGROUND, UPDATE_MODE, DRYRUN, REMAINING_ARGS, PROCESS_TARGET
parse_common_args() {
    # Reset globals
    EXECUTION_MODE="local"
    CORES=1
    JOBS=100
    CUSTOM_CONFIG=""
    USE_TEST=false
    BACKGROUND=false
    UPDATE_MODE="full"
    DRYRUN=""
    PROCESS_TARGET=""
    REMAINING_ARGS=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --local)
                # Accepted for back-compat; local is the only mode now
                # (SGE/cluster retired in the Enju migration).
                EXECUTION_MODE="local"
                shift
                ;;
            --cores)
                CORES="$2"
                shift 2
                ;;
            --config)
                CUSTOM_CONFIG="$2"
                shift 2
                ;;
            --test)
                USE_TEST=true
                shift
                ;;
            --bg|-b)
                BACKGROUND=true
                shift
                ;;
            --mode)
                UPDATE_MODE="$2"
                shift 2
                ;;
            --dryrun|--dry-run|-n)
                DRYRUN="-n"
                shift
                ;;
            --compounds-only)
                PROCESS_TARGET="patents_compounds_only"
                shift
                ;;
            --text-only)
                PROCESS_TARGET="patents_text_only"
                shift
                ;;
            --biobtree)
                PROCESS_TARGET="patents_biobtree"
                shift
                ;;
            --)
                # Stop parsing options, collect rest as remaining args
                shift
                while [[ $# -gt 0 ]]; do
                    REMAINING_ARGS+=("$1")
                    shift
                done
                break
                ;;
            *)
                REMAINING_ARGS+=("$1")
                shift
                ;;
        esac
    done
}

# Check if conda environment exists
# Usage: check_conda_env [env_name]
check_conda_env() {
    local env_name="${1:-$DEFAULT_CONDA_ENV}"

    if ! conda env list 2>/dev/null | grep -q "^${env_name} "; then
        log_error "Conda environment '${env_name}' not found!"
        log_info "Please create it with: conda env create -f tamer.yml"
        return 1
    fi
    return 0
}

# Check if snakemake is available
check_snakemake() {
    if ! command -v snakemake &> /dev/null; then
        log_error "Snakemake not found!"
        log_info "Please activate conda environment first: conda activate ${DEFAULT_CONDA_ENV}"
        log_info "If snakemake not installed: mamba install -n ${DEFAULT_CONDA_ENV} -c bioconda snakemake"
        return 1
    fi
    return 0
}

# Check if graphviz dot is available
check_graphviz() {
    if ! command -v dot &> /dev/null; then
        log_error "Graphviz 'dot' command not found."
        log_info "Install with: conda install graphviz"
        return 1
    fi
    return 0
}

# Check if a command exists
# Usage: require_command <command_name> [install_hint]
require_command() {
    local cmd="$1"
    local hint="${2:-}"

    if ! command -v "$cmd" &> /dev/null; then
        log_error "Required command not found: $cmd"
        if [[ -n "$hint" ]]; then
            log_info "$hint"
        fi
        return 1
    fi
    return 0
}

# Wait for a URL to become available
# Usage: wait_for_url <url> [timeout_seconds] [check_interval]
wait_for_url() {
    local url="$1"
    local timeout="${2:-30}"
    local interval="${3:-1}"
    local elapsed=0

    while [[ $elapsed -lt $timeout ]]; do
        if curl -s "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    return 1
}

# Generate a timestamp string
get_timestamp() {
    date +%Y%m%d_%H%M%S
}

# Confirm action with user
# Usage: confirm_action <message> [default_yes]
confirm_action() {
    local message="$1"
    local default_yes="${2:-false}"

    if [[ "$default_yes" == "true" ]]; then
        log_warning "${message} (Y/n)"
        read -r response
        [[ ! "$response" =~ ^[Nn]$ ]]
    else
        log_warning "${message} (y/N)"
        read -r response
        [[ "$response" =~ ^[Yy]$ ]]
    fi
}

# Print version information
print_version() {
    echo "BioYoda v${BIOYODA_VERSION}"
}

# Safely change to pipeline directory and back
# Usage: with_pipeline_dir <command>
# This function ensures we run commands from the pipeline directory
run_in_pipeline_dir() {
    local original_dir="$PWD"
    cd "${PIPELINE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../..}"
    eval "$@"
    local exit_code=$?
    cd "$original_dir"
    return $exit_code
}
