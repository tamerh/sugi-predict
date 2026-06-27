#!/bin/bash
##############################################################################
#
#   BioYoda Qdrant Commands
#   Manages Qdrant vector database (start/stop/status/reindex/rebuild).
#   NB inserts are no longer here: collections are built via `bioyoda.sh build <collection> insert`
#   (the retired Snakemake insert path was removed along with modules/qdrant/Snakefile).
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Show qdrant help
qdrant_help() {
    cat << 'EOF'
Qdrant Vector Database Management

Usage: bioyoda.sh qdrant <subcommand> [options]

Subcommands:
    start         Start Qdrant server (docker compose)
    stop          Stop Qdrant server
    restart       Restart with existing storage directory
    status        Check Qdrant server status and collections
    reindex       Trigger HNSW index build after a bulk build
    rebuild       Rebuild a collection from its profile (clean copy + HNSW)

Start Options:
    --runtime <hours>         Runtime in hours (default: 48)
    --memory <mb>             Memory in MB (default: 32000)
    --out-dir <path>          Use specific storage directory
    --test                    Use test configuration
    --config <file>           Use custom config file

Reindex Options:
    --threshold N             Indexing threshold (default: 20000)
    --monitor                 Monitor indexing progress after triggering
    --timeout N               Monitoring timeout in seconds (default: wait forever)

Collections (served):
    patent_compounds        Patent compounds (alias -> patent_compounds_v2)
    chembl                  ChEMBL reference ligands
    clinical_trials_medcpt  Clinical trials (MedCPT)
    patents_text            Patent text (MedCPT; alias -> patents_text_medcpt)
    esm2                    Protein embeddings (ESM-2)
    all                     All collections

NB to ingest/build a collection, use `bioyoda.sh build <collection> ...` (the insert path moved there).

Examples:
    bioyoda.sh qdrant start
    bioyoda.sh qdrant start --out-dir /path/to/existing/qdrant  # Restart with existing storage
    bioyoda.sh qdrant restart                                   # Auto-detect and restart
    bioyoda.sh qdrant reindex patent_compounds                  # Trigger HNSW indexing
    bioyoda.sh qdrant reindex patent_compounds --monitor        # Trigger and monitor progress
    bioyoda.sh qdrant reindex all                               # Reindex all collections
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
        reindex)     qdrant_reindex "$@" ;;
        rebuild)     qdrant_rebuild "$@" ;;
        help|--help|-h) qdrant_help ;;
        *)
            log_error "Unknown qdrant subcommand: $subcommand"
            qdrant_help
            exit 1
            ;;
    esac
}

# Rebuild a collection from its FAISS source using its proven profile
# Usage: bioyoda.sh qdrant rebuild <collection> [--recreate]
qdrant_rebuild() {
    local py="/data/miniconda3/envs/bioyoda/bin/python"
    [[ -x "$py" ]] || py="python3"
    "$py" /data/bioyoda/modules/qdrant/scripts/rebuild_collection.py "$@"
}

# --- Qdrant container lifecycle (docker compose: config/docker-compose.bioyoda.yml) ---
QDRANT_COMPOSE="${COMMANDS_DIR}/../../config/docker-compose.bioyoda.yml"

qdrant_start() {     # bring up the Qdrant container (data persists in the mounted volume qdrant/storage)
    log_info "qdrant: docker compose up -d"
    docker compose -p bioyoda -f "$QDRANT_COMPOSE" up -d qdrant && qdrant_status
}

qdrant_stop() {      # stop the container (data volume untouched)
    log_info "qdrant: docker compose stop"
    docker compose -p bioyoda -f "$QDRANT_COMPOSE" stop qdrant
}

qdrant_restart() {   # restart (e.g. to clear a wedged optimizer); data persists
    log_info "qdrant: docker compose restart"
    docker compose -p bioyoda -f "$QDRANT_COMPOSE" restart qdrant && qdrant_status
}

qdrant_status() {    # container state + health + memory
    docker compose -p bioyoda -f "$QDRANT_COMPOSE" ps qdrant 2>/dev/null
    docker stats --no-stream --format '  mem {{.MemUsage}}  cpu {{.CPUPerc}}' qdrant-bioyoda 2>/dev/null
    curl -sf http://localhost:6333/healthz >/dev/null 2>&1 && echo "  healthz: OK" || echo "  healthz: DOWN"
}

# Trigger HNSW index build after a bulk build
qdrant_reindex() {
    if [[ $# -eq 0 ]]; then
        log_error "No collection specified for reindexing"
        echo ""
        echo "Available collections:"
        echo "  patent_compounds        Patent compounds (30M+ vectors)"
        echo "  chembl                  ChEMBL reference ligands"
        echo "  clinical_trials_medcpt  Clinical trials (MedCPT)"
        echo "  patents_text            Patent text (MedCPT)"
        echo "  esm2                    Protein embeddings (ESM-2)"
        echo "  all                     All collections"
        exit 1
    fi

    local collection=$1
    shift

    # Parse options
    local threshold=20000
    local monitor=false
    local timeout=0

    while [[ $# -gt 0 ]]; do
        case $1 in
            --threshold)
                threshold="$2"
                shift 2
                ;;
            --monitor)
                monitor=true
                shift
                ;;
            --timeout)
                timeout="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # Get Qdrant URL
    local qdrant_url="http://localhost:6333"

    # Check if Qdrant is running
    if ! curl -s "${qdrant_url}/collections" > /dev/null 2>&1; then
        log_error "Qdrant server not running at ${qdrant_url}"
        echo "Start it with: ./bioyoda.sh qdrant start"
        exit 1
    fi

    # Handle 'all' collection
    local collections=()
    if [[ "$collection" == "all" ]]; then
        collections=("patent_compounds" "chembl" "clinical_trials_medcpt" "patents_text" "esm2")
    else
        collections=("$collection")
    fi

    for col in "${collections[@]}"; do
        log_info "Triggering reindex for ${col}..."

        # Check if collection exists
        if ! curl -s "${qdrant_url}/collections/${col}" | grep -q '"status":"ok"' 2>/dev/null; then
            log_warning "Collection ${col} not found, skipping"
            continue
        fi

        # Get current state
        local current_indexed=$(curl -s "${qdrant_url}/collections/${col}" | \
            python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('indexed_vectors_count',0))" 2>/dev/null || echo "0")
        local total_points=$(curl -s "${qdrant_url}/collections/${col}" | \
            python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('points_count',0))" 2>/dev/null || echo "0")

        echo "  Current state: ${current_indexed} / ${total_points} indexed"

        # Step 1: Set indexing threshold
        log_info "  Setting indexing_threshold to ${threshold}..."
        local patch_result=$(curl -s -X PATCH "${qdrant_url}/collections/${col}" \
            -H 'Content-Type: application/json' \
            -d "{\"optimizers_config\": {\"indexing_threshold\": ${threshold}}}")

        if ! echo "$patch_result" | grep -q '"status":"ok"'; then
            log_error "  Failed to update indexing_threshold: ${patch_result}"
            continue
        fi

        # Step 2: Create dummy vector based on collection
        local vector_size=768  # Default (text collections)
        case $col in
            esm2) vector_size=1280 ;;
            patent_compounds|chembl) vector_size=2048 ;;
        esac

        log_info "  Inserting dummy point to trigger optimizer..."

        # Generate dummy vector
        local dummy_vector=$(python3 -c "import json; v=[0.0]*${vector_size}; v[0]=1.0; print(json.dumps(v))")
        local dummy_payload="{\"points\":[{\"id\":999999999999,\"vector\":${dummy_vector},\"payload\":{\"_dummy\":true}}]}"

        # Insert dummy point
        curl -s -X PUT "${qdrant_url}/collections/${col}/points?wait=true" \
            -H 'Content-Type: application/json' \
            -d "$dummy_payload" > /dev/null

        # Delete dummy point
        curl -s -X POST "${qdrant_url}/collections/${col}/points/delete?wait=true" \
            -H 'Content-Type: application/json' \
            -d '{"points": [999999999999]}' > /dev/null

        log_success "  Reindex triggered for ${col}"

        # Check new state
        local new_status=$(curl -s "${qdrant_url}/collections/${col}" | \
            python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('status','unknown'))" 2>/dev/null || echo "unknown")
        echo "  Status: ${new_status} (yellow = indexing in progress)"
    done

    # Monitor if requested
    if [[ "$monitor" == "true" ]]; then
        echo ""
        log_info "Monitoring indexing progress (Ctrl+C to stop)..."
        echo "============================================================"

        local start_time=$(date +%s)
        while true; do
            local all_done=true

            for col in "${collections[@]}"; do
                local result=$(curl -s "${qdrant_url}/collections/${col}" 2>/dev/null)
                if [[ -z "$result" ]]; then
                    continue
                fi

                local indexed=$(echo "$result" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('indexed_vectors_count',0))" 2>/dev/null || echo "0")
                local total=$(echo "$result" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('points_count',0))" 2>/dev/null || echo "0")
                local status=$(echo "$result" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('status','unknown'))" 2>/dev/null || echo "unknown")
                local segments=$(echo "$result" | python3 -c "import json,sys; r=json.load(sys.stdin).get('result',{}); print(r.get('segments_count',0))" 2>/dev/null || echo "0")

                local pct=0
                if [[ "$total" -gt 0 ]]; then
                    pct=$(python3 -c "print(f'{${indexed}/${total}*100:.1f}')")
                fi

                local indicator="🔄"
                if [[ "$status" == "green" ]] && [[ "$indexed" == "$total" ]]; then
                    indicator="✅"
                elif [[ "$indexed" == "0" ]]; then
                    indicator="⏳"
                    all_done=false
                else
                    all_done=false
                fi

                printf "[%s] %-20s %s Segments: %2s | Indexed: %12s / %12s (%5s%%)\n" \
                    "$(date '+%H:%M:%S')" "$col" "$indicator" "$segments" "$indexed" "$total" "$pct"
            done

            if [[ "$all_done" == "true" ]]; then
                echo ""
                log_success "All collections indexed!"
                break
            fi

            # Check timeout
            if [[ "$timeout" -gt 0 ]]; then
                local elapsed=$(($(date +%s) - start_time))
                if [[ "$elapsed" -ge "$timeout" ]]; then
                    echo ""
                    log_warning "Timeout reached (${timeout}s). Indexing continues in background."
                    break
                fi
            fi

            sleep 30
            echo ""
        done
    else
        echo ""
        echo "Indexing started in background. Monitor with:"
        echo "  ./scripts/check_qdrant_indexing.sh"
        echo "  or: ./bioyoda.sh qdrant reindex ${collection} --monitor"
    fi
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_qdrant "$@"
fi
