#!/bin/bash
# Diamond PoC stage 1: build DB + split query fasta into chunks (fixture all-vs-all).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/diamond_poc
rm -rf "$OUT"; mkdir -p "$OUT/chunks" "$OUT/results"
FASTA=tests/fixtures/diamond/test_proteins.fasta

diamond makedb --in "$FASTA" --db "$OUT/db" >/dev/null 2>&1
python modules/diamond/scripts/split_fasta.py "$FASTA" 2 "$OUT/chunks" \
    --state-file "$OUT/processed_chunks.json" >&2

echo "prepare: chunks:" >&2
ls "$OUT"/chunks/chunk_*.fasta | xargs -n1 basename | sed 's/^chunk_//; s/\.fasta$//' >&2
