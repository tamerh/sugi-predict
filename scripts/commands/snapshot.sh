#!/bin/bash
##############################################################################
#
#   BioYoda Snapshot Command
#   Creates isolated code snapshots for production runs
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Main snapshot function
cmd_snapshot() {
    local snapshot_name=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                snapshot_name="$2"
                shift 2
                ;;
            --help|-h)
                echo "Usage: bioyoda.sh snapshot --name <name>"
                echo ""
                echo "Creates an isolated code snapshot for production runs."
                echo ""
                echo "Example:"
                echo "  bioyoda.sh snapshot --name prod_v1.0"
                echo "  cd snapshots/prod_v1.0/code"
                echo "  ./bioyoda.sh enju pubmed"
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                echo "Usage: bioyoda.sh snapshot --name <name>"
                exit 1
                ;;
        esac
    done

    if [[ -z "$snapshot_name" ]]; then
        log_error "--name required"
        echo "Usage: bioyoda.sh snapshot --name <name>"
        exit 1
    fi

    # Create snapshot structure
    local snapshots_dir="${PIPELINE_DIR}/snapshots"
    local snapshot_root="${snapshots_dir}/${snapshot_name}"
    local code_dir="${snapshot_root}/code"

    if [[ -d "$snapshot_root" ]]; then
        log_error "Snapshot '${snapshot_name}' already exists at: ${snapshot_root}"
        exit 1
    fi

    log_divider
    log_info "Creating snapshot: ${snapshot_name}"
    log_divider
    echo ""

    # Step 1: Create directory structure
    log_info "Step 1/4: Creating directory structure"
    mkdir -p "${snapshots_dir}"
    mkdir -p "${code_dir}"

    # Symlink each snapshot's raw_data to the shared repo-root raw_data store
    local shared_raw_data="$(dirname "${snapshots_dir}")/raw_data"
    mkdir -p "${shared_raw_data}"
    ln -s "${shared_raw_data}" "${snapshot_root}/raw_data"
    log_info "  raw_data: SYMLINKED to shared ${shared_raw_data}"

    # Create per-snapshot directories
    mkdir -p "${snapshot_root}"/{data,logs,state}
    log_info "  data/: Per-snapshot (outputs)"
    log_info "  logs/: Per-snapshot (logs)"
    log_info "  state/: Per-snapshot (tracking files)"
    log_success "Directories created"
    echo ""

    # Step 2: Copy code
    log_info "Step 2/4: Copying code"
    log_info "  Copying modules/..."
    rsync -a --exclude='out*/' --exclude='*_out/' --exclude='.git/' \
        --exclude='__pycache__/' --exclude='*.pyc' --exclude='.snakemake/' \
        "${PIPELINE_DIR}/modules/" "${code_dir}/modules/"

    log_info "  Copying config/..."
    rsync -a "${PIPELINE_DIR}/config/" "${code_dir}/config/"

    log_info "  Copying scripts/..."
    rsync -a "${PIPELINE_DIR}/scripts/" "${code_dir}/scripts/"

    log_info "  Copying bioyoda.sh..."
    cp "${PIPELINE_DIR}/bioyoda.sh" "${code_dir}/"
    chmod +x "${code_dir}/bioyoda.sh"

    log_success "Code copied"
    echo ""

    # Step 3: Modify config files
    log_info "Step 3/4: Modifying config files"

    for config_file in "${code_dir}"/config/*.yaml; do
        if [[ -f "$config_file" ]]; then
            local filename=$(basename "$config_file")
            log_info "  Processing ${filename}..."

            python3 "${COMMANDS_DIR}/../modify_snapshot_config.py" \
                "$config_file" \
                "$snapshot_root" \
                "$code_dir" || {
                log_warning "Could not update ${filename}"
            }
        fi
    done

    log_success "Config files updated"
    echo ""

    # Step 4: Create manifest
    log_info "Step 4/4: Creating snapshot manifest"

    local git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    local git_commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    local git_short=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    local git_status="clean"
    if ! git diff --quiet 2>/dev/null; then
        git_status="MODIFIED"
    fi

    cat > "${code_dir}/SNAPSHOT_INFO.txt" << EOF
================================================================================
                      BioYoda Snapshot Information
================================================================================

Snapshot Name:    ${snapshot_name}
Created:          $(date)
Created By:       $(whoami)
Source Directory: ${PIPELINE_DIR}

Git Information:
  Branch:         ${git_branch}
  Commit:         ${git_commit}
  Short Hash:     ${git_short}
  Status:         ${git_status}

Directory Structure:
  ${snapshot_root}/
  ├── code/              # Code snapshot (this directory)
  │   ├── modules/       # Pipeline modules
  │   ├── scripts/       # Modular scripts
  │   ├── config/        # Modified configs
  │   └── bioyoda.sh     # Main script
  ├── raw_data/          # SYMLINK to shared repo-root raw_data/
  ├── data/              # Processed data and outputs (PER-SNAPSHOT)
  ├── logs/              # Pipeline logs (PER-SNAPSHOT)
  └── state/             # State tracking files (PER-SNAPSHOT)

Usage:
  cd snapshots/${snapshot_name}/code
  ./bioyoda.sh enju pubmed --config config/config.yaml

Configuration:
  - All config files have been updated with:
    base_dir: ${snapshot_root}
    project_root: ${code_dir}

  - This ensures all outputs go to the snapshot directory
  - Scripts are loaded from the snapshot code directory
  - Fully isolated from the main development directory

Raw Data Sharing:
  - raw_data/ is SYMLINKED to shared repo-root raw_data/
  - Saves disk space by reusing downloaded data across snapshots
  - Each snapshot maintains its own state/ for tracking

================================================================================
EOF

    log_success "Manifest created"
    echo ""

    # Final summary
    echo ""
    log_divider
    log_success "Snapshot created successfully!"
    log_divider
    echo ""
    log_info "Snapshot Details:"
    log_info "  Name:     ${snapshot_name}"
    log_info "  Location: ${snapshot_root}/"
    log_info "  Code:     ${code_dir}/"
    log_info "  Git:      ${git_short} (${git_branch})"
    echo ""
    log_info "To use this snapshot:"
    echo ""
    echo "  cd snapshots/${snapshot_name}/code"
    echo "  ./bioyoda.sh enju pubmed --config config/config.yaml"
    echo ""
    log_info "Snapshot info: snapshots/${snapshot_name}/code/SNAPSHOT_INFO.txt"
    echo ""
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_snapshot "$@"
fi
