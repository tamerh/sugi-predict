#!/bin/bash
##############################################################################
#
#   BioYoda Test Framework
#   Runs end-to-end tests with fixtures or full pipeline
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

# Test cleanup function
test_cleanup() {
    local base_dir="$1"
    log_info "Cleaning up test environment..."

    # Stop servers if running (api.sh removed when the API layer moved to sugi-agent)
    if [[ -f "${COMMANDS_DIR}/api.sh" ]]; then
        source "${COMMANDS_DIR}/api.sh"
        api_stop --test 2>/dev/null || true
    fi

    source "${COMMANDS_DIR}/qdrant.sh"
    qdrant_stop --test 2>/dev/null || true
}

# Main test function
cmd_test() {
    local pipeline_mode=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --pipeline)
                pipeline_mode=true
                shift
                ;;
            --help|-h)
                echo "Usage: bioyoda.sh test [--pipeline]"
                echo ""
                echo "  Default: Run tests with fixtures (fast - 2-3 minutes)"
                echo "  --pipeline: Run full pipeline test (slow - 15-20 minutes)"
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                echo "Usage: bioyoda.sh test [--pipeline]"
                exit 1
                ;;
        esac
    done

    # Generate test config
    merge_test_config || exit 1

    local test_config="config/test_config.yaml"
    local base_dir="test_out"

    echo ""
    log_divider
    if [[ "$pipeline_mode" == "true" ]]; then
        log_info "BioYoda Test Suite - PIPELINE MODE"
        log_info "This will run the full E2E pipeline with test data"
    else
        log_info "BioYoda Test Suite - FIXTURE MODE"
        log_info "This will use pre-processed test fixtures (fast)"
    fi
    log_divider
    echo ""

    # Trap cleanup on exit
    trap "test_cleanup ${base_dir}" EXIT

    # Step 1: Setup
    log_info "Step 1/6: Setting up test environment"

    if [[ "$pipeline_mode" == "true" ]]; then
        log_info "  Cleaning test_out directory..."
        rm -rf "${base_dir}/"* 2>/dev/null || true
    fi

    # Create directories
    mkdir -p "${base_dir}/raw_data/pubmed/baseline"
    mkdir -p "${base_dir}/raw_data/clinical_trials"
    mkdir -p "${base_dir}/logs"

    # Copy fixtures
    log_info "  Copying test fixtures..."
    if [[ -f "tests/fixtures/pubmed/test_abstracts.xml.gz" ]]; then
        cp "tests/fixtures/pubmed/test_abstracts.xml.gz" "${base_dir}/raw_data/pubmed/baseline/" || {
            log_error "Failed to copy PubMed fixture"
            exit 1
        }
    else
        log_warning "PubMed fixture not found: tests/fixtures/pubmed/test_abstracts.xml.gz"
    fi

    log_success "Test environment ready"
    echo ""

    # Step 2: Process data
    if [[ "$pipeline_mode" == "true" ]]; then
        log_info "Step 2/6: Running data processing pipeline"
        log_info "  This may take 15-20 minutes..."

        source "${COMMANDS_DIR}/run.sh"
        cmd_run all --test --local --cores 4 || {
            log_error "Pipeline processing failed"
            exit 1
        }

        log_success "Pipeline processing complete"
    else
        log_info "Step 2/6: Using pre-processed fixtures (skipping full pipeline)"

        source "${COMMANDS_DIR}/run.sh"
        cmd_run all --test --local --cores 2 || {
            log_error "Fixture processing failed"
            exit 1
        }

        log_success "Fixture data ready"
    fi
    echo ""

    # Step 3: Start Qdrant
    log_info "Step 3/6: Starting Qdrant server"
    source "${COMMANDS_DIR}/qdrant.sh"
    qdrant_start --mode local --test || {
        log_error "Failed to start Qdrant server"
        exit 1
    }

    # Wait for Qdrant
    sleep 3
    if ! wait_for_url "http://localhost:6333/healthz" 10; then
        log_error "Qdrant server not responding"
        exit 1
    fi

    log_success "Qdrant server running"
    echo ""

    # Step 4: Insert data
    log_info "Step 4/6: Inserting data to Qdrant"
    qdrant_insert all --test --local --cores 2 || {
        log_error "Data insertion failed"
        exit 1
    }

    log_success "Data insertion complete"
    echo ""

    # Step 5: Start API
    # NOTE: the API/query layer was extracted out of bioyoda into sugi-agent and
    # scripts/commands/api.sh was removed. When it's absent we run a pipeline-only
    # smoke test (Steps 1-4) and skip API-dependent query validation (Steps 5-6).
    local test_result=0
    if [[ -f "${COMMANDS_DIR}/api.sh" ]]; then
        log_info "Step 5/6: Starting API server"
        source "${COMMANDS_DIR}/api.sh"
        api_start --test || {
            log_error "Failed to start API server"
            exit 1
        }

        # Wait for API (model loading can take time)
        log_info "  Waiting for API to be ready (loading model)..."
        sleep 5

        local api_ready=false
        for i in {1..30}; do
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                api_ready=true
                break
            fi
            if (( i % 5 == 0 )); then
                log_info "    Still waiting... (${i}s elapsed)"
            fi
            sleep 1
        done

        if [[ "$api_ready" != "true" ]]; then
            log_error "API server not responding after 35 seconds"
            log_info "Check API log: ${base_dir}/logs/api/"
            exit 1
        fi

        log_success "API server running"
        echo ""

        # Step 6: Run query validation
        log_info "Step 6/6: Running query validation"
        echo ""

        if [[ -f "tests/validate_queries.py" ]]; then
            python tests/validate_queries.py --verbose --api-url http://localhost:8000
            test_result=$?
        else
            log_warning "Validation script not found: tests/validate_queries.py"
            log_info "Skipping query validation"
        fi

        echo ""
        api_stop --test 2>/dev/null || true
        sleep 1
    else
        log_warning "Step 5/6: API layer not present (api.sh removed; moved to sugi-agent)"
        log_info "  Running PIPELINE-ONLY smoke test: query validation skipped."
        log_info "  Pipeline + Qdrant insert (Steps 1-4) is what's being validated."
        echo ""
    fi

    # Cleanup happens via trap
    log_info "Cleaning up test environment..."
    sleep 1
    qdrant_stop --test 2>/dev/null || true
    sleep 1

    # Remove trap since we cleaned up manually
    trap - EXIT

    echo ""
    log_divider
    if [[ $test_result -eq 0 ]]; then
        log_success "ALL TESTS PASSED"
        log_divider
        echo ""
        return 0
    else
        log_error "TESTS FAILED"
        log_divider
        echo ""
        log_info "Check logs:"
        echo "  - API log: ${base_dir}/logs/api/"
        echo "  - Qdrant log: ${base_dir}/logs/qdrant/"
        echo "  - Pipeline logs: ${base_dir}/logs/"
        echo ""
        return 1
    fi
}

# If script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cmd_test "$@"
fi
