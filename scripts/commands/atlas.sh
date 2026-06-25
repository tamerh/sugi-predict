#!/bin/bash
##############################################################################
#
#   BioYoda Atlas Build Chain
#   Reproducible build steps over the patent target atlas. Each step is a
#   committed, parameterized Python module — wired here so the atlas and its
#   derived payload/indexes are rebuildable from source, not from one-off scripts.
#
##############################################################################

COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"
ROOT="$(cd "${COMMANDS_DIR}/../.." && pwd)"

atlas_help() {
    cat << 'EOF'
Atlas build chain — reproducible steps over the patent target atlas.

Usage: bioyoda.sh atlas <subcommand> [options]

Subcommands:
    bake [options]   Bake patent provenance (top-N span) into the Qdrant patent_atlas payload.
                       --top N (default 20)  --snapshot DIR  --collection C
                       --dry-run  --resume  --limit N
    targets [opts]   De-noise the reverse landscape: rewrite each compound's `targets` membership
                       from `predicted`, dropping single-weak hits (support==1 & conf<FLOOR) + top-N cap.
                       --floor F (default 0.4)  --cap N (default 50)  --dry-run  --resume  --limit N
    text <stage>     Refresh patents_text to MedCPT on the June-2026 base (prepare|embed|insert).
                       prepare=CPU shards, embed=GPU(pod)/CPU, insert=FAISS->patents_text_medcpt.
    grounding        Build the ChEMBL grounding JSONs (chembl_names, chembl_mechanisms).   [TODO]
    indexes          Build the web indexes (featured.json, compound_index.json).            [TODO]

Small-data test:  bioyoda.sh test --atlas

Examples:
    bioyoda.sh atlas bake --dry-run --limit 1000      # sanity-check, no writes
    bioyoda.sh atlas bake --top 20 --resume           # the real bake (resumable)
EOF
}

cmd_atlas() {
    if [[ $# -eq 0 ]]; then atlas_help; exit 0; fi
    local py="/data/miniconda3/envs/bioyoda/bin/python"
    [[ -x "$py" ]] || py="python3"
    local subcommand=$1; shift
    case $subcommand in
        bake)
            "$py" "${ROOT}/modules/compounds/bake_provenance.py" "$@"
            ;;
        targets)
            "$py" "${ROOT}/modules/compounds/bake_targets.py" "$@"
            ;;
        text)
            # patents_text refresh -> MedCPT on the June-2026 base. Reproducible, device-agnostic:
            # `embed` runs on GPU on a pod, or CPU here for small incremental deltas.
            local stage=${1:-help}; shift || true
            local SC="${ROOT}/raw_data/patents/surechembl/2026-06-01/patents.parquet"
            local UH="${ROOT}/raw_data/patents/historical_uspto/uspto_historical.parquet"
            local UG="${ROOT}/work/data/processed/patents/uspto_gap_enriched.parquet"
            local IN="${ROOT}/work/data/medcpt_input/patents"
            local OUT="${ROOT}/work/data/medcpt_output/patents"
            case $stage in
                prepare) "$py" "${ROOT}/modules/patents/scripts/prepare_medcpt_shards.py" \
                            --patents "$SC" --uspto "$UH" "$UG" --out-dir "$IN" "$@" ;;
                embed)   "$py" "${ROOT}/scripts/gpu/embed_text_medcpt_gpu.py" \
                            --input-dir "$IN" --output-dir "$OUT" "$@" ;;
                insert)  "$py" "${ROOT}/modules/qdrant/scripts/insert_from_faiss.py" \
                            --faiss-dir "$OUT" --collection patents_text_medcpt \
                            --qdrant-url http://localhost:6333 --vector-size 768 "$@" ;;
                *) cat <<'EOF'
atlas text <stage> — patents_text refresh to MedCPT (June-2026 base):
  prepare   CPU: June patents + USPTO full-text -> JSONL input shards
  embed     MedCPT-Article -> FAISS (GPU on a pod for the full run; CPU for small deltas)
  insert    FAISS -> Qdrant patents_text_medcpt (old patents_text left untouched)
Full run: prepare (here) -> embed (RunPod) -> insert (here) -> flip engine routing to MedCPT.
EOF
                ;;
            esac
            ;;
        grounding)
            log_warning "atlas grounding: build_grounding.py not yet committed (chembl_names/mechanisms still inline)"
            ;;
        indexes)
            log_warning "atlas indexes: build_indexes.py not yet committed (featured/compound_index still inline)"
            ;;
        --help|-h|help)
            atlas_help
            ;;
        *)
            log_error "Unknown atlas subcommand: $subcommand"
            atlas_help
            exit 1
            ;;
    esac
}
