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
