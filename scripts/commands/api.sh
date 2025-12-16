#!/bin/bash
##############################################################################
#
#   BioYoda API Commands
#   Manages the BioYoda APIs (both legacy and v1 Agent System API)
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# API version: "v1" (new agent system) or "legacy" (old search API)
API_VERSION="v1"

# Show API help
api_help() {
    cat << 'EOF'
BioYoda API Management

Usage: bioyoda.sh api <subcommand> [options]

Subcommands:
    start     Start API server
    stop      Stop API server
    status    Check API server status
    search    CLI search tool (legacy API only)

API Version Options:
    --v1              Use new Agent System API (default)
    --legacy          Use legacy Search API (PubMed/ClinicalTrials)

Start Options:
    --port N          Port number (default: 8000)
    --host HOST       Host address (default: 0.0.0.0)
    --bg, -b          Run in background with logging
    --reload          Auto-reload on code changes (development)
    --test            Use test configuration (auto-background)
    --config FILE     Use custom config file

Search Options (legacy API):
    <query>           Search query text
    --interactive     Interactive search mode
    --limit N         Number of results (default: 10)
    --collection COL  Specific collection to search

Examples:
    # New Agent System API (v1) - default
    bioyoda.sh api start                      # Start v1 API
    bioyoda.sh api start --bg --port 8001     # Background on port 8001
    bioyoda.sh api status                     # Check status
    bioyoda.sh api stop                       # Stop server

    # Legacy Search API
    bioyoda.sh api start --legacy             # Start legacy API
    bioyoda.sh api search "CRISPR" --legacy   # Search with legacy
    bioyoda.sh api stop --legacy              # Stop legacy server
EOF
}

# Parse API version from arguments and store remaining args in REMAINING_API_ARGS array
parse_api_version() {
    API_VERSION="v1"  # Default to new API
    REMAINING_API_ARGS=()

    for arg in "$@"; do
        case "$arg" in
            --v1)
                API_VERSION="v1"
                ;;
            --legacy)
                API_VERSION="legacy"
                ;;
            *)
                REMAINING_API_ARGS+=("$arg")
                ;;
        esac
    done
}

# Main API dispatcher
cmd_api() {
    if [[ $# -eq 0 ]]; then
        api_help
        exit 1
    fi

    local subcommand=$1
    shift

    # Parse API version from remaining args (sets API_VERSION and REMAINING_API_ARGS)
    parse_api_version "$@"

    case $subcommand in
        start)  api_start "${REMAINING_API_ARGS[@]}" ;;
        stop)   api_stop "${REMAINING_API_ARGS[@]}" ;;
        status) api_status "${REMAINING_API_ARGS[@]}" ;;
        search) api_search "${REMAINING_API_ARGS[@]}" ;;
        help|--help|-h) api_help ;;
        *)
            log_error "Unknown api subcommand: $subcommand"
            api_help
            exit 1
            ;;
    esac
}

# Start API server
api_start() {
    local port=8000
    local host="0.0.0.0"
    local reload=false

    # Parse common args first
    parse_common_args "$@"

    # Parse API-specific args from REMAINING_ARGS
    local i=0
    while [[ $i -lt ${#REMAINING_ARGS[@]} ]]; do
        case ${REMAINING_ARGS[$i]} in
            --port)
                port="${REMAINING_ARGS[$((i+1))]}"
                ((i+=2))
                ;;
            --host)
                host="${REMAINING_ARGS[$((i+1))]}"
                ((i+=2))
                ;;
            --reload)
                reload=true
                ((i++))
                ;;
            *)
                ((i++))
                ;;
        esac
    done

    # Resolve config
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")

    # Test mode: automatically run in background
    if [[ "$USE_TEST" == "true" ]]; then
        BACKGROUND=true
        log_info "Test mode: running in background automatically"
    fi

    local base_dir=$(get_base_dir "$active_config")
    local pid_dir="${base_dir}/logs/pids"

    # Use version-specific PID files
    local pid_file
    if [[ "$API_VERSION" == "v1" ]]; then
        pid_file="${pid_dir}/api_v1_server.pid"
    else
        pid_file="${pid_dir}/api_server.pid"
    fi

    # Check if already running
    local api_label="API server (${API_VERSION})"
    if ! check_not_running "$pid_file" "$api_label"; then
        log_info "Use './bioyoda.sh api stop --${API_VERSION}' to stop it first"
        exit 1
    fi

    log_info "Starting BioYoda ${API_VERSION} API server (port=${port}, host=${host})"

    # Check if Qdrant is running (check both localhost and scc2)
    local qdrant_running=false
    if curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
        qdrant_running=true
    elif curl -s http://scc2:6333/healthz > /dev/null 2>&1; then
        qdrant_running=true
    fi

    if [[ "$qdrant_running" != "true" ]]; then
        log_error "Qdrant server is not running!"
        echo ""
        log_info "Please start Qdrant first:"
        echo "  ./bioyoda.sh qdrant start"
        echo "  ./bioyoda.sh qdrant start --mode cluster --queue gpu"
        exit 1
    fi
    log_success "Qdrant server is running"

    # Create directories
    mkdir -p "${base_dir}/logs/api"
    mkdir -p "$pid_dir"

    # Build uvicorn command based on API version
    local reload_flag=""
    if [[ "$reload" == "true" ]]; then
        reload_flag="--reload"
    fi

    local uvicorn_cmd
    local working_dir
    if [[ "$API_VERSION" == "v1" ]]; then
        # New Agent System API
        uvicorn_cmd="python -m uvicorn modules.api_v1.main:app --host ${host} --port ${port} ${reload_flag} --log-level info"
        working_dir="${PIPELINE_DIR}"
    else
        # Legacy Search API
        uvicorn_cmd="python -m uvicorn scripts.main:app --host ${host} --port ${port} ${reload_flag} --log-level info"
        working_dir="${PIPELINE_DIR}/modules/api"
    fi

    if [[ "$BACKGROUND" == "true" ]]; then
        local timestamp=$(get_timestamp)
        local api_log="${base_dir}/logs/api/${API_VERSION}_server_${timestamp}.log"

        log_info "Starting ${API_VERSION} API server in background..."
        log_info "Log: ${api_log}"

        # Create wrapper script
        local wrapper_script="${pid_dir}/api_${API_VERSION}_wrapper.sh"
        cat > "$wrapper_script" << WRAPPER
#!/bin/bash
cd "${working_dir}"
${uvicorn_cmd}
EXIT_CODE=\$?
rm -f "${pid_file}"
exit \$EXIT_CODE
WRAPPER
        chmod +x "$wrapper_script"

        nohup bash "$wrapper_script" > "$api_log" 2>&1 &
        local api_pid=$!
        echo "$api_pid" > "$pid_file"

        # Wait and verify
        sleep 2
        if ps -p "$api_pid" > /dev/null 2>&1; then
            log_success "${API_VERSION} API server started in background (PID: ${api_pid})"
            log_info "API available at: http://localhost:${port}"
            log_info "Docs available at: http://localhost:${port}/docs"
            log_info "Monitor with: tail -f ${api_log}"
            log_info "To stop: ./bioyoda.sh api stop --${API_VERSION}"
        else
            log_error "${API_VERSION} API server failed to start. Check log: ${api_log}"
            rm -f "$pid_file"
            exit 1
        fi
    else
        log_info "Starting ${API_VERSION} API server in foreground..."
        log_info "API will be available at: http://localhost:${port}"
        log_info "Docs will be available at: http://localhost:${port}/docs"
        log_info "Press Ctrl+C to stop"
        echo ""

        cd "${working_dir}"
        eval "$uvicorn_cmd"
    fi
}

# Stop API server
api_stop() {
    parse_common_args "$@"
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")
    local base_dir=$(get_base_dir "$active_config")

    # Use version-specific PID files
    local pid_file
    if [[ "$API_VERSION" == "v1" ]]; then
        pid_file="${base_dir}/logs/pids/api_v1_server.pid"
    else
        pid_file="${base_dir}/logs/pids/api_server.pid"
    fi

    log_info "Stopping ${API_VERSION} API server..."

    if [[ ! -f "$pid_file" ]]; then
        log_warning "No running ${API_VERSION} API server found (PID file not found)"
        return 0
    fi

    local api_pid=$(cat "$pid_file")

    if ps -p "$api_pid" > /dev/null 2>&1; then
        log_info "Stopping ${API_VERSION} API server (PID: ${api_pid})..."
        kill_process_tree "$api_pid" false "$base_dir" "api"
        log_success "${API_VERSION} API server stopped"
    else
        log_warning "Process ${api_pid} not running (stale PID file)"
    fi

    rm -f "$pid_file"
}

# Check API status
api_status() {
    parse_common_args "$@"
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")
    local base_dir=$(get_base_dir "$active_config")

    # Use version-specific PID files
    local pid_file
    if [[ "$API_VERSION" == "v1" ]]; then
        pid_file="${base_dir}/logs/pids/api_v1_server.pid"
    else
        pid_file="${base_dir}/logs/pids/api_server.pid"
    fi

    log_info "Checking ${API_VERSION} API server status..."
    echo ""

    # Check PID file
    if [[ -f "$pid_file" ]]; then
        local api_pid=$(cat "$pid_file")
        if ps -p "$api_pid" > /dev/null 2>&1; then
            log_success "${API_VERSION} API server is running (PID: ${api_pid})"
        else
            log_warning "PID file exists but process not running (stale)"
        fi
    else
        log_info "${API_VERSION} API server is not running (no PID file)"
    fi

    # Check if API is responding (use appropriate health endpoint)
    local health_endpoint
    if [[ "$API_VERSION" == "v1" ]]; then
        health_endpoint="http://localhost:8000/v1/health"
    else
        health_endpoint="http://localhost:8000/health"
    fi

    if curl -s "$health_endpoint" > /dev/null 2>&1; then
        log_success "${API_VERSION} API is responding at ${health_endpoint}"
        echo ""
        echo "API Health Check:"
        curl -s "$health_endpoint" | python -m json.tool 2>/dev/null || echo "  (Could not format JSON)"
    else
        log_info "${API_VERSION} API not accessible at ${health_endpoint}"
    fi

    echo ""
}

# CLI search
api_search() {
    python "${PIPELINE_DIR}/modules/api/scripts/bioyoda_search.py" "$@"
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_api "$@"
fi
