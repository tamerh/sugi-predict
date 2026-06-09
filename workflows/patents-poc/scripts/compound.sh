#!/bin/bash
# Patents compound pipeline (fan-out): Morgan fingerprints via RDKit (CPU).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/patents_poc
CHUNK="$ENJU_PARAM_chunk"
python modules/patents/scripts/process_compounds.py \
    --input snapshots/raw_data/patents/chunked_compounds/compounds_chunk_${CHUNK}.parquet \
    --output-index "$OUT/compounds/compounds_${CHUNK}.index" \
    --output-metadata "$OUT/compounds/compounds_${CHUNK}.json" \
    --limit 2000
echo "compound: chunk $CHUNK done" >&2
