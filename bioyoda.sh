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
# Note: log_dir and pid_dir are set dynamically based on base_dir from config

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
    start [--test]            Start both Qdrant and API servers (shortcut)
    stop [--test]             Stop both Qdrant and API servers (shortcut)
    run <module> [options]    Run data processing pipeline (PubMed/Clinical Trials)
    stop <module> [options]   Stop a running data processing pipeline
    status                    Show pipeline status
    test [--pipeline]         Run test suite (default: fixture mode, --pipeline: full E2E)
    qdrant <subcommand>       Manage Qdrant vector database (start/stop/insert/status)
    api <subcommand>          Manage BioYoda Search API (start/stop/test/search/status)
    search [query]            Quick search across collections (interactive if no query)
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
    stop-insert <dataset>     Stop a running insertion job

API Subcommands:
    start                     Start API server (foreground or background)
    stop                      Stop API server
    status                    Check API server status
    search                    CLI search tool (interactive and non-interactive)

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
    --bg, -b                  Run in background with nohup
    --cores N                 Number of cores (for local mode)
    --jobs N                  Max parallel jobs (for cluster mode)
    --test                    Use test config (config/test_config.yaml)
    --cuda11.4                Use CUDA 11.4 nodes (scc116, scc117, scc066) with bioyoda_gpu_cuda11 env

API Start Options:
    --port N                  Port number (default: 8000)
    --host HOST               Host address (default: 0.0.0.0)
    --bg, -b                  Run in background with logging
    --reload                  Auto-reload on code changes (development)
    --config FILE             Use custom config file
    --test                    Use test config (config/test_config.yaml)

Stop Options:
    --clean, -c               Also clean intermediate files after stopping

Examples:
    # Quick Start/Stop (both Qdrant and API)
    $0 start                                   # Start both servers
    $0 start --test                            # Start both with test config
    $0 stop                                    # Stop both servers
    $0 stop --test                             # Stop both with test config

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
    $0 qdrant insert pubmed --cluster --jobs 10 --bg
    $0 qdrant insert clinical_trials --cluster --jobs 10 --bg
    $0 qdrant insert all --cluster --jobs 20 --bg

    # Use CUDA 11.4 nodes for insertion
    $0 qdrant insert pubmed --cluster --jobs 10 --cuda11.4 --bg

    # 4. Stop insertion if needed
    $0 qdrant stop-insert pubmed

    # 5. Stop server when done
    $0 qdrant stop

    # API Operations (search and query data)
    # 1. Start API server (requires Qdrant to be running)
    $0 api start                           # Start in foreground
    $0 api start --bg                      # Start in background
    $0 api start --port 8001 --bg          # Custom port, background

    # 2. Use API for searching
    $0 search                              # Interactive mode
    $0 search "CRISPR gene editing"        # Quick search
    $0 api search "cancer" --limit 5       # Search with options
    $0 api status                          # Check API status
    $0 api stop                            # Stop API server

    # Testing
    # Run tests with fixtures (fast - 2-3 minutes)
    $0 test

    # Run full pipeline test (slow - 15-20 minutes)
    $0 test --pipeline

    # Monitor progress
    tail -f out/logs/bioyoda_pubmed_main.log
    tail -f out/logs/qdrant/insert_pubmed.log

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

    # Extract base_dir from config to create logs in correct location
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    # Set pid_dir based on base_dir
    local pid_dir="${base_dir}/logs/pids"

    # Create necessary directories (use base_dir for logs)
    mkdir -p ${base_dir}/logs/cluster
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
    local main_log="${base_dir}/logs/bioyoda_${module}_main.log"

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

    # Extract base_dir from config
    local base_dir=$(grep "^base_dir:" ${config_file} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    # Check PubMed status
    echo ""
    echo "=== PubMed Module ==="
    if [[ -f "${base_dir}/data/merged/pubmed/master_pubmed.index" ]]; then
        local size=$(du -h ${base_dir}/data/merged/pubmed/master_pubmed.index | cut -f1)
        log_success "Merged index exists (${size})"
    else
        log_warning "Merged index not found"
    fi

    # Count processed files
    local processed_count=$(find ${base_dir}/data/processed/pubmed -name "*.index" 2>/dev/null | wc -l)
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
    if [[ -f "${base_dir}/data/processed/clinical_trials/trials_data.json" ]]; then
        local size=$(du -h ${base_dir}/data/processed/clinical_trials/trials_data.json | cut -f1)
        log_success "Trials data exists (${size})"
    else
        log_warning "Trials data not found"
    fi

    echo ""
    echo "=== Qdrant Module ==="

    # Check if Qdrant server is running
    if [[ -f "${base_dir}/data/qdrant/connection_info.txt" ]]; then
        log_success "Qdrant server connection info found"
        cat ${base_dir}/data/qdrant/connection_info.txt | grep QDRANT_URL
    else
        log_info "Qdrant server not running"
    fi

    # Check collections
    if [[ -f "${base_dir}/data/qdrant/collections/pubmed_abstracts.done" ]]; then
        log_success "PubMed collection complete"
    else
        log_info "PubMed collection not completed"
    fi

    if [[ -f "${base_dir}/data/qdrant/collections/clinical_trials.done" ]]; then
        log_success "Clinical Trials collection complete"
    else
        log_info "Clinical Trials collection not completed"
    fi

    # Check storage size
    if [[ -d "${base_dir}/data/qdrant/storage" ]]; then
        local qdrant_size=$(du -sh ${base_dir}/data/qdrant/storage 2>/dev/null | cut -f1)
        log_info "Qdrant storage size: ${qdrant_size}"
    fi
}

validate() {
    local module="${1:-pubmed}"

    # Extract base_dir from config
    local base_dir=$(grep "^base_dir:" ${config_file} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    log_info "Validating module: ${module}"

    case $module in
        pubmed)
            if [[ ! -f "${base_dir}/data/merged/pubmed/master_pubmed.index" ]]; then
                log_error "PubMed index not found. Run pipeline first."
                exit 1
            fi

            # Run validation rule
            snakemake --snakefile ${snakefile} --configfile ${config_file} \
                pubmed_validate --cores 1 --use-conda

            # Display validation report
            if [[ -f "${base_dir}/data/merged/pubmed/validation_report.txt" ]]; then
                echo ""
                cat ${base_dir}/data/merged/pubmed/validation_report.txt
            fi
            ;;
        qdrant)
            if [[ ! -f "${base_dir}/data/qdrant/connection_info.txt" ]]; then
                log_error "Qdrant server not running or connection info not found."
                exit 1
            fi

            log_info "Checking Qdrant collections..."
            source ${base_dir}/data/qdrant/connection_info.txt

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

    # Extract base_dir from config
    local base_dir=$(grep "^base_dir:" ${config_file} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    log_warning "This will remove intermediate files. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log_info "Cancelled"
        exit 0
    fi

    case $module in
        pubmed)
            log_info "Cleaning PubMed processed files..."
            rm -rf ${base_dir}/data/processed/pubmed/*
            log_success "PubMed cleaned"
            ;;
        clinical_trials)
            log_info "Cleaning Clinical Trials processed files..."
            rm -rf ${base_dir}/data/processed/clinical_trials/*
            log_success "Clinical Trials cleaned"
            ;;
        qdrant)
            log_info "Cleaning Qdrant storage and collections..."
            rm -rf ${base_dir}/data/qdrant/storage/*
            rm -f ${base_dir}/data/qdrant/connection_info.txt
            rm -f ${base_dir}/data/qdrant/collections/*.done
            log_success "Qdrant cleaned"
            ;;
        all)
            log_info "Cleaning all processed files..."
            rm -rf ${base_dir}/data/processed/*
            rm -rf ${base_dir}/data/qdrant/storage/*
            rm -f ${base_dir}/data/qdrant/connection_info.txt
            rm -f ${base_dir}/data/qdrant/collections/*.done
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
    # Args: $1 = main_pid, $2 = is_cluster (true/false), $3 = base_dir, $4 = module

    if [[ -z "$1" ]]; then
        log_error "No process ID provided"
        return 1
    fi

    local main_pid=$1
    local is_cluster=${2:-false}
    local base_dir=${3:-"out"}
    local module=${4:-"unknown"}

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
        local main_log="${base_dir}/logs/bioyoda_${module}_main.log"
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
    # Extract base_dir from config
    local base_dir=$(grep "^base_dir:" ${config_file} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    local qdrant_pid_file="${base_dir}/data/qdrant/qdrant.pid"
    local connection_info="${base_dir}/data/qdrant/connection_info.txt"

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

    # Extract base_dir from config to find pid files
    local base_dir=$(grep "^base_dir:" ${config_file} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi
    local pid_dir="${base_dir}/logs/pids"

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
        kill_process ${main_pid} ${is_cluster} ${base_dir} ${module}
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
        echo "  start       - Start Qdrant server (local or cluster)"
        echo "  stop        - Stop Qdrant server"
        echo "  status      - Check Qdrant server status"
        echo "  insert      - Insert data to Qdrant (pubmed, clinical_trials, or all)"
        echo "  stop-insert - Stop a running insertion job"
        echo ""
        echo "Examples:"
        echo "  $0 qdrant start --mode cluster --queue gpu"
        echo "  $0 qdrant insert pubmed --bg"
        echo "  $0 qdrant stop-insert pubmed"
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
        stop-insert)
            qdrant_stop_insert "$@"
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
    local use_test_config=false
    local custom_config=""

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
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Determine active config
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
        log_info "Using test configuration: config/test_config.yaml"
    fi

    log_info "Starting Qdrant server (mode=${mode}, queue=${queue})"

    # Use base_dir from config for consistent output location
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    # Ensure log directories exist (use base_dir)
    mkdir -p ${base_dir}/logs/qdrant
    mkdir -p ${base_dir}/data/qdrant

    # Call start_server.sh directly
    bash modules/qdrant/scripts/start_server.sh \
        --container modules/qdrant/setup/singularity/qdrant.sif \
        --config config/qdrant_config.yaml \
        --storage ${base_dir}/data/qdrant \
        --memory-mb ${memory_mb} \
        --runtime $((runtime_hours * 3600)) \
        --job-name q_server \
        --mode ${mode} \
        --connection-info ${base_dir}/data/qdrant/connection_info.txt \
        --log ${base_dir}/logs/qdrant/server.log \
        --queue ${queue}

    if [[ $? -eq 0 ]]; then
        log_success "Qdrant server started successfully"
        if [[ -f "${base_dir}/data/qdrant/connection_info.txt" ]]; then
            echo ""
            cat ${base_dir}/data/qdrant/connection_info.txt
        fi
    else
        log_error "Failed to start Qdrant server"
        exit 1
    fi
}

qdrant_stop() {
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Determine active config
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
    fi

    # Get base_dir from config
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"
    fi

    log_info "Stopping Qdrant server (base_dir=${base_dir})..."

    # Call stop_server.sh with paths relative to base_dir
    # Override the STORAGE path by setting environment variable
    QDRANT_STORAGE_PATH="${base_dir}/data/qdrant" \
    bash modules/qdrant/scripts/stop_server.sh
}

qdrant_status() {
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Determine active config
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
    fi

    # Get base_dir from config
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"
    fi

    # Call check_status.sh with paths relative to base_dir
    # Override the STORAGE path by setting environment variable
    QDRANT_STORAGE_PATH="${base_dir}/data/qdrant" \
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
    local custom_config=""
    local background=false

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
            --bg|-b)
                background=true
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
            --config)
                custom_config="$2"
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
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
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

    # Get base_dir for logging and PID management
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"  # default fallback
    fi

    # Create necessary directories
    local pid_dir="${base_dir}/logs/pids"
    mkdir -p ${base_dir}/logs/qdrant
    mkdir -p ${pid_dir}

    # Determine PID file name
    local pid_file="${pid_dir}/qdrant_insert_${dataset}"
    if [[ "$execution_mode" == "cluster" ]]; then
        pid_file="${pid_file}.cluster.pid"
    else
        pid_file="${pid_file}.local.pid"
    fi

    # Check if already running
    if [[ -f "${pid_file}" ]]; then
        local existing_pid=$(cat "${pid_file}")
        if ps -p ${existing_pid} > /dev/null 2>&1; then
            log_error "Qdrant insertion already running for ${dataset} with PID ${existing_pid}"
            log_info "Use './bioyoda.sh qdrant stop-insert ${dataset}' to stop it first"
            exit 1
        else
            # Stale PID file, remove it
            rm -f "${pid_file}"
        fi
    fi

    # Execute
    local main_log="${base_dir}/logs/qdrant/insert_${dataset}_main.log"

    if [[ "$background" == true ]]; then
        log_info "Starting Qdrant insertion in background..."
        log_info "Executing: ${snakemake_cmd}"
        log_info "Main log: ${main_log}"
        log_info "Monitor with: tail -f ${main_log}"

        # Create wrapper script with cleanup
        local wrapper_script="${pid_dir}/qdrant_insert_${dataset}_wrapper.sh"
        cat > "${wrapper_script}" <<WRAPPER
#!/bin/bash
# Wrapper script for background execution with cleanup

# Run Qdrant insertion
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

        log_success "Qdrant insertion started in background (PID: ${main_pid})"
        log_info "To monitor: tail -f ${main_log}"
        log_info "To stop: ./bioyoda.sh qdrant stop-insert ${dataset}"
        log_info "Rule logs directory: ${base_dir}/logs/qdrant/"
    else
        log_info "Executing: ${snakemake_cmd}"
        eval ${snakemake_cmd}
        local exit_code=$?

        if [[ ${exit_code} -eq 0 ]]; then
            log_success "Insertion completed successfully!"
        else
            log_error "Insertion failed! Check logs for details."
            log_info "Main log: ${main_log}"
            log_info "Rule logs directory: ${base_dir}/logs/qdrant/"
            exit 1
        fi
    fi
}

qdrant_stop_insert() {
    if [[ $# -eq 0 ]]; then
        log_error "No dataset specified"
        echo ""
        echo "Available datasets:"
        echo "  pubmed           - Stop PubMed insertion"
        echo "  clinical_trials  - Stop Clinical Trials insertion"
        echo "  all              - Stop all insertions"
        exit 1
    fi

    local dataset=$1
    shift

    # Parse additional options
    local use_test_config=false
    local custom_config=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    log_info "Stopping Qdrant insertion for ${dataset}..."

    # Determine config file
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
    fi

    # Get base_dir
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"
    fi
    local pid_dir="${base_dir}/logs/pids"

    # Check for PID files (cluster or local)
    local pid_file=""
    local is_cluster=false

    if [[ -f "${pid_dir}/qdrant_insert_${dataset}.cluster.pid" ]]; then
        pid_file="${pid_dir}/qdrant_insert_${dataset}.cluster.pid"
        is_cluster=true
    elif [[ -f "${pid_dir}/qdrant_insert_${dataset}.local.pid" ]]; then
        pid_file="${pid_dir}/qdrant_insert_${dataset}.local.pid"
        is_cluster=false
    else
        log_warning "No running insertion found for dataset: ${dataset}"
        log_info "Cleaning up Snakemake locks anyway..."
        rm -rf modules/qdrant/.snakemake/locks/ 2>/dev/null || true
        return 0
    fi

    # Read PID and check if process is running
    local main_pid=$(cat "${pid_file}")

    if ps -p ${main_pid} > /dev/null 2>&1; then
        log_info "Killing process tree (PID: ${main_pid})..."
        kill_process ${main_pid} ${is_cluster} ${base_dir} "qdrant_insert_${dataset}"
        log_success "Insertion stopped"
    else
        log_warning "Process ${main_pid} not running (stale PID file)"
    fi

    # Remove PID file
    rm -f "${pid_file}"

    # Clean up Snakemake locks for Qdrant workflow
    log_info "Cleaning up Snakemake locks..."
    rm -rf modules/qdrant/.snakemake/locks/ 2>/dev/null || true

    log_success "Stop completed"
}

##############################################################################
# API Management Functions
##############################################################################

api() {
    if [[ $# -eq 0 ]]; then
        log_error "No api subcommand specified"
        echo ""
        echo "Available subcommands:"
        echo "  start    - Start API server (local or background)"
        echo "  stop     - Stop API server"
        echo "  status   - Check API server status"
        echo "  search   - CLI search tool (interactive and non-interactive)"
        echo ""
        echo "Examples:"
        echo "  $0 api start                    # Start in foreground"
        echo "  $0 api start --bg               # Start in background"
        echo "  $0 api start --test             # Start in test mode (auto-background)"
        echo "  $0 api start --port 8001        # Use custom port"
        echo "  $0 api search \"CRISPR\"          # Quick search"
        echo "  $0 api search --interactive     # Interactive mode"
        echo "  $0 api stop                     # Stop server"
        exit 1
    fi

    local subcommand=$1
    shift

    case $subcommand in
        start)
            api_start "$@"
            ;;
        stop)
            api_stop "$@"
            ;;
        status)
            api_status "$@"
            ;;
        search)
            api_search "$@"
            ;;
        *)
            log_error "Unknown api subcommand: $subcommand"
            exit 1
            ;;
    esac
}

api_start() {
    local port=8000
    local host="0.0.0.0"
    local reload=false
    local background=false
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port)
                port="$2"
                shift 2
                ;;
            --host)
                host="$2"
                shift 2
                ;;
            --reload)
                reload=true
                shift
                ;;
            --bg|-b)
                background=true
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
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Determine active config
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
        log_info "Using test configuration: config/test_config.yaml"
        # Test mode: automatically run in background
        background=true
        log_info "Test mode: running in background automatically"
    fi

    # Get base_dir from config
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"
    fi

    local pid_dir="${base_dir}/logs/pids"
    local pid_file="${pid_dir}/api_server.pid"

    # Check if already running
    if [[ -f "${pid_file}" ]]; then
        local existing_pid=$(cat "${pid_file}")
        if ps -p ${existing_pid} > /dev/null 2>&1; then
            log_error "API server already running with PID ${existing_pid}"
            log_info "Use './bioyoda.sh api stop' to stop it first"
            exit 1
        else
            # Stale PID file, remove it
            rm -f "${pid_file}"
        fi
    fi

    log_info "Starting BioYoda API server (port=${port}, host=${host})"

    # Check if Qdrant is running
    if ! curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
        log_error "Qdrant server is not running!"
        echo ""
        log_info "Please start Qdrant first:"
        echo "  ./bioyoda.sh qdrant start                                    # local mode"
        echo "  ./bioyoda.sh qdrant start --mode cluster --queue gpu        # cluster mode"
        echo ""
        exit 1
    fi
    log_success "Qdrant server is running"

    # Create necessary directories
    mkdir -p ${base_dir}/logs/api
    mkdir -p ${pid_dir}

    # Build uvicorn command
    local reload_flag=""
    if [[ "$reload" == true ]]; then
        reload_flag="--reload"
    fi

    local uvicorn_cmd="python -m uvicorn scripts.main:app --host ${host} --port ${port} ${reload_flag} --log-level info"

    # Execute
    if [[ "$background" == true ]]; then
        local api_log="${base_dir}/logs/api/server.log"
        log_info "Starting API server in background..."
        log_info "Log: ${api_log}"
        log_info "Monitor with: tail -f ${api_log}"

        # Create wrapper script with cleanup
        local wrapper_script="${pid_dir}/api_wrapper.sh"
        cat > "${wrapper_script}" <<WRAPPER
#!/bin/bash
# Wrapper script for background API execution with cleanup

# Change to API directory
cd "${pipeline_dir}/modules/api"

# Run API server
${uvicorn_cmd}
EXIT_CODE=\$?

# Remove PID file
rm -f "${pid_file}"

exit \$EXIT_CODE
WRAPPER
        chmod +x "${wrapper_script}"

        nohup bash "${wrapper_script}" > "${api_log}" 2>&1 &
        local api_pid=$!
        echo ${api_pid} > "${pid_file}"

        # Wait a moment and check if it's still running
        sleep 2
        if ps -p ${api_pid} > /dev/null 2>&1; then
            log_success "API server started in background (PID: ${api_pid})"
            log_info "API available at: http://localhost:${port}"
            log_info "Docs available at: http://localhost:${port}/docs"
            log_info "To monitor: tail -f ${api_log}"
            log_info "To stop: ./bioyoda.sh api stop"
        else
            log_error "API server failed to start. Check log: ${api_log}"
            rm -f "${pid_file}"
            exit 1
        fi
    else
        log_info "Starting API server in foreground..."
        log_info "API will be available at: http://localhost:${port}"
        log_info "Docs will be available at: http://localhost:${port}/docs"
        log_info "Press Ctrl+C to stop"
        echo ""

        cd "${pipeline_dir}/modules/api"
        eval ${uvicorn_cmd}
    fi
}

api_stop() {
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Determine active config
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
    fi

    # Get base_dir from config
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"
    fi

    local pid_dir="${base_dir}/logs/pids"
    local pid_file="${pid_dir}/api_server.pid"

    log_info "Stopping API server..."

    if [[ ! -f "${pid_file}" ]]; then
        log_warning "No running API server found (PID file not found)"
        return 0
    fi

    local api_pid=$(cat "${pid_file}")

    if ps -p ${api_pid} > /dev/null 2>&1; then
        log_info "Stopping API server (PID: ${api_pid})..."
        # Use kill_process to kill entire process tree (wrapper + uvicorn)
        kill_process ${api_pid} false ${base_dir} "api"
        log_success "API server stopped"
    else
        log_warning "Process ${api_pid} not running (stale PID file)"
    fi

    rm -f "${pid_file}"
}

api_status() {
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                custom_config="$2"
                shift 2
                ;;
            --test)
                use_test_config=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Determine active config
    local active_config="$config_file"
    if [[ -n "$custom_config" ]]; then
        active_config="$custom_config"
    elif [[ "$use_test_config" == true ]]; then
        active_config="config/test_config.yaml"
    fi

    # Get base_dir from config
    local base_dir=$(grep "^base_dir:" ${active_config} | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    if [[ -z "$base_dir" ]]; then
        base_dir="out"
    fi

    local pid_file="${base_dir}/logs/pids/api_server.pid"

    log_info "Checking API server status..."
    echo ""

    # Check PID file
    if [[ -f "${pid_file}" ]]; then
        local api_pid=$(cat "${pid_file}")
        if ps -p ${api_pid} > /dev/null 2>&1; then
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

api_search() {
    # Forward all arguments to the search CLI tool
    python "${pipeline_dir}/modules/api/scripts/bioyoda_search.py" "$@"
}

##############################################################################
# Test Functions
##############################################################################

test() {
    local pipeline_mode=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --pipeline)
                pipeline_mode=true
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                echo "Usage: $0 test [--pipeline]"
                echo ""
                echo "  Default: Run tests with fixtures (fast - 2-3 minutes)"
                echo "  --pipeline: Run full pipeline test (slow - 15-20 minutes)"
                exit 1
                ;;
        esac
    done

    # Use test config
    local test_config="config/test_config.yaml"
    local base_dir="test_out"  # test_config.yaml uses base_dir: test_out/

    echo ""
    log_info "============================================================"
    if [[ "$pipeline_mode" == true ]]; then
        log_info "BioYoda Test Suite - PIPELINE MODE"
        log_info "This will run the full E2E pipeline with test data"
    else
        log_info "BioYoda Test Suite - FIXTURE MODE"
        log_info "This will use pre-processed test fixtures (fast)"
    fi
    log_info "============================================================"
    echo ""

    # Trap cleanup on exit
    trap "test_cleanup ${base_dir}" EXIT

    # Step 1: Setup
    log_info "Step 1/6: Setting up test environment"

    # Clean test_out directory if pipeline mode
    if [[ "$pipeline_mode" == true ]]; then
        log_info "  Cleaning test_out directory..."
        rm -rf ${base_dir}/* 2>/dev/null || true
    fi

    # Create necessary directories
    mkdir -p ${base_dir}/raw_data/pubmed/baseline
    mkdir -p ${base_dir}/raw_data/clinical_trials
    mkdir -p ${base_dir}/logs

    # Copy fixtures to test_out for processing
    log_info "  Copying test fixtures..."
    cp tests/fixtures/pubmed/test_abstracts.xml.gz ${base_dir}/raw_data/pubmed/baseline/ || {
        log_error "Failed to copy PubMed fixture"
        exit 1
    }

    log_success "Test environment ready"
    echo ""

    # Step 2: Process data or use fixtures
    if [[ "$pipeline_mode" == true ]]; then
        log_info "Step 2/6: Running data processing pipeline"
        log_info "  This may take 15-20 minutes..."

        # Run both pipelines
        ./bioyoda.sh run all --test --local --cores 4 || {
            log_error "Pipeline processing failed"
            exit 1
        }

        log_success "Pipeline processing complete"
    else
        log_info "Step 2/6: Using pre-processed fixtures (skipping pipeline)"

        # In fixture mode, copy pre-processed data if needed
        # For now, we'll just run minimal processing
        ./bioyoda.sh run all --test --local --cores 2 || {
            log_error "Fixture processing failed"
            exit 1
        }

        log_success "Fixture data ready"
    fi
    echo ""

    # Step 3: Start Qdrant server
    log_info "Step 3/6: Starting Qdrant server"
    ./bioyoda.sh qdrant start --mode local --test || {
        log_error "Failed to start Qdrant server"
        exit 1
    }

    # Wait for Qdrant to be ready
    sleep 3
    if ! curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
        log_error "Qdrant server not responding"
        exit 1
    fi

    log_success "Qdrant server running"
    echo ""

    # Step 4: Insert data to Qdrant
    log_info "Step 4/6: Inserting data to Qdrant"
    ./bioyoda.sh qdrant insert all --test --local --cores 2 || {
        log_error "Data insertion failed"
        exit 1
    }

    log_success "Data insertion complete"
    echo ""

    # Step 5: Start API server
    log_info "Step 5/6: Starting API server"
    ./bioyoda.sh api start --test || {
        log_error "Failed to start API server"
        exit 1
    }

    # Wait for API to be ready (model loading can take time)
    log_info "  Waiting for API to be ready (loading model)..."
    sleep 5
    local api_ready=false
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            api_ready=true
            break
        fi
        # Show progress every 5 seconds
        if (( i % 5 == 0 )); then
            log_info "    Still waiting... (${i}s elapsed)"
        fi
        sleep 1
    done

    if [[ "$api_ready" != true ]]; then
        log_error "API server not responding after 35 seconds"
        log_info "Check API log: ${base_dir}/logs/api/server.log"
        exit 1
    fi

    log_success "API server running"
    echo ""

    # Step 6: Run query validation
    log_info "Step 6/6: Running query validation"
    echo ""

    # Run the validation script
    python tests/validate_queries.py --verbose --api-url http://localhost:8000
    local test_result=$?

    echo ""

    # Cleanup
    log_info "Cleaning up test environment..."
    ./bioyoda.sh api stop --test 2>/dev/null || true
    sleep 1
    ./bioyoda.sh qdrant stop --test 2>/dev/null || true
    sleep 1

    echo ""
    log_info "============================================================"
    if [[ ${test_result} -eq 0 ]]; then
        log_success "ALL TESTS PASSED"
        log_info "============================================================"
        echo ""
        return 0
    else
        log_error "TESTS FAILED"
        log_info "============================================================"
        echo ""
        log_info "Check logs:"
        echo "  - API log: ${base_dir}/logs/api/server.log"
        echo "  - Qdrant log: ${base_dir}/logs/qdrant/server.log"
        echo "  - Pipeline logs: ${base_dir}/logs/"
        echo ""
        return 1
    fi
}

test_cleanup() {
    local base_dir=$1

    # Cleanup servers if still running
    ./bioyoda.sh api stop --test 2>/dev/null || true
    ./bioyoda.sh qdrant stop --test 2>/dev/null || true
}

##############################################################################
# Quick Start/Stop Functions
##############################################################################

start_all() {
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test)
                use_test_config=true
                shift
                ;;
            --config)
                custom_config="$2"
                shift 2
                ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                echo "Usage: $0 start [--test] [--config FILE]"
                exit 1
                ;;
        esac
    done

    log_info "============================================================"
    log_info "Starting BioYoda servers (Qdrant + API)"
    log_info "============================================================"
    echo ""

    # Build arguments for subcommands
    local config_args=""
    if [[ "$use_test_config" == true ]]; then
        config_args="--test"
        log_info "Using test configuration"
    elif [[ -n "$custom_config" ]]; then
        config_args="--config $custom_config"
    fi

    # Step 1: Start Qdrant
    log_info "Step 1/2: Starting Qdrant server"
    qdrant_start --mode local $config_args || {
        log_error "Failed to start Qdrant server"
        exit 1
    }

    # Wait for Qdrant to be ready
    log_info "  Waiting for Qdrant to be ready..."
    sleep 3
    if ! curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
        log_error "Qdrant server not responding"
        exit 1
    fi
    log_success "Qdrant server ready"
    echo ""

    # Step 2: Start API
    log_info "Step 2/2: Starting API server"
    api_start --bg $config_args || {
        log_error "Failed to start API server"
        log_warning "Cleaning up: stopping Qdrant..."
        qdrant_stop $config_args 2>/dev/null || true
        exit 1
    }

    echo ""
    log_info "============================================================"
    log_success "BioYoda servers started successfully!"
    log_info "============================================================"
    echo ""
    log_info "Services:"
    log_info "  - Qdrant: http://localhost:6333"
    log_info "  - API: http://localhost:8000"
    log_info "  - API Docs: http://localhost:8000/docs"
    echo ""
    log_info "To stop: $0 stop $config_args"
    echo ""
}

stop_all() {
    local use_test_config=false
    local custom_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test)
                use_test_config=true
                shift
                ;;
            --config)
                custom_config="$2"
                shift 2
                ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                echo "Usage: $0 stop [--test] [--config FILE]"
                exit 1
                ;;
        esac
    done

    log_info "============================================================"
    log_info "Stopping BioYoda servers (API + Qdrant)"
    log_info "============================================================"
    echo ""

    # Build arguments for subcommands
    local config_args=""
    if [[ "$use_test_config" == true ]]; then
        config_args="--test"
    elif [[ -n "$custom_config" ]]; then
        config_args="--config $custom_config"
    fi

    # Step 1: Stop API first (it depends on Qdrant)
    log_info "Step 1/2: Stopping API server"
    api_stop $config_args 2>/dev/null || true
    sleep 1
    echo ""

    # Step 2: Stop Qdrant
    log_info "Step 2/2: Stopping Qdrant server"
    qdrant_stop $config_args 2>/dev/null || true
    sleep 1

    echo ""
    log_info "============================================================"
    log_success "BioYoda servers stopped"
    log_info "============================================================"
    echo ""
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
        start)
            # Check if it's a module stop (e.g., "stop pubmed") or server stop
            if [[ $# -gt 0 ]] && [[ "$1" != "--"* ]]; then
                # This is likely a typo or old usage, show error
                log_error "Unknown module: $1"
                echo ""
                echo "Did you mean:"
                echo "  $0 start              # Start Qdrant and API servers"
                echo "  $0 run $1             # Run data processing pipeline"
                exit 1
            else
                # Start both Qdrant and API
                start_all "$@"
            fi
            ;;
        stop)
            # Check if it's a module stop (e.g., "stop pubmed") or server stop
            if [[ $# -gt 0 ]] && [[ "$1" != "--"* ]]; then
                # This is stopping a pipeline module
                stop "$@"
            else
                # Stop both API and Qdrant servers
                stop_all "$@"
            fi
            ;;
        run)
            run "$@"
            ;;
        status)
            status "$@"
            ;;
        test)
            test "$@"
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
        api)
            api "$@"
            ;;
        search)
            # Top-level alias for api search (convenient for frequent use)
            # If no arguments, start interactive mode
            if [[ $# -eq 0 ]]; then
                python "${pipeline_dir}/modules/api/scripts/bioyoda_search.py" --interactive
            else
                python "${pipeline_dir}/modules/api/scripts/bioyoda_search.py" "$@"
            fi
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
