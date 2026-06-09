#!/bin/bash
# esm2 PoC stage 1: stage the precomputed ESM-2 embedding fixture (h5).
# In production this is the OUTPUT of the GPU `generate` task.
set -euo pipefail
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/esm2_poc
rm -rf "$OUT"; mkdir -p "$OUT/embeddings" "$OUT/faiss"
cp tests/fixtures/esm2/reference_embeddings_chunk_001.h5 "$OUT/embeddings/"
echo "prepare: h5 chunk ids:" >&2
ls "$OUT"/embeddings/*.h5 | xargs -n1 basename | sed 's/^reference_embeddings_chunk_//; s/\.h5$//' >&2
