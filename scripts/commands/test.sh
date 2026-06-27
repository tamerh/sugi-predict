#!/bin/bash
##############################################################################
#
#   BioYoda Test Framework
#   Runs end-to-end tests with fixtures or full pipeline
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Test cleanup function
test_cleanup() {
    local base_dir="$1"
    log_info "Cleaning up test environment..."

    # Stop servers if running (api.sh removed when the API layer moved to sugi-agent)
    if [[ -f "${COMMANDS_DIR}/api.sh" ]]; then
        source "${COMMANDS_DIR}/api.sh"
        api_stop --test 2>/dev/null || true
    fi

    source "${COMMANDS_DIR}/qdrant.sh"
    qdrant_stop --test 2>/dev/null || true
}

# Main test function
# Two-tier test runner. Default = tier 1 (pipeline on small fixtures). --integration = tier 2 (live full DB).
cmd_test() {
    local py="/data/miniconda3/envs/bioyoda/bin/python"; [[ -x "$py" ]] || py="python3"
    local root="${COMMANDS_DIR}/../.." tier="pipeline"
    while [[ $# -gt 0 ]]; do
        case $1 in
            --integration) tier="integration"; shift ;;
            --pipeline)    tier="pipeline";    shift ;;
            --atlas)       tier="atlas";       shift ;;
            --help|-h)
                cat <<USAGE
Usage: bioyoda.sh test [--integration|--atlas]
  (default)       tier 1 — full pipeline on SMALL fixtures -> *_test collections (no GPU). Pre-commit gate.
  --integration   tier 2 — READ-ONLY regression vs the LIVE full DB (green, counts, known answers). Pre/post-update gate.
  --atlas         legacy atlas build-chain component tests (bake/targets).
USAGE
                return 0 ;;
            *) log_error "Unknown argument: $1"; return 1 ;;
        esac
    done
    local fail=0 t
    case $tier in
        pipeline)    log_info "Test tier 1 — pipeline on small fixtures (-> *_test collections, no GPU)"
                     for t in "$root"/tests/pipeline/test_*.py; do log_info "  $(basename "$t")"; "$py" "$t" || fail=1; done ;;
        integration) log_info "Test tier 2 — regression vs the LIVE full DB (read-only)"
                     for t in "$root"/tests/integration/test_*.py; do log_info "  $(basename "$t")"; "$py" "$t" || fail=1; done ;;
        atlas)       "$py" "$root/tests/test_atlas_bake.py" || fail=1; "$py" "$root/tests/test_atlas_targets.py" || fail=1 ;;
    esac
    if [[ $fail -eq 0 ]]; then log_info "✓ all $tier tests passed"; else log_error "$tier tests FAILED"; return 1; fi
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_test "$@"
fi
