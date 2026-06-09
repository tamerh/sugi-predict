#!/bin/bash
# Diamond PoC stage 3 (fan-in): concatenate + filter top-K.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/diamond_poc
cat "$OUT"/results/chunk_*.tsv > "$OUT/all_hits.tsv"
python modules/diamond/scripts/filter_top_k.py "$OUT/all_hits.tsv" "$OUT/filtered_top100.tsv" --k 100 >&2
echo "merge: $(wc -l < "$OUT/all_hits.tsv") raw hits -> $(wc -l < "$OUT/filtered_top100.tsv") filtered" | tee "$OUT/merge_report.txt" >&2
