#!/bin/bash
# qdrant-insert PoC (fan-in): report point counts per inserted collection.
set -euo pipefail
cd "${BIOYODA_ROOT:-/data/bioyoda}"
REPORT=test_out/qdrant_poc/insert_report.txt
: > "$REPORT"
for c in poc_pubmed poc_esm2; do
  n=$(curl -s "http://localhost:6333/collections/$c" | python3 -c "import sys,json;print(json.load(sys.stdin)['result'].get('points_count'))" 2>/dev/null || echo "?")
  echo "$c : $n points" | tee -a "$REPORT"
done
echo "verify: report at $REPORT" >&2
