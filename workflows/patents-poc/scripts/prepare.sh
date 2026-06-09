#!/bin/bash
set -euo pipefail
cd "${BIOYODA_ROOT:-/data/bioyoda}"
OUT=test_out/patents_poc
rm -rf "$OUT"; mkdir -p "$OUT/text" "$OUT/compounds"
echo "prepare: dirs ready" >&2
