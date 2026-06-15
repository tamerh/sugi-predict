# BioYoda → BioBTree delegation

**Architecture (locked 2026-06-15):** BioBTree = deterministic ground truth + features
(70+ DBs, ontologies *with synonyms*, id-mapping, Monarch incoming). BioYoda = the
predictive vector side. **BioYoda delegates EVERY symbolic/grounding/lookup to BioBTree's
REST API — never reimplements it.** Win-win: bioyoda requests datasets/features from
biobtree as needed; each system stays focused.

## The API (delegated via `scripts/integrations/biobtree_client.py`)
BioBTree prod web, direct Go transport, `mode=lite`. Base: `BIOYODA_BIOBTREE` (default
`http://127.0.0.1:9291`). Mirrors sugi-atlas's client. Three primitives:
- `search(term, source=None)` → `/ws/` → `{schema:"id|dataset|name|xref_count", data:[...]}`.
  Ground a free-text name → canonical id(s). `source="mondo"` scopes; `source=None` returns
  ALL matching ontologies (MONDO+MESH+EFO+HPO+Orphanet+Cellosaurus) — synonym-aware.
- `entry(id, source)` → `/ws/entry/` → full entry + xref table.
- `bmap(ids, chain)` → `/ws/map/` → id-mapping via the chain DSL, e.g. `>>ensembl>>uniprot`,
  `>>ensembl>>uniprot>>go[type=="biological_process"]`. Returns `{mappings:[{input,source,targets}]}`.

Verified live: `search("Hepatocellular Carcinoma", s=mondo)` → `MONDO:0007256`;
`map("TP53", ">>ensembl>>uniprot")` → UniProt accessions. Grounding coverage on real CT
conditions: **60% of trials** (beats the local-sqlite grounder's 51%).

## What BioYoda delegates (the menu — biobtree has 80+ capability categories)
1. **Grounding-as-payload** — name → canonical CURIE (disease→MONDO, gene→uniprot,
   compound→CHEBI/ChEMBL, …). Attach to Qdrant payload so predictive hits are traceable.
   `bb.ground(name, source)`. Replaces the local MONDO sqlite grounder.
2. **Cross-modal join (the hero capability)** — use `bmap` chains to link ids across
   modalities, then query BioYoda's other vector collections:
   - compound → target UniProt (`>>chembl>>uniprot` / InChIKey path) → query esm2 (similar proteins).
   - gene/protein → uniprot → esm2; → associated diseases/drugs → query pubmed/trials.
   - disease → genes/drugs/pathways → query literature/patents.
3. **Synonyms / xrefs / entry details** — payload enrichment, query expansion.
4. **Ontology hierarchy** — expand a disease query to its subtypes before vector search.
5. **Existing loop:** biobtree already serves `protein_embedding_similarity` (bioyoda's esm2
   export) + `diamond_similarity` — the file-based exchange that predates this REST delegation.

## Rule of thumb
If it's a FACT / ID / synonym / cross-reference / hierarchy → **biobtree**. If it's a
SIMILARITY / semantic-prediction → **bioyoda**. The cross-modal join is bioyoda calling
biobtree for the id-links between its own predictive lookups.
