#!/bin/bash
##############################################################################
#
#   BioYoda Process Management
#   Handles PID file management, process tracking, and background execution
#
##############################################################################

# Check if a process is running from PID file
# Usage: is_process_running <pid_file>
is_process_running() {
    local pid_file="$1"

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Get PID from file if process is running
# Usage: get_running_pid <pid_file>
# Returns: PID if running, empty string otherwise
get_running_pid() {
    local pid_file="$1"

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
            return 0
        fi
    fi
    echo ""
    return 1
}

# Clean stale PID file if process is not running
# Usage: clean_stale_pid <pid_file>
clean_stale_pid() {
    local pid_file="$1"

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ! ps -p "$pid" > /dev/null 2>&1; then
            rm -f "$pid_file"
            return 0
        fi
    fi
    return 1
}

# Check if already running and exit with error if so
# Usage: check_not_running <pid_file> <process_name>
check_not_running() {
    local pid_file="$1"
    local process_name="$2"

    if is_process_running "$pid_file"; then
        local pid=$(cat "$pid_file")
        log_error "${process_name} already running with PID ${pid}"
        return 1
    fi

    # Clean stale PID file
    clean_stale_pid "$pid_file"
    return 0
}

# Kill a process and its children
# Usage: kill_process_tree <main_pid> [is_cluster] [base_dir] [module_name]
kill_process_tree() {
    local main_pid="$1"
    local is_cluster="${2:-false}"
    local base_dir="${3:-out}"
    local module="${4:-unknown}"

    if [[ -z "$main_pid" ]]; then
        log_error "No process ID provided"
        return 1
    fi

    # Get current shell PID to avoid killing it
    local shell_pid=$PPID

    # Check if pstree is available
    if command -v pstree &> /dev/null; then
        # Get all child PIDs using pstree
        local child_pids=$(pstree -p "$main_pid" 2>/dev/null | grep -o '([0-9]\+)' | sed 's/[()]//g')

        # Kill all child processes except current shell
        for pid in $main_pid $child_pids; do
            if [[ "$pid" != "$shell_pid" ]]; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
    else
        log_warning "pstree not found, killing main process only"
        kill -9 "$main_pid" 2>/dev/null || true
    fi

    # If cluster mode, cancel SGE jobs
    if [[ "$is_cluster" == "true" ]] && command -v qstat &> /dev/null; then
        cancel_cluster_jobs "$base_dir" "$module"
    fi
}

# SGE cluster job cancellation was retired in the Enju migration (no qsub).
# Kept as a no-op so any legacy caller still resolves.
cancel_cluster_jobs() {
    :
}

# Create a wrapper script for background execution
# Usage: create_wrapper_script <wrapper_path> <command> <pid_file>
create_wrapper_script() {
    local wrapper_path="$1"
    local command="$2"
    local pid_file="$3"

    cat > "$wrapper_path" << WRAPPER
#!/bin/bash
# Wrapper script for background execution with cleanup

# Run command
${command}
EXIT_CODE=\$?

# Remove PID file
rm -f "${pid_file}"

exit \$EXIT_CODE
WRAPPER
    chmod +x "$wrapper_path"
}

# Run a command in background with PID tracking
# Usage: run_background <command> <pid_file> <log_file> <wrapper_dir>
run_background() {
    local command="$1"
    local pid_file="$2"
    local log_file="$3"
    local wrapper_dir="$4"

    local wrapper_name=$(basename "$pid_file" .pid)
    local wrapper_script="${wrapper_dir}/${wrapper_name}_wrapper.sh"

    # Create wrapper script
    create_wrapper_script "$wrapper_script" "$command" "$pid_file"

    # Run in background
    nohup bash "$wrapper_script" > "$log_file" 2>&1 &
    local bg_pid=$!
    echo "$bg_pid" > "$pid_file"

    echo "$bg_pid"
}

# Run command with optional background execution
# Usage: run_with_tracking <command> <pid_base> <log_file> <background> <execution_mode>
run_with_tracking() {
    local command="$1"
    local pid_base="$2"
    local log_file="$3"
    local background="${4:-false}"
    local execution_mode="${5:-local}"

    local pid_dir=$(dirname "$pid_base")
    local pid_name=$(basename "$pid_base")
    local pid_file="${pid_base}.${execution_mode}.pid"

    # Ensure directories exist
    mkdir -p "$pid_dir"
    mkdir -p "$(dirname "$log_file")"

    # Check if already running
    if ! check_not_running "$pid_file" "$pid_name"; then
        log_info "Use stop command to stop it first"
        return 1
    fi

    if [[ "$background" == "true" ]]; then
        log_info "Starting in background..."
        log_info "Command: ${command}"
        log_info "Log: ${log_file}"

        local bg_pid=$(run_background "$command" "$pid_file" "$log_file" "$pid_dir")

        log_success "Started in background (PID: ${bg_pid})"
        log_info "Monitor with: tail -f ${log_file}"
    else
        log_info "Executing: ${command}"
        eval "$command"
        local exit_code=$?

        if [[ $exit_code -eq 0 ]]; then
            log_success "Completed successfully!"
        else
            log_error "Failed! Check logs for details."
            return 1
        fi
    fi
}

# Stop a running process by PID file
# Usage: stop_process <pid_base> <process_name> [base_dir] [clean_locks]
stop_process() {
    local pid_base="$1"
    local process_name="$2"
    local base_dir="${3:-out}"
    local clean_locks="${4:-true}"

    local pid_file=""
    local is_cluster=false

    # Check for cluster or local PID file
    if [[ -f "${pid_base}.cluster.pid" ]]; then
        pid_file="${pid_base}.cluster.pid"
        is_cluster=true
    elif [[ -f "${pid_base}.local.pid" ]]; then
        pid_file="${pid_base}.local.pid"
        is_cluster=false
    else
        log_warning "No running process found for: ${process_name}"
        return 0
    fi

    local main_pid=$(cat "$pid_file")

    if ps -p "$main_pid" > /dev/null 2>&1; then
        log_info "Killing process tree (PID: ${main_pid})..."
        kill_process_tree "$main_pid" "$is_cluster" "$base_dir" "$process_name"
        log_success "Process stopped"
    else
        log_warning "Process ${main_pid} not running (stale PID file)"
    fi

    rm -f "$pid_file"

}
