#!/bin/bash
# patents_text update — STAGE 2 (fan-out): embed one batch JSONL shard with MedCPT-Article -> FAISS.
# 1 combined vector per patent (prepare built text = title doubled + abstract + claims + description),
# keyed for upsert by hash(patent_id) at insert time. Uses the SAME embed path as the base build
# (modules/text/embed_text_medcpt_gpu.py, CLS pooling) so vectors share the served patents_text_medcpt
# space. embed_text_medcpt_gpu.py runs on the whole --input-dir, so we point it at a single-shard dir.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"

BATCH="$ENJU_PARAM_batch"               # "01".."32"
IN="work/data/processed/patents/text_gap_batches/batch_${BATCH}.jsonl"
OUT=work/data/processed/patents/text_gap
mkdir -p "$OUT"

# Resumable: skip if already embedded (embed_text_medcpt_gpu.py names output <shard>.index)
if [[ -f "$OUT/batch_${BATCH}.index" ]]; then
    echo "batch $BATCH already embedded, skipping" >&2
    exit 0
fi
[[ -f "$IN" ]] || { echo "batch input missing: $IN" >&2; exit 1; }

# Single-shard input dir for this batch (embed_text_medcpt_gpu.py globs *.jsonl in --input-dir)
SHARD_DIR="work/data/processed/patents/text_gap_shard_${BATCH}"
mkdir -p "$SHARD_DIR"
ln -sf "$(cd "${BIOYODA_ROOT:-/data/bioyoda}" && pwd)/$IN" "$SHARD_DIR/batch_${BATCH}.jsonl"

python modules/text/embed_text_medcpt_gpu.py \
    --input-dir "$SHARD_DIR" --output-dir "$OUT" \
    --model ncbi/MedCPT-Article-Encoder --text-field text \
    --max-length 512 --batch-size 64 --device auto
rm -rf "$SHARD_DIR"
echo "embed batch $BATCH done" >&2
