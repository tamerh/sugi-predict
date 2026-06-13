#!/bin/bash
set -euo pipefail
c="$1"; base=$(basename "$c" .parquet)
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
cd /data/bioyoda
source /data/miniconda3/etc/profile.d/conda.sh && conda activate bioyoda 2>/dev/null
OUT=work/data/processed/patents/compounds_new
[[ -f "$OUT/${base}.index" ]] && exit 0   # resumable: skip done chunks
python modules/patents/scripts/process_compounds.py \
    --input "$c" \
    --output-index "$OUT/${base}.index" --output-metadata "$OUT/${base}.json" \
    --existing-ids work/state/patents/existing_compound_ids.txt.gz >/dev/null 2>&1 || { echo "FAIL $c" >&2; exit 1; }
