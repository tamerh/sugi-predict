# Sugi Predict documentation

**Sugi Predict** is an open, reproducible **predicted-target atlas of patent chemical
space**. ~30M SureChEMBL patent compounds are annotated with their likely human protein
targets by chemical k-NN transfer from a ~1.25M-pair ChEMBL ligand→target reference, joined
to patent provenance. It reads both directions — *what does this molecule hit?* and *what
patented chemistry is predicted against this target, and who claimed it?*

Each prediction carries a `confidence` (best Tanimoto to a backing ChEMBL ligand) and a
`support` count (n of 20 neighbours agreeing); below ~0.3 Tanimoto is novel/whitespace
chemistry. Targets are predicted by chemical similarity; the supporting substrate (patent
text, trials, proteins) is used as retrieval context.
One engine (internal codename `bioyoda`) serves it as a web atlas, a REST API, and an MCP
server. Part of the [sugi.bio](https://sugi.bio) family: BioBTree · Sugi Atlas · Enju · Sugi Predict.

**Start here:**

- **[how-it-works.md](how-it-works.md)** — the prediction method (exact-Tanimoto k-NN over the
  ChEMBL reference), provenance join, the substrate, and the confidence and support signals.
- **[getting-started.md](getting-started.md)** — how to use it: browse, query the API, drive it
  from an agent (MCP), or rebuild a collection.
- **[api.md](api.md)** — the full REST + MCP reference (endpoints, params, response shapes).
- **[cli.md](cli.md)** — building and serving the engine (`bioyoda.sh build <collection>`,
  orchestrated by Enju workflows).

**Quick links:**

- **Web atlas** — [sugi.bio/predict](https://sugi.bio/predict) (public)
- **REST API + MCP server** — the engine on `:8011` (REST under `/api`, MCP at `/mcp`); see
  [api.md](api.md)
- **Engine repo** — [github.com/tamerh/sugi-predict](https://github.com/tamerh/sugi-predict)
- **Web repo** — [github.com/tamerh/sugi-predict-web](https://github.com/tamerh/sugi-predict-web)
  (a separate HTTP consumer of the engine)
- **Preprint** — *(forthcoming)*
