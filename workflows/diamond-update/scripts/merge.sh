#!/usr/bin/env bash
# diamond-update stage 3 (fan-in): concatenate the per-chunk hit TSVs into merged_results.tsv.
# Faithful to the old Snakemake rule: merge_results (plain `cat` of all chunk result files).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-$(git rev-parse --show-toplevel)}"

BASE_DIR="${DIAMOND_BASE_DIR:-work}"
RESULTS_DIR="$BASE_DIR/data/processed/diamond/results"
MERGED_DIR="$BASE_DIR/data/processed/diamond/merged"
LOG_DIR="$BASE_DIR/logs/diamond"
mkdir -p "$MERGED_DIR" "$LOG_DIR"

MERGED="$MERGED_DIR/merged_results.tsv"

{
    echo "Merging chunk results..."
    echo "Number of chunk result files: $(ls "$RESULTS_DIR"/chunk_*.tsv 2>/dev/null | wc -l)"
} > "$LOG_DIR/merge_results.log"

cat "$RESULTS_DIR"/chunk_*.tsv > "$MERGED"

{
    echo "Merge complete. Output: $MERGED"
    wc -l "$MERGED"
} >> "$LOG_DIR/merge_results.log"

echo "merge: $(wc -l < "$MERGED") raw hits -> $MERGED" >&2
