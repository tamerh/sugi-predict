#!/bin/bash
# PoC stage 1: consume biobtree's trials.json fixture and chunk it.
# Reuses BioYoda's existing clinical_trials consumer (--source-json mode).
set -euo pipefail

source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "$ENJU_PROJECT_DIR"

OUT=test_out/ct_poc
rm -rf "$OUT"
mkdir -p "$OUT/data/processed/clinical_trials/full" "$OUT/state"

python modules/clinical_trials/scripts/download_and_extract.py \
    --download-dir "$OUT/dl" \
    --extract-dir "$OUT/ex" \
    --output-json "$OUT/data/processed/clinical_trials/full/trials_data.json" \
    --processed-chunks-output "$OUT/state/processed_chunks.json" \
    --tracking-db "$OUT/state/trials_tracking.db" \
    --min-summary-length 100 \
    --chunk-size 50 \
    --source-json tests/fixtures/clinical_trials/trials.json

N=$(ls "$OUT"/raw_data/clinical_trials/chunked/trials_chunk_*.json 2>/dev/null | wc -l)
echo "prepare: produced $N chunk files in $OUT/raw_data/clinical_trials/chunked/" >&2
