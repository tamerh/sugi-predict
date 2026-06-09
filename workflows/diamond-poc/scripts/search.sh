#!/bin/bash
# Diamond PoC stage 2 (fan-out): all-vs-all BLASTP for one query chunk.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/diamond_poc
CHUNK="$ENJU_PARAM_chunk"
diamond blastp \
    --query "$OUT/chunks/chunk_${CHUNK}.fasta" \
    --db "$OUT/db" \
    --out "$OUT/results/chunk_${CHUNK}.tsv" \
    --threads 4 --max-target-seqs 1000 --evalue 0.001 --sensitive --outfmt 6 \
    >/dev/null 2>&1
echo "search: chunk $CHUNK -> $(wc -l < "$OUT/results/chunk_${CHUNK}.tsv") hits" >&2
