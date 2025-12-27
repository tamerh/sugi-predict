#!/bin/bash
##############################################################################
#
#   BioYoda Snakemake Command Builders
#   Constructs Snakemake commands for local and cluster execution
#
#   Note: GPU processing is done via Google Colab, not cluster.
#         See modules/*/README.md for Colab GPU instructions.
#
##############################################################################

# Default Snakemake settings
DEFAULT_SNAKEFILE="modules/Snakefile"
DEFAULT_LATENCY_WAIT=60
DEFAULT_MEM_MB=8192
DEFAULT_RUNTIME=604800  # 7 days in seconds
DEFAULT_RETRIES=3
TEST_RETRIES=0

# Build the cluster submission command
# Usage: build_cluster_submit_cmd <queue>
build_cluster_submit_cmd() {
    local queue="$1"
    echo "qsub -cwd -V -q ${queue} -N {rule}.{jobid} -pe smp {threads} -l h_vmem={resources.mem_mb}M -l h_rt={resources.runtime} -o {params.LOG_cluster_log} -j y"
}

# Build base Snakemake command
# Usage: build_snakemake_base <snakefile> <config_file>
build_snakemake_base() {
    local snakefile="$1"
    local config_file="$2"

    echo "snakemake --snakefile ${snakefile} --configfile ${config_file} --latency-wait ${DEFAULT_LATENCY_WAIT}"
}

# Build cluster execution options
# Usage: build_cluster_options <config_file> <jobs>
build_cluster_options() {
    local config_file="$1"
    local jobs="$2"

    local queue=$(get_queue_from_config "$config_file")
    local submit_cmd=$(build_cluster_submit_cmd "$queue")

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
# Usage: build_config_overrides <execution_mode> <update_mode>
build_config_overrides() {
    local execution_mode="$1"
    local update_mode="$2"

    echo "execution_mode=${execution_mode} update_mode=${update_mode}"
}

# Build complete Snakemake command for pipeline execution
# Usage: build_pipeline_command <snakefile> <config_file> <execution_mode> <jobs> <cores> <use_test> <update_mode> [dryrun] [target]
build_pipeline_command() {
    local snakefile="$1"
    local config_file="$2"
    local execution_mode="$3"
    local jobs="$4"
    local cores="$5"
    local use_test="$6"
    local update_mode="$7"
    local dryrun="${8:-}"
    local target="${9:-}"

    # Start with base command
    local cmd=$(build_snakemake_base "$snakefile" "$config_file")

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        cmd="${cmd} $(build_cluster_options "$config_file" "$jobs")"
    else
        cmd="${cmd} $(build_local_options "$cores")"
    fi

    # Add common options
    cmd="${cmd} $(build_common_options "$use_test" "$dryrun")"

    # Add config overrides
    local overrides=$(build_config_overrides "$execution_mode" "$update_mode")
    cmd="${cmd} --config ${overrides}"

    # Add target if specified
    if [[ -n "$target" ]] && [[ "$target" != "all" ]]; then
        cmd="${cmd} -- ${target}"
    fi

    echo "$cmd"
}

# Build Snakemake command for Qdrant insertion
# Usage: build_qdrant_insert_command <config_file> <execution_mode> <jobs> <cores> <use_test> <dataset>
build_qdrant_insert_command() {
    local config_file="$1"
    local execution_mode="$2"
    local jobs="$3"
    local cores="$4"
    local use_test="$5"
    local dataset="$6"

    local snakefile="modules/qdrant/Snakefile"

    # Start with base command
    local cmd=$(build_snakemake_base "$snakefile" "$config_file")

    # Add execution mode options
    if [[ "$execution_mode" == "cluster" ]]; then
        cmd="${cmd} $(build_cluster_options "$config_file" "$jobs")"
    else
        cmd="${cmd} $(build_local_options "$cores")"
    fi

    # Add common options (without keep-going for insertion)
    local retries=$DEFAULT_RETRIES
    if [[ "$use_test" == "true" ]]; then
        retries=$TEST_RETRIES
    fi
    cmd="${cmd} --use-conda --rerun-incomplete --retries ${retries} --printshellcmds"

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
# Usage: log_cluster_info <queue> <jobs>
log_cluster_info() {
    local queue="$1"
    local jobs="$2"
    log_info "Submitting to SGE cluster (queue=${queue}, max ${jobs} parallel jobs)"
}

# Log local execution info
# Usage: log_local_info <cores>
log_local_info() {
    local cores="$1"
    log_info "Running locally with ${cores} cores"
}
