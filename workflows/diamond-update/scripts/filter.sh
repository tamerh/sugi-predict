#!/usr/bin/env bash
# diamond-update stage 4: filter merged_results.tsv to top-K per query protein (BioBTree-ready TSV).
# Faithful to the old Snakemake rule: filter_top_k (reuses modules/diamond/scripts/filter_top_k.py).
# Output filtered_top{K}.tsv is the file biobtree's `diamond_similarity` source consumes
# (promoted into snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-$(git rev-parse --show-toplevel)}"

TOP_K="${ENJU_PARAM_top_k:-100}"
MIN_IDENTITY="${ENJU_PARAM_min_identity:-0}"

BASE_DIR="${DIAMOND_BASE_DIR:-work}"
MERGED_DIR="$BASE_DIR/data/processed/diamond/merged"
LOG_DIR="$BASE_DIR/logs/diamond"
mkdir -p "$MERGED_DIR" "$LOG_DIR"

MERGED="$MERGED_DIR/merged_results.tsv"
FILTERED="$MERGED_DIR/filtered_top${TOP_K}.tsv"

python modules/diamond/scripts/filter_top_k.py \
    "$MERGED" \
    "$FILTERED" \
    --k "$TOP_K" \
    --min-identity "$MIN_IDENTITY" \
    2>&1 | tee "$LOG_DIR/filter_top_k.log" >&2

echo "filter: top-${TOP_K} per protein -> $FILTERED ($(wc -l < "$FILTERED") lines)" >&2
echo "filter: promote to snapshots/diamond_latest/data/processed/diamond/merged/ for biobtree to consume" >&2
