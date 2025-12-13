#!/bin/bash
##############################################################################
#
#   BioYoda API Commands
#   Manages the BioYoda Search API (FastAPI server)
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Show API help
api_help() {
    cat << 'EOF'
BioYoda Search API Management

Usage: bioyoda.sh api <subcommand> [options]

Subcommands:
    start     Start API server
    stop      Stop API server
    status    Check API server status
    search    CLI search tool

Start Options:
    --port N          Port number (default: 8000)
    --host HOST       Host address (default: 0.0.0.0)
    --bg, -b          Run in background with logging
    --reload          Auto-reload on code changes (development)
    --test            Use test configuration (auto-background)
    --config FILE     Use custom config file

Search Options:
    <query>           Search query text
    --interactive     Interactive search mode
    --limit N         Number of results (default: 10)
    --collection COL  Specific collection to search

Examples:
    bioyoda.sh api start
    bioyoda.sh api start --bg --port 8001
    bioyoda.sh api start --test
    bioyoda.sh api search "CRISPR gene editing"
    bioyoda.sh api search --interactive
    bioyoda.sh api stop
EOF
}

# Main API dispatcher
cmd_api() {
    if [[ $# -eq 0 ]]; then
        api_help
        exit 1
    fi

    local subcommand=$1
    shift

    case $subcommand in
        start)  api_start "$@" ;;
        stop)   api_stop "$@" ;;
        status) api_status "$@" ;;
        search) api_search "$@" ;;
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
    local pid_file="${pid_dir}/api_server.pid"

    # Check if already running
    if ! check_not_running "$pid_file" "API server"; then
        log_info "Use './bioyoda.sh api stop' to stop it first"
        exit 1
    fi

    log_info "Starting BioYoda API server (port=${port}, host=${host})"

    # Check if Qdrant is running
    if ! curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
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

    # Build uvicorn command
    local reload_flag=""
    if [[ "$reload" == "true" ]]; then
        reload_flag="--reload"
    fi

    local uvicorn_cmd="python -m uvicorn scripts.main:app --host ${host} --port ${port} ${reload_flag} --log-level info"

    if [[ "$BACKGROUND" == "true" ]]; then
        local timestamp=$(get_timestamp)
        local api_log="${base_dir}/logs/api/server_${timestamp}.log"

        log_info "Starting API server in background..."
        log_info "Log: ${api_log}"

        # Create wrapper script
        local wrapper_script="${pid_dir}/api_wrapper.sh"
        cat > "$wrapper_script" << WRAPPER
#!/bin/bash
cd "${PIPELINE_DIR}/modules/api"
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
            log_success "API server started in background (PID: ${api_pid})"
            log_info "API available at: http://localhost:${port}"
            log_info "Docs available at: http://localhost:${port}/docs"
            log_info "Monitor with: tail -f ${api_log}"
            log_info "To stop: ./bioyoda.sh api stop"
        else
            log_error "API server failed to start. Check log: ${api_log}"
            rm -f "$pid_file"
            exit 1
        fi
    else
        log_info "Starting API server in foreground..."
        log_info "API will be available at: http://localhost:${port}"
        log_info "Docs will be available at: http://localhost:${port}/docs"
        log_info "Press Ctrl+C to stop"
        echo ""

        cd "${PIPELINE_DIR}/modules/api"
        eval "$uvicorn_cmd"
    fi
}

# Stop API server
api_stop() {
    parse_common_args "$@"
    local active_config=$(resolve_config "$USE_TEST" "$CUSTOM_CONFIG")
    local base_dir=$(get_base_dir "$active_config")
    local pid_file="${base_dir}/logs/pids/api_server.pid"

    log_info "Stopping API server..."

    if [[ ! -f "$pid_file" ]]; then
        log_warning "No running API server found (PID file not found)"
        return 0
    fi

    local api_pid=$(cat "$pid_file")

    if ps -p "$api_pid" > /dev/null 2>&1; then
        log_info "Stopping API server (PID: ${api_pid})..."
        kill_process_tree "$api_pid" false "$base_dir" "api"
        log_success "API server stopped"
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
    local pid_file="${base_dir}/logs/pids/api_server.pid"

    log_info "Checking API server status..."
    echo ""

    # Check PID file
    if [[ -f "$pid_file" ]]; then
        local api_pid=$(cat "$pid_file")
        if ps -p "$api_pid" > /dev/null 2>&1; then
            log_success "API server is running (PID: ${api_pid})"
        else
            log_warning "PID file exists but process not running (stale)"
        fi
    else
        log_info "API server is not running (no PID file)"
    fi

    # Check if API is responding
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_success "API is responding at http://localhost:8000"
        echo ""
        echo "API Health Check:"
        curl -s http://localhost:8000/health | python -m json.tool 2>/dev/null || echo "  (Could not format JSON)"
    else
        log_info "API not accessible at http://localhost:8000"
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
