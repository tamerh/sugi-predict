# clinical_trials

Builds the `clinical_trials_medcpt` collection — ClinicalTrials.gov records embedded with
MedCPT-Article (768-d), served as retrieval context for a target's trial landscape.

## Build

```bash
./bioyoda.sh build trials <stage>     # chunk | embed | insert | all
```

`chunk` turns biobtree's `trials.json` into MedCPT input shards (incremental by default vs the
tracking DB; `--full` rebuilds); `embed` runs MedCPT-Article (GPU via the pod, CPU otherwise);
`insert` upserts into Qdrant and commits the delta tracking hashes. The source (AACT download +
extract) is owned by biobtree; this module consumes `trials.json` directly. The scheduled
refresh runs as the `clinical-trials-update` Enju workflow (`workflows/clinical-trials-update/`).

## Key scripts (`scripts/`)

- `chunk_trials_to_jsonl.py` — trials.json → MedCPT input shards, delta vs the tracking DB.
- `tracking_db.py`, `chunk_tracking.py` — per-trial content-hash delta tracking.
- `process_trials*.py`, `merge_trials.py` — record processing / merge helpers.

Deep-dive notes (not part of this overview): `LIFECYCLE_DATA.md`, `ADVERSE_EVENTS_*.md`,
`CONDITIONS_FEATURE.md`, `TIER2_PLAN.md`.

See [docs/how-it-works.md](../../docs/how-it-works.md) for how the substrate is used and
[docs/cli.md](../../docs/cli.md) for the full build reference.
