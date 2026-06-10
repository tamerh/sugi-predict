#!/bin/bash
# Pubmed UPDATE — embed one BATCH of pubmed files (PMID-delta: skip already-embedded).
# Covers BOTH baseline/ and updatefiles/ in one fan-out (mirrors the Snakemake
# pubmed_download checkpoint, which globs both dirs). Throttled: OMP/MKL threads=2
# per task; run with Enju --parallel 8 => ~16 of 32 cores.
set -euo pipefail
source /data/miniconda3/etc/profile.d/conda.sh
conda activate bioyoda
cd "${BIOYODA_ROOT:-/data/bioyoda}"
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2

BATCH="$ENJU_PARAM_batch"                 # e.g. "00".."NN"
BATCH_SIZE="${PUBMED_BATCH_SIZE:-45}"
OUT=out/data/processed/pubmed/embeddings
mkdir -p "$OUT"

# Both baseline + updatefiles, deterministic order (basenames don't collide:
# baseline pubmed26n0001-1334, updatefiles pubmed26n1335+).
mapfile -t files < <(ls out/raw_data/pubmed/baseline/*.xml.gz \
                        out/raw_data/pubmed/updatefiles/*.xml.gz 2>/dev/null | sort)
start=$(( 10#$BATCH * BATCH_SIZE ))
slice=( "${files[@]:start:BATCH_SIZE}" )
echo "batch $BATCH: files ${start}..$((start+${#slice[@]}-1)) (${#slice[@]} files)" >&2

DELETED=out/raw_data/pubmed/deleted.pmids.sorted.gz
[[ -f "$DELETED" ]] || DELETED=out/state/pubmed/none.gz

for f in "${slice[@]}"; do
    python modules/pubmed/scripts/index.py "$f" "$OUT" \
        --deleted-pmids "$DELETED" \
        --existing-pmids out/state/pubmed/existing_pmids.txt.gz \
        --model-name "pritamdeka/S-BioBERT-snli-multinli-stsb" --vector-dim 768
done
echo "batch $BATCH done (${#slice[@]} files)" >&2
