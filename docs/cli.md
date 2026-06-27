# CLI Reference

`bioyoda.sh` is the single entry point for the engine: build and refresh collections, run
the Qdrant container, run the test suite, and drive build pipelines as Enju workflow DAGs.

**Orchestration model.** One consistent system, no Snakemake: atomic bash `build` steps
compose into **Enju workflow DAGs** for distribution. `biobtree` owns the raw sources
(downloads/extracts); `bioyoda` owns the compute (embed → insert → bake → serve). GPU
stages auto push/run/pull on a remote pod when `POD_HOST`/`POD_PORT`/`POD_KEY` are set,
else run locally if a GPU is present.

```
bioyoda.sh build <collection> <stage>   Build / refresh a collection
bioyoda.sh qdrant <subcommand>          Qdrant container lifecycle (docker compose)
bioyoda.sh test [--integration|--atlas] Test suite (fixtures by default; live-DB regression)
bioyoda.sh enju <module>                Run a module's build pipeline as an Enju DAG
bioyoda.sh snapshot --name <n>          Create an isolated production copy
bioyoda.sh status | validate | clean    Maintenance helpers
bioyoda.sh push | pull <module>         Google Drive sync (for off-box GPU)
bioyoda.sh help | version
```

---

## `build` — build / refresh a collection

```
bioyoda.sh build <collection> <stage> [--full|--delta] [--prod]
```

The reproducible build chain. Collections and their stages:

| Collection | Target (prod) | Stages |
|---|---|---|
| `compounds` | `patent_compounds` | `all` · `chunk` · `predict` · `ingest` · `provenance` · `denoise` · `defer` · `build` · `rebuild` · `swap` |
| `text` | `pubmed_abstracts_medcpt` | `all` · `chunk` · `embed` · `insert` |
| `trials` | `clinical_trials_medcpt` | `all` · `chunk` · `embed` · `insert` |
| `reference` | `chembl` | `chembl` |
| `proteins` | `esm2` | `all` · `prepare` · `embed` · `insert` |

**`all`** runs the full chain for a collection. For `compounds` it wraps the payload passes
(`ingest → provenance → denoise`) in **one deferred-index window**: Qdrant indexing is
paused across every payload pass and the HNSW build is triggered **once** at the end (the
`defer` / `build` stages do this manually).

**Safety — `--prod` vs `*_test`.** This is the key default: **without `--prod`, `build`
targets `*_test` collections built from small fixtures under `work/test/`** (no GPU, no
real data). `--prod` targets the real collections + full snapshots. Always develop without
`--prod`.

**`--delta` (default) vs `--full`.** Incremental by default — process only what changed
since the last build, merging new work in additively (e.g. an 897K-compound delta took ~97s
vs ~10h for a full rebuild; the reused ~30M neighbours are never recomputed). `--full`
forces a rebuild from the whole snapshot (the one-time bootstrap).

```bash
# Safe dev: full chain on test fixtures -> *_test collections
bioyoda.sh build compounds all

# Monthly prod refresh, GPU on a pod, incremental
POD_HOST=root@ip POD_PORT=22 POD_KEY=~/.ssh/k \
  bioyoda.sh build compounds all --delta --prod

# Single stage
bioyoda.sh build trials embed --prod
```

**Collection swaps** (`compounds` only): `rebuild` clean-copies into `<COLL>_v2` with one
fresh HNSW build (use when the optimizer state gets tangled); `swap` retires the old
collection and aliases the name → `_v2` (refuses unless `_v2` is green). Every stage tees
to `logs/build/<collection>/<stage>-<ts>.log`.

---

## `qdrant` — vector DB lifecycle

Manages the Qdrant container via `docker compose` (config
`config/docker-compose.bioyoda.yml`, project `bioyoda`). Data persists in the mounted
`qdrant/storage` volume.

| Subcommand | Action |
|---|---|
| `start` | `docker compose up -d qdrant` then status |
| `stop` | stop the container (volume untouched) |
| `restart` | restart (e.g. to clear a wedged optimizer) |
| `status` | container state + memory + `healthz` probe |
| `reindex <coll>` | trigger an HNSW index build after bulk insert (`--monitor`, `--threshold N`) |
| `rebuild <coll>` | rebuild a collection from its FAISS source |

```bash
bioyoda.sh qdrant start
bioyoda.sh qdrant status
bioyoda.sh qdrant reindex patents_compounds --monitor
```

Qdrant listens on `:6333` (the engine reads `BIOYODA_QDRANT_URL`, default
`http://localhost:6333`).

---

## `test` — two-tier suite

```
bioyoda.sh test [--integration|--atlas]
```

| Tier | What it runs |
|---|---|
| *(default)* `pipeline` | Tier 1 — the full build pipeline on **small fixtures** → `*_test` collections (no GPU). The pre-commit gate. Runs `tests/pipeline/test_*.py`. |
| `--integration` | Tier 2 — **read-only** regression against the **live full DB**: green status, point counts, known-answer checks. Pre/post-update gate. Runs `tests/integration/test_*.py`. |
| `--atlas` | Legacy atlas build-chain component tests (`bake` / `targets`). |

```bash
bioyoda.sh test                 # fast, fixtures, safe — run before committing
bioyoda.sh test --integration   # validate the live DB after a refresh
```

---

## `enju` — run a build pipeline as an Enju DAG

```
bioyoda.sh enju <module>
  modules: clinical_trials | pubmed | diamond | patents | esm2 | qdrant-insert
```

Runs the module's workflow (`workflows/<module>-poc/enju.yaml`) end-to-end via `enju go`.
Enju compute tasks can't emit dynamic lists, so the driver first runs the module's
`prepare` step to resolve the fan-out list, writes it to a params file, then launches with
`--run-branch auto` (each run gets its own branch). Distribution is handled by Enju across
citizens — assign GPU tasks to a GPU citizen. The `enju` binary is resolved from `ENJU_BIN`,
`PATH`, or known install locations.

```bash
bioyoda.sh enju clinical_trials    # prepare -> fan-out -> embed -> merge, as a DAG
bioyoda.sh enju esm2
```

See the [Enju CLI](/data/enju/docs/reference/cli.md) for the underlying `enju go` /
`resume` / `drive` verbs.

---

## Other commands

| Command | Purpose |
|---|---|
| `start` / `stop` | Shorthand for the Qdrant server (no module arg) |
| `snapshot --name <n>` | Create an isolated production copy under `snapshots/<n>/` |
| `status` | Pipeline status |
| `validate <module>` | Validate a module's outputs |
| `clean <module>` | Remove intermediate files |
| `push` / `pull <module>` | Google Drive sync, for off-box (Colab) GPU processing |
| `run <module>` | Legacy local Snakemake path (retired for cluster use) |

```bash
bioyoda.sh snapshot --name prod_v1.0
bioyoda.sh push patents --code-only      # push scripts only (fast)
```

---

## See also

- [../README.md](../README.md) — the engine repo
- [how-it-works.md](how-it-works.md) — the prediction method + provenance + substrate
- [getting-started.md](getting-started.md) — browse, query the API, drive from an agent, rebuild
- [api.md](api.md) — the REST + MCP reference
