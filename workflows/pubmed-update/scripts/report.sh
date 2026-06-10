#!/bin/bash
# Fan-in: count NEW vectors produced across all batches (not yet inserted to Qdrant).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=out/data/processed/pubmed/embeddings
python3 - "$OUT" <<'PY'
import sys, glob, faiss
d=sys.argv[1]
idxs=glob.glob(f"{d}/*.index")
tot=sum(faiss.read_index(f).ntotal for f in idxs)
print(f"new-abstract indices: {len(idxs)} files, {tot:,} new vectors (PMID-delta)")
open(f"{d}/../update_report.txt","w").write(f"{len(idxs)} files, {tot} new vectors\n")
PY
echo "report done; Qdrant insert is a SEPARATE deliberate step (additive: new PMIDs only)." >&2
