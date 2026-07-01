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


## Substrate

Five served Qdrant collections (chemistry powers prediction; the rest is retrieval context):

| Collection | Modality | Embedding | Vectors |
|---|---|---|---|
| `patent_compounds` | chemical | Morgan ECFP4 (2048-bit) | ~30.9M |
| `chembl` | chemical | Morgan ECFP4 (2048-bit) | ~1.25M |
| `patents_text` | text | MedCPT (768-d) | ~39.6M |
| `clinical_trials_medcpt` | text | MedCPT (768-d) | ~4.5M |
| `esm2` | protein | ESM-2 (1280-d) | ~0.57M |


## Docs

- [docs/how-it-works.md](docs/how-it-works.md) — the prediction method, provenance, substrate, signals
- [docs/getting-started.md](docs/getting-started.md) — browse, query the API, drive it from an agent, rebuild
- [docs/api.md](docs/api.md) — full REST + MCP reference
- [docs/cli.md](docs/cli.md) — building and serving the engine

## Publication

Preprint
- https://sugi.bio/predict/method
- https://zenodo.org/records/21109920

## License
 
 AGPL-3.0 ([LICENSE](LICENSE)). For on-premise deployment or other commercial terms, get in touch.
