#!/bin/bash
# PoC stage 2 (fan-out): embed one clinical-trials chunk with S-BioBERT -> FAISS.
# The chunk id comes from the Enju for_each iteration variable.
set -euo pipefail

source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/ct_poc
CHUNK="$ENJU_PARAM_chunk"
IN="$OUT/raw_data/clinical_trials/chunked/trials_chunk_${CHUNK}.json"

if [[ ! -f "$IN" ]]; then
    echo "ERROR: chunk input not found: $IN" >&2
    exit 1
fi

python modules/clinical_trials/scripts/process_trials_chunk.py \
    --input-json "$IN" \
    --output-index "$OUT/data/processed/clinical_trials/full/trials_chunk_${CHUNK}.index" \
    --output-metadata "$OUT/data/processed/clinical_trials/full/trials_chunk_${CHUNK}_meta.json" \
    --encode-batch-size 32

echo "embed: chunk $CHUNK done" >&2
