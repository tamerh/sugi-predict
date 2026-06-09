#!/bin/bash
# Patents text pipeline: S-BioBERT embeddings on a real SureChEMBL parquet slice.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/patents_poc
python modules/patents/scripts/process_patents.py \
    --input snapshots/raw_data/patents/surechembl/2025-12-15/patents.parquet \
    --output-index "$OUT/text/patents_text.index" \
    --output-metadata "$OUT/text/patents_text.json" \
    --limit 200 --encode-batch-size 32
echo "text: done" >&2
