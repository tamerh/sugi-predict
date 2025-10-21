#!/bin/bash
#
# HNSW Parameter Benchmark Suite
# Tests different HNSW configurations with single large segment
#
# Usage: ./run_hnsw_benchmark.sh [test_data_dir]
#

set -e

# Configuration
TEST_DATA_DIR="${1:-/localscratch/tgur/test_data}"
QDRANT_PORT=6333
QDRANT_BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$QDRANT_BENCH_DIR/benchmark_run.log"
RESULTS_DIR="$QDRANT_BENCH_DIR/results"
QDRANT_DATA_DIR="$QDRANT_BENCH_DIR/qdrant_data"  # Preserve Qdrant storage for investigation
COLLECTION_NAME="pubmed_bench"
PRESERVE_DATA="${PRESERVE_DATA:-true}"  # Set to false to cleanup (default: preserve)

# ============================================================================
# BENCHMARK CONFIGURATION - Edit these arrays to customize your tests
# ============================================================================
# HNSW configurations to test
M_VALUES=(32 64)                      # Graph connectivity (16=fast, 32=balanced, 64=high-quality)
EF_CONSTRUCT_VALUES=(256 512)        # Index build quality (100=fast, 256=balanced, 512=high-quality)
SEARCH_EF_VALUES=(256)        # Search accuracy (64=fast, 256=balanced, 512=accurate)

# Example: Test only m=32 with ef_construct=256
# M_VALUES=(32)
# EF_CONSTRUCT_VALUES=(256)
# SEARCH_EF_VALUES=(128 256)
# ============================================================================

# Fixed: Single large segment for all tests
MAX_SEGMENT_SIZE=1000000  # 1M points (enough for test data)
DEFAULT_SEGMENT_NUMBER=0  # 0 = dynamic (will create 1 large segment with MAX_SEGMENT_SIZE)
INDEXING_THRESHOLD=100000  # 100K points - force indexing for 712K dataset (lower = fewer segments)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log_section() {
    echo "" | tee -a "$LOG_FILE"
    echo "================================================================================" | tee -a "$LOG_FILE"
    echo -e "${BLUE}$*${NC}" | tee -a "$LOG_FILE"
    echo "================================================================================" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
}

# Initialize
mkdir -p "$RESULTS_DIR"
mkdir -p "$QDRANT_DATA_DIR"
> "$LOG_FILE"

log_section "QDRANT HNSW PARAMETER BENCHMARK"
log "Test data: $TEST_DATA_DIR"
log "Results: $RESULTS_DIR"
log "Qdrant data: $QDRANT_DATA_DIR"
log "Collection: $COLLECTION_NAME"
log "Segment strategy: max_segment_size=${MAX_SEGMENT_SIZE}, default_segment_number=${DEFAULT_SEGMENT_NUMBER}, indexing_threshold=${INDEXING_THRESHOLD}"
log "Data preservation: $PRESERVE_DATA"

# Verify test data
if [ ! -d "$TEST_DATA_DIR" ]; then
    log "${RED}ERROR: Test data not found: $TEST_DATA_DIR${NC}"
    exit 1
fi

NUM_FILES=$(ls -1 "$TEST_DATA_DIR"/*.index 2>/dev/null | wc -l)
log "${GREEN}✓ Found $NUM_FILES test files${NC}"

# Stop Qdrant function
stop_qdrant() {
    log "Stopping Qdrant..."
    "$QDRANT_BENCH_DIR/stop_local_qdrant.sh" >> "$LOG_FILE" 2>&1 || true
    sleep 2
}

# Cleanup function
cleanup() {
    log "Cleaning up storage..."
    rm -rf /localscratch/tgur/qdrant_test 2>/dev/null || true
    sleep 1
}

# Run benchmark for one configuration
run_benchmark() {
    local m=$1
    local ef_construct=$2
    local search_ef=$3
    local test_name="m${m}_efc${ef_construct}_ef${search_ef}"

    log_section "TEST: $test_name"

    # 1. Clean start
    log "Step 1: Clean environment"
    stop_qdrant
    cleanup

    # 2. Start Qdrant
    log "Step 2: Starting Qdrant server"
    "$QDRANT_BENCH_DIR/setup_local_qdrant.sh" >> "$LOG_FILE" 2>&1

    if ! curl -s "http://localhost:$QDRANT_PORT" > /dev/null 2>&1; then
        log "${RED}ERROR: Qdrant failed to start${NC}"
        return 1
    fi
    log "${GREEN}✓ Qdrant started${NC}"

    # 3. Insert data (collection will be created with HNSW settings if needed)
    log "Step 3: Inserting data (m=$m, ef_construct=$ef_construct, segments=$DEFAULT_SEGMENT_NUMBER, max_size=$MAX_SEGMENT_SIZE, indexing_threshold=$INDEXING_THRESHOLD)"
    INSERTION_START=$(date +%s)

    python "$QDRANT_BENCH_DIR/../../modules/qdrant/scripts/insert_from_faiss.py" \
        --faiss-dir "$TEST_DATA_DIR" \
        --qdrant-url "http://localhost:$QDRANT_PORT" \
        --collection "$COLLECTION_NAME" \
        --batch-size 500 \
        --hnsw-m "$m" \
        --hnsw-ef-construct "$ef_construct" \
        --max-segment-size "$MAX_SEGMENT_SIZE" \
        --default-segment-number "$DEFAULT_SEGMENT_NUMBER" \
        --indexing-threshold "$INDEXING_THRESHOLD" \
        --disable-quantization \
        >> "$LOG_FILE" 2>&1

    INSERTION_END=$(date +%s)
    INSERTION_TIME=$((INSERTION_END - INSERTION_START))

    log "${GREEN}✓ Data inserted (${INSERTION_TIME}s)${NC}"

    # 4. Wait for GREEN status
    log "Step 4: Waiting for collection to be GREEN"
    MAX_WAIT=1800
    WAIT_COUNT=0
    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
        COLL_STATUS=$(curl -s "http://localhost:$QDRANT_PORT/collections/$COLLECTION_NAME" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['status'])" 2>/dev/null || echo "unknown")

        if [ "$COLL_STATUS" = "green" ]; then
            log "${GREEN}✓ Collection is GREEN${NC}"
            break
        fi

        if [ $((WAIT_COUNT % 30)) -eq 0 ]; then
            log "  Status: $COLL_STATUS (waiting... ${WAIT_COUNT}s)"
        fi

        sleep 5
        WAIT_COUNT=$((WAIT_COUNT + 5))
    done

    if [ "$COLL_STATUS" != "green" ]; then
        log "${YELLOW}⚠ Collection still $COLL_STATUS after ${MAX_WAIT}s${NC}"
    fi

    # 5. Get memory usage
    MEMORY_USED_MB=$(ps aux | grep '[s]ingularity run.*qdrant' | awk '{sum+=$6} END {print int(sum/1024)}')
    if [ -z "$MEMORY_USED_MB" ]; then
        MEMORY_USED_MB=0
    fi

    # 6. Run benchmark
    log "Step 5: Running benchmark (search_ef=$search_ef)"
    python3 "$QDRANT_BENCH_DIR/qdrant_benchmark.py" \
        --qdrant-url "http://localhost:$QDRANT_PORT" \
        --collection "$COLLECTION_NAME" \
        --ef "$search_ef" \
        --output "$RESULTS_DIR/${test_name}.json" \
        2>&1 | tee -a "$LOG_FILE"

    # 7. Add insertion metrics
    if [ -f "$RESULTS_DIR/${test_name}.json" ]; then
        python3 << EOF
import json
result_file = "$RESULTS_DIR/${test_name}.json"
with open(result_file, 'r') as f:
    data = json.load(f)

data['insertion_time_s'] = $INSERTION_TIME
data['memory_used_mb'] = $MEMORY_USED_MB
data['hnsw_m'] = $m
data['hnsw_ef_construct'] = $ef_construct

with open(result_file, 'w') as f:
    json.dump(data, f, indent=2)
EOF

        avg_time=$(python3 -c "import json; print(json.load(open('$RESULTS_DIR/${test_name}.json'))['average_time_ms'])")
        log "${GREEN}✓ Avg time: ${avg_time}ms | Insert: ${INSERTION_TIME}s | Memory: ${MEMORY_USED_MB}MB${NC}"
    fi

    # 8. Preserve or cleanup Qdrant data
    log "Step 6: Stopping Qdrant"
    stop_qdrant

    if [ "$PRESERVE_DATA" = "true" ]; then
        # Copy Qdrant storage to persistent location for investigation
        log "Preserving Qdrant data for investigation..."
        TEST_DATA_DIR_PRESERVE="$QDRANT_DATA_DIR/$test_name"
        mkdir -p "$TEST_DATA_DIR_PRESERVE"

        if [ -d "/localscratch/tgur/qdrant_test/storage" ]; then
            cp -r /localscratch/tgur/qdrant_test/storage "$TEST_DATA_DIR_PRESERVE/" 2>/dev/null || true
            cp -r /localscratch/tgur/qdrant_test/snapshots "$TEST_DATA_DIR_PRESERVE/" 2>/dev/null || true
            cp /localscratch/tgur/qdrant_test/qdrant_config.yaml "$TEST_DATA_DIR_PRESERVE/" 2>/dev/null || true
            cp /localscratch/tgur/qdrant_test/logs/*.log "$TEST_DATA_DIR_PRESERVE/" 2>/dev/null || true

            # Get storage size and segment info
            STORAGE_SIZE=$(du -sh "$TEST_DATA_DIR_PRESERVE/storage" 2>/dev/null | cut -f1)
            log "  └─ Saved to: $TEST_DATA_DIR_PRESERVE"
            log "  └─ Storage size: $STORAGE_SIZE"

            # Show segment info
            if [ -d "$TEST_DATA_DIR_PRESERVE/storage/collections/$COLLECTION_NAME/0/segments" ]; then
                SEGMENT_COUNT=$(ls -1d "$TEST_DATA_DIR_PRESERVE/storage/collections/$COLLECTION_NAME/0/segments"/*/ 2>/dev/null | wc -l)
                log "  └─ Segments found: $SEGMENT_COUNT"
            fi
        fi

        # Still cleanup local scratch to free space
        cleanup
    else
        log "Cleaning up (PRESERVE_DATA=false)..."
        cleanup
    fi

    log "${GREEN}✓ Test completed${NC}"
}

# Run all benchmarks
log_section "RUNNING BENCHMARK TESTS"

test_count=0
total_tests=$((${#M_VALUES[@]} * ${#EF_CONSTRUCT_VALUES[@]} * ${#SEARCH_EF_VALUES[@]}))

for m in "${M_VALUES[@]}"; do
    for ef_construct in "${EF_CONSTRUCT_VALUES[@]}"; do
        for search_ef in "${SEARCH_EF_VALUES[@]}"; do
            test_count=$((test_count + 1))
            log "${BLUE}Progress: $test_count/$total_tests${NC}"
            run_benchmark "$m" "$ef_construct" "$search_ef" || log "${RED}Test failed, continuing...${NC}"
            sleep 2
        done
    done
done

# Generate report
log_section "GENERATING COMPARISON REPORT"

REPORT_FILE="$RESULTS_DIR/benchmark_report_$(date '+%Y%m%d_%H%M%S').txt"
python3 "$QDRANT_BENCH_DIR/generate_report.py" --results-dir "$RESULTS_DIR" --output "$REPORT_FILE"
cat "$REPORT_FILE" | tee -a "$LOG_FILE"
log "Report saved to: $REPORT_FILE"

log_section "BENCHMARK COMPLETE"
log "Total tests: $test_count"
log "Results: $RESULTS_DIR"
log "Qdrant data preserved: $QDRANT_DATA_DIR ($(du -sh "$QDRANT_DATA_DIR" 2>/dev/null | cut -f1))"
log "Log: $LOG_FILE"

if [ "$PRESERVE_DATA" = "true" ]; then
    echo ""
    echo -e "${GREEN}Qdrant data preserved for investigation:${NC}"
    echo "  Location: $QDRANT_DATA_DIR"
    echo "  Example: ls -lh $QDRANT_DATA_DIR/m16_efc100_ef64/storage/collections/"
    echo ""
fi

echo ""
echo -e "${GREEN}Benchmark complete!${NC}"
