# BioYoda Multi-Agent System

Intelligent RAG system combining deterministic mappings (BioBTree) with vector similarity search (Qdrant) for bioinformatics analysis.

## Architecture

**Reasoning Engine** routes queries to specialized agents, each with domain-specific prompts, chain templates, and tools.

| Component | Location | Purpose |
|-----------|----------|---------|
| Agents | `agents/` | Specialized query handlers (ID mapping, drug discovery) |
| Tools | `tools/` | BioBTree queries, disease-drug discovery, similarity search |
| Integrations | `integrations/` | BioBTree gRPC, Qdrant vector DB clients |
| LLM | `llm/` | Multi-provider framework (OpenRouter, Gemini, Anthropic) |
| Tests | `tests/` | CLI tools and automated test runner |

## Available Tools

| Tool | Data Source | Records | Use Case |
|------|-------------|---------|----------|
| `biobtree_query` | BioBTree gRPC | 40+ databases | ID mapping, cross-references |
| `biobtree_search` | BioBTree gRPC | - | Keyword search across datasets |
| `disease_drug_discovery` | BioBTree | - | Multi-path disease→drug queries |
| `protein_similarity_search` | Qdrant ESM-2 | 573K proteins | Find similar proteins by embedding |
| `compound_similarity_search` | Qdrant Morgan FP | 30.8M compounds | Find similar compounds by fingerprint |

## Key Learnings

### BioBTree Query Patterns

**Lite vs Full mode**: Always use `mode="lite"` for ID-only results (fast, compact). Use `mode="full"` only when you need attributes like SMILES, phase, or names.

**Pagination is critical**: BioBTree returns paginated results. Without fetching all pages, you miss data (e.g., BEVACIZUMAB for glioblastoma was on page 2). Use `map_query_all_pages()` for complete results.

**Filter syntax**: `dataset[dataset.attribute==value]` - note the dataset prefix is required inside brackets.

**Chain direction matters**: `GENE >> ensembl >> uniprot` works, but reverse queries need the protein ID directly.

### Drug Discovery (Multi-Path Architecture)

Single-path queries miss evidence. The drug discovery tool runs 5+ parallel paths:
- **PATH 1**: Direct disease→drug indications via EFO ontology
- **PATH 2**: GWAS genetic associations → genes → drugs
- **PATH 3**: ClinVar variants via MONDO ontology → genes → drugs
- **PATH 6**: PubChem FDA-approved drugs
- **PATH 7**: Reactome pathway context

**Ontology choice matters**: EFO works for GWAS and ChEMBL. ClinVar requires MONDO. Some paths (efo→reactome, efo→uniprot) don't exist yet.

**Phase filtering**: Filter by indication-specific phase, not drug-level. A drug may be Phase 4 overall but Phase 2 for a specific disease.

### Similarity Search (Qdrant Integration)

**Protein similarity** uses ESM-2 embeddings (1280-dim). Query by UniProt ID or gene name (resolved via BioBTree).

**Compound similarity** uses Morgan fingerprints (2048-bit, radius=2). Query by SMILES, PubChem CID, ChEMBL ID, or compound name.

**ID resolution order**: Direct SMILES → PubChem CID → ChEMBL ID → Name search. ChEMBL lookup falls back to PubChem when SMILES is missing (e.g., CHEMBL25/aspirin).

**SureChEMBL lookup is slow**: 30M compound scan without payload index. Prefer PubChem CID or direct SMILES input.

### Data Nuances

**ChEMBL vs PubChem**: ChEMBL has disease-specific drug phases (clinical candidates). PubChem has FDA approval flag but no disease context.

**Missing SMILES in ChEMBL**: Some entries (like CHEMBL25/aspirin) lack SMILES in BioBTree despite schema support. Tool falls back to PubChem via altNames.

**PubChem lacks drug names**: Only IUPAC names in `title` field; `synonyms` field is empty. Cannot display "Gefitinib", only the chemical name.

**BioBTree patent_compound vs Qdrant**: Different ID schemes. BioBTree uses numeric IDs without SCHEMBL prefix and has no SMILES. Qdrant has SMILES but slow ID lookup.

### LLM Provider Experience

**Model reliability varies**: When LLM orchestrates multi-step queries, Llama skips queries, Gemini hallucinates data. Claude Haiku was most faithful but adds latency.

**Specialized tools > LLM orchestration**: For complex multi-path queries, hardcoded tool logic is faster and more reliable than LLM coordination.

**Temperature 0 for agents**: Deterministic responses prevent tool call variations.

## Configuration

Main config: `config/agent_system.yaml`

- **BioBTree**: `scc2:7777` (gRPC)
- **Qdrant**: `scc2:6333` (collections: esm2, patents_compounds)
- **LLM**: Configurable provider (default: OpenRouter with Claude Haiku for reliability)

## Maintenance

### Regenerating BioBTree Protobuf Files

When BioBTree adds new datasets or attributes (e.g., BindingDB, Antibody), the Python protobuf files need to be regenerated from the latest proto definitions.

```bash
# From bioyoda root:
python modules/agent_system/integrations/biobtree_pb/regenerate_protobuf.py
```

The script:
1. Reads proto files from `biobtreev2/src/pbuf/`
2. Generates Python protobuf files using `grpc_tools.protoc`
3. Fixes import statements for package usage
4. Clears `__pycache__` and verifies key message types

## Running Tests

From `modules/agent_system/` directory:
- `python -m tests.cli "query"` - Interactive with reasoning engine
- `python -m tests.cli --direct "query"` - Bypass agents, direct tool use
- `python -m tests.runner --quick` - Automated smoke tests

## Adding New Agents

Each agent is self-contained in `agents/<name>/`:
- `agent.py` - Implementation extending base Agent
- `prompt.txt` - System prompt (auto-loaded, cached)
- `chains.yaml` - BioBTree chain templates
- `examples.yaml` - Test queries and known issues

Register in `agents/factory.py` and update `agents/__init__.py`.

## Known Issues

Tracked in `data/issues/issues.log`. Current:
- Missing SMILES for some ChEMBL entries (CHEMBL25)
- No efo→reactome or efo→uniprot links in BioBTree
- PubChem synonyms/drug_names fields empty

## Roadmap

- Variant Analysis Agent (ClinVar/dbSNP focus)
- Antibody dataset integration (pending BioBTree efo→antibody link)
- Response token optimization (full pagination returns 2000+ results)
- Fine-tuning with collected training data (`data/fine_tuning/`)
