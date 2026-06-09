#!/bin/bash
##############################################################################
#
#   BioYoda Snakemake Command Builders
#   Constructs Snakemake commands for LOCAL execution only.
#
#   Note: SGE/cluster execution was retired in the Enju migration — distribution
#         is handled by Enju (multi-citizen + git), not qsub. GPU work runs on a
#         GPU citizen (or via Colab). Use `bioyoda.sh enju <module>` for the DAG.
#
##############################################################################

# Default Snakemake settings
DEFAULT_SNAKEFILE="modules/Snakefile"
DEFAULT_LATENCY_WAIT=60
DEFAULT_MEM_MB=8192
DEFAULT_RUNTIME=604800  # 7 days in seconds
DEFAULT_RETRIES=3
TEST_RETRIES=0

# Build base Snakemake command
# Usage: build_snakemake_base <snakefile> <config_file>
build_snakemake_base() {
    local snakefile="$1"
    local config_file="$2"

    echo "snakemake --snakefile ${snakefile} --configfile ${config_file} --latency-wait ${DEFAULT_LATENCY_WAIT}"
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
# Usage: build_pipeline_command <snakefile> <config_file> <cores> <use_test> <update_mode> [dryrun] [target]
build_pipeline_command() {
    local snakefile="$1"
    local config_file="$2"
    local cores="$3"
    local use_test="$4"
    local update_mode="$5"
    local dryrun="${6:-}"
    local target="${7:-}"

    # Start with base command
    local cmd=$(build_snakemake_base "$snakefile" "$config_file")

    # Local execution only (SGE/cluster retired — Enju handles distribution)
    cmd="${cmd} $(build_local_options "$cores")"

    # Add common options
    cmd="${cmd} $(build_common_options "$use_test" "$dryrun")"

    # Add config overrides
    local overrides=$(build_config_overrides "local" "$update_mode")
    cmd="${cmd} --config ${overrides}"

    # Add target if specified
    if [[ -n "$target" ]] && [[ "$target" != "all" ]]; then
        cmd="${cmd} -- ${target}"
    fi

    echo "$cmd"
}

# Build Snakemake command for Qdrant insertion
# Usage: build_qdrant_insert_command <config_file> <cores> <use_test> <dataset>
build_qdrant_insert_command() {
    local config_file="$1"
    local cores="$2"
    local use_test="$3"
    local dataset="$4"

    local snakefile="modules/qdrant/Snakefile"

    # Start with base command
    local cmd=$(build_snakemake_base "$snakefile" "$config_file")

    # Local execution only (SGE/cluster retired)
    cmd="${cmd} $(build_local_options "$cores")"

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

# Log local execution info
# Usage: log_local_info <cores>
log_local_info() {
    local cores="$1"
    log_info "Running locally with ${cores} cores"
}
