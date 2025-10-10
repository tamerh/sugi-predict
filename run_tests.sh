#!/bin/bash
##############################################################################
#
#   BioYoda Test Runner
#   Quick script to run tests with common configurations
#
##############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== BioYoda Test Suite ===${NC}"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest not installed${NC}"
    echo "Install with: pip install pytest pytest-cov"
    exit 1
fi

# Setup test fixtures
echo -e "${BLUE}Setting up test fixtures...${NC}"

# Create test raw data directories
mkdir -p test_out/raw_data/pubmed/baseline
mkdir -p test_out/raw_data/clinical_trials

# Copy PubMed fixture if it exists
PUBMED_FIXTURE="tests/fixtures/pubmed/test_abstracts.xml.gz"
if [ -f "$PUBMED_FIXTURE" ]; then
    echo -e "${GREEN}  ✓ Copying PubMed test fixture to test_out/raw_data/pubmed/baseline/${NC}"
    cp "$PUBMED_FIXTURE" test_out/raw_data/pubmed/baseline/
else
    echo -e "${YELLOW}  ⚠ PubMed fixture not found: $PUBMED_FIXTURE${NC}"
    echo -e "${YELLOW}    Generate it with: python tests/scripts/generate_pubmed_fixture.py${NC}"
fi

# Clinical Trials uses NCT ID filtering via config (no file copy needed)
NCT_IDS_FILE="tests/fixtures/clinical_trials/test_nct_ids.txt"
if [ -f "$NCT_IDS_FILE" ]; then
    echo -e "${GREEN}  ✓ Clinical Trials NCT IDs file ready: $NCT_IDS_FILE${NC}"
else
    echo -e "${YELLOW}  ⚠ Clinical Trials NCT IDs file not found: $NCT_IDS_FILE${NC}"
fi

echo ""

# Parse command line arguments
MODE="${1:-all}"

case $MODE in
    "all")
        echo -e "${BLUE}Running all tests...${NC}"
        pytest -v
        ;;

    "unit")
        echo -e "${BLUE}Running unit tests only...${NC}"
        pytest -v tests/unit/
        ;;

    "integration")
        echo -e "${BLUE}Running integration tests only (validates existing data)...${NC}"
        pytest -v tests/integration/ -m integration
        ;;

    "e2e")
        echo -e "${YELLOW}Running E2E tests (SLOW - actually runs pipeline)...${NC}"
        echo -e "${YELLOW}This will take 15-25 minutes!${NC}"
        pytest -v tests/integration/test_pubmed_e2e.py tests/integration/test_clinical_trials_e2e.py -m e2e
        ;;

    "quick")
        echo -e "${BLUE}Running quick tests (no slow tests)...${NC}"
        pytest -v -m "not slow"
        ;;

    "coverage")
        echo -e "${BLUE}Running tests with coverage report...${NC}"
        pytest --cov=modules --cov-report=term --cov-report=html
        echo -e "${GREEN}Coverage report saved to htmlcov/index.html${NC}"
        ;;

    "pubmed")
        echo -e "${BLUE}Running PubMed tests (unit + e2e)...${NC}"
        echo -e "${YELLOW}Note: E2E test will run full pipeline (~10-15 min with test config)${NC}"
        pytest -v tests/unit/pubmed/ tests/integration/test_pubmed_e2e.py
        ;;

    "ct"|"clinical_trials")
        echo -e "${BLUE}Running Clinical Trials tests (unit + e2e)...${NC}"
        echo -e "${YELLOW}Note: E2E test will run full pipeline (~5-10 min with test config)${NC}"
        pytest -v tests/unit/clinical_trials/ tests/integration/test_clinical_trials_e2e.py
        ;;

    "qdrant")
        echo -e "${BLUE}Running Qdrant tests (unit + e2e)...${NC}"
        echo -e "${YELLOW}Note: E2E test requires Qdrant server (~5-10 min)${NC}"
        pytest -v tests/unit/qdrant/ tests/integration/test_qdrant_e2e.py
        ;;

    "api")
        echo -e "${BLUE}Running API tests...${NC}"
        echo -e "${YELLOW}Note: This will start API server in test mode if not running${NC}"

        # Check if API is already running
        API_RUNNING=false
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}API server already running${NC}"
            API_RUNNING=true
        else
            echo -e "${YELLOW}Starting API server in background (test mode)...${NC}"
            ./bioyoda.sh api start --test

            # Wait for API to be ready (poll with timeout)
            echo -e "${YELLOW}Waiting for API server to be ready...${NC}"
            MAX_WAIT=30
            ELAPSED=0
            until curl -s http://localhost:8000/health > /dev/null 2>&1; do
                if [ $ELAPSED -ge $MAX_WAIT ]; then
                    echo -e "${RED}Failed to start API server (timeout after ${MAX_WAIT}s)${NC}"
                    echo -e "${YELLOW}Check log: test_out/logs/api/server.log${NC}"
                    # Try to stop the potentially hung server
                    ./bioyoda.sh api stop --test 2>/dev/null || true
                    exit 1
                fi
                sleep 1
                ELAPSED=$((ELAPSED + 1))
                echo -n "."
            done
            echo ""
            echo -e "${GREEN}API server started and ready (took ${ELAPSED}s)${NC}"
        fi

        # Run the tests directly
        echo ""
        echo -e "${BLUE}Testing API endpoints at http://localhost:8000...${NC}"
        echo ""

        API_URL="http://localhost:8000"
        test_passed=0
        test_failed=0

        # Helper function to test endpoint
        test_endpoint() {
            local name="$1"
            local url="$2"
            local method="${3:-GET}"
            local data="$4"

            echo -n "Testing $name... "

            if [ "$method" = "POST" ]; then
                response=$(curl -s -w "\n%{http_code}" -X POST "$url" \
                    -H "Content-Type: application/json" \
                    -d "$data" 2>&1)
            else
                response=$(curl -s -w "\n%{http_code}" "$url" 2>&1)
            fi

            http_code=$(echo "$response" | tail -n1)
            body=$(echo "$response" | sed '$d')

            if [ "$http_code" = "200" ]; then
                echo -e "${GREEN}PASS${NC} (HTTP $http_code)"
                test_passed=$((test_passed + 1))
                if command -v jq &> /dev/null; then
                    echo "$body" | jq -C '.' 2>/dev/null || echo "$body"
                else
                    echo "$body" | python -m json.tool 2>/dev/null || echo "$body"
                fi
            else
                echo -e "${RED}FAIL${NC} (HTTP $http_code)"
                test_failed=$((test_failed + 1))
                echo "$body"
            fi
            echo ""
        }

        # Test 1: Root endpoint
        test_endpoint "Root Endpoint" "$API_URL/"

        # Test 2: Health check
        test_endpoint "Health Check" "$API_URL/health"

        # Test 3: List collections
        test_endpoint "List Collections" "$API_URL/collections"

        # Test 4: Search PubMed
        test_endpoint "Search PubMed" "$API_URL/search" "POST" '{
            "query": "CRISPR gene editing",
            "collections": ["pubmed_abstracts"],
            "limit": 3
        }'

        # Test 5: Multi-collection search
        test_endpoint "Multi-Collection Search" "$API_URL/search" "POST" '{
            "query": "cancer treatment",
            "collections": ["pubmed_abstracts", "clinical_trials"],
            "limit": 2
        }'

        # Test 6: Error handling (invalid collection)
        echo -n "Testing Error Handling (invalid collection)... "
        response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/search" \
            -H "Content-Type: application/json" \
            -d '{"query": "test", "collections": ["invalid_collection"], "limit": 5}' 2>&1)
        http_code=$(echo "$response" | tail -n1)

        if [ "$http_code" = "400" ] || [ "$http_code" = "404" ]; then
            echo -e "${GREEN}PASS${NC} (HTTP $http_code - correctly rejected)"
            test_passed=$((test_passed + 1))
        else
            echo -e "${RED}FAIL${NC} (HTTP $http_code - should return 400 or 404)"
            test_failed=$((test_failed + 1))
        fi
        echo ""

        # Summary
        echo "=============================================================================="
        echo "Test Summary"
        echo "=============================================================================="
        echo "Passed: ${test_passed}"
        echo "Failed: ${test_failed}"
        echo "Total: $((test_passed + test_failed))"
        echo ""

        if [ $test_failed -eq 0 ]; then
            echo -e "${GREEN}All tests passed!${NC}"
            TEST_RESULT=0
        else
            echo -e "${RED}Some tests failed${NC}"
            TEST_RESULT=1
        fi

        # Stop API if we started it
        if [ "$API_RUNNING" = false ]; then
            echo ""
            echo -e "${YELLOW}Stopping API server...${NC}"
            ./bioyoda.sh api stop --test
        fi

        exit $TEST_RESULT
        ;;

    "merge")
        echo -e "${BLUE}Running merge tests only...${NC}"
        pytest -v tests/unit/pubmed/test_merge.py
        ;;

    "index")
        echo -e "${BLUE}Running index tests only...${NC}"
        pytest -v tests/unit/pubmed/test_index.py
        ;;

    "config")
        echo -e "${BLUE}Running config tests only...${NC}"
        pytest -v tests/unit/common/test_config.py
        ;;

    "failed")
        echo -e "${BLUE}Re-running failed tests...${NC}"
        pytest --lf -v
        ;;

    "help"|"-h"|"--help")
        echo "Usage: ./run_tests.sh [MODE]"
        echo ""
        echo "Modes:"
        echo "  all                 Run all tests (default)"
        echo "  unit                Run unit tests only (fast)"
        echo "  integration         Run integration tests only (validates existing data)"
        echo "  e2e                 Run end-to-end tests (SLOW - runs full pipeline)"
        echo "  quick               Run fast tests only (skip slow)"
        echo "  coverage            Run tests with coverage report"
        echo ""
        echo "By Module:"
        echo "  pubmed              Run PubMed tests (unit + e2e)"
        echo "  ct|clinical_trials  Run Clinical Trials tests (unit + e2e)"
        echo "  qdrant              Run Qdrant tests (unit + integration)"
        echo "  api                 Run API tests (starts server if needed)"
        echo ""
        echo "Specific Tests:"
        echo "  merge               Run merge tests only"
        echo "  index               Run index tests only"
        echo "  config              Run config tests only"
        echo "  failed              Re-run only failed tests"
        echo ""
        echo "  help                Show this help"
        echo ""
        echo "Examples:"
        echo "  ./run_tests.sh                # Run all tests"
        echo "  ./run_tests.sh unit           # Run unit tests"
        echo "  ./run_tests.sh pubmed         # Run PubMed tests"
        echo "  ./run_tests.sh ct             # Run Clinical Trials tests"
        echo "  ./run_tests.sh api            # Run API tests"
        echo "  ./run_tests.sh coverage       # Generate coverage report"
        exit 0
        ;;

    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        echo "Use './run_tests.sh help' for usage"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Test run complete!${NC}"
