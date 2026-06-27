# tests/integration — tier-2 LIVE-database regression gate

These tests run against the **real, full production Qdrant** at `localhost:6333` and
assert it is healthy and still gives known-correct answers. They are the safety net
to run **before and after a data update** (a re-ingest, a re-index, an atlas
re-bake): run them on the known-good DB, do the update, run them again — a diff in
pass/fail tells you the update broke something.

This is **tier 2** of a two-tier setup:

| tier | location | data | purpose |
|------|----------|------|---------|
| 1 — pipeline | `tests/pipeline/`, `tests/test_atlas_*.py` | tiny throwaway fixtures | logic of the build steps |
| 2 — integration (here) | `tests/integration/` | the LIVE full collections | the real DB is healthy + correct |

## READ-ONLY — this never mutates the database

Every call is `get_collections` / `get_aliases` / `get_collection` / `count` /
`retrieve` / `scroll` / `query_points`. There is **no** upsert, delete,
create/delete_collection, or optimizer trigger anywhere in this suite. It is safe to
run against production at any time, including mid-update (counts will just be
higher). It creates no temp collections (unlike the tier-1 atlas tests).

## How to run

Use the project's conda python (the one with `qdrant_client`):

```bash
PY=/data/miniconda3/envs/bioyoda/bin/python

$PY tests/integration/test_collections_health.py
$PY tests/integration/test_known_answers.py
```

Each file is a plain script (matching the existing `tests/test_atlas_*.py` style):
it prints per-check lines, ends with `... PASSED`, and **exits non-zero on any
failure** so it drops straight into CI / a shell `&&` chain. Override the endpoint
with `BIOYODA_QDRANT_URL` if needed.

## What each file asserts

### `test_collections_health.py`
- the two aliases still resolve: `patent_compounds -> patent_compounds_v2`,
  `patents_text -> patents_text_medcpt`;
- every production collection (`patent_compounds_v2`, `clinical_trials_medcpt`,
  `patents_text_medcpt`, `esm2`, `chembl`) is **GREEN**;
- `indexed_vectors_count` is within ±2% of `points_count` (HNSW fully built, not
  wedged/partial);
- `points_count >= a floor` set a few % below the known-good June-2026 state.
  **Floors, not equality** — updates add data.

### `test_known_answers.py`
- **EGFR landscape**: `count(patent_compounds where targets contains "P00533")` is
  in `500k..1.5M` (was ~841,765) — catches the `targets` index or bake collapsing;
- **imatinib** (point id 3827 / SCHEMBL3827): still carries its real targets
  ABL1 (P00519), BCR (P11274), KIT (P10721) in `targets[]` / `predicted[]`;
- **vector self-search** on the fingerprint collections (patent_compounds, chembl):
  a point's own vector returns itself in the top-k at score ≈ 1.0, fast — HNSW
  sanity. (Top-1 may be a *duplicate* fingerprint, so we check top-k membership +
  score, not literal top-1 == self.)
- **chembl** known ligand cid 6 keeps target P00811;
- **clinical_trials_medcpt** returns chunks for a known `nct_id`;
- **patents_text_medcpt** is present and a point is retrievable by id.

## Tuning the floors / ranges

The floors and the EGFR range are intentionally **loose enough to survive growth**
but **tight enough to catch a dropped collection, a yellow/wedged index, or a
landscape collapsing to ~0**. The known-good values observed 2026-06-27 are in code
comments next to each floor; bump the floors after a large verified update if you
want the gate to keep its margin.
