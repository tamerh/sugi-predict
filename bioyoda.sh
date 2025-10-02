#!/bin/bash

##############################################################################
#
#   BioYoda Main Execution Script
#   Orchestrates Snakemake workflows for biomedical data processing
#
##############################################################################

# Exit on error
set -eo pipefail

# Capture initial directory
user_dir=$PWD
pipeline_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$pipeline_dir"

# Configuration
bioyoda_version="0.1.0"
conda_env="bioyoda"
config_file="config/config.yaml"
snakefile="modules/Snakefile"
log_dir="logs"
pid_dir="logs/pids"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

##############################################################################
# Helper Functions
##############################################################################

goback() {
    rc=$?
    cd "$user_dir"
    exit $rc
}
trap goback SIGINT EXIT

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_conda_env() {
    if ! conda env list | grep -q "^${conda_env} "; then
        log_error "Conda environment '${conda_env}' not found!"
        log_info "Please create it with: conda env create -f tamer.yml"
        exit 1
    fi
}

check_snakemake() {
    if ! command -v snakemake &> /dev/null; then
        log_error "Snakemake not found!"
        log_info "Please activate conda environment first: conda activate ${conda_env}"
        log_info "If snakemake not installed: mamba install -n ${conda_env} -c bioconda snakemake"
        exit 1
    fi
}

##############################################################################
# Command Functions
##############################################################################

help() {
    cat << EOF
BioYoda v${bioyoda_version} - AI-powered biomedical search system

Usage: $0 <command> [options]

Commands:
    run <module> [options]    Run a specific module workflow
    stop <module> [options]   Stop a running pipeline
    status                    Show pipeline status
    validate <module>         Validate module outputs
    clean [module]            Clean intermediate files
    dryrun <module>           Show what would be executed (dry run)
    dag <module>              Generate workflow DAG visualization
    unlock                    Unlock working directory after crash
    help                      Show this help message
    version                   Show version information

Modules:
    pubmed                    PubMed literature processing
    clinical_trials           Clinical trials data processing (Phase 2)
    qdrant                    Qdrant vector database migration (Phase 2)
    all                       Run all modules

Run Options:
    --cluster                 Submit jobs to SGE cluster
    --local                   Run locally (default)
    --bg, -b                  Run in background with nohup
    --cores N                 Number of cores to use (default: 1)
    --jobs N                  Max parallel jobs on cluster (default: 100)
    --config FILE             Use custom config file (default: config/config.yaml)
    --dryrun                  Show what would be executed without running

Stop Options:
    --clean, -c               Also clean intermediate files after stopping

Examples:
    # Run PubMed pipeline locally in foreground
    $0 run pubmed --local

    # Run PubMed pipeline on cluster in background
    $0 run pubmed --cluster --bg --jobs 50

    # Run test pipeline with test config
    $0 run pubmed --config config/test_config.yaml --cluster --bg --jobs 5

    # Monitor background pipeline
    tail -f logs/bioyoda_pubmed_main.log

    # Stop running pipeline
    $0 stop pubmed

    # Stop and clean intermediate files
    $0 stop pubmed --clean

    # Dry run to see what would execute
    $0 dryrun pubmed

    # Generate workflow visualization
    $0 dag pubmed

    # Check pipeline status
    $0 status

    # Validate PubMed outputs
    $0 validate pubmed

For more information, visit: https://github.com/yourusername/bioyoda
EOF
}

version() {
    echo "BioYoda v${bioyoda_version}"
}

run() {
    local module="all"
    local execution_mode="local"
    local cores=1
    local jobs=100
    local dryrun=""
    local custom_config=""
    local background=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --cluster)
                execution_mode="cluster"
                shift
                ;;
            --local)
                execution_mode="local"
                shift
                ;;
            --cores)
                cores="$2"
                shift 2
                ;;
            --jobs)
                jobs="$2"
                shift 2
                ;;
            --dryrun)
                dryrun="-n"
                shift
                ;;
            --config)
                custom_config="$2"
                shift 2
                ;;
            --bg|-b)
                background=true
                shift
                ;;
            *)
                module="$1"
                shift
                ;;
        esac
    done

    # Use custom config if provided, otherwise use default
    local active_config="${custom_config:-$config_file}"

    log_info "Running BioYoda pipeline: module=${module}, mode=${execution_mode}, config=${active_config}"

    # Check prerequisites
    check_conda_env
    check_snakemake

    # Create necessary directories
    mkdir -p logs/cluster
    mkdir -p ${pid_dir}

    # Build Snakemake command
    local snakemake_cmd="snakemake --snakefile ${snakefile} --configfile ${active_config}"

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        log_info "Submitting jobs to SGE cluster (max ${jobs} parallel jobs)"
        # Snakemake 9+ uses executor plugins instead of --cluster
        # Using -e parameter to redirect stderr to LOG_cluster_log (like tieri)
        snakemake_cmd="${snakemake_cmd} --executor cluster-generic \
            --cluster-generic-submit-cmd 'qsub -cwd -V -q scc -N {rule}.{jobid} -l h_vmem={resources.mem_mb}M -l h_rt={resources.runtime} -e {params.LOG_cluster_log}' \
            --jobs ${jobs} \
            --default-resources mem_mb=8192 runtime=1440"
    else
        log_info "Running locally with ${cores} cores"
        snakemake_cmd="${snakemake_cmd} --cores ${cores}"
    fi

    # Add other options
    # --keep-going: Continue with independent jobs even if some fail (good for parallel file processing)
    # Remove --keep-going if you want fail-fast behavior (stop on first failure)
    snakemake_cmd="${snakemake_cmd} --use-conda --keep-going --rerun-incomplete --retries 3 --printshellcmds ${dryrun}"

    # Add target at the end
    if [[ "$module" != "all" ]]; then
        snakemake_cmd="${snakemake_cmd} -- ${module}"
    fi

    # Determine execution type and PID file
    local pid_file="${pid_dir}/${module}"
    if [[ "$execution_mode" == "cluster" ]]; then
        pid_file="${pid_file}.cluster.pid"
    else
        pid_file="${pid_file}.local.pid"
    fi

    # Check if already running
    if [[ -f "${pid_file}" ]]; then
        local existing_pid=$(cat "${pid_file}")
        if ps -p ${existing_pid} > /dev/null 2>&1; then
            log_error "Pipeline already running with PID ${existing_pid}"
            log_info "Use './bioyoda.sh stop ${module}' to stop it first"
            exit 1
        else
            # Stale PID file, remove it
            rm -f "${pid_file}"
        fi
    fi

    # Execute
    local main_log="${log_dir}/bioyoda_${module}_main.log"

    if [[ "$background" == true ]]; then
        log_info "Starting pipeline in background..."
        log_info "Executing: ${snakemake_cmd}"
        log_info "Main log: ${main_log}"
        log_info "Monitor with: tail -f ${main_log}"

        nohup bash -c "${snakemake_cmd}" > "${main_log}" 2>&1 &
        local main_pid=$!
        echo ${main_pid} > "${pid_file}"

        log_success "Pipeline started in background (PID: ${main_pid})"
        log_info "To monitor: tail -f ${main_log}"
        log_info "To stop: ./bioyoda.sh stop ${module}"
    else
        log_info "Executing: ${snakemake_cmd}"
        eval ${snakemake_cmd}

        if [[ $? -eq 0 ]]; then
            log_success "Pipeline completed successfully!"
        else
            log_error "Pipeline failed! Check logs for details."
            exit 1
        fi
    fi
}

status() {
    log_info "Checking BioYoda pipeline status..."

    if [[ ! -f "$config_file" ]]; then
        log_error "Configuration file not found: $config_file"
        exit 1
    fi

    # Check PubMed status
    echo ""
    echo "=== PubMed Module ==="
    if [[ -f "data/final/pubmed/master_pubmed.index" ]]; then
        local size=$(du -h data/final/pubmed/master_pubmed.index | cut -f1)
        log_success "Final index exists (${size})"
    else
        log_warning "Final index not found"
    fi

    # Count processed files
    local processed_count=$(find data/processed/pubmed -name "*.index" 2>/dev/null | wc -l)
    log_info "Processed files: ${processed_count}"

    # Check for running jobs
    if command -v qstat &> /dev/null; then
        local running_jobs=0
        running_jobs=$(qstat 2>/dev/null | grep -c bioyoda || true)
        if [[ ${running_jobs} -gt 0 ]]; then
            log_info "Running cluster jobs: ${running_jobs}"
        fi
    fi

    echo ""
    echo "=== Clinical Trials Module (Phase 2) ==="
    log_info "Not yet implemented"

    echo ""
    echo "=== Qdrant Module (Phase 2) ==="
    log_info "Not yet implemented"
}

validate() {
    local module="${1:-pubmed}"

    log_info "Validating module: ${module}"

    case $module in
        pubmed)
            if [[ ! -f "data/final/pubmed/master_pubmed.index" ]]; then
                log_error "PubMed index not found. Run pipeline first."
                exit 1
            fi

            # Run validation rule
            snakemake --snakefile ${snakefile} --configfile ${config_file} \
                pubmed_validate --cores 1 --use-conda

            # Display validation report
            if [[ -f "data/final/pubmed/validation_report.txt" ]]; then
                echo ""
                cat data/final/pubmed/validation_report.txt
            fi
            ;;
        *)
            log_error "Unknown module: ${module}"
            exit 1
            ;;
    esac
}

clean() {
    local module="${1:-all}"

    log_warning "This will remove intermediate files. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log_info "Cancelled"
        exit 0
    fi

    case $module in
        pubmed)
            log_info "Cleaning PubMed processed files..."
            rm -rf data/processed/pubmed/*
            log_success "PubMed cleaned"
            ;;
        all)
            log_info "Cleaning all processed files..."
            rm -rf data/processed/*
            log_success "All modules cleaned"
            ;;
        *)
            log_error "Unknown module: ${module}"
            exit 1
            ;;
    esac
}

dryrun() {
    local module="${1:-all}"
    log_info "Performing dry run for module: ${module}"

    check_snakemake

    if [[ "$module" != "all" ]]; then
        snakemake --snakefile ${snakefile} --configfile ${config_file} \
            --dryrun --printshellcmds -- ${module}
    else
        snakemake --snakefile ${snakefile} --configfile ${config_file} \
            --dryrun --printshellcmds
    fi
}

dag() {
    local module="${1:-all}"
    local output_file="workflow_dag.pdf"

    log_info "Generating DAG for module: ${module}"

    check_snakemake

    if ! command -v dot &> /dev/null; then
        log_error "Graphviz 'dot' command not found. Install with: conda install graphviz"
        exit 1
    fi

    if [[ "$module" != "all" ]]; then
        snakemake --snakefile ${snakefile} --configfile ${config_file} \
            --dag -- ${module} | dot -Tpdf > ${output_file}
    else
        snakemake --snakefile ${snakefile} --configfile ${config_file} \
            --dag | dot -Tpdf > ${output_file}
    fi

    log_success "DAG saved to: ${output_file}"
}

unlock() {
    log_info "Unlocking working directory..."
    snakemake --snakefile ${snakefile} --configfile ${config_file} --unlock
    log_success "Directory unlocked"
}

kill_process() {
    # Kill process tree using pstree
    # Args: $1 = main_pid, $2 = is_cluster (true/false)

    if [[ -z "$1" ]]; then
        log_error "No process ID provided"
        return 1
    fi

    local main_pid=$1
    local is_cluster=${2:-false}

    # Check if pstree is available
    if ! command -v pstree &> /dev/null; then
        log_warning "pstree not found. Install with: sudo yum install psmisc"
        log_info "Killing main process only..."
        kill -9 ${main_pid} 2>/dev/null || true
        return 0
    fi

    # Get current shell PID to avoid killing it
    local shell_pid=$PPID

    # Get all child PIDs using pstree
    local child_pids=$(pstree -p ${main_pid} 2>/dev/null | grep -o '([0-9]\+)' | sed 's/[()]//g')

    # Kill all child processes except current shell
    for pid in ${main_pid} ${child_pids}; do
        if [[ ${pid} != ${shell_pid} ]]; then
            kill -9 ${pid} 2>/dev/null || true
        fi
    done

    # If cluster mode, cancel SGE jobs
    if [[ "${is_cluster}" == "true" ]]; then
        local main_log="${log_dir}/bioyoda_${module}_main.log"
        if [[ -f "${main_log}" ]]; then
            # Extract job IDs from main log
            local job_ids=$(grep 'Your job' "${main_log}" 2>/dev/null | sed -n "s/.*Your job \([0-9]*\).*/\1/p")

            if [[ -n "${job_ids}" ]]; then
                log_info "Cancelling SGE jobs..."
                for job_id in ${job_ids}; do
                    qdel ${job_id} 2>/dev/null || true
                done
            fi
        fi
    fi
}

stop() {
    local module="pubmed"
    local clean=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --clean|-c)
                clean=true
                shift
                ;;
            *)
                module="$1"
                shift
                ;;
        esac
    done

    log_info "Stopping BioYoda pipeline: module=${module}"

    # Check for PID files (cluster or local)
    local pid_file=""
    local is_cluster=false

    if [[ -f "${pid_dir}/${module}.cluster.pid" ]]; then
        pid_file="${pid_dir}/${module}.cluster.pid"
        is_cluster=true
    elif [[ -f "${pid_dir}/${module}.local.pid" ]]; then
        pid_file="${pid_dir}/${module}.local.pid"
        is_cluster=false
    else
        log_warning "No running process found for module: ${module}"
        log_info "Cleaning up Snakemake locks anyway..."
        rm -rf .snakemake/locks/ 2>/dev/null || true
        return 0
    fi

    # Read PID and check if process is running
    local main_pid=$(cat "${pid_file}")

    if ps -p ${main_pid} > /dev/null 2>&1; then
        log_info "Killing process tree (PID: ${main_pid})..."
        kill_process ${main_pid} ${is_cluster}
        log_success "Process stopped"
    else
        log_warning "Process ${main_pid} not running (stale PID file)"
    fi

    # Remove PID file
    rm -f "${pid_file}"

    # Clean up Snakemake locks
    log_info "Cleaning up Snakemake locks..."
    rm -rf .snakemake/locks/ 2>/dev/null || true

    # Optional: clean intermediate files
    if [[ "${clean}" == true ]]; then
        log_warning "Cleaning intermediate files for ${module}..."
        rm -rf data/processed/${module}/* 2>/dev/null || true
        log_success "Intermediate files cleaned"
    fi

    log_success "Stop completed"
}

##############################################################################
# Main Entry Point
##############################################################################

main() {
    if [[ $# -eq 0 ]]; then
        log_error "No command specified"
        echo ""
        help
        exit 1
    fi

    local command=$1
    shift

    case $command in
        run)
            run "$@"
            ;;
        stop)
            stop "$@"
            ;;
        status)
            status "$@"
            ;;
        validate)
            validate "$@"
            ;;
        clean)
            clean "$@"
            ;;
        dryrun)
            dryrun "$@"
            ;;
        dag)
            dag "$@"
            ;;
        unlock)
            unlock "$@"
            ;;
        help|--help|-h)
            help
            ;;
        version|--version|-v)
            version
            ;;
        *)
            log_error "Unknown command: $command"
            echo ""
            help
            exit 1
            ;;
    esac
}

main "$@"
