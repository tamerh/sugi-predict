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

# 4. Build the combined searchable text (title doubled + abstract + claims + description),
#    tag has_full_text=True / text_source=surechembl+uspto, and write 32 JSONL shards in the
#    EXACT record shape modules/patents/scripts/prepare_medcpt_shards.py emits, so the embed
#    step can use the shared MedCPT-Article path (embed_text_medcpt_gpu.py) and the vectors
#    land in the same CLS-pooled MedCPT space as the served patents_text_medcpt base build.
python3 - "$WORK/uspto_gap_parsed.parquet" "$WORK/text_gap_batches" <<'PY'
import sys, os, re, json, math, pandas as pd

src, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)

_URL = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
def clean_text(t):                                    # same normalization as prepare_medcpt_shards.py
    if t is None or (isinstance(t, float) and pd.isna(t)):
        return ""
    t = str(t)
    t = re.sub(r"\s+", " ", t.strip())
    t = re.sub(r"\r\n|\r|\n", " ", t)
    t = re.sub(r"\t+", " ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _URL.sub("", t)
    return t.strip()

df = pd.read_parquet(src)
recs = []
for _, r in df.iterrows():
    pid = r.get("patent_number")
    if not pid:
        continue
    title = clean_text(r.get("title"))
    parts = [title, title] if title else []           # title doubled (weighting), as in the base build
    for x in (r.get("abstract"), r.get("claims"), r.get("description")):
        x = clean_text(x)
        if x:
            parts.append(x)
    text = " ".join(parts)
    if not text or len(text) < 50:                    # min_text_length=50, matching the base build
        continue
    recs.append({
        "patent_id": pid,
        "text": text,
        "title": title,
        "has_full_text": True,
        "text_source": "surechembl+uspto",
    })

N = 32
size = math.ceil(len(recs) / N) if recs else 0
for i in range(N):
    part = recs[i*size:(i+1)*size] if size else []
    with open(f"{outdir}/batch_{i+1:02d}.jsonl", "w") as fh:
        for rec in part:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"prepared {len(recs):,} full-text patents -> {N} JSONL shards in {outdir}")
PY
echo "prepare done" >&2
