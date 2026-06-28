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
qc=QdrantClient(url=sys.argv[2],timeout=120,check_compatibility=False); n=sys.argv[1]
# no-op if the collection doesn't exist yet (fresh build: insert_from_faiss creates it already-deferred).
# Only the incremental case has a pre-existing collection to pause.
if not qc.collection_exists(n):
    print("  [defer] collection", n, "not present yet — insert will create it deferred"); sys.exit(0)
qc.update_collection(n, optimizer_config=models.OptimizersConfigDiff(indexing_threshold=1_000_000_000))
print("  [defer] indexing paused for", n)
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
_SSHOPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=25 -o ServerAliveInterval=15 -o ServerAliveCountMax=3"   # keepalive from medcpt_orchestrator.sh: long monitors/transfers don't drop
_pssh(){ ssh -i "${POD_KEY}" -p "${POD_PORT}" ${_SSHOPTS} "${POD_HOST}" "$@"; }
_pup(){  rsync -rltz --partial -e "ssh -i ${POD_KEY} -p ${POD_PORT} ${_SSHOPTS}" "$@"; }   # NOT -a: pod volumes forbid chown (owner/group) -> rsync exits 23
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
  log "[pod] ensure embed deps (transformers, faiss-cpu; torch comes from the pod base image)"
  _pssh "python -c 'import transformers, faiss' 2>/dev/null || pip install -q --break-system-packages transformers faiss-cpu"   # pod Python is Debian PEP-668 (externally-managed)
  log "[pod] launch MedCPT-Article embed under tmux"
  _pssh "cd /workspace && tmux kill-session -t embed 2>/dev/null; tmux new-session -d -s embed 'PYTHONUNBUFFERED=1 python -u embed_text_medcpt_gpu.py --input-dir input/ct --output-dir output/ct --model ncbi/MedCPT-Article-Encoder --text-field text --batch-size 512 --max-length 512 --device auto > embed.log 2>&1; echo EXIT=\$? >> embed.log'" </dev/null >/dev/null 2>&1   # fd redirect: tmux-over-SSH hangs the channel otherwise (June lesson)
  log "[pod] monitoring ($n shards expected)..."
  until [ "$(_pssh 'ls /workspace/output/ct/*.index 2>/dev/null | wc -l')" -ge "$n" ] || _pssh 'grep -q EXIT= /workspace/embed.log 2>/dev/null'; do sleep 60; done
  log "[pod] pull embeddings -> ${out#${ROOT}/}"; mkdir -p "$out"; _pup "${POD_HOST}:/workspace/output/ct/" "$out/"
  log "[pod] embed complete"
}
pod_embed_esm2(){   # $1=input dir (chunk_*.fasta)  $2=local output dir  — ESM-2 650M protein embed on the pod
  # Parallel to pod_embed_text, NOT a parameterization: ESM-2 is a different shape — FASTA shards (not jsonl),
  # the `esm`+biopython stack (not transformers), batch_esm2_gpu.py (not embed_text_medcpt_gpu.py), and that
  # script writes its .index/.json into an embeddings/ SUBDIR of --output-dir. So we monitor/pull that subdir.
  local in="$1" out="$2" n; n=$(ls "$in"/chunk_*.fasta 2>/dev/null | wc -l)
  log "[pod] push $n FASTA chunks + ESM-2 embed script -> ${POD_HOST}"
  _pssh "mkdir -p /workspace/input/esm2 /workspace/output/esm2 /workspace/state/esm2"
  _pup "$in/" "${POD_HOST}:/workspace/input/esm2/"
  _pup "${ROOT}/modules/esm2/scripts/batch_esm2_gpu.py" "${POD_HOST}:/workspace/"
  log "[pod] ensure embed deps (fair-esm, biopython, faiss-cpu; torch comes from the pod base image)"
  _pssh "python -c 'import esm, Bio, faiss' 2>/dev/null || pip install -q --break-system-packages fair-esm biopython faiss-cpu"   # pod Python is Debian PEP-668 (externally-managed)
  log "[pod] launch ESM-2 650M (esm2_t33_650M_UR50D, 1280-dim) embed under tmux"
  _pssh "cd /workspace && tmux kill-session -t embed 2>/dev/null; tmux new-session -d -s embed 'PYTHONUNBUFFERED=1 python -u batch_esm2_gpu.py --input-dir input/esm2 --output-dir output/esm2 --state-file state/esm2/gpu_progress.json --model esm2_t33_650M_UR50D --skip-existing > embed.log 2>&1; echo EXIT=\$? >> embed.log'" </dev/null >/dev/null 2>&1   # fd redirect: tmux-over-SSH hangs the channel otherwise (June lesson)
  log "[pod] monitoring ($n chunks expected)..."
  until [ "$(_pssh 'ls /workspace/output/esm2/embeddings/*.index 2>/dev/null | wc -l')" -ge "$n" ] || _pssh 'grep -q EXIT= /workspace/embed.log 2>/dev/null'; do sleep 60; done
  log "[pod] pull embeddings -> ${out#${ROOT}/}"; mkdir -p "$out"; _pup "${POD_HOST}:/workspace/output/esm2/embeddings/" "$out/"   # batch_esm2_gpu.py writes into an embeddings/ subdir
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
      # source dir is overridable (CHEMBL_REF_DIR) so test mode can point at a small fixture; default = full prod reference
      local CHEMBL_REF="${CHEMBL_REF_DIR:-${ROOT}/work/chembl_reference}"
      case $stage in
        chembl) $PY "${ROOT}/modules/qdrant/scripts/build_chembl_collection.py" --collection "$COLL" --ref "$CHEMBL_REF" ;;
        *) echo "reference stages: chembl  (make/fpsim2 TODO)"; ;;
      esac ;;
    trials)
      # clinical_trials MedCPT pipeline: chunk biobtree's trials.json -> MedCPT-Article embed (GPU) -> insert.
      # Source is biobtree (it owns the AACT download/extract/process); we consume trials.json directly.
      local COLL="clinical_trials_medcpt${suffix}"
      local CT_SRC="${CT_TRIALS_JSON:-/data/biobtree/raw_data/clinical_trials/trials.json}"
      # scratch/state: test mode (suffix=_test) is isolated under work/test/ so it NEVER touches the prod scratch/tracking DB
      local CT_BASE="${ROOT}/work" CT_SBASE="${ROOT}/work/state"
      [[ -n "$suffix" ]] && { CT_BASE="${ROOT}/work/test"; CT_SBASE="${ROOT}/work/test/state"; }
      local CT_IN="${CT_BASE}/data/medcpt_input/clinical_trials" CT_OUT="${CT_BASE}/data/medcpt_output/clinical_trials"
      local CT_DB="${CT_SBASE}/clinical_trials/trials_tracking.db" CT_PEND="${CT_SBASE}/clinical_trials/pending_track.json"
      mkdir -p "$CT_IN" "$(dirname "$CT_DB")"
      local M="${ROOT}/modules/clinical_trials/scripts"
      case $stage in
        chunk)  local _full=""; [[ $mode == full ]] && _full="--full"   # default: incremental (delta vs tracking DB)
                $PY "$M/chunk_trials_to_jsonl.py" --trials-json "$CT_SRC" --out-dir "$CT_IN" --tracking-db "$CT_DB" $_full ;;
        embed)  mkdir -p "$CT_OUT"; rm -f "$CT_OUT"/shard_*.index "$CT_OUT"/shard_*.json   # clear stale output: the delta shards (shard_00000+) must not collide with a prior full embed's names (would be skipped, and re-inserted)
                if pod_configured; then pod_embed_text "$CT_IN" "$CT_OUT"
                else log "GPU stage — MedCPT on CPU is ~7 text/s (~9h for this delta); set POD_HOST/POD_PORT/POD_KEY for the pod (~2 min)"
                     $PY "${ROOT}/scripts/gpu/embed_text_medcpt_gpu.py" --input-dir "$CT_IN" --output-dir "$CT_OUT" --model ncbi/MedCPT-Article-Encoder --text-field text --batch-size 512 --max-length 512 --device auto; fi ;;
        insert) qdrant_defer "$COLL"
                $PY "${ROOT}/modules/qdrant/scripts/insert_from_faiss.py" --faiss-dir "$CT_OUT" --collection "$COLL" --qdrant-url "$QURL" --vector-size 768
                qdrant_build "$COLL"
                # commit the deferred tracking hashes ONLY now that the insert succeeded (so a failed embed/insert never marks trials done)
                if [[ -f "$CT_PEND" ]]; then $PY -c "import sys,json; sys.path.insert(0,'${ROOT}'); from modules.clinical_trials.scripts.tracking_db import TrialsTracker; u=json.load(open('${CT_PEND}')); TrialsTracker('${CT_DB}').add_or_update_batch(u); print(f'  tracking: committed {len(u):,} delta hashes')" && rm -f "$CT_PEND"; fi ;;   # if-form: no spurious exit 1 when there's no pending file
        all)    build trials chunk ${prod:+--prod}; build trials embed ${prod:+--prod}; build trials insert ${prod:+--prod} ;;
        *) echo "trials stages: all | chunk | embed | insert  (source: biobtree trials.json; embed = MedCPT-Article, GPU)"; ;;
      esac ;;
    text)
      # pubmed_abstracts MedCPT pipeline: parse PubMed XML -> MedCPT-Article embed (GPU) -> insert.
      # Mirrors the trials case exactly. Source is the NCBI PubMed download (baseline/ + updatefiles/);
      # the chunk step replaces the legacy index.py (which embedded with S-BioBERT in one CPU step).
      local COLL="pubmed_abstracts_medcpt${suffix}"
      local PM_RAW="${PUBMED_RAW_DIR:-${ROOT}/work/raw_data/pubmed}"
      # scratch/state: test mode (suffix=_test) is isolated under work/test/ so it NEVER touches the prod scratch/existing-pmids
      local PM_BASE="${ROOT}/work" PM_SBASE="${ROOT}/work/state"
      [[ -n "$suffix" ]] && { PM_BASE="${ROOT}/work/test"; PM_SBASE="${ROOT}/work/test/state"; }
      local PM_IN="${PM_BASE}/data/medcpt_input/pubmed" PM_OUT="${PM_BASE}/data/medcpt_output/pubmed"
      local PM_DELETED="${PM_RAW}/deleted.pmids.sorted.gz"
      local PM_EXIST="${PM_SBASE}/pubmed/existing_pmids.txt.gz"
      mkdir -p "$PM_IN" "$(dirname "$PM_EXIST")"
      local M="${ROOT}/modules/pubmed/scripts"
      case $stage in
        chunk)  local _full=""; [[ $mode == full ]] && _full="--full"   # default: incremental (PMID-delta vs existing_pmids)
                $PY "$M/chunk_pubmed_to_jsonl.py" --raw-dir "$PM_RAW" --out-dir "$PM_IN" \
                    --deleted-pmids "$PM_DELETED" --existing-pmids "$PM_EXIST" $_full ;;
        embed)  mkdir -p "$PM_OUT"; rm -f "$PM_OUT"/shard_*.index "$PM_OUT"/shard_*.json   # clear stale output: delta shard_00000+ must not collide with a prior full embed's names (would be skipped, never re-inserted)
                if pod_configured; then pod_embed_text "$PM_IN" "$PM_OUT"
                else log "GPU stage — MedCPT on CPU is ~1 text/s (infeasible at PubMed scale); set POD_HOST/POD_PORT/POD_KEY for the pod"
                     $PY "${ROOT}/scripts/gpu/embed_text_medcpt_gpu.py" --input-dir "$PM_IN" --output-dir "$PM_OUT" --model ncbi/MedCPT-Article-Encoder --text-field text --batch-size 512 --max-length 512 --device auto; fi ;;
        insert) qdrant_defer "$COLL"
                # additive PMID-delta: insert_from_faiss keys points by pmid (int) -> re-running a PMID is idempotent (no --update-mode needed)
                $PY "${ROOT}/modules/qdrant/scripts/insert_from_faiss.py" --faiss-dir "$PM_OUT" --collection "$COLL" --qdrant-url "$QURL" --vector-size 768
                qdrant_build "$COLL"
                # refresh the already-embedded PMID set from the new sidecars so the NEXT delta skips them
                $PY "$M/build_existing_pmids.py" --metadata-dir "$PM_OUT" --output "$PM_EXIST" || log "warn: existing_pmids refresh failed (next --full not affected)" ;;
        all)    build text chunk ${prod:+--prod}; build text embed ${prod:+--prod}; build text insert ${prod:+--prod} ;;
        *) echo "text stages: all | chunk | embed | insert  (source: PubMed XML baseline+updatefiles; embed = MedCPT-Article, GPU)"; ;;
      esac ;;
    proteins)
      # esm2 ESM-2 protein pipeline: split UniProt FASTA -> ESM-2 650M embed (GPU) -> insert.
      # Mirrors the trials/text cases, but ESM-2 (protein LM, dim 1280) NOT MedCPT text:
      #   embed = modules/esm2/scripts/batch_esm2_gpu.py (esm2_t33_650M_UR50D), GPU via pod_embed_esm2.
      # The live `esm2` collection (574K points) is updated INCREMENTALLY: delta = only proteins whose
      # UniProt accession is not already in the collection (the June new_proteins.fasta flow). insert_from_faiss
      # keys points by hashed protein_id -> additive & idempotent (cannot collide with the legacy sequential IDs).
      local COLL="esm2${suffix}"
      local PR_SRC="${ESM2_SOURCE_FASTA:-${ROOT}/raw_data/esm2/uniprot_swissprot.fasta}"
      # scratch/state: test mode (suffix=_test) is isolated under work/test/ so it NEVER touches the prod chunks/state/existing-proteins
      local PR_CDIR="${ROOT}/raw_data/esm2" PR_OUTPARENT="${ROOT}/work/data/esm2_output" PR_SBASE="${ROOT}/work/state"
      [[ -n "$suffix" ]] && { PR_CDIR="${ROOT}/work/test/esm2"; PR_OUTPARENT="${ROOT}/work/test/data/esm2_output"; PR_SBASE="${ROOT}/work/test/state"; }
      local PR_CHUNKS="${PR_CDIR}/chunks" PR_NEW="${PR_CDIR}/new_proteins.fasta"
      local PR_OUT="${PR_OUTPARENT}/embeddings"   # batch_esm2_gpu.py writes its .index/.json under <output-dir>/embeddings
      local PR_EXIST="${PR_SBASE}/esm2/existing_proteins.txt.gz"
      local PR_STATE="${PR_SBASE}/esm2/gpu_progress.json"
      mkdir -p "$PR_CHUNKS" "$(dirname "$PR_EXIST")"
      local M="${ROOT}/modules/esm2/scripts"
      case $stage in
        prepare) local _full=""; [[ $mode == full ]] && _full="--full"   # default: delta (only NEW accessions vs the existing set)
                $PY "$M/prepare_delta.py" --source "$PR_SRC" --out-dir "$PR_CHUNKS" \
                    --existing-proteins "$PR_EXIST" --new-fasta "$PR_NEW" --per-chunk 5000 --num-chunks 62 $_full ;;
        embed)  mkdir -p "$PR_OUT"; rm -f "$PR_OUT"/chunk_*.index "$PR_OUT"/chunk_*.json "$PR_OUT"/chunk_*.h5   # clear stale output: delta chunk_001+ must not collide with a prior full embed's names (would be skipped, never re-inserted)
                if pod_configured; then pod_embed_esm2 "$PR_CHUNKS" "$PR_OUT"
                else log "GPU stage — ESM-2 650M on CPU is very slow; set POD_HOST/POD_PORT/POD_KEY for the pod, or run locally if a GPU is present"
                     $PY "$M/batch_esm2_gpu.py" --input-dir "$PR_CHUNKS" --output-dir "$PR_OUTPARENT" --state-file "$PR_STATE" --model esm2_t33_650M_UR50D --skip-existing; fi ;;
        insert) qdrant_defer "$COLL"
                # additive protein-delta: insert_from_faiss keys points by hashed protein_id -> re-running a protein is idempotent (no --update-mode needed)
                $PY "${ROOT}/modules/qdrant/scripts/insert_from_faiss.py" --faiss-dir "$PR_OUT" --collection "$COLL" --qdrant-url "$QURL" --vector-size 1280
                qdrant_build "$COLL"
                # refresh the already-embedded accession set from the new sidecars so the NEXT delta skips them
                $PY "$M/build_existing_proteins.py" --metadata-dir "$PR_OUT" --output "$PR_EXIST" --merge || log "warn: existing_proteins refresh failed (next --full not affected)" ;;
        all)    build proteins prepare ${prod:+--prod}; build proteins embed ${prod:+--prod}; build proteins insert ${prod:+--prod} ;;
        *) echo "proteins stages: all | prepare | embed | insert  (collection: esm2; source: UniProt FASTA; embed = ESM-2 650M esm2_t33_650M_UR50D dim 1280, GPU)"; ;;
      esac ;;
    patents-text)
      # patents_text MedCPT pipeline: SureChEMBL patents.parquet (title) + USPTO full-text overlay -> JSONL shards
      #   -> MedCPT-Article embed (GPU) -> insert into patents_text_medcpt (served as the patents_text alias).
      # Mirrors the trials/text cases (MedCPT-Article, dim 768), but the source is patents not pubmed/trials:
      #   prepare = modules/patents/scripts/prepare_medcpt_shards.py (title doubled + USPTO abstract/claims/desc
      #   where has_full_text). The same chain the retired `atlas text` ran; this is now its single home.
      local COLL="patents_text_medcpt${suffix}"
      local PT_SC="${SURECHEMBL_PATENTS:-${ROOT}/raw_data/patents/surechembl/2026-06-01/patents.parquet}"
      local PT_UH="${ROOT}/raw_data/patents/historical_uspto/uspto_historical.parquet"
      local PT_UG="${ROOT}/work/data/processed/patents/uspto_gap_enriched.parquet"
      # scratch: test mode (suffix=_test) isolated under work/test/ so it NEVER touches the prod shards/output
      local PT_BASE="${ROOT}/work"
      [[ -n "$suffix" ]] && PT_BASE="${ROOT}/work/test"
      local PT_IN="${PT_BASE}/data/medcpt_input/patents" PT_OUT="${PT_BASE}/data/medcpt_output/patents"
      mkdir -p "$PT_IN"
      case $stage in
        prepare) $PY "${ROOT}/modules/patents/scripts/prepare_medcpt_shards.py" \
                    --patents "$PT_SC" --uspto "$PT_UH" "$PT_UG" --out-dir "$PT_IN" ;;
        embed)  mkdir -p "$PT_OUT"; rm -f "$PT_OUT"/shard_*.index "$PT_OUT"/shard_*.json   # clear stale output: delta shards must not collide with a prior full embed's names (would be skipped, never re-inserted)
                if pod_configured; then pod_embed_text "$PT_IN" "$PT_OUT"
                else log "GPU stage — MedCPT on CPU is infeasible at patent scale (~39M); set POD_HOST/POD_PORT/POD_KEY for the pod"
                     $PY "${ROOT}/scripts/gpu/embed_text_medcpt_gpu.py" --input-dir "$PT_IN" --output-dir "$PT_OUT" --model ncbi/MedCPT-Article-Encoder --text-field text --batch-size 512 --max-length 512 --device auto; fi ;;
        insert) qdrant_defer "$COLL"
                # additive: insert_from_faiss keys points by hash(patent_id) -> re-running a patent is idempotent (upgrades title-only -> full-text in place)
                $PY "${ROOT}/modules/qdrant/scripts/insert_from_faiss.py" --faiss-dir "$PT_OUT" --collection "$COLL" --qdrant-url "$QURL" --vector-size 768
                qdrant_build "$COLL" ;;
        all)    build patents-text prepare ${prod:+--prod}; build patents-text embed ${prod:+--prod}; build patents-text insert ${prod:+--prod} ;;
        *) echo "patents-text stages: all | prepare | embed | insert  (collection: patents_text_medcpt; source: SureChEMBL patents.parquet + USPTO full-text; embed = MedCPT-Article, dim 768, GPU)"; ;;
      esac ;;
    *) cat <<EOF
bioyoda.sh build <collection> <stage> [--full|--delta] [--prod]
  collections: compounds | patents-text | text | reference | proteins | trials
  compounds stages:    all | chunk | predict | ingest | provenance | denoise | defer | build
  patents-text stages: all | prepare | embed | insert (patents_text_medcpt; source: SureChEMBL + USPTO full-text; MedCPT-Article)
  text stages:         all | chunk | embed | insert   (pubmed_abstracts_medcpt; source: PubMed XML; MedCPT-Article)
  trials stages:       all | chunk | embed | insert   (clinical_trials_medcpt; source: biobtree trials.json; MedCPT-Article)
  proteins stages:     all | prepare | embed | insert (esm2; source: UniProt FASTA; embed = ESM-2 650M, dim 1280)

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
