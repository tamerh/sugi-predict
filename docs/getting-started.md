# Getting started

Four ways to use Sugi Predict, by audience. Targets are predicted by chemical similarity;
the signals: `confidence` is the best Tanimoto to a backing ChEMBL ligand, `support` is
how many of the 20 nearest neighbours agree, and below ~0.3 is novel/whitespace chemistry.
Deployment-realistic recall@1 is ~41% (the 83%/77% figures are upper bounds). See
[how-it-works.md](how-it-works.md) for the method.

## Browse

The web app at **[sugi.bio/predict](https://sugi.bio/predict)** is the no-setup way in.

- **One page per target** — `/target/<gene>` (e.g. `/target/EGFR`, or a UniProt accession): the
  patented chemistry predicted against that target, how much is high-confidence, the top
  predicted compounds (its landscape), plus supporting context (related trials, neighbouring
  proteins). Context is retrieved by similarity, not extra prediction.
- **One page per compound** — `/compound/<sid>` (e.g. `/compound/SCHEMBL12345`): its ranked
  predicted targets with confidence + support, which targets are already known, the patents
  that claim it, and chemically nearest patent compounds.
- **Predict a pasted molecule** — `/predict` takes a SMILES and runs the same prediction live.

The web UI is a separate repo
([sugi-predict-web](https://github.com/tamerh/sugi-predict-web)) that talks to the engine only
over HTTP.

## Query the API

The engine exposes a read-only REST API under `/api` on port **8011** (behind nginx in
production). Operations: `predict`, `provenance`, `query`, `similar-compounds`,
`patent-text-support`, plus `collections` / `count` / `depict`.

```sh
# Predict targets for a molecule (aspirin) — ranked targets with confidence + support
curl 'http://localhost:8011/api/predict?smiles=CC(=O)Oc1ccccc1C(=O)O&top=20&human_only=true'

# Patent provenance for a SureChEMBL compound — which patents claim/disclose it
curl 'http://localhost:8011/api/provenance?ids=12345&max_per=8'

# A target's landscape — count + filter the dataset by predicted target accession
curl -s http://localhost:8011/api/count \
  -H 'Content-Type: application/json' \
  -d '{"collection":"patent_compounds","filter":{"targets":"P00533","best_tanimoto":{"gte":0.6}}}'

# Is the patent abstract consistent with the chemistry-predicted target(s)?
curl 'http://localhost:8011/api/patent-text-support?compound_id=12345'

# Chemically nearest patent compounds (vector search on the Morgan fingerprint)
curl 'http://localhost:8011/api/similar-compounds?compound_id=12345&limit=10'
```

`/api/query` searches or filters any collection — body is
`{collection, text?|smiles?|accession?, filter?, limit?, offset?}`. See [api.md](api.md) for the
full reference (every param, response shapes, the collection map from `/api/collections`).

## Agents (MCP)

The same primitives are exposed as Model Context Protocol tools, so a language-model agent can
call the substrate directly: **`bioyoda_predict`**, **`bioyoda_provenance`**, and
**`bioyoda_query`**. Two transports:

- **Local (stdio)** — for a Claude CLI / desktop client:

  ```sh
  python -m mcp_srv --mode stdio
  ```

- **Remote (HTTP)** — JSON-RPC over `POST /mcp` on the same `:8011` server:

  ```sh
  python -m mcp_srv --mode http     # REST under /api + MCP at /mcp
  ```

  ```sh
  # list the tools
  curl -s http://localhost:8011/mcp \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

  # call one
  curl -s http://localhost:8011/mcp \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
         "params":{"name":"bioyoda_predict","arguments":{"smiles":"CC(=O)Oc1ccccc1C(=O)O"}}}'
  ```

`GET /health` reports Qdrant connectivity and the live collection count.

## Rebuild it

Everything is reproducible from source. Each collection is built (or incrementally refreshed
with `--delta`) by a single plain-bash command, `bioyoda.sh build`:

```sh
./bioyoda.sh build compounds all --prod     # the patent-compound collection (predict → provenance → denoise)
./bioyoda.sh build reference chembl --prod  # the ~1.25M ChEMBL ligand→target answer key
./bioyoda.sh build trials all --prod        # clinical-trials context (MedCPT)
./bioyoda.sh build proteins ...             # proteins context (ESM-2)
./bioyoda.sh build text ...                 # patent text (MedCPT)
```

Defaults target small `*_test` fixtures; `--prod` targets the real collections. See
[cli.md](cli.md) for stages, the deferred-index window, and alias swaps.
