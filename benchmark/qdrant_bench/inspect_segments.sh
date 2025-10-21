#!/bin/bash
#
# Inspect Qdrant segment data from preserved benchmarks
#
# Usage: ./inspect_segments.sh [config_name]
#   Example: ./inspect_segments.sh m32_efc256_ef128
#   Or just: ./inspect_segments.sh  (shows all)
#

QDRANT_BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
QDRANT_DATA_DIR="$QDRANT_BENCH_DIR/qdrant_data_subset"
COLLECTION_NAME="pubmed_bench"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -d "$QDRANT_DATA_DIR" ]; then
    echo "ERROR: No preserved data found at $QDRANT_DATA_DIR"
    echo "Run ./run_subset_benchmark.sh first"
    exit 1
fi

if [ -n "$1" ]; then
    # Inspect specific config
    CONFIG_DIR="$QDRANT_DATA_DIR/$1"
    if [ ! -d "$CONFIG_DIR" ]; then
        echo "ERROR: Config not found: $1"
        echo "Available configs:"
        ls -1 "$QDRANT_DATA_DIR"
        exit 1
    fi

    echo "========================================="
    echo -e "${GREEN}Inspecting: $1${NC}"
    echo "========================================="
    echo ""

    COLL_DIR="$CONFIG_DIR/storage/collections/$COLLECTION_NAME"

    if [ -d "$COLL_DIR" ]; then
        echo -e "${BLUE}Collection directory:${NC}"
        echo "  $COLL_DIR"
        echo ""

        echo -e "${BLUE}Segments:${NC}"
        SEGMENT_COUNT=$(ls -1d "$COLL_DIR"/*/ 2>/dev/null | wc -l)
        echo "  Total segments: $SEGMENT_COUNT"
        echo ""

        for segment_dir in "$COLL_DIR"/*/; do
            if [ -d "$segment_dir" ]; then
                segment_name=$(basename "$segment_dir")
                segment_size=$(du -sh "$segment_dir" 2>/dev/null | cut -f1)
                echo "  • $segment_name ($segment_size)"

                # Check for segment.json
                if [ -f "$segment_dir/segment.json" ]; then
                    echo "    Files:"
                    ls -lh "$segment_dir" | grep -v "^d" | awk '{print "      " $9 " (" $5 ")"}'
                fi
            fi
        done
        echo ""

        # Show config if exists
        if [ -f "$CONFIG_DIR/qdrant_config.yaml" ]; then
            echo -e "${BLUE}Server config:${NC}"
            echo "  $CONFIG_DIR/qdrant_config.yaml"
            echo ""
        fi

        # Show logs if exist
        if ls "$CONFIG_DIR"/*.log >/dev/null 2>&1; then
            echo -e "${BLUE}Logs available:${NC}"
            ls -lh "$CONFIG_DIR"/*.log | awk '{print "  " $9 " (" $5 ")"}'
            echo ""
            echo -e "${YELLOW}View logs:${NC}"
            echo "  tail -100 $CONFIG_DIR/*.log"
        fi
    else
        echo "No collection data found in $COLL_DIR"
    fi

else
    # Show all configs
    echo "========================================="
    echo -e "${GREEN}Preserved Qdrant Data${NC}"
    echo "========================================="
    echo ""
    echo "Location: $QDRANT_DATA_DIR"
    echo "Total size: $(du -sh "$QDRANT_DATA_DIR" 2>/dev/null | cut -f1)"
    echo ""

    echo -e "${BLUE}Configurations:${NC}"
    for config_dir in "$QDRANT_DATA_DIR"/*/; do
        if [ -d "$config_dir" ]; then
            config_name=$(basename "$config_dir")
            config_size=$(du -sh "$config_dir" 2>/dev/null | cut -f1)

            COLL_DIR="$config_dir/storage/collections/$COLLECTION_NAME"
            if [ -d "$COLL_DIR" ]; then
                SEGMENT_COUNT=$(ls -1d "$COLL_DIR"/*/ 2>/dev/null | wc -l)
                echo "  • $config_name ($config_size, $SEGMENT_COUNT segments)"
            else
                echo "  • $config_name ($config_size)"
            fi
        fi
    done
    echo ""

    echo -e "${YELLOW}Inspect specific config:${NC}"
    echo "  ./inspect_segments.sh <config_name>"
    echo ""
    echo "Examples:"
    for config_dir in "$QDRANT_DATA_DIR"/*/; do
        if [ -d "$config_dir" ]; then
            config_name=$(basename "$config_dir")
            echo "  ./inspect_segments.sh $config_name"
            break
        fi
    done
fi
