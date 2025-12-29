#!/bin/bash
##############################################################################
#
#   BioYoda Configuration Management
#   Handles config file resolution, merging, and value extraction
#
##############################################################################

# Default configuration
BIOYODA_VERSION="0.2.0"
DEFAULT_CONFIG="config/config.yaml"
TEST_CONFIG="config/test_config.yaml"
DEFAULT_CONDA_ENV="bioyoda"

# Get base_dir from config file
# Usage: get_base_dir [config_file]
get_base_dir() {
    local config_file="${1:-$DEFAULT_CONFIG}"
    local base_dir

    if [[ -f "$config_file" ]]; then
        base_dir=$(grep "^base_dir:" "$config_file" | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    fi

    echo "${base_dir:-out}"
}

# Get a value from config file
# Usage: get_config_value <key> [config_file] [default]
get_config_value() {
    local key="$1"
    local config_file="${2:-$DEFAULT_CONFIG}"
    local default_value="${3:-}"
    local value

    if [[ -f "$config_file" ]]; then
        value=$(grep "^${key}:" "$config_file" | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/' | head -1)
    fi

    echo "${value:-$default_value}"
}

# Get nested config value (e.g., cluster.default_queue)
# Usage: get_nested_config_value <section> <key> [config_file] [default]
get_nested_config_value() {
    local section="$1"
    local key="$2"
    local config_file="${3:-$DEFAULT_CONFIG}"
    local default_value="${4:-}"
    local value

    if [[ -f "$config_file" ]]; then
        value=$(grep -A20 "^${section}:" "$config_file" | grep "${key}:" | head -1 | sed 's/.*: *"\?\([^"]*\)"\?.*/\1/')
    fi

    echo "${value:-$default_value}"
}

# Get cluster queue from config
# Usage: get_queue_from_config [config_file]
get_queue_from_config() {
    local config_file="${1:-$DEFAULT_CONFIG}"
    get_nested_config_value "cluster" "default_queue" "$config_file" "scc"
}

# Get Qdrant storage path from config
# Usage: get_qdrant_storage_path [config_file]
# Returns: absolute path to Qdrant storage directory
get_qdrant_storage_path() {
    local config_file="${1:-$DEFAULT_CONFIG}"
    local value

    if [[ -f "$config_file" ]]; then
        value=$(grep -A10 "^qdrant:" "$config_file" | grep -A5 "storage:" | grep "path:" | sed 's/.*path:\s*"\?\([^"#]*\)"\?.*/\1/' | xargs)
    fi

    # Default to snapshots/qdrant_latest if not set
    value="${value:-snapshots/qdrant_latest}"

    # Make absolute if relative
    if [[ ! "$value" = /* ]]; then
        value="$(pwd)/$value"
    fi

    echo "$value"
}

# Merge test config from base config + overrides
# Usage: merge_test_config
merge_test_config() {
    if [[ ! -f "config/config.yaml" ]]; then
        log_error "config/config.yaml not found!"
        return 1
    fi

    if [[ ! -f "config/test_overrides.yaml" ]]; then
        log_error "config/test_overrides.yaml not found!"
        return 1
    fi

    log_info "Generating test_config.yaml from config.yaml + test_overrides.yaml..."

    # Use the standalone Python script
    if [[ -f "${SCRIPT_DIR}/merge_config.py" ]]; then
        python3 "${SCRIPT_DIR}/merge_config.py"
    else
        # Fallback to inline Python if script not found
        python3 << 'MERGE_PYTHON'
import sys

try:
    from ruamel.yaml import YAML
    use_ruamel = True
except ImportError:
    import yaml
    use_ruamel = False
    print("  Warning: ruamel.yaml not found, using standard yaml (comments will be lost)", file=sys.stderr)

def deep_merge(base, override):
    """Deep merge override dict into base dict"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base

if use_ruamel:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.default_flow_style = False

    with open('config/config.yaml') as f:
        config = yaml.load(f)
    with open('config/test_overrides.yaml') as f:
        overrides = yaml.load(f)

    merged = deep_merge(config, overrides)

    with open('config/test_config.yaml', 'w') as f:
        yaml.dump(merged, f)

    print("  Generated config/test_config.yaml (comments preserved)")
else:
    with open('config/config.yaml') as f:
        config = yaml.safe_load(f)
    with open('config/test_overrides.yaml') as f:
        overrides = yaml.safe_load(f)

    merged = deep_merge(config, overrides)

    with open('config/test_config.yaml', 'w') as f:
        yaml.dump(merged, f, default_flow_style=False, sort_keys=False)

    print("  Generated config/test_config.yaml (no comments)")
MERGE_PYTHON
    fi

    return $?
}

# Resolve which config file to use based on arguments
# Usage: resolve_config <use_test> <custom_config> [default_config]
# Returns: path to config file to use
resolve_config() {
    local use_test="${1:-false}"
    local custom_config="$2"
    local default_config="${3:-$DEFAULT_CONFIG}"

    if [[ -n "$custom_config" ]]; then
        echo "$custom_config"
    elif [[ "$use_test" == "true" ]]; then
        merge_test_config >/dev/null 2>&1 || true
        echo "$TEST_CONFIG"
    else
        echo "$default_config"
    fi
}

# Auto-select GPU config if cluster queue is gpu
# Usage: auto_select_gpu_config <current_config> <execution_mode>
auto_select_gpu_config() {
    local current_config="$1"
    local execution_mode="$2"

    if [[ "$execution_mode" == "cluster" ]]; then
        local queue=$(get_queue_from_config "$current_config")
        if [[ "$queue" == "gpu" ]] && [[ -f "config/config_gpu.yaml" ]]; then
            echo "config/config_gpu.yaml"
            return 0
        fi
    fi

    echo "$current_config"
}

# Ensure required directories exist based on config
# Usage: ensure_directories <config_file>
ensure_directories() {
    local config_file="${1:-$DEFAULT_CONFIG}"
    local base_dir=$(get_base_dir "$config_file")

    mkdir -p "${base_dir}/logs/cluster"
    mkdir -p "${base_dir}/logs/pids"
    mkdir -p "${base_dir}/logs/qdrant"
    mkdir -p "${base_dir}/logs/api"
    mkdir -p "${base_dir}/data/qdrant"
    mkdir -p "${base_dir}/data/processed"
}
