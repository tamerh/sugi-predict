#!/bin/bash
# patents_text update — STAGE 2 (fan-out): embed one batch parquet with S-BioBERT -> FAISS.
# 1 combined vector per patent (process_patents.py combines title+abstract+claims+description
# when has_full_text=True), keyed for upsert by hash(patent_id) at insert time.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"

BATCH="$ENJU_PARAM_batch"               # "01".."32"
IN="work/data/processed/patents/text_gap_batches/batch_${BATCH}.parquet"
OUT=work/data/processed/patents/text_gap
mkdir -p "$OUT"

# Resumable: skip if already embedded
if [[ -f "$OUT/uspto_gap_${BATCH}.index" ]]; then
    echo "batch $BATCH already embedded, skipping" >&2
    exit 0
fi
[[ -f "$IN" ]] || { echo "batch input missing: $IN" >&2; exit 1; }

python modules/patents/scripts/process_patents.py \
    --input "$IN" \
    --output-index "$OUT/uspto_gap_${BATCH}.index" \
    --output-metadata "$OUT/uspto_gap_${BATCH}.json" \
    --model-name "pritamdeka/S-BioBERT-snli-multinli-stsb" --vector-dimension 768 \
    --encode-batch-size 64
echo "embed batch $BATCH done" >&2
