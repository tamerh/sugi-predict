#!/bin/bash
# PoC stage 3 (fan-in via collects): verify all per-chunk FAISS indices and
# report the aggregate vector count + chunk-type breakdown.
set -euo pipefail

source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "$ENJU_PROJECT_DIR"

OUT=test_out/ct_poc
DIR="$OUT/data/processed/clinical_trials/full"

python3 - "$DIR" "$OUT/merge_report.txt" <<'PY'
import sys, glob, json, faiss
from collections import Counter
d, report = sys.argv[1], sys.argv[2]
idxs = sorted(glob.glob(f"{d}/trials_chunk_*.index"))
total = 0
types = Counter()
for ix in idxs:
    total += faiss.read_index(ix).ntotal
    meta = ix.replace(".index", "_meta.json")
    try:
        m = json.load(open(meta))
        recs = m.values() if isinstance(m, dict) else m
        for r in recs:
            if isinstance(r, dict):
                types[r.get("chunk_type")] += 1
    except Exception:
        pass
lines = [
    f"chunks indexed : {len(idxs)}",
    f"total vectors  : {total}",
    f"by chunk_type  : {dict(types)}",
]
open(report, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
PY

echo "merge: report written to $OUT/merge_report.txt" >&2
