#!/bin/bash
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/esm2_poc
python3 - "$OUT/faiss" "$OUT/merge_report.txt" <<'PY'
import sys, glob, faiss
d, report = sys.argv[1], sys.argv[2]
idxs = sorted(glob.glob(f"{d}/*.index"))
total = sum(faiss.read_index(f).ntotal for f in idxs)
lines = [f"esm2 faiss chunks : {len(idxs)}", f"protein vectors   : {total} (1280-dim ESM-2)"]
open(report,"w").write("\n".join(lines)+"\n"); print("\n".join(lines))
PY
echo "merge: done" >&2
