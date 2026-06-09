#!/bin/bash
# PoC stage 1: stage PubMed XML fixture (in prod this is the download checkpoint).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

OUT=test_out/pubmed_poc
rm -rf "$OUT"
mkdir -p "$OUT/raw/baseline" "$OUT/processed"
cp tests/fixtures/pubmed/test_abstracts.xml.gz "$OUT/raw/baseline/"
: > "$OUT/none.gz"   # empty deleted-PMIDs placeholder (load tolerates missing/empty)

N=$(ls "$OUT"/raw/baseline/*.xml.gz 2>/dev/null | wc -l)
echo "prepare: staged $N XML file(s); basenames:" >&2
ls "$OUT"/raw/baseline/*.xml.gz | xargs -n1 basename | sed 's/\.xml\.gz$//' >&2
