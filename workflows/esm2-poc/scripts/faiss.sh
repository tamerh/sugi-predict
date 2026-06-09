#!/bin/bash
# esm2 PoC stage 3 (fan-out per h5 chunk): h5 embeddings -> FAISS (CPU, no GPU).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/esm2_poc
CHUNK="$ENJU_PARAM_h5chunk"
python modules/esm2/scripts/h5_to_faiss.py \
    "$OUT/embeddings/reference_embeddings_chunk_${CHUNK}.h5" \
    "$OUT/faiss/chunk_${CHUNK}.index" \
    "$OUT/faiss/chunk_${CHUNK}.json" \
    --vector-dim 1280
echo "faiss: chunk $CHUNK done" >&2
