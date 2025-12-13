#!/bin/bash
##############################################################################
#
#   BioYoda Snakemake Command Builders
#   Constructs Snakemake commands for local and cluster execution
#
##############################################################################

# Default Snakemake settings
DEFAULT_SNAKEFILE="modules/Snakefile"
DEFAULT_LATENCY_WAIT=60
DEFAULT_MEM_MB=8192
DEFAULT_RUNTIME=604800  # 7 days in seconds
DEFAULT_RETRIES=3
TEST_RETRIES=0

# CUDA 12.x nodes (newer GPUs)
CUDA12_NODES="scc213|scc192|spiderman|hulk|scc195|scc196|scc197|scc198|scc199"

# CUDA 11.4 nodes (older GPUs)
CUDA11_NODES="scc116|scc117|scc066"

# Build GPU-specific cluster options
# Usage: build_gpu_options <cuda_version>
# Returns: gpu_resource node_restriction conda_env
build_gpu_options() {
    local cuda_version="$1"
    local gpu_resource="-l gpu=1"
    local node_restriction=""
    local conda_env=""

    if [[ "$cuda_version" == "11.4" ]]; then
        node_restriction="-l hostname='\"'\"'${CUDA11_NODES}'\"'\"'"
        conda_env="bioyoda_gpu_cuda11"
    else
        node_restriction="-l hostname='\"'\"'${CUDA12_NODES}'\"'\"'"
        conda_env="bioyoda_gpu"
    fi

    echo "$gpu_resource" "$node_restriction" "$conda_env"
}

# Build the cluster submission command
# Usage: build_cluster_submit_cmd <queue> <cuda_version>
build_cluster_submit_cmd() {
    local queue="$1"
    local cuda_version="$2"
    local gpu_resource=""
    local node_restriction=""

    if [[ "$queue" == "gpu" ]]; then
        gpu_resource="-l gpu=1"
        if [[ "$cuda_version" == "11.4" ]]; then
            node_restriction="-l hostname='\"'\"'${CUDA11_NODES}'\"'\"'"
        else
            node_restriction="-l hostname='\"'\"'${CUDA12_NODES}'\"'\"'"
        fi
    fi

    echo "qsub -cwd -V -q ${queue} ${gpu_resource} ${node_restriction} -N {rule}.{jobid} -pe smp {threads} -l h_vmem={resources.mem_mb}M -l h_rt={resources.runtime} -o {params.LOG_cluster_log} -j y"
}

# Get conda environment override based on queue and CUDA version
# Usage: get_conda_env_override <queue> <cuda_version>
get_conda_env_override() {
    local queue="$1"
    local cuda_version="$2"

    if [[ "$queue" == "gpu" ]]; then
        if [[ "$cuda_version" == "11.4" ]]; then
            echo "conda_env=bioyoda_gpu_cuda11"
        else
            echo "conda_env=bioyoda_gpu"
        fi
    fi
}

# Build base Snakemake command
# Usage: build_snakemake_base <snakefile> <config_file>
build_snakemake_base() {
    local snakefile="$1"
    local config_file="$2"

    echo "snakemake --snakefile ${snakefile} --configfile ${config_file} --latency-wait ${DEFAULT_LATENCY_WAIT}"
}

# Build cluster execution options
# Usage: build_cluster_options <config_file> <jobs> <cuda_version>
build_cluster_options() {
    local config_file="$1"
    local jobs="$2"
    local cuda_version="$3"

    local queue=$(get_queue_from_config "$config_file")
    local submit_cmd=$(build_cluster_submit_cmd "$queue" "$cuda_version")

    echo "--executor cluster-generic --cluster-generic-submit-cmd '${submit_cmd}' --jobs ${jobs} --default-resources mem_mb=${DEFAULT_MEM_MB} runtime=${DEFAULT_RUNTIME} threads=1"
}

# Build local execution options
# Usage: build_local_options <cores>
build_local_options() {
    local cores="$1"
    echo "--cores ${cores}"
}

# Build common Snakemake options
# Usage: build_common_options <use_test> [dryrun]
build_common_options() {
    local use_test="$1"
    local dryrun="${2:-}"

    local retries=$DEFAULT_RETRIES
    if [[ "$use_test" == "true" ]]; then
        retries=$TEST_RETRIES
    fi

    echo "--use-conda --keep-going --rerun-incomplete --retries ${retries} --printshellcmds ${dryrun}"
}

# Build config overrides string
# Usage: build_config_overrides <execution_mode> <update_mode> <queue> <cuda_version>
build_config_overrides() {
    local execution_mode="$1"
    local update_mode="$2"
    local queue="$3"
    local cuda_version="$4"

    local overrides="execution_mode=${execution_mode} update_mode=${update_mode}"

    local conda_override=$(get_conda_env_override "$queue" "$cuda_version")
    if [[ -n "$conda_override" ]]; then
        overrides="${overrides} ${conda_override}"
    fi

    echo "$overrides"
}

# Build complete Snakemake command for pipeline execution
# Usage: build_pipeline_command <snakefile> <config_file> <execution_mode> <jobs> <cores> <cuda_version> <use_test> <update_mode> [dryrun] [target]
build_pipeline_command() {
    local snakefile="$1"
    local config_file="$2"
    local execution_mode="$3"
    local jobs="$4"
    local cores="$5"
    local cuda_version="$6"
    local use_test="$7"
    local update_mode="$8"
    local dryrun="${9:-}"
    local target="${10:-}"

    # Start with base command
    local cmd=$(build_snakemake_base "$snakefile" "$config_file")

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        cmd="${cmd} $(build_cluster_options "$config_file" "$jobs" "$cuda_version")"
    else
        cmd="${cmd} $(build_local_options "$cores")"
    fi

    # Add common options
    cmd="${cmd} $(build_common_options "$use_test" "$dryrun")"

    # Add config overrides
    local queue=$(get_queue_from_config "$config_file")
    local overrides=$(build_config_overrides "$execution_mode" "$update_mode" "$queue" "$cuda_version")
    cmd="${cmd} --config ${overrides}"

    # Add target if specified
    if [[ -n "$target" ]] && [[ "$target" != "all" ]]; then
        cmd="${cmd} -- ${target}"
    fi

    echo "$cmd"
}

# Build Snakemake command for Qdrant insertion
# Usage: build_qdrant_insert_command <config_file> <execution_mode> <jobs> <cores> <cuda_version> <use_test> <dataset>
build_qdrant_insert_command() {
    local config_file="$1"
    local execution_mode="$2"
    local jobs="$3"
    local cores="$4"
    local cuda_version="$5"
    local use_test="$6"
    local dataset="$7"

    local snakefile="modules/qdrant/Snakefile"

    # Start with base command
    local cmd=$(build_snakemake_base "$snakefile" "$config_file")

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        cmd="${cmd} $(build_cluster_options "$config_file" "$jobs" "$cuda_version")"
    else
        cmd="${cmd} $(build_local_options "$cores")"
    fi

    # Add common options (without keep-going for insertion)
    local retries=$DEFAULT_RETRIES
    if [[ "$use_test" == "true" ]]; then
        retries=$TEST_RETRIES
    fi
    cmd="${cmd} --use-conda --rerun-incomplete --retries ${retries} --printshellcmds"

    # Add conda env override if GPU
    local queue=$(get_queue_from_config "$config_file")
    local conda_override=$(get_conda_env_override "$queue" "$cuda_version")
    if [[ -n "$conda_override" ]]; then
        cmd="${cmd} --config ${conda_override}"
    fi

    # Map dataset to target
    local target=""
    case $dataset in
        pubmed) target="insert_pubmed" ;;
        clinical_trials) target="insert_clinical_trials" ;;
        patents) target="insert_patents" ;;
        patents_text) target="insert_patents_text" ;;
        patents_compounds) target="insert_patents_compounds" ;;
        esm2) target="insert_esm2" ;;
        all) target="insert_all" ;;
        *)
            log_error "Unknown dataset: ${dataset}"
            return 1
            ;;
    esac

    cmd="${cmd} -- ${target}"
    echo "$cmd"
}

# Log cluster submission info
# Usage: log_cluster_info <queue> <cuda_version> <jobs>
log_cluster_info() {
    local queue="$1"
    local cuda_version="$2"
    local jobs="$3"

    if [[ "$queue" == "gpu" ]]; then
        if [[ "$cuda_version" == "11.4" ]]; then
            log_info "Submitting to GPU cluster (queue=${queue}, env=bioyoda_gpu_cuda11, CUDA 11.4 nodes: ${CUDA11_NODES}, max ${jobs} parallel jobs)"
        else
            log_info "Submitting to GPU cluster (queue=${queue}, env=bioyoda_gpu, CUDA 12.x nodes, max ${jobs} parallel jobs)"
        fi
    else
        log_info "Submitting to SGE cluster (queue=${queue}, max ${jobs} parallel jobs)"
    fi
}

# Log local execution info
# Usage: log_local_info <cores>
log_local_info() {
    local cores="$1"
    log_info "Running locally with ${cores} cores"
}
