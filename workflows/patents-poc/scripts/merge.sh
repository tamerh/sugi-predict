#!/bin/bash
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/patents_poc
python3 - "$OUT" <<'PY'
import sys, glob, faiss
o=sys.argv[1]
tx=glob.glob(f"{o}/text/*.index"); cp=glob.glob(f"{o}/compounds/*.index")
tv=sum(faiss.read_index(f).ntotal for f in tx)
cv=sum(faiss.read_index(f).ntotal for f in cp)
lines=[f"text indices : {len(tx)} ({tv} vectors, 768-dim S-BioBERT)",
       f"compound idx : {len(cp)} ({cv} vectors, 2048-bit Morgan)"]
open(f"{o}/merge_report.txt","w").write("\n".join(lines)+"\n"); print("\n".join(lines))
PY
echo "merge: done" >&2
