#!/bin/bash
##############################################################################
#
#   BioYoda Enju Driver
#   Run a module's pipeline as an Enju DAG (replaces the retired Snakemake
#   cluster path). Enju compute tasks can't emit dynamic lists, so the driver
#   resolves the fan-out list (by running the module's `prepare` step) and then
#   `enju go`s the workflow with that list as a param-file.
#
#   Usage:
#     ./bioyoda.sh enju <module>
#     modules: clinical_trials | pubmed | diamond | patents | esm2 | qdrant-insert
#
##############################################################################

COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Resolve the enju binary: $ENJU_BIN -> PATH -> known install locations.
_find_enju() {
    if [[ -n "${ENJU_BIN:-}" ]]; then echo "$ENJU_BIN"; return; fi
    if command -v enju >/dev/null 2>&1; then echo "enju"; return; fi
    local c
    for c in /data/enju/enju /usr/local/bin/enju "$HOME/.local/bin/enju"; do
        [[ -x "$c" ]] && { echo "$c"; return; }
    done
    echo ""
}

# Read stdin lines -> compact JSON array of strings.
_json_array() {
    python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))"
}

cmd_enju() {
    local module="${1:-}"
    if [[ -z "$module" || "$module" == "--help" || "$module" == "-h" ]]; then
        echo "Usage: bioyoda.sh enju <module>"
        echo "  modules: clinical_trials | pubmed | diamond | patents | esm2 | qdrant-insert"
        echo ""
        echo "Runs the module's Enju workflow (workflows/<module>-poc/enju.yaml) end-to-end."
        echo "Distribution is handled by Enju, not SGE — assign GPU tasks to a GPU citizen."
        return 0
    fi

    local ENJU; ENJU="$(_find_enju)"
    if [[ -z "$ENJU" ]]; then
        log_error "enju binary not found. Install it or set ENJU_BIN=/path/to/enju"
        exit 1
    fi

    local root="${PIPELINE_DIR:-/data/bioyoda}"
    export BIOYODA_ROOT="$root"
    cd "$root"

    # `enju go --run-branch` leaves the worktree on the run branch; the next
    # create_run refuses unless we're back on the project default. Return to it
    # first. (Safe: code is committed; test_out/ is gitignored.)
    local default_branch
    default_branch=$(git -C "$root" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
    default_branch="${default_branch:-main}"
    if [[ "$(git -C "$root" branch --show-current)" != "$default_branch" ]]; then
        git -C "$root" checkout "$default_branch" >/dev/null 2>&1 \
            || { log_error "Could not checkout ${default_branch} (uncommitted changes on a run branch?)"; exit 1; }
    fi

    local wf="" param="" list=""

    case "$module" in
        clinical_trials|ct)
            wf="workflows/ct-poc/enju.yaml"; param="chunks"
            bash workflows/ct-poc/scripts/prepare.sh >&2
            list=$(ls test_out/ct_poc/raw_data/clinical_trials/chunked/trials_chunk_*.json \
                   | sed 's#.*/trials_chunk_##; s#\.json$##' | _json_array)
            ;;
        pubmed)
            wf="workflows/pubmed-poc/enju.yaml"; param="files"
            bash workflows/pubmed-poc/scripts/prepare.sh >&2
            list=$(ls test_out/pubmed_poc/raw/baseline/*.xml.gz \
                   | xargs -n1 basename | sed 's#\.xml\.gz$##' | _json_array)
            ;;
        diamond)
            wf="workflows/diamond-poc/enju.yaml"; param="chunks"
            bash workflows/diamond-poc/scripts/prepare.sh >&2
            list=$(ls test_out/diamond_poc/chunks/chunk_*.fasta \
                   | sed 's#.*/chunk_##; s#\.fasta$##' | _json_array)
            ;;
        esm2)
            wf="workflows/esm2-poc/enju.yaml"; param="h5chunks"
            bash workflows/esm2-poc/scripts/prepare.sh >&2
            list=$(ls test_out/esm2_poc/embeddings/*.h5 \
                   | sed 's#.*reference_embeddings_chunk_##; s#\.h5$##' | _json_array)
            ;;
        patents)
            wf="workflows/patents-poc/enju.yaml"; param="compound_chunks"
            list='["0002","0005"]'   # real-data compound chunk slice (PoC)
            ;;
        qdrant-insert|qdrant_insert)
            wf="workflows/qdrant-insert-poc/enju.yaml"; param="collections"
            list='["pubmed","esm2"]'
            ;;
        *)
            log_error "Unknown module: $module"
            echo "  modules: clinical_trials | pubmed | diamond | patents | esm2 | qdrant-insert"
            exit 1
            ;;
    esac

    if [[ -z "$list" || "$list" == "[]" ]]; then
        log_error "Could not resolve fan-out list for ${module} (prepare produced nothing?)"
        exit 1
    fi

    # Write a params file (avoids the comma-in-JSON-value issue with inline --params).
    local params_file; params_file="$(mktemp)"
    printf '{"%s": %s}\n' "$param" "$list" > "$params_file"

    log_info "Enju run: module=${module} workflow=${wf} ${param}=${list}"
    # --run-branch auto: give each run its own branch (avoids the serial-per-branch
    # conflict on the project default branch).
    "$ENJU" go --run-branch auto --params-file "$params_file" "$wf"
    local rc=$?
    rm -f "$params_file"
    return $rc
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_enju "$@"
fi
