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
    run <module> [options]    Run data processing pipeline (PubMed/Clinical Trials)
    stop <module> [options]   Stop a running pipeline
    status                    Show pipeline status
    qdrant <subcommand>       Manage Qdrant vector database (start/stop/insert/status)
    validate <module>         Validate module outputs
    clean [module]            Clean intermediate files
    dryrun <module>           Show what would be executed (dry run)
    dag <module>              Generate workflow DAG visualization
    unlock                    Unlock working directory after crash
    help                      Show this help message
    version                   Show version information

Dataset Modules:
    pubmed                    PubMed literature processing (FAISS creation)
    clinical_trials           Clinical trials data processing (FAISS creation)
    all                       Run all dataset modules

Qdrant Subcommands:
    start                     Start Qdrant server (local or cluster)
    stop                      Stop Qdrant server
    status                    Check Qdrant server status and collections
    insert <dataset>          Insert data to Qdrant (pubmed, clinical_trials, or all)

Run Options:
    --cluster                 Submit jobs to SGE cluster
    --local                   Run locally (default)
    --bg, -b                  Run in background with nohup
    --cores N                 Number of cores to use (default: 1)
    --jobs N                  Max parallel jobs on cluster (default: 100)
    --config FILE             Use custom config file (default: config/config.yaml)
    --test                    Use test config (config/test_config.yaml)
    --dryrun                  Show what would be executed without running
    --cuda11.4                Use CUDA 11.4 nodes (scc116, scc117, scc066) with bioyoda_gpu_cuda11 env

Qdrant Start Options:
    --mode <local|cluster>    Run mode (default: local)
    --queue <name>            SGE queue name (default: scc, can use: gpu)
    --runtime <hours>         Runtime in hours (default: 48)
    --memory <mb>             Memory in MB (default: 32000)

Qdrant Insert Options:
    --cluster                 Submit insertion jobs to cluster
    --local                   Run insertion locally (default)
    --cores N                 Number of cores (for local mode)
    --jobs N                  Max parallel jobs (for cluster mode)
    --test                    Use test config (config/test_config.yaml)
    --cuda11.4                Use CUDA 11.4 nodes (scc116, scc117, scc066) with bioyoda_gpu_cuda11 env

Stop Options:
    --clean, -c               Also clean intermediate files after stopping

Examples:
    # Data Processing Pipeline (no Qdrant)
    $0 run pubmed --cluster --bg --jobs 50
    $0 run clinical_trials --cluster --bg --jobs 20
    $0 run all --cluster --bg --jobs 100

    # Test with small dataset
    $0 run pubmed --test --local

    # Use CUDA 11.4 nodes instead
    $0 run pubmed --cluster --bg --jobs 50 --cuda11.4

    # Qdrant Operations (separate from data processing)
    # 1. Start Qdrant server on GPU node for long-running session
    $0 qdrant start --mode cluster --queue gpu --runtime 168

    # 2. Check server status
    $0 qdrant status

    # 3. Insert data when ready (can be done days later)
    $0 qdrant insert pubmed --cluster --jobs 10
    $0 qdrant insert clinical_trials --cluster --jobs 10
    $0 qdrant insert all --cluster --jobs 20

    # Use CUDA 11.4 nodes for insertion
    $0 qdrant insert pubmed --cluster --jobs 10 --cuda11.4

    # 4. Stop server when done
    $0 qdrant stop

    # Monitor progress
    tail -f logs/bioyoda_pubmed_main.log
    tail -f logs/qdrant/insert_pubmed.log

    # Stop running pipeline
    $0 stop pubmed --clean

    # Dry run to see what would execute
    $0 dryrun pubmed

    # Generate workflow visualization
    $0 dag pubmed

    # Check overall status
    $0 status

    # Validate outputs
    $0 validate pubmed

    # Clean specific module
    $0 clean pubmed
    $0 clean qdrant

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
    local cuda_version=""
    local use_test_config=false

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
            --dryrun|--dry-run|-n)
                dryrun="-n"
                shift
                ;;
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            --bg|-b)
                background=true
                shift
                ;;
            --cuda11.4)
                cuda_version="11.4"
                shift
                ;;
            *)
                module="$1"
                shift
                ;;
        esac
    done

    # Determine active config: --config takes precedence, then --test, then default
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
        log_info "Using test configuration: config/test_config.yaml"
    fi

    # Auto-detect GPU queue and use config_gpu.yaml if no custom config specified
    if [[ -z "$custom_config" ]] && [[ "$execution_mode" == "cluster" ]]; then
        local queue=$(grep -A2 "^cluster:" ${active_config} | grep "default_queue:" | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/' || echo "scc")
        if [[ "$queue" == "gpu" ]]; then
            # Check if config_gpu.yaml exists
            if [[ -f "config/config_gpu.yaml" ]]; then
                active_config="config/config_gpu.yaml"
                log_info "Auto-selected GPU config: config_gpu.yaml (queue=gpu detected)"
            fi
        fi
    fi

    log_info "Running BioYoda pipeline: module=${module}, mode=${execution_mode}, config=${active_config}"

    # Check prerequisites
    check_conda_env
    check_snakemake

    # Create necessary directories
    mkdir -p logs/cluster
    mkdir -p ${pid_dir}

    # Build Snakemake command
    # Add --latency-wait for HPC filesystem delays (60 seconds like tieri, default is 5)
    local snakemake_cmd="snakemake --snakefile ${snakefile} --configfile ${active_config} --latency-wait 60"

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        # Get queue from config file (default: scc)
        local queue=$(grep -A2 "^cluster:" ${active_config} | grep "default_queue:" | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/' || echo "scc")

        # Build resource requirements and conda environment based on queue
        local gpu_resource=""
        local node_restriction=""
        local conda_env_override=""
        if [[ "$queue" == "gpu" ]]; then
            gpu_resource="-l gpu=1"

            # Check if CUDA 11.4 is requested
            if [[ "$cuda_version" == "11.4" ]]; then
                # Restrict to nodes with CUDA 11.4: scc116, scc117, scc066
                node_restriction="-l hostname='\"'\"'scc116|scc117|scc066'\"'\"'"
                conda_env_override="conda_env=bioyoda_gpu_cuda11"
                log_info "Submitting jobs to GPU cluster (queue=${queue}, env=bioyoda_gpu_cuda11, CUDA 11.4 nodes: scc116, scc117, scc066, max ${jobs} parallel jobs)"
            else
                # Restrict to nodes with CUDA 12.8: scc213, scc192, spiderman, hulk, scc195-scc199
                # Using single quotes inside to avoid shell interpretation of pipe
                node_restriction="-l hostname='\"'\"'scc213|scc192|spiderman|hulk|scc195|scc196|scc197|scc198|scc199'\"'\"'"
                conda_env_override="conda_env=bioyoda_gpu"
                log_info "Submitting jobs to GPU cluster (queue=${queue}, env=bioyoda_gpu, CUDA 12.8 nodes only, max ${jobs} parallel jobs)"
            fi
        else
            log_info "Submitting jobs to SGE cluster (queue=${queue}, max ${jobs} parallel jobs)"
        fi

        # Snakemake 9+ uses executor plugins instead of --cluster
        # Using -e parameter to redirect stderr to LOG_cluster_log (like tieri)
        snakemake_cmd="${snakemake_cmd} --executor cluster-generic \
            --cluster-generic-submit-cmd 'qsub -cwd -V -q ${queue} ${gpu_resource} ${node_restriction} -N {rule}.{jobid} -pe smp {threads} -l h_vmem={resources.mem_mb}M -l h_rt={resources.runtime} -o {params.LOG_cluster_log} -j y' \
            --jobs ${jobs} \
            --default-resources mem_mb=8192 runtime=604800 threads=1"
    else
        log_info "Running locally with ${cores} cores"
        snakemake_cmd="${snakemake_cmd} --cores ${cores}"
    fi

    # Add other options
    # --keep-going: Continue with independent jobs even if some fail (good for parallel file processing)
    # Remove --keep-going if you want fail-fast behavior (stop on first failure)
    # In test mode, no retries for faster feedback
    local retries=3
    if [[ "$use_test_config" == true ]]; then
        retries=0
    fi
    snakemake_cmd="${snakemake_cmd} --use-conda --keep-going --rerun-incomplete --retries ${retries} --printshellcmds ${dryrun}"

    # Build config overrides (all in one --config)
    local config_overrides="execution_mode=${execution_mode}"
    if [[ -n "$conda_env_override" ]]; then
        config_overrides="${config_overrides} ${conda_env_override}"
    fi
    snakemake_cmd="${snakemake_cmd} --config ${config_overrides}"

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

        # Create wrapper script with cleanup
        local wrapper_script="${pid_dir}/${module}_wrapper.sh"
        cat > "${wrapper_script}" <<WRAPPER
#!/bin/bash
# Wrapper script for background execution with cleanup

# Run pipeline
${snakemake_cmd}
EXIT_CODE=\$?

# Remove PID file
rm -f "${pid_file}"

exit \$EXIT_CODE
WRAPPER
        chmod +x "${wrapper_script}"

        nohup bash "${wrapper_script}" > "${main_log}" 2>&1 &
        local main_pid=$!
        echo ${main_pid} > "${pid_file}"

        log_success "Pipeline started in background (PID: ${main_pid})"
        log_info "To monitor: tail -f ${main_log}"
        log_info "To stop: ./bioyoda.sh stop ${module}"
    else
        log_info "Executing: ${snakemake_cmd}"
        eval ${snakemake_cmd}
        local exit_code=$?

        if [[ ${exit_code} -eq 0 ]]; then
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
    echo "=== Clinical Trials Module ==="
    if [[ -f "data/processed/clinical_trials/trials_data.json" ]]; then
        local size=$(du -h data/processed/clinical_trials/trials_data.json | cut -f1)
        log_success "Trials data exists (${size})"
    else
        log_warning "Trials data not found"
    fi

    echo ""
    echo "=== Qdrant Module ==="

    # Check if Qdrant server is running
    if [[ -f "data/qdrant/connection_info.txt" ]]; then
        log_success "Qdrant server connection info found"
        cat data/qdrant/connection_info.txt | grep QDRANT_URL
    else
        log_info "Qdrant server not running"
    fi

    # Check collections
    if [[ -f "data/qdrant/collections/pubmed_abstracts.done" ]]; then
        log_success "PubMed collection complete"
    else
        log_info "PubMed collection not completed"
    fi

    if [[ -f "data/qdrant/collections/clinical_trials.done" ]]; then
        log_success "Clinical Trials collection complete"
    else
        log_info "Clinical Trials collection not completed"
    fi

    # Check storage size
    if [[ -d "data/qdrant/storage" ]]; then
        local qdrant_size=$(du -sh data/qdrant/storage 2>/dev/null | cut -f1)
        log_info "Qdrant storage size: ${qdrant_size}"
    fi
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
        qdrant)
            if [[ ! -f "data/qdrant/connection_info.txt" ]]; then
                log_error "Qdrant server not running or connection info not found."
                exit 1
            fi

            log_info "Checking Qdrant collections..."
            source data/qdrant/connection_info.txt

            # Check collections via API
            log_info "Querying Qdrant at: $QDRANT_URL"
            curl -s "$QDRANT_URL/collections" | python -m json.tool 2>/dev/null || log_warning "Failed to connect to Qdrant"

            # Check specific collections
            if curl -s "$QDRANT_URL/collections/pubmed_abstracts" >/dev/null 2>&1; then
                log_success "PubMed collection accessible"
                curl -s "$QDRANT_URL/collections/pubmed_abstracts" | python -m json.tool 2>/dev/null | grep -E "(points_count|status)"
            fi

            if curl -s "$QDRANT_URL/collections/clinical_trials" >/dev/null 2>&1; then
                log_success "Clinical Trials collection accessible"
                curl -s "$QDRANT_URL/collections/clinical_trials" | python -m json.tool 2>/dev/null | grep -E "(points_count|status)"
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
        clinical_trials)
            log_info "Cleaning Clinical Trials processed files..."
            rm -rf data/processed/clinical_trials/*
            log_success "Clinical Trials cleaned"
            ;;
        qdrant)
            log_info "Cleaning Qdrant storage and collections..."
            rm -rf data/qdrant/storage/*
            rm -f data/qdrant/connection_info.txt
            rm -f data/qdrant/collections/*.done
            log_success "Qdrant cleaned"
            ;;
        all)
            log_info "Cleaning all processed files..."
            rm -rf data/processed/*
            rm -rf data/qdrant/storage/*
            rm -f data/qdrant/connection_info.txt
            rm -f data/qdrant/collections/*.done
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

##############################################################################
# Qdrant Server Management
##############################################################################

stop_qdrant_server() {
    local qdrant_pid_file="data/qdrant/qdrant.pid"
    local connection_info="data/qdrant/connection_info.txt"

    # Check for local PID file
    if [[ -f "${qdrant_pid_file}" ]]; then
        local qdrant_pid=$(cat "${qdrant_pid_file}")
        if ps -p ${qdrant_pid} > /dev/null 2>&1; then
            log_info "Stopping Qdrant server (PID: ${qdrant_pid})..."
            kill ${qdrant_pid} 2>/dev/null || true
            sleep 2
            # Force kill if still running
            if ps -p ${qdrant_pid} > /dev/null 2>&1; then
                kill -9 ${qdrant_pid} 2>/dev/null || true
            fi
            log_success "Qdrant server stopped"
        fi
        rm -f "${qdrant_pid_file}"
    fi

    # Check for cluster job (look for qdrant_server job)
    if command -v qstat &> /dev/null; then
        local qdrant_jobs=$(qstat -u $(whoami) 2>/dev/null | grep "qdrant_server" | awk '{print $1}' || true)
        if [[ -n "${qdrant_jobs}" ]]; then
            log_info "Stopping Qdrant cluster job(s)..."
            for job_id in ${qdrant_jobs}; do
                qdel ${job_id} 2>/dev/null || true
                log_info "  Cancelled job: ${job_id}"
            done
            log_success "Qdrant cluster job(s) stopped"
        fi
    fi

    # Clean up connection info
    if [[ -f "${connection_info}" ]]; then
        rm -f "${connection_info}"
    fi
}

##############################################################################
# Pipeline Control Functions
##############################################################################

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
# Qdrant Management Functions
##############################################################################

qdrant() {
    if [[ $# -eq 0 ]]; then
        log_error "No qdrant subcommand specified"
        echo ""
        echo "Available subcommands:"
        echo "  start    - Start Qdrant server (local or cluster)"
        echo "  stop     - Stop Qdrant server"
        echo "  status   - Check Qdrant server status"
        echo "  insert   - Insert data to Qdrant (pubmed, clinical_trials, or all)"
        echo ""
        echo "Examples:"
        echo "  $0 qdrant start --mode cluster --queue gpu"
        echo "  $0 qdrant insert pubmed"
        echo "  $0 qdrant status"
        echo "  $0 qdrant stop"
        exit 1
    fi

    local subcommand=$1
    shift

    case $subcommand in
        start)
            qdrant_start "$@"
            ;;
        stop)
            qdrant_stop "$@"
            ;;
        status)
            qdrant_status "$@"
            ;;
        insert)
            qdrant_insert "$@"
            ;;
        *)
            log_error "Unknown qdrant subcommand: $subcommand"
            exit 1
            ;;
    esac
}

qdrant_start() {
    local mode="local"
    local queue="scc"
    local runtime_hours=48
    local memory_mb=32000

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --mode)
                mode="$2"
                shift 2
                ;;
            --queue)
                queue="$2"
                shift 2
                ;;
            --runtime)
                runtime_hours="$2"
                shift 2
                ;;
            --memory)
                memory_mb="$2"
                shift 2
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    log_info "Starting Qdrant server (mode=${mode}, queue=${queue})"

    # Ensure log directories exist
    mkdir -p logs/qdrant
    mkdir -p data/qdrant

    # Call start_server.sh directly
    bash modules/qdrant/scripts/start_server.sh \
        --container modules/qdrant/setup/singularity/qdrant.sif \
        --config modules/qdrant/setup/singularity/config.yaml \
        --storage data/qdrant \
        --memory-mb ${memory_mb} \
        --runtime $((runtime_hours * 3600)) \
        --job-name q_server \
        --mode ${mode} \
        --connection-info data/qdrant/connection_info.txt \
        --log logs/qdrant/server.log \
        --queue ${queue}

    if [[ $? -eq 0 ]]; then
        log_success "Qdrant server started successfully"
        if [[ -f "data/qdrant/connection_info.txt" ]]; then
            echo ""
            cat data/qdrant/connection_info.txt
        fi
    else
        log_error "Failed to start Qdrant server"
        exit 1
    fi
}

qdrant_stop() {
    log_info "Stopping Qdrant server..."
    bash modules/qdrant/scripts/stop_server.sh
}

qdrant_status() {
    bash modules/qdrant/scripts/check_status.sh
}

qdrant_insert() {
    if [[ $# -eq 0 ]]; then
        log_error "No dataset specified for insertion"
        echo ""
        echo "Available datasets:"
        echo "  pubmed           - Insert PubMed data"
        echo "  clinical_trials  - Insert Clinical Trials data"
        echo "  all              - Insert all datasets"
        exit 1
    fi

    local dataset=$1
    shift

    # Parse additional options
    local execution_mode="local"
    local cores=1
    local jobs=10
    local cuda_version=""
    local use_test_config=false

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
            --test)
                use_test_config=true
                shift
                ;;
            --cuda11.4)
                cuda_version="11.4"
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    log_info "Inserting ${dataset} to Qdrant (mode=${execution_mode})"

    # Check prerequisites
    check_snakemake

    # Determine config file
    local active_config="$config_file"
    if [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
        log_info "Using test configuration: config/test_config.yaml"
    fi

    # Auto-detect GPU queue and use config_gpu.yaml if on cluster (unless test mode)
    if [[ "$use_test_config" == false ]] && [[ "$execution_mode" == "cluster" ]]; then
        local queue=$(grep -A2 "^cluster:" ${active_config} | grep "default_queue:" | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/' || echo "scc")
        if [[ "$queue" == "gpu" ]]; then
            # Check if config_gpu.yaml exists
            if [[ -f "config/config_gpu.yaml" ]]; then
                active_config="config/config_gpu.yaml"
                log_info "Auto-selected GPU config: config_gpu.yaml (queue=gpu detected)"
            fi
        fi
    fi

    # Build Snakemake command for Qdrant insertion
    local snakemake_cmd="snakemake --snakefile modules/qdrant/Snakefile --configfile ${active_config} --latency-wait 60"

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        # Get queue from active config file (default: scc)
        local queue=$(grep -A2 "^cluster:" ${active_config} | grep "default_queue:" | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/' || echo "scc")

        # Build resource requirements and conda environment based on queue
        local gpu_resource=""
        local node_restriction=""
        local conda_env_override=""
        if [[ "$queue" == "gpu" ]]; then
            gpu_resource="-l gpu=1"

            # Check if CUDA 11.4 is requested
            if [[ "$cuda_version" == "11.4" ]]; then
                # Restrict to nodes with CUDA 11.4: scc116, scc117, scc066
                node_restriction="-l hostname=\\\"scc116|scc117|scc066\\\""
                conda_env_override="conda_env=bioyoda_gpu_cuda11"
                log_info "Submitting jobs to GPU cluster (queue=${queue}, env=bioyoda_gpu_cuda11, CUDA 11.4 nodes: scc116, scc117, scc066, max ${jobs} parallel jobs)"
            else
                # Restrict to nodes with CUDA 12.8: scc213, scc192, spiderman, hulk, scc195-scc199
                node_restriction="-l hostname=\\\"scc213|scc192|spiderman|hulk|scc195|scc196|scc197|scc198|scc199\\\""
                conda_env_override="conda_env=bioyoda_gpu"
                log_info "Submitting jobs to GPU cluster (queue=${queue}, env=bioyoda_gpu, CUDA 12.8 nodes only, max ${jobs} parallel jobs)"
            fi
        else
            log_info "Submitting jobs to SGE cluster (queue=${queue}, max ${jobs} parallel jobs)"
        fi

        snakemake_cmd="${snakemake_cmd} --executor cluster-generic \
            --cluster-generic-submit-cmd 'qsub -cwd -V -q ${queue} ${gpu_resource} ${node_restriction} -N {rule}.{jobid} -pe smp {threads} -l h_vmem={resources.mem_mb}M -l h_rt={resources.runtime} -o {params.LOG_cluster_log} -j y' \
            --jobs ${jobs} \
            --default-resources mem_mb=8192 runtime=604800 threads=1"
    else
        log_info "Running locally with ${cores} cores"
        snakemake_cmd="${snakemake_cmd} --cores ${cores}"
    fi

    # Add other options
    # In test mode, no retries for faster feedback
    local retries=3
    if [[ "$use_test_config" == true ]]; then
        retries=0
    fi
    snakemake_cmd="${snakemake_cmd} --use-conda --rerun-incomplete --retries ${retries} --printshellcmds"

    # Add conda env override if GPU queue
    if [[ -n "$conda_env_override" ]]; then
        snakemake_cmd="${snakemake_cmd} --config ${conda_env_override}"
    fi

    # Add target
    case $dataset in
        pubmed)
            snakemake_cmd="${snakemake_cmd} -- insert_pubmed"
            ;;
        clinical_trials)
            snakemake_cmd="${snakemake_cmd} -- insert_clinical_trials"
            ;;
        all)
            snakemake_cmd="${snakemake_cmd} -- insert_all"
            ;;
        *)
            log_error "Unknown dataset: ${dataset}"
            exit 1
            ;;
    esac

    log_info "Executing: ${snakemake_cmd}"
    eval ${snakemake_cmd}

    if [[ $? -eq 0 ]]; then
        log_success "Insertion completed successfully!"
    else
        log_error "Insertion failed! Check logs for details."
        exit 1
    fi
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
        qdrant)
            qdrant "$@"
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
