#!/usr/bin/env python3
"""Single source of truth for BioYoda / Sugi Predict build & data paths.

Every Python module imports its work/raw_data locations from HERE instead of hardcoding
absolute strings. Renaming/moving the work tree (e.g. `work/` -> `out_prod/work`) or moving
the whole repo to another machine becomes a ONE-LINE / one-env-var change.

Resolution order (portable — NO hardcoded /data/bioyoda):
  ROOT     = $BIOYODA_ROOT  or  the repo root inferred from this file's location
             (modules/paths.py -> repo root is its parent's parent).
  WORK     = $BIOYODA_WORK  or  ROOT/<base_dir>          (base_dir defaults to "work")
  RAW_DATA = ROOT/raw_data

The bash entrypoint (bioyoda.sh / scripts/lib/config.sh) exports BIOYODA_ROOT and
BIOYODA_WORK from config.yaml `base_dir` before invoking any Python, so config.yaml's
`base_dir` stays the single knob and the Python side honors it. For standalone Python runs
(no env), the __file__-derived defaults reproduce today's layout exactly.

  >>> from modules.paths import WORK, CHEMBL_REF, ATLAS_NBRS
"""
import os
from pathlib import Path

# --- ROOT: env override, else infer from this file (modules/paths.py -> repo root) ---
ROOT = Path(os.environ.get("BIOYODA_ROOT") or Path(__file__).resolve().parent.parent)

# --- WORK: env override, else config.yaml base_dir (the one knob), else "work". ---
# The bash layer exports BIOYODA_WORK from config.yaml; for direct/standalone Python runs we
# read base_dir straight from config.yaml so the renamed layout is honored without the env too.
def _base_dir_from_config() -> str:
    try:
        for _line in (ROOT / "config" / "config.yaml").read_text().splitlines():
            _s = _line.strip()
            if _s.startswith("base_dir:"):
                return _s.split(":", 1)[1].split("#", 1)[0].strip().strip('"').strip("'") or "work"
    except Exception:
        pass
    return "work"

_base = os.environ.get("BIOYODA_WORK") or _base_dir_from_config()
_w = Path(_base)
WORK = _w if _w.is_absolute() else (ROOT / _w)

RAW_DATA = ROOT / "raw_data"

# --------------------------------------------------------------------------- work/ subpaths
CHEMBL_REF          = WORK / "chembl_reference"                     # ChEMBL ligand->target reference
ATLAS_NBRS          = WORK / "atlas_nbrs"                           # GPU k-NN raw neighbours (full substrate)
ATLAS_PREDS_ALIGNED = WORK / "atlas_preds_aligned"                 # per-June-chunk aligned predictions
FPSIM2              = WORK / "fpsim2"                               # exact-Tanimoto FPSim2 store
FPSIM2_PATENTS_H5   = FPSIM2 / "patents_compounds_morgan_r2_2048.h5"  # served FTO index (fto.py)
QSAR_MODELS         = WORK / "qsar_models"                          # trained QSAR models (qsar.py)
DIAMOND_TSV         = WORK / "data" / "processed" / "diamond" / "merged" / "filtered_top100.tsv"  # xmodal protein->compound
PATENT_TEXT_SUPPORT = WORK / "patent_text_support"                 # patents_text abstract-consistency assets
STATE               = WORK / "state"                               # tracking DBs / existing-id sets
DATA                = WORK / "data"                                 # medcpt_input/output, processed/

# common reference files (under CHEMBL_REF)
TARGET_GENES_JSON   = CHEMBL_REF / "target_genes.json"
CID_TARGETS_JSON    = CHEMBL_REF / "cid_targets.json"
CHEMBL_REF_TSV      = CHEMBL_REF / "reference.tsv"

# engine assets (served at query time)
CHEMBL_NAMES_JSON      = WORK / "chembl_names.json"
CHEMBL_MECHANISMS_JSON = WORK / "chembl_mechanisms.json"
TEXT_SUPPORT_QUERY_EMB = PATENT_TEXT_SUPPORT / "target_query_emb.npz"

# medcpt / esm2 faiss output dirs (consumed by rebuild/insert; relative to WORK)
MEDCPT_OUT_PUBMED   = DATA / "medcpt_output" / "pubmed"
MEDCPT_OUT_TRIALS   = DATA / "medcpt_output" / "clinical_trials"
MEDCPT_OUT_PATENTS  = DATA / "medcpt_output" / "patents"
ESM2_EMBEDDINGS     = DATA / "processed" / "esm2" / "embeddings"

# clinical_trials / pubmed input + tracking
MEDCPT_IN_TRIALS    = DATA / "medcpt_input" / "clinical_trials"
MEDCPT_IN_PUBMED    = DATA / "medcpt_input" / "pubmed"
TRIALS_TRACKING_DB  = STATE / "clinical_trials" / "trials_tracking.db"
PUBMED_RAW          = WORK / "raw_data" / "pubmed"

# bake intermediates
BAKE_PROVENANCE_CKPT = WORK / "bake_provenance.ckpt"
BAKE_TARGETS_CKPT    = WORK / "bake_targets.ckpt"
PATENT_COMPOUND_MAP_SORTED = WORK / "patent_compound_map.sorted.parquet"
DUCKDB_TMP           = WORK / "duckdb_tmp"

# --------------------------------------------------------------------------- raw_data/ subpaths
CHUNKED_COMPOUNDS   = RAW_DATA / "patents" / "chunked_compounds"    # SureChEMBL chunked compound parquets

def surechembl_snapshot(date: str) -> Path:
    """raw_data/patents/surechembl/<date> (the default snapshot dirs in the bake/provenance modules)."""
    return RAW_DATA / "patents" / "surechembl" / date
