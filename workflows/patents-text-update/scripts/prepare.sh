#!/bin/bash
# patents_text update — STAGE 1: build US-ID filter, parse USPTO ZIPs to filtered
# full-text, tag flags, split into 32 fixed batches for the embed fan-out.
# Codifies the proven 2026-06-14 gap-fill (see workflows/patents-text-update/enju.yaml).
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"

SURECHEMBL_PATENTS="${ENJU_PARAM_surechembl_patents:?set surechembl_patents param}"
MANUAL_DIR="${ENJU_PARAM_manual_dir:-raw_data/patents/manual}"
USPTO_RAW=raw_data/patents/uspto/2026-gap
WORK=work/data/processed/patents
STATE=work/state/patents
mkdir -p "$USPTO_RAW" "$WORK" "$STATE"

# 1. US patent-ID filter from SureChEMBL
python modules/patents/scripts/extract_us_patent_ids.py \
    --input "$SURECHEMBL_PATENTS" \
    --output "$STATE/us_patent_ids.txt"

# 2. Organize the manual ZIPs. download_uspto.py writes BROKEN relative symlinks
#    (target relative to the symlink dir) -> rewrite them absolute so parse_uspto can open.
python modules/patents/scripts/download_uspto.py \
    --raw-dir "$USPTO_RAW" --manual-dir "$MANUAL_DIR"
( cd "$USPTO_RAW" && for l in *.zip; do
      [[ -L "$l" ]] || continue
      tgt=$(readlink "$l"); case "$tgt" in /*) : ;; *) rm "$l"; ln -s "$(cd "${BIOYODA_ROOT:-/data/bioyoda}" && pwd)/$tgt" "$l";; esac
  done )

# 3. Parse USPTO XML -> filtered full-text parquet (abstract+claims+description)
python modules/patents/scripts/parse_uspto.py \
    --input-dir "$USPTO_RAW" \
    --filter-ids "$STATE/us_patent_ids.txt" \
    --output "$WORK/uspto_gap_parsed.parquet"

# 4. Tag has_full_text=True / text_source=surechembl+uspto, then split into 32 batches.
#    process_patents.py defaults has_full_text=False (-> title-only) without these flags.
python3 - "$WORK/uspto_gap_parsed.parquet" "$WORK/text_gap_batches" <<'PY'
import sys, pandas as pd, os, math
src, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
df = pd.read_parquet(src)
df['has_full_text'] = True
df['text_source'] = 'surechembl+uspto'
N = 32
size = math.ceil(len(df) / N)
for i in range(N):
    part = df.iloc[i*size:(i+1)*size]
    part.to_parquet(f"{outdir}/batch_{i+1:02d}.parquet")
print(f"prepared {len(df):,} full-text patents -> {N} batches in {outdir}")
PY
echo "prepare done" >&2
