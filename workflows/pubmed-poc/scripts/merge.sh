#!/bin/bash
# PoC stage 3 (fan-in): verify all per-file FAISS indices.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/pubmed_poc
python3 - "$OUT/processed" "$OUT/merge_report.txt" <<'PY'
import sys, glob, faiss
d, report = sys.argv[1], sys.argv[2]
idxs = sorted(glob.glob(f"{d}/*.index"))
total = sum(faiss.read_index(f).ntotal for f in idxs)
lines = [f"files indexed : {len(idxs)}", f"total vectors : {total}"]
open(report, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
PY
echo "merge: report at $OUT/merge_report.txt" >&2
