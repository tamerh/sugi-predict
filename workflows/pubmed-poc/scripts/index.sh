#!/bin/bash
# PoC stage 2 (fan-out): index one PubMed XML file with S-BioBERT -> FAISS.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/pubmed_poc
FILE="$ENJU_PARAM_file"
IN="$OUT/raw/baseline/${FILE}.xml.gz"
[[ -f "$IN" ]] || { echo "ERROR: missing $IN" >&2; exit 1; }

python modules/pubmed/scripts/index.py \
    "$IN" "$OUT/processed" \
    --deleted-pmids "$OUT/none.gz" \
    --model-name "pritamdeka/S-BioBERT-snli-multinli-stsb" \
    --vector-dim 768

echo "index: $FILE done" >&2
