# API Reference

Sugi Predict serves one **read-only** engine (codename `bioyoda`) behind two faces that
give identical answers: a **REST API** under `/api`, and an **MCP server** for agents. Both
are thin wrappers over the same engine primitives — nothing here writes; every route is a
Qdrant search/scroll/count or the FPSim2 k-NN predictor.

> Targets are **predicted** by chemical k-NN to ChEMBL ligands, not measured activity.
> Only chemistry is used to predict targets; the other collections are retrieval context.
> `patent-text-support` reports whether a patent's abstract is textually about a predicted
> target — a consistency signal, not a binding measurement. See [how-it-works.md](how-it-works.md).

**Base URL:** `http://localhost:8011/api` (port `8011`; configurable via `BIOYODA_PORT`).
Run the server with `python -m mcp_srv --mode http`. Health probe: `GET /health`.

**Limits:** `limit` is clamped to **1–100** (`MAX_LIMIT = 100`). Vectors are stripped from
all responses.

**Collections** (the capability map, from `GET /api/collections`):

| Collection | Modality | Dim | Query by |
|---|---|---|---|
| `patent_compounds` | chemical | 2048 | `smiles` (Morgan ECFP4) |
| `chembl` | chemical | 2048 | `smiles` |
| `clinical_trials_medcpt` | text | 768 | `text` (MedCPT) |
| `patents_text` | text | 768 | `text` (MedCPT) |
| `esm2` | protein | 1280 | `accession` (UniProt id) |

---

## REST endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/collections` | GET | Capability map: collections, modality, vector dim |
| `/api/query` | POST | Search / filter / id-lookup any collection |
| `/api/count` | POST | Count points matching a payload filter |
| `/api/predict` | GET | SMILES → ranked predicted targets |
| `/api/provenance` | GET | SureChEMBL id(s) → patent metadata |
| `/api/patent-text-support` | GET | Patent-text consistency badges for a compound |
| `/api/similar-compounds` | GET | Chemically nearest patent compounds |
| `/api/depict` | GET | Render a SMILES to SVG (RDKit) |
| `/health` | GET | Liveness + Qdrant connectivity |

### `GET /api/collections`

The capability map clients read instead of querying Qdrant blind.

```bash
curl "http://localhost:8011/api/collections"
```
```json
{ "patent_compounds": {"modality": "chemical", "dim": 2048}, ... }
```

### `POST /api/query`

Retrieve from any collection. Exactly one mode applies, in priority order:
**by id** (`ids`) → **vector search** (`text` / `smiles` / `accession`, matching the
collection's modality) → **payload filter** (`scroll`, no ranking). A query input may be
combined with a `filter` to restrict a similarity search.

| Field | Type | Notes |
|---|---|---|
| `collection` | string | **required** |
| `text` | string | semantic query, text collections |
| `smiles` | string | similarity query, chemical collections |
| `accession` | string | UniProt id, `esm2` only |
| `ids` | list | exact point lookup (int or string) |
| `filter` | object | payload filter, AND-ed (see below) |
| `limit` | int | 1–100, default 10 |
| `offset` | int / token | numeric offset (vector) or scroll token |
| `with_names` | bool | chemical only — attach ChEMBL `name` per hit |
| `with_known` | bool | chemical only — attach curated `known` target genes |

**Filter syntax:** `{field: value}` exact · `{field: [v1,v2]}` any-of ·
`{field: {gte: x, lte: y}}` numeric range. Multiple fields are AND-ed.
Useful `patent_compounds` payload fields: `targets`, `best_tanimoto`, `novel`,
`exact_match`, `surechembl_id`.

```bash
curl -X POST "http://localhost:8011/api/query" \
  -H 'Content-Type: application/json' \
  -d '{"collection":"patent_compounds","smiles":"CC(=O)Oc1ccccc1C(=O)O",
       "filter":{"best_tanimoto":{"gte":0.5}},"limit":5}'
```
```json
{ "hits": [ {"id": 12345, "score": 0.83, "payload": {"smiles": "...", "predicted": [...]}} ],
  "next": null }
```
(`score` present for vector search; `next` is the scroll token for filter-only queries.)

### `POST /api/count`

Cheap count of points matching a payload filter (drives broad-vs-confident sliders).

```bash
curl -X POST "http://localhost:8011/api/count" \
  -H 'Content-Type: application/json' \
  -d '{"collection":"patent_compounds","filter":{"targets":"P00533","novel":true}}'
```
```json
{ "collection": "patent_compounds", "count": 41822 }
```

### `GET /api/predict`

Predict protein targets for an arbitrary SMILES (FPSim2 chemical k-NN to the ChEMBL
reference — the predictor, not a lookup). Predictions below the calibrated `floor` (0.3)
are dropped below the novel-chemistry floor; experimentally **known** targets are always kept.

| Param | Default | Notes |
|---|---|---|
| `smiles` | **required** | the molecule |
| `top` | 20 | max targets returned |
| `human_only` | true | restrict to human targets |

```bash
curl "http://localhost:8011/api/predict?smiles=CC(=O)Oc1ccccc1C(=O)O&top=10"
```
```json
{ "smiles": "...", "name": "Aspirin", "n_targets": 7, "known": ["PTGS1","PTGS2"],
  "predictions": [ {"accession":"P23219","gene":"PTGS1","name":"...","confidence":0.61,
                    "support":14,"band":"...","known":true} ] }
```
`confidence` = best Tanimoto to a backing ligand; `support` = n of 20 nearest neighbours
agreeing; `<0.3` = novel/whitespace.

### `GET /api/provenance`

Resolve SureChEMBL id(s) to patent metadata (number, country, assignee, publication date,
claimed flag). Reads the baked `prov` payload span; falls back to a live parquet join for
un-baked ids.

| Param | Default | Notes |
|---|---|---|
| `ids` | **required** | comma-separated SureChEMBL ids (`SCHEMBL964` or bare int) |
| `max_per` | 8 | max patents per compound |

```bash
curl "http://localhost:8011/api/provenance?ids=SCHEMBL964,SCHEMBL8383&max_per=5"
```
```json
{ "SCHEMBL964": { "n_patents": 31, "noise": false,
                  "patents": [ {"number":"US...","assignee":"...","claimed":true} ] } }
```
`noise: true` flags a compound in thousands of patents (a generic fragment, not
IP-informative).

### `GET /api/patent-text-support`

For a compound, rank its full-text patents' human targets and report where each
chemistry-predicted target lands — the **weak** consistency check. Returns per-prediction
`badges` (`confirms` / `suggests_other` / `weak`) plus per-patent detail. No model load at
request time (precomputed target embeddings). Noise compounds return empty.

| Param | Default | Notes |
|---|---|---|
| `compound_id` | **required** | SureChEMBL int id |

```bash
curl "http://localhost:8011/api/patent-text-support?compound_id=964"
```
```json
{ "compound_id": 964, "n_full_text_patents": 3,
  "patents": [ {"number":"...","text_top":[...],"predicted_ranks":{"P00533":4}} ],
  "badges": { "P00533": {"verdict":"confirms","rank":4,"patent":"..."} } }
```

### `GET /api/similar-compounds`

Chemically nearest patent compounds (vector search on the compound's own Morgan
fingerprint). Each neighbour: id, name, smiles, cosine, its top predicted target, and the
predicted-target genes **shared** with the query.

| Param | Default | Notes |
|---|---|---|
| `compound_id` | **required** | SureChEMBL int id |
| `limit` | 10 | neighbours returned |

```bash
curl "http://localhost:8011/api/similar-compounds?compound_id=964&limit=5"
```
```json
{ "compound_id": 964, "neighbours": [ {"id":8383,"name":null,"cosine":0.91,
    "top_gene":"EGFR","shared_targets":["EGFR"]} ] }
```

### `GET /api/depict`

Render a SMILES to an SVG (RDKit). `404` if the SMILES does not parse.

| Param | Default |
|---|---|
| `smiles` | **required** |
| `w` | 240 |
| `h` | 150 |

```bash
curl "http://localhost:8011/api/depict?smiles=c1ccccc1" -o mol.svg
```

---

## MCP server

The same engine, exposed as **MCP tools** for agents (Claude and any MCP-compatible
client). Identical answers to REST — it calls the same primitives.

**Launch:**

```bash
python -m mcp_srv --mode stdio    # local MCP for a Claude CLI (default)
python -m mcp_srv --mode http     # MCP-over-HTTP at POST /mcp on :8011
```

MCP config for an HTTP client:

```json
{ "mcpServers": { "bioyoda": { "url": "http://localhost:8011/mcp" } } }
```

**Tools** (three — the core primitives; the REST extras like depict / similar-compounds /
patent-text-support are web-facing only):

| Tool | Maps to | Key args |
|---|---|---|
| `bioyoda_query` | `POST /api/query` | `collection` (req), `text`/`smiles`/`accession`, `filter`, `limit`, `offset` |
| `bioyoda_predict` | `GET /api/predict` | `smiles` (req), `top`, `human_only` |
| `bioyoda_provenance` | `GET /api/provenance` | `ids` (req, array), `max_per` |

Note: the MCP `bioyoda_query` does not pass `with_names` / `with_known` (those are
REST/web-only enrichments). Results are returned as a JSON string, truncated past ~50 KB.

```text
bioyoda_predict(smiles="CC(=O)Oc1ccccc1C(=O)O", top=10)
bioyoda_query(collection="patent_compounds", filter={"targets":"P00533","novel":true})
bioyoda_provenance(ids=["SCHEMBL964"], max_per=5)
```

---

## See also

- [../README.md](../README.md) — the engine repo
- [how-it-works.md](how-it-works.md) — the prediction method + the confidence and support signals
- [getting-started.md](getting-started.md) — browse, query, drive from an agent, rebuild
- [cli.md](cli.md) — `bioyoda.sh` build + serve commands
