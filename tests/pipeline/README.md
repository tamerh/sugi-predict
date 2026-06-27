# tests/pipeline/ — tier-1 pipeline tests (small fixtures, no prod, no GPU)

These tests run the **real** build pipeline (`bioyoda.sh build <collection> <stage>`) on **small
fixtures**, in **TEST MODE** (no `--prod`, so every build targets the `*_test` collection), then
assert the `*_test` collection comes out populated and a representative query works.

They catch pipeline regressions — a broken chunk/embed/insert step, a payload-shape change, a wrong
vector dimension — before they reach prod. This is **tier 1** of a two-tier setup; tier 2 lives in
`tests/integration/` and validates the full production DB.

## What each test covers

| Test | Collection built | Source fixture | Stages run | Embed (CPU) | Runtime |
|------|------------------|----------------|------------|-------------|---------|
| `test_build_compounds.py` | `patent_compounds_test` | `work/test/` (chunks + atlas_nbrs + preds, 1000 compounds) | `ingest` | none (RDKit FP + pre-computed k-NN) | ~2-3 min |
| `test_build_trials.py` | `clinical_trials_medcpt_test` | `tests/fixtures/clinical_trials/trials_small.json` (5 trials) | `all` (chunk→embed→insert) | MedCPT-Article, ~35 chunks | ~1 min |
| `test_build_text.py` | `pubmed_abstracts_medcpt_test` | `tests/fixtures/pubmed/test_abstracts.xml.gz` (50 abstracts) | `all` (chunk→embed→insert) | MedCPT-Article, 50 abstracts | ~1 min |
| `test_build_proteins.py` | `esm2_test` | `tests/fixtures/esm2/reference_proteins.fasta` (60 SwissProt) | `all --full` (prepare→embed→insert) | ESM-2 650M, 60 short seqs | ~1-2 min |
| `test_build_reference.py` | `chembl_test` | `tests/fixtures/chembl/` (10 cid/smiles + targets) | `chembl` | none (RDKit Morgan FP) | ~20 s |

Each test:
1. drops the `*_test` collection at the start (idempotent; refuses to ever touch a non-`_test` name),
2. runs the build command via subprocess (pointing the source at the fixture — see below),
3. asserts the collection exists with roughly the fixture's point count,
4. runs a representative query (retrieve-by-id / payload filter / vector search) and checks the payload.

## How the source is pointed at a fixture

In test mode `bioyoda.sh build` targets the `*_test` collection, but for trials/text/proteins/reference
the SOURCE path does **not** auto-switch to a fixture. Each test points it via an env var:

- **trials**: `CT_TRIALS_JSON=<fixture trials.json>`
- **text**: `PUBMED_RAW_DIR=<dir with baseline/*.xml.gz>` (the chunk step globs `<raw>/baseline/*.xml.gz`)
- **proteins**: `ESM2_SOURCE_FASTA=<fixture .fasta>`
- **reference**: `CHEMBL_REF_DIR=<dir with reference.tsv + cid_targets.json>`
- **compounds**: nothing — test mode already reads `work/test/` fixtures.

Test-mode scratch/state for trials/text/proteins is isolated under `work/test/` (build.sh `suffix`
logic), so a test run never touches the prod scratch dirs, tracking DBs, or `existing_*` delta sets.

## The embed problem (how it's handled)

trials/text/proteins have a model embed stage. There is **no GPU** on this machine, so each test runs
the embed on **CPU** with a **tiny** fixture — a handful of records embed in seconds after a one-time
model load (~30 s). All three models are already cached locally (MedCPT in HF cache, ESM-2 650M in
torch hub), so the tests run **offline** and need **no GPU/pod**. compounds and reference have no neural
embed at all (RDKit fingerprints), so they're the fastest.

## Running

```bash
PY=/data/miniconda3/envs/bioyoda/bin/python   # the bioyoda conda env (has qdrant_client, torch, esm, rdkit, h5py)

# one collection
$PY tests/pipeline/test_build_reference.py

# all of them
tests/pipeline/run_all.sh
```

Requires a live Qdrant at `localhost:6333` (override with `BIOYODA_QDRANT_URL`). Each test prints
`<name>: PASSED` and exits 0 on success, non-zero on failure (CI-friendly). The `*_test` collections
are left in place after the run (cheap, and handy for inspection); they are dropped + rebuilt on the
next run.

## Fixtures used

- `tests/fixtures/clinical_trials/trials_small.json` — 5 trials, biobtree `{"trials":[...]}` shape.
- `tests/fixtures/pubmed/test_abstracts.xml.gz` — 50 real PubMed abstracts.
- `tests/fixtures/esm2/reference_proteins.fasta` — 60 SwissProt sequences.
- `tests/fixtures/chembl/{reference.tsv,cid_targets.json}` — 10 real ChEMBL cid/smiles + their targets.
- `work/test/{chunks,preds,atlas_nbrs}/` — the 1000-compound atlas fixture (pre-computed GPU k-NN).

## Notes / build.sh fixes these tests required

See the report from the change that added this suite; in short, three minimal build.sh / build-script
fixes were needed so the first-time (fresh `*_test` collection) path works and test scratch is isolated:
1. `qdrant_defer` is a no-op when the collection doesn't exist yet (fresh build).
2. `build_chembl_collection.py` green-wait treats a sub-threshold (never-HNSW-indexed) collection as done.
3. trials/text/proteins scratch + state dirs are routed under `work/test/` in test mode (no prod clobber);
   reference gained a `CHEMBL_REF_DIR` source override.
```
```
