#!/bin/bash
# patents_text update — STAGE 3 (fan-in via collects): aggregate vector count across
# the per-batch FAISS indices and remind of the follow-up Qdrant upsert.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

DIR=work/data/processed/patents/text_gap
python3 - "$DIR" <<'PY'
import sys, glob, faiss
d = sys.argv[1]
idxs = sorted(glob.glob(f"{d}/uspto_gap_*.index"))
total = sum(faiss.read_index(ix).ntotal for ix in idxs)
print(f"batches embedded : {len(idxs)}")
print(f"full-text vectors: {total:,}")
print("NEXT (follow-up, not in DAG): additive UPSERT into patents_text ->")
print(f"  python modules/qdrant/scripts/insert_from_faiss.py \\")
print(f"    --faiss-dir {d} --collection patents_text \\")
print(f"    --qdrant-url http://localhost:6333 --vector-size 768")
PY
echo "report done" >&2
