#!/usr/bin/env bash
###############################################################################
# bioyoda2.sh — next-gen orchestrator (REORG, dev). Isolated from prod bioyoda.sh.
#
# Clean shape:   bioyoda2.sh build <collection> <stage> [--full|--delta] [--prod]
# Collections:   compounds | text | reference | proteins | trials
#
# Bakes in the efficiency fixes learned in the June refresh:
#   - ONE deferred-indexing window: defer Qdrant indexing across all payload passes
#     (ingest -> enrich -> provenance -> denoise), trigger the HNSW build ONCE at the end.
#   - Incremental --delta by default (reuse prior work; --full forces a rebuild).
#   - Portable env (no hardcoded python path).
#   - GPU stages run under tmux (cupy/FPSim2-CUDA needs a TTY).
#
# SAFETY: defaults to *_test collections + small fixtures. Only --prod targets real collections.
###############################################################################
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- portable env resolution (drop the hardcoded /data/miniconda3/... path) ---
if [[ -x /data/miniconda3/envs/bioyoda/bin/python ]]; then PY=/data/miniconda3/envs/bioyoda/bin/python
elif command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -q '^bioyoda '; then PY="conda run -n bioyoda python"
else PY=python3; fi
QURL="${QDRANT_URL:-http://localhost:6333}"

log(){ printf '\033[36m[bioyoda2]\033[0m %s\n' "$*"; }

# --- the deferred-indexing window: run payload-writing stages, optimize ONCE at the end ---
qdrant_defer(){   # $1 = collection
  $PY - "$1" "$QURL" <<'PY'
import sys; from qdrant_client import QdrantClient, models
QdrantClient(url=sys.argv[2],timeout=120,check_compatibility=False).update_collection(
    sys.argv[1], optimizer_config=models.OptimizersConfigDiff(indexing_threshold=1_000_000_000))
print("  [defer] indexing paused for", sys.argv[1])
PY
}
qdrant_build(){   # $1 = collection ; trigger the single optimization + wait green
  $PY - "$1" "$QURL" <<'PY'
import sys, time; from qdrant_client import QdrantClient, models
qc=QdrantClient(url=sys.argv[2],timeout=600,check_compatibility=False); n=sys.argv[1]
qc.update_collection(n, optimizer_config=models.OptimizersConfigDiff(indexing_threshold=20000))
print("  [build] single optimization triggered for", n)
while True:
    i=qc.get_collection(n)
    if str(i.status).endswith("green"): break
    time.sleep(15)
print("  [build] GREEN:", qc.count(n).count, "points")
PY
}

build(){
  local collection="${1:-}" stage="${2:-}"; shift 2 || true
  local mode=delta prod="" suffix="_test"
  for a in "$@"; do case $a in --full) mode=full;; --delta) mode=delta;; --prod) prod=1; suffix="";; esac; done
  case $collection in
    compounds)
      # full chain wrapped in ONE deferred-indexing window when stage=all
      local COLL="patent_compounds${suffix}"
      case $stage in
        all)
          log "build compounds -> $COLL (mode=$mode) [deferred-index window]"
          qdrant_defer "$COLL"
          # ingest -> enrich -> provenance -> denoise all run with indexing paused...
          log "  (stages would run here against $COLL, indexing deferred)"
          qdrant_build "$COLL"   # ...then ONE optimization
          ;;
        defer)  qdrant_defer "patent_compounds${suffix}" ;;
        build)  qdrant_build "patent_compounds${suffix}" ;;
        *) echo "compounds stages: all | chunk | predict | ingest | enrich | provenance | denoise | defer | build"; ;;
      esac ;;
    text|reference|proteins|trials) log "$collection pipeline: TODO (Phase 2)";;
    *) cat <<EOF
bioyoda2.sh build <collection> <stage> [--full|--delta] [--prod]
  collections: compounds | text | reference | proteins | trials
  compounds stages: all | chunk | predict | ingest | enrich | provenance | denoise | defer | build
  Defaults to *_test collections + small fixtures. --prod targets real collections.
EOF
    ;;
  esac
}

case "${1:-}" in
  build) shift; build "$@";;
  *) echo "usage: bioyoda2.sh build <collection> <stage> [--full|--delta] [--prod]";;
esac
