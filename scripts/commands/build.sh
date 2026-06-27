#!/usr/bin/env bash
###############################################################################
# commands/build.sh — the bioyoda.sh `build` command (reorg). Unified collection build/refresh.
#
# Clean shape:   bioyoda.sh build <collection> <stage> [--full|--delta] [--prod]
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
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${COMMANDS_DIR}/../.." && pwd)"

# --- portable env resolution (drop the hardcoded /data/miniconda3/... path) ---
if [[ -x /data/miniconda3/envs/bioyoda/bin/python ]]; then PY=/data/miniconda3/envs/bioyoda/bin/python
elif command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -q '^bioyoda '; then PY="conda run -n bioyoda python"
else PY=python3; fi
QURL="${QDRANT_URL:-http://localhost:6333}"

log(){ printf '\033[36m[build]\033[0m %s\n' "$*"; }

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

# --- pod-sync: automate the GPU hop (push -> tmux run -> monitor -> pull). Blueprint: work/medcpt_orchestrator.sh ---
# Config from env: POD_HOST (root@ip), POD_PORT, POD_KEY. Without them, GPU stages run locally if a GPU is present.
_pssh(){ ssh -i "${POD_KEY}" -p "${POD_PORT}" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=25 "${POD_HOST}" "$@"; }
_pup(){  rsync -a -e "ssh -i ${POD_KEY} -p ${POD_PORT} -o StrictHostKeyChecking=accept-new" "$@"; }
pod_configured(){ [[ -n "${POD_HOST:-}" && -n "${POD_PORT:-}" && -n "${POD_KEY:-}" ]]; }
pod_predict(){   # $1=chunks dir  $2=ref dir  $3=local nbrs out  — run fused k-NN on the pod
  local chunks="$1" ref="$2" out="$3" n; n=$(ls "$chunks"/compounds_chunk_*.parquet 2>/dev/null | wc -l)
  log "[pod] push reference + $n chunks + fused kernel -> ${POD_HOST}"
  _pssh "mkdir -p /atlas/knn/ref /atlas/knn/patents /atlas/knn/nbrs"
  _pup "$ref/reference.tsv" "${POD_HOST}:/atlas/knn/ref/"
  _pup "$chunks/" "${POD_HOST}:/atlas/knn/patents/"
  _pup "${ROOT}/modules/compounds/gpu/gpu_atlas_fused.py" "${POD_HOST}:/atlas/"
  log "[pod] launch fused k-NN under tmux (cupy needs a TTY)"
  _pssh "cd /atlas && tmux kill-session -t knn 2>/dev/null; tmux new-session -d -s knn 'PYTHONUNBUFFERED=1 python -u gpu_atlas_fused.py --refsmi knn/ref/reference.tsv --patents knn/patents --outdir knn/nbrs --knn 100 --procs 24 > fused.log 2>&1; echo EXIT=\$? >> fused.log'"
  log "[pod] monitoring ($n chunks expected)..."
  until [ "$(_pssh 'ls /atlas/knn/nbrs/*.parquet 2>/dev/null | wc -l')" -ge "$n" ] || _pssh 'grep -q EXIT= /atlas/fused.log 2>/dev/null'; do sleep 60; done
  log "[pod] pull nbrs -> ${out#${ROOT}/}"; mkdir -p "$out"; _pup "${POD_HOST}:/atlas/knn/nbrs/" "$out/"
  log "[pod] predict complete"
}
pod_embed_text(){   # $1=input dir (jsonl shards)  $2=local output dir  — MedCPT text embed on the pod
  local in="$1" out="$2" n; n=$(ls "$in"/shard_*.jsonl 2>/dev/null | wc -l)
  log "[pod] push $n input shards + MedCPT embed script -> ${POD_HOST}"
  _pssh "mkdir -p /workspace/input/ct /workspace/output/ct"
  _pup "$in/" "${POD_HOST}:/workspace/input/ct/"
  _pup "${ROOT}/scripts/gpu/embed_text_medcpt_gpu.py" "${POD_HOST}:/workspace/"
  log "[pod] launch MedCPT-Article embed under tmux"
  _pssh "cd /workspace && tmux kill-session -t embed 2>/dev/null; tmux new-session -d -s embed 'PYTHONUNBUFFERED=1 python -u embed_text_medcpt_gpu.py --input-dir input/ct --output-dir output/ct --model ncbi/MedCPT-Article-Encoder --text-field text --batch-size 512 --max-length 512 --device auto > embed.log 2>&1; echo EXIT=\$? >> embed.log'"
  log "[pod] monitoring ($n shards expected)..."
  until [ "$(_pssh 'ls /workspace/output/ct/*.index 2>/dev/null | wc -l')" -ge "$n" ] || _pssh 'grep -q EXIT= /workspace/embed.log 2>/dev/null'; do sleep 60; done
  log "[pod] pull embeddings -> ${out#${ROOT}/}"; mkdir -p "$out"; _pup "${POD_HOST}:/workspace/output/ct/" "$out/"
  log "[pod] embed complete"
}

build(){   # logging wrapper — every stage tees to logs/build/<collection>/<stage>-<ts>.log (organized, not /tmp)
  local _c="${1:-misc}" _s="${2:-_}"; local _d="${ROOT}/logs/build/${_c}"; mkdir -p "$_d"
  local _lf="${_d}/${_s}-$(date +%Y%m%d-%H%M%S).log"
  [[ "$_s" != _ && "$_s" != help ]] && log "log -> ${_lf#${ROOT}/}"
  _dispatch "$@" 2>&1 | tee "$_lf"; return "${PIPESTATUS[0]}"
}
_dispatch(){
  local collection="${1:-}" stage="${2:-}"; shift 2 || true
  local mode=delta prod="" suffix="_test"
  for a in "$@"; do case $a in --full) mode=full;; --delta) mode=delta;; --prod) prod=1; suffix="";; esac; done
  case $collection in
    compounds)
      local COLL="patent_compounds${suffix}" M="${ROOT}/modules/compounds" REF="${ROOT}/work/chembl_reference"
      local SNAP CHUNKS NBRS PREDDIR WORKERS
      # --delta workspace (incremental): kept separate so it NEVER clobbers the full atlas_nbrs; new neighbours merge in
      local DCHUNKS="${ROOT}/work/atlas_delta/chunks" DNBRS="${ROOT}/work/atlas_delta/nbrs"
      if [[ -n "$prod" ]]; then   # --prod: real snapshot + full data
        SNAP="${ROOT}/raw_data/patents/surechembl/2026-06-01"; CHUNKS="${ROOT}/raw_data/patents/chunked_compounds"
        NBRS="${ROOT}/work/atlas_nbrs"; PREDDIR="${ROOT}/work/atlas_preds_aligned"; WORKERS=16
      else                        # default: TEST fixtures (work/test/*) -> *_test collection, no GPU/prod
        SNAP="${ROOT}/work/test"; CHUNKS="${ROOT}/work/test/chunks"
        NBRS="${ROOT}/work/test/atlas_nbrs"; PREDDIR="${ROOT}/work/test/preds"; WORKERS=2
      fi
      case $stage in
        # INCREMENTAL (--delta, default): chunk + predict ONLY the compounds not already in atlas_nbrs, then
        #   merge the new neighbours into atlas_nbrs additively — the reused ~30M neighbours are NEVER recomputed.
        #   Proven in the June run: an 897K delta took 97s vs ~10h for a full re-run. --full forces the whole snapshot.
        chunk)
          if [[ $mode == delta ]]; then
            $PY "${ROOT}/modules/patents/scripts/chunk_compounds.py" --input "$SNAP/compounds.parquet" --out-dir "$DCHUNKS" --delta --nbrs "$NBRS"
          else
            $PY "${ROOT}/modules/patents/scripts/chunk_compounds.py" --input "$SNAP/compounds.parquet" --out-dir "$CHUNKS" --chunks 62
          fi ;;
        predict)
          # delta runs the fused k-NN on the (small) delta chunks -> a temp dir; full runs it on every chunk.
          local _pc="$CHUNKS" _po="$NBRS"; [[ $mode == delta ]] && { _pc="$DCHUNKS"; _po="$DNBRS"; }
          if pod_configured; then pod_predict "$_pc" "$REF" "$_po"
          else log "GPU stage — set POD_HOST/POD_PORT/POD_KEY for the pod (auto push/run/pull), or run locally if a GPU is present"
               $PY "$M/gpu/gpu_atlas_fused.py" --refsmi "$REF/reference.tsv" --patents "$_pc" --outdir "$_po" --knn 100 --procs 24; fi
          if [[ $mode == delta ]]; then   # fold the delta neighbours into atlas_nbrs under distinct names (additive, never overwrites)
            local _ts _k=1; _ts=$(date +%Y%m%d-%H%M%S)
            for f in "$DNBRS"/nbrs_*.parquet; do [[ -e "$f" ]] || continue; cp "$f" "$NBRS/nbrs_delta_${_ts}_$(printf %04d "$_k").parquet"; _k=$((_k+1)); done
            log "merged $((_k-1)) delta neighbour file(s) into atlas_nbrs (reused ~30M untouched)"
          fi ;;
        ingest)     $PY "$M/build_patent_compounds.py" --collection "$COLL" --nbrs "$NBRS" --compounds "$CHUNKS" --preddir "$PREDDIR" --workers "$WORKERS" ;;
        provenance) $PY "$M/bake_provenance.py" --collection "$COLL" --snapshot "$SNAP" ;;
        denoise)    $PY "$M/bake_targets.py" --collection "$COLL" --floor 0.4 --cap 50 ;;
        all)
          # ONE deferred-index window over every payload pass -> a single optimization
          log "build compounds -> $COLL (mode=$mode) [one deferred-index window]"
          qdrant_defer "$COLL"
          build compounds ingest     ${prod:+--prod}
          build compounds provenance ${prod:+--prod}
          build compounds denoise    ${prod:+--prod}
          qdrant_build "$COLL"
          ;;
        defer)  qdrant_defer "$COLL" ;;
        build)  qdrant_build "$COLL" ;;
        # rebuild: clean-copy into a fresh collection + one clean HNSW build. Use when the optimizer state gets
        #   tangled by repeated stop-start optimizations (a restart only reloads the same tangle). No recompute;
        #   source left intact as a fallback. After verifying ${COLL}_v2 is green: swap alias, drop the old.
        rebuild) $PY "${ROOT}/modules/qdrant/scripts/clean_copy.py" --src "$COLL" --dst "${COLL}_v2" ;;
        # swap: retire the old <COLL>, alias <COLL> -> <COLL>_v2 (engine/web keep the same name). Refuses unless _v2 is green.
        swap)    $PY "${ROOT}/modules/qdrant/scripts/swap_alias.py" --name "$COLL" ;;
        *) echo "compounds stages: all | chunk | predict | ingest | provenance | denoise | defer | build | rebuild | swap"; ;;
      esac ;;
    reference)
      # ChEMBL ligand->target answer-key as a served Qdrant collection (FPs recomputed from reference.tsv; no GPU).
      # The full 1.25M lives in work/chembl_reference/reference.tsv; rebuild whenever that reference is refreshed.
      local COLL="chembl${suffix}"
      case $stage in
        chembl) $PY "${ROOT}/modules/qdrant/scripts/build_chembl_collection.py" --collection "$COLL" --ref "${ROOT}/work/chembl_reference" ;;
        *) echo "reference stages: chembl  (make/fpsim2 TODO)"; ;;
      esac ;;
    trials)
      # clinical_trials MedCPT pipeline: chunk biobtree's trials.json -> MedCPT-Article embed (GPU) -> insert.
      # Source is biobtree (it owns the AACT download/extract/process); we consume trials.json directly.
      local COLL="clinical_trials_medcpt${suffix}"
      local CT_SRC="${CT_TRIALS_JSON:-/data/biobtree/raw_data/clinical_trials/trials.json}"
      local CT_IN="${ROOT}/work/data/medcpt_input/clinical_trials" CT_OUT="${ROOT}/work/data/medcpt_output/clinical_trials"
      local M="${ROOT}/modules/clinical_trials/scripts"
      case $stage in
        chunk)  $PY "$M/chunk_trials_to_jsonl.py" --trials-json "$CT_SRC" --out-dir "$CT_IN" ;;
        embed)  if pod_configured; then pod_embed_text "$CT_IN" "$CT_OUT"
                else log "GPU stage — set POD_HOST/POD_PORT/POD_KEY for the pod (auto push/run/pull), or run locally if a GPU is present"
                     $PY "${ROOT}/scripts/gpu/embed_text_medcpt_gpu.py" --input-dir "$CT_IN" --output-dir "$CT_OUT" --model ncbi/MedCPT-Article-Encoder --text-field text --batch-size 512 --max-length 512 --device auto; fi ;;
        insert) qdrant_defer "$COLL"
                $PY "${ROOT}/modules/qdrant/scripts/insert_from_faiss.py" --faiss-dir "$CT_OUT" --collection "$COLL" --qdrant-url "$QURL" --vector-size 768
                qdrant_build "$COLL" ;;
        all)    build trials chunk ${prod:+--prod}; build trials embed ${prod:+--prod}; build trials insert ${prod:+--prod} ;;
        *) echo "trials stages: all | chunk | embed | insert  (source: biobtree trials.json; embed = MedCPT-Article, GPU)"; ;;
      esac ;;
    text|proteins) log "$collection pipeline: TODO (Phase 2)";;
    *) cat <<EOF
bioyoda.sh build <collection> <stage> [--full|--delta] [--prod]
  collections: compounds | text | reference | proteins | trials
  compounds stages: all | chunk | predict | ingest | provenance | denoise | defer | build

  --delta (default, incremental):  process ONLY what changed since the last build.
      chunk/predict  -> compute the fused k-NN for compounds NOT already in work/atlas_nbrs/, then merge the
                        new neighbours in additively (the reused ~30M are never recomputed). [chunk/predict: DONE]
      ingest/provenance/denoise -> upsert/bake only the delta (additive). [TODO — currently still full]
  --full:  rebuild the whole snapshot from scratch (the one-time bootstrap, e.g. the June 2026 run).
  --prod:  target the real collections + full data. Default is *_test collections + small fixtures (safe dev).

  Efficiency: ingest -> provenance -> denoise run inside ONE deferred-index window (a single Qdrant
  optimization, not one per stage). GPU stages auto push/run/pull on a pod when POD_HOST/POD_PORT/POD_KEY set.

  e.g. a monthly refresh:  POD_HOST=root@ip POD_PORT=N POD_KEY=~/.ssh/k \
         bioyoda.sh build compounds all --delta --prod
EOF
    ;;
  esac
}


# entry point (sourced by bioyoda.sh)
cmd_build(){ build "$@"; }
