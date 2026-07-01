# Sugi Predict

An open, reproducible **prediction of human protein targets across patent chemical space**,
published at **[sugi.bio/predict](https://sugi.bio/predict)**.

~30M SureChEMBL patent compounds are annotated with their likely human protein targets by
chemical k-nearest-neighbour transfer from a ~1.25M-pair ChEMBL ligand→target reference,
joined to patent provenance (which patents claim each compound — assignee, publication date,
claimed-vs-disclosed). It reads both directions: *what does this molecule hit?* and *what
patented chemistry is predicted against this target, and who claimed it?*

Each prediction carries a `confidence` (best Tanimoto to a backing ChEMBL ligand) and a
`support` count (n of 20 nearest neighbours agreeing); below ~0.3 Tanimoto is novel/whitespace
chemistry. Targets are predicted by chemical similarity, not measured; the supporting substrate
(patent text, clinical trials, proteins) is used as retrieval context. One engine serves it as
a web app, a REST API, and an MCP server over Qdrant.
Part of the [sugi.bio](https://sugi.bio) family: BioBTree · Sugi Atlas · Enju · Sugi Predict.

> **How the prediction works, the provenance join, the substrate, and the build all live in
> [`docs/`](docs/)** — start with [docs/how-it-works.md](docs/how-it-works.md).

## Use it

- **Browse** — the web app at **[sugi.bio/predict](https://sugi.bio/predict)** (no setup).
- **API + agents** — a REST API under `/api` and an MCP server at `/mcp`, both over the same
  three primitives (`query` / `predict` / `provenance`). See [docs/api.md](docs/api.md).

## Build it — `bioyoda.sh`

Every collection rebuilds from source via plain bash `bioyoda.sh build`:

```bash
conda env create -f environment.yml && conda activate bioyoda
./bioyoda.sh test                      # small-data fixture tests (the pre-build gate)
./bioyoda.sh build compounds all       # rebuild a collection (compounds·text·trials·reference·proteins)
```

Full command reference and the build sequence: [docs/cli.md](docs/cli.md) ·
[docs/getting-started.md](docs/getting-started.md).

## Substrate

Five served Qdrant collections (chemistry powers prediction; the rest is retrieval context):

| Collection | Modality | Embedding | Vectors |
|---|---|---|---|
| `patent_compounds` | chemical | Morgan ECFP4 (2048-bit) | ~30.9M |
| `chembl` | chemical | Morgan ECFP4 (2048-bit) | ~1.25M |
| `patents_text` | text | MedCPT (768-d) | ~39.6M |
| `clinical_trials_medcpt` | text | MedCPT (768-d) | ~4.5M |
| `esm2` | protein | ESM-2 (1280-d) | ~0.57M |

## Layout

| Path | Role |
|---|---|
| `mcp_srv/` | the engine — REST API + MCP server over `query`/`predict`/`provenance` |
| `modules/` | per-collection build code (compounds, patents, clinical_trials, esm2, qdrant) |
| `scripts/` | `bioyoda.sh` command implementations + shared libs |
| `workflows/` | one remaining Enju workflow: `diamond-update` (standalone DIAMOND protein-similarity data-prep) |
| `config/` | engine + collection configuration |
| `web/` | static assets served by the engine |
| `tests/` | fixture pipeline + integration (collection-health) tests |
| `docs/` | how-it-works, getting-started, API, CLI |

## Docs

- [docs/how-it-works.md](docs/how-it-works.md) — the prediction method, provenance, substrate, signals
- [docs/getting-started.md](docs/getting-started.md) — browse, query the API, drive it from an agent, rebuild
- [docs/api.md](docs/api.md) — full REST + MCP reference
- [docs/cli.md](docs/cli.md) — building and serving the engine

## Publication

Preprint — *forthcoming*.

## License

- **Code** — AGPL-3.0 ([LICENSE](LICENSE)). For on-premise deployment or other commercial terms, get in touch.
- **Data** — built from public databases (ChEMBL, SureChEMBL, ClinicalTrials.gov, UniProt); reuse is subject to each source's terms (ChEMBL is CC-BY-SA 3.0).
