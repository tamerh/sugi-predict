#!/bin/bash
# Delta-refresh patents_compounds from a SureChEMBL compounds.parquet.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh && conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
INPUT="${1:?usage: refresh.sh <compounds.parquet>}"
CHUNKDIR=out/raw_data/patents/compounds_chunks_new
OUT=out/data/processed/patents/compounds_new
mkdir -p "$CHUNKDIR" "$OUT"

echo "=== split $INPUT into 1M-row chunks ===" >&2
python3 - "$INPUT" "$CHUNKDIR" <<'PY'
import sys, os, pyarrow.parquet as pq, pyarrow as pa
inp, outd = sys.argv[1], sys.argv[2]
if any(f.endswith('.parquet') for f in os.listdir(outd)):
    print("chunks already exist, skipping split"); sys.exit(0)
pf = pq.ParquetFile(inp)
for i, b in enumerate(pf.iter_batches(batch_size=1_000_000)):
    pq.write_table(pa.Table.from_batches([b]), f"{outd}/chunk_{i:04d}.parquet")
print(f"split into {len(os.listdir(outd))} chunks")
PY

echo "=== delta-process chunks (4-way, --existing-ids) ===" >&2
ls "$CHUNKDIR"/chunk_*.parquet | xargs -P 4 -I{} workflows/patents-compound-update/scripts/one_chunk.sh {}

python3 -c "import faiss,glob; fs=glob.glob('$OUT/*.index'); print(f'NEW compounds fingerprinted: {sum(faiss.read_index(f).ntotal for f in fs):,} across {len(fs)} chunks')"
