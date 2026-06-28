# qdrant

The Qdrant vector database layer: server lifecycle, per-collection build recipes, and the
FAISS→Qdrant loader. The five served collections all live in one Qdrant instance.

## Served collections

| Collection | Modality | Dim | Notes |
|---|---|---|---|
| `patent_compounds` | chemical | 2048 | Morgan ECFP4; alias → `patent_compounds_v2` |
| `chembl` | chemical | 2048 | ChEMBL reference ligands |
| `patents_text` | text | 768 | MedCPT; alias → `patents_text_medcpt` |
| `clinical_trials_medcpt` | text | 768 | MedCPT |
| `esm2` | protein | 1280 | ESM-2 650M |

## Lifecycle

```bash
./bioyoda.sh qdrant <subcommand>      # start | stop | restart | status | reindex | rebuild
```

`start`/`stop`/`restart` manage the Docker-compose container; `status` shows health + memory;
`reindex <collection>` triggers the HNSW build after a bulk load; `rebuild <collection>`
clean-copies into a fresh collection (per its profile) when the optimizer state gets tangled.

Inserts are **not** a qdrant command — each collection is loaded via its build stage
(`./bioyoda.sh build <collection> insert`).

## Key scripts (`scripts/`)

- `collection_profiles.py` — per-collection build recipes (dim, quantization, HNSW params).
- `insert_from_faiss.py` — load FAISS shards + sidecars into a collection (used by every build).
- `rebuild_collection.py`, `clean_copy.py`, `swap_alias.py` — rebuild / clean-copy / alias-swap.
- `build_chembl_collection.py` — build the `chembl` reference collection.
- `start_server.sh`, `stop_server.sh`, `check_status.sh` — container helpers.

Deep-dive notes (not part of this overview): `VIRTUAL_MEMORY_LIMIT_INVESTIGATION.md`,
`UPSERT_STRATEGY.md`.

See [docs/cli.md](../../docs/cli.md) for the full build/serve reference.
