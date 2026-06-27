#!/usr/bin/env bash
# diamond-update stage 1: download UniProt FASTA, makedb, split query fasta into chunks.
# Reuses modules/diamond/scripts/{download_uniprot,split_fasta}.py + the diamond binary (compute, not a collection).
# Faithful to the old Snakemake rules: download_uniprot, create_diamond_db, split_fasta_checkpoint.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-$(git rev-parse --show-toplevel)}"

# --- params (prod defaults match the old Snakefile) ---
DATASET="${ENJU_PARAM_dataset:-swissprot}"
NUM_CHUNKS="${ENJU_PARAM_num_chunks:-20}"

# --- directory layout (faithful to the Snakefile: BASE_DIR=work for prod) ---
BASE_DIR="${DIAMOND_BASE_DIR:-work}"
RAW_DIR="$BASE_DIR/raw_data/diamond"
CHUNKS_DIR="$RAW_DIR/chunks"
DB_DIR="$RAW_DIR/diamond_db"
STATE_DIR="$BASE_DIR/state/diamond"
LOG_DIR="$BASE_DIR/logs/diamond"
mkdir -p "$RAW_DIR" "$CHUNKS_DIR" "$DB_DIR" "$STATE_DIR" "$LOG_DIR"

if [[ "$DATASET" == "test" ]]; then
    RAW_FASTA="$RAW_DIR/test_proteins.fasta"
    DIAMOND_DB="$DB_DIR/test_proteins"
else
    RAW_FASTA="$RAW_DIR/uniprot_${DATASET}.fasta"
    DIAMOND_DB="$DB_DIR/uniprot_${DATASET}"
fi

# --- 1. download UniProt FASTA (download_uniprot rule) ---
if [[ ! -s "$RAW_FASTA" ]]; then
    python modules/diamond/scripts/download_uniprot.py \
        --dataset "$DATASET" \
        --output-dir "$RAW_DIR" \
        2>&1 | tee "$LOG_DIR/download_uniprot.log" >&2
else
    echo "prepare: reusing existing FASTA $RAW_FASTA" >&2
fi

# --- 2. makedb (create_diamond_db rule) ---
diamond makedb \
    --in "$RAW_FASTA" \
    --db "$DIAMOND_DB" \
    --threads "${ENJU_PARAM_threads:-4}" \
    2>&1 | tee "$LOG_DIR/create_diamond_db.log" >&2

# --- 3. split into chunks + state file (split_fasta_checkpoint rule) ---
python modules/diamond/scripts/split_fasta.py \
    "$RAW_FASTA" \
    "$NUM_CHUNKS" \
    "$CHUNKS_DIR" \
    --state-file "$STATE_DIR/processed_chunks.json" \
    2>&1 | tee "$LOG_DIR/split_fasta.log" >&2
touch "$CHUNKS_DIR/.split_complete"

# --- emit the chunk-id list for the fan-out (driver-resolved into the `chunks` param) ---
echo "prepare: chunks:" >&2
ls "$CHUNKS_DIR"/chunk_*.fasta | xargs -n1 basename | sed 's/^chunk_//; s/\.fasta$//' >&2
