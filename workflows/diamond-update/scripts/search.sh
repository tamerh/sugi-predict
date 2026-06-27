#!/usr/bin/env bash
# diamond-update stage 2 (fan-out): all-vs-all BLASTP for one query chunk against the db.
# Faithful to the old Snakemake rule: diamond_search (same flags). CPU multi-core, one invocation per chunk.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-$(git rev-parse --show-toplevel)}"

DATASET="${ENJU_PARAM_dataset:-swissprot}"

BASE_DIR="${DIAMOND_BASE_DIR:-work}"
RAW_DIR="$BASE_DIR/raw_data/diamond"
CHUNKS_DIR="$RAW_DIR/chunks"
DB_DIR="$RAW_DIR/diamond_db"
RESULTS_DIR="$BASE_DIR/data/processed/diamond/results"
LOG_DIR="$BASE_DIR/logs/diamond"
mkdir -p "$RESULTS_DIR" "$LOG_DIR"

if [[ "$DATASET" == "test" ]]; then
    DIAMOND_DB="$DB_DIR/test_proteins"
else
    DIAMOND_DB="$DB_DIR/uniprot_${DATASET}"
fi

CHUNK="$ENJU_PARAM_chunk"

# diamond blastp flags faithful to the Snakefile diamond_search rule
diamond blastp \
    --query "$CHUNKS_DIR/chunk_${CHUNK}.fasta" \
    --db "$DIAMOND_DB" \
    --out "$RESULTS_DIR/chunk_${CHUNK}.tsv" \
    --threads "${ENJU_PARAM_threads:-4}" \
    --max-target-seqs "${ENJU_PARAM_max_target_seqs:-1000}" \
    --evalue "${ENJU_PARAM_evalue:-0.001}" \
    "--${ENJU_PARAM_sensitivity:-sensitive}" \
    --outfmt 6 \
    --compress 0 \
    2>&1 | tee "$LOG_DIR/diamond_search_chunk_${CHUNK}.log" >&2

echo "search: chunk $CHUNK -> $(wc -l < "$RESULTS_DIR/chunk_${CHUNK}.tsv") hits" >&2
