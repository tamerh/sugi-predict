#!/bin/bash
# qdrant-insert PoC (fan-out per collection): insert a module's FAISS dir into Qdrant.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
COLL="$ENJU_PARAM_collection"
case "$COLL" in
  pubmed) DIR=test_out/pubmed_poc/processed; DIM=768 ;;
  esm2)   DIR=test_out/esm2_poc/faiss;       DIM=1280 ;;
  *) echo "unknown collection $COLL" >&2; exit 1 ;;
esac
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir "$DIR" --collection "poc_${COLL}" \
    --qdrant-url http://localhost:6333 --vector-size "$DIM" --batch-size 200
echo "insert: $COLL done" >&2
