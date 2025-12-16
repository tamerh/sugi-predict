# BioYoda Agent System API (v1)

**Status**: Active Development
**Version**: 1.0.0
**Last Updated**: December 2024

## Overview

RESTful API for the BioYoda Multi-Agent System. Provides both a unified query endpoint (routed to specialized agents) and direct access endpoints for specific functionalities.

### Features

- **Unified Query Endpoint** - Natural language queries routed to appropriate agents
- **ID Mapping** - Convert between gene symbols, UniProt, Ensembl, HGNC
- **Drug Discovery** - Multi-path disease-to-drug queries (9 evidence paths)
- **Protein Similarity** - ESM-2 embedding search across 573K SwissProt proteins
- **Compound Similarity** - Morgan fingerprint search across 30.8M patent compounds
- **Interactive Documentation** - Swagger UI and ReDoc

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ /query  │ │/id-map  │ │ /drug   │ │/protein │ ...       │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │
└───────┼───────────┼───────────┼───────────┼─────────────────┘
        │           │           │           │
        ▼           ▼           ▼           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Agent System (modules/agent_system)        │
│  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ ReasoningEngine  │  │   Agents     │  │    Tools      │  │
│  │ (query routing)  │  │ - id_mapping │  │ - biobtree    │  │
│  │                  │  │ - drug_disc  │  │ - similarity  │  │
│  └──────────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
        │                       │                   │
        ▼                       ▼                   ▼
┌───────────────┐      ┌───────────────┐    ┌───────────────┐
│   BioBTree    │      │    Qdrant     │    │  LLM Provider │
│  (gRPC/REST)  │      │  (Vector DB)  │    │  (OpenRouter) │
└───────────────┘      └───────────────┘    └───────────────┘
```

## Quick Start

### Prerequisites

1. **Qdrant server running** (for similarity search):
   ```bash
   ./bioyoda.sh qdrant start
   ```

2. **BioBTree server running** (for ID mapping & drug discovery):
   ```bash
   # BioBTree should be running on scc2:9292 (REST) or scc2:7777 (gRPC)
   ```

3. **Conda environment activated**:
   ```bash
   conda activate bioyoda
   ```

### Start API Server

```bash
# Foreground (see logs directly)
./bioyoda.sh api start

# Background mode
./bioyoda.sh api start --bg

# With auto-reload for development
./bioyoda.sh api start --reload

# Custom port
./bioyoda.sh api start --port 8001
```

API will be available at: **http://localhost:8000**

### Quick Test

```bash
# Health check
curl http://localhost:8000/v1/health

# Simple query
curl -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the UniProt ID for TP53?"}'
```

## API Endpoints

### GET /v1/health

Health check - returns API status and component health.

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "biobtree_connected": true,
  "qdrant_connected": true,
  "llm_available": true,
  "agents_available": ["id_mapping", "drug_discovery"],
  "tools_available": ["biobtree_query", "biobtree_search", "disease_drug_discovery", "protein_similarity_search", "compound_similarity_search"]
}
```

### POST /v1/query

Unified query endpoint - routes to appropriate agent based on query intent.

**Request**:
```json
{
  "query": "What drugs target breast cancer?",
  "context": {}
}
```

**Response**:
```json
{
  "answer": "The key findings for drugs targeting breast cancer are...",
  "routing": {
    "agent_name": "drug_discovery",
    "confidence": 0.8,
    "reasoning": "High confidence match for drug_discovery"
  },
  "agent_result": {
    "status": "completed",
    "answer": "...",
    "reasoning": ["Action: disease_drug_discovery(...)", "Observation: ..."],
    "tool_calls": [...],
    "iterations": 2
  },
  "execution_time_ms": 8541.2
}
```

### POST /v1/id-mapping

Direct ID mapping between biological databases.

**Request**:
```json
{
  "ids": ["BRCA1", "TP53", "EGFR"],
  "to_type": "uniprot",
  "from_type": null
}
```

**Response**:
```json
{
  "results": [
    { "input_id": "BRCA1", "mapped_ids": ["P38398"], "success": true },
    { "input_id": "TP53", "mapped_ids": ["P04637"], "success": true },
    { "input_id": "EGFR", "mapped_ids": ["P00533"], "success": true }
  ],
  "total_input": 3,
  "total_mapped": 3,
  "total_failed": 0,
  "execution_time_ms": 23.1
}
```

**Supported mappings**:
- Gene symbol → UniProt (`to_type: "uniprot"`)
- Gene symbol → Ensembl (`to_type: "ensembl"`)
- UniProt → Gene symbol (`to_type: "gene_symbol"`)

### POST /v1/drug-discovery

Multi-path drug discovery for a disease.

**Request**:
```json
{
  "disease": "glioblastoma",
  "min_indication_phase": 3,
  "include_gwas": true,
  "include_clinvar": true,
  "include_similar_proteins": false
}
```

**Response** includes:
- `direct_indications` - Drugs with clinical trials for this disease
- `gwas_targets` - Drugs targeting GWAS-associated genes
- `clinvar_targets` - Drugs targeting ClinVar variant genes
- `pubchem_fda` - FDA-approved drugs for targets
- `reactome_pathways` - Disease-related biological pathways

### POST /v1/protein-similarity

Find similar proteins using ESM-2 embeddings.

**Request**:
```json
{
  "query": "P04637",
  "limit": 10,
  "min_score": 0.8
}
```

**Query formats**:
- UniProt ID: `"P04637"`
- Gene symbol: `"TP53"`
- Protein sequence: `"MEEPQSDPSVEPPLSQETFSDLWKLLPENNVLS..."`

**Response**:
```json
{
  "query": "P04637",
  "query_uniprot": "P04637",
  "results": [
    { "uniprot_id": "P56424", "protein_name": "Cellular tumor antigen p53", "score": 0.9998 },
    { "uniprot_id": "P61260", "protein_name": "Cellular tumor antigen p53", "score": 0.9998 }
  ],
  "total_results": 5,
  "collection": "swissprot_esm2",
  "execution_time_ms": 238.2
}
```

### POST /v1/compound-similarity

Find similar compounds using Morgan fingerprints.

**Request**:
```json
{
  "query": "CHEMBL25",
  "limit": 10,
  "min_score": 0.7
}
```

**Query formats**:
- ChEMBL ID: `"CHEMBL25"`
- SMILES: `"CC(=O)Oc1ccccc1C(=O)O"`
- PubChem CID: `"2244"`
- Compound name: `"aspirin"`

## Usage Examples

### Python

```python
import requests

BASE_URL = "http://localhost:8000/v1"

# Unified query
response = requests.post(f"{BASE_URL}/query", json={
    "query": "What is the UniProt ID for BRCA1?"
})
print(response.json()["answer"])

# ID mapping
response = requests.post(f"{BASE_URL}/id-mapping", json={
    "ids": ["TP53", "BRCA1"],
    "to_type": "uniprot"
})
for result in response.json()["results"]:
    print(f"{result['input_id']} -> {result['mapped_ids']}")

# Drug discovery
response = requests.post(f"{BASE_URL}/drug-discovery", json={
    "disease": "breast cancer"
})
data = response.json()
print(f"Found {data['summary']['total_drugs']} drugs")

# Protein similarity
response = requests.post(f"{BASE_URL}/protein-similarity", json={
    "query": "P04637",
    "limit": 5
})
for protein in response.json()["results"]:
    print(f"{protein['uniprot_id']}: {protein['score']:.4f}")
```

### cURL

```bash
# ID mapping
curl -X POST http://localhost:8000/v1/id-mapping \
  -H "Content-Type: application/json" \
  -d '{"ids": ["TP53", "BRCA1", "EGFR"], "to_type": "uniprot"}'

# Drug discovery
curl -X POST http://localhost:8000/v1/drug-discovery \
  -H "Content-Type: application/json" \
  -d '{"disease": "lung cancer"}'

# Protein similarity
curl -X POST http://localhost:8000/v1/protein-similarity \
  -H "Content-Type: application/json" \
  -d '{"query": "P04637", "limit": 5}'
```

### JavaScript/TypeScript

```typescript
const BASE_URL = 'http://localhost:8000/v1';

// Unified query
async function query(text: string) {
  const response = await fetch(`${BASE_URL}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: text })
  });
  return response.json();
}

// Usage
const result = await query('What drugs target glioblastoma?');
console.log(result.answer);
console.log(`Routed to: ${result.routing.agent_name}`);
```

## Configuration

Main config: `config/agent_system.yaml`

```yaml
integrations:
  biobtree:
    protocol: "rest"  # or "grpc"
    rest:
      host: "scc2"
      port: 9292
    grpc:
      host: "scc2"
      port: 7777

  qdrant:
    host: "scc2"
    port: 6333

llm:
  default_provider: openrouter
  providers:
    openrouter:
      model: "anthropic/claude-3-haiku"
      temperature: 0.0
```

## Module Structure

```
modules/api_v1/
├── README.md              # This file
├── __init__.py            # Version info
├── main.py                # FastAPI application & lifespan
├── dependencies.py        # Dependency injection (singletons)
├── routes/
│   ├── __init__.py
│   ├── health.py          # GET /v1/health
│   ├── query.py           # POST /v1/query (unified)
│   ├── id_mapping.py      # POST /v1/id-mapping
│   ├── drug_discovery.py  # POST /v1/drug-discovery
│   ├── protein_similarity.py   # POST /v1/protein-similarity
│   └── compound_similarity.py  # POST /v1/compound-similarity
├── schemas/
│   ├── __init__.py
│   ├── common.py          # HealthResponse, ErrorResponse
│   ├── query.py           # QueryRequest, QueryResponse
│   ├── id_mapping.py      # IDMappingRequest, IDMappingResponse
│   ├── drug_discovery.py  # DrugDiscoveryRequest, DrugDiscoveryResponse
│   └── similarity.py      # Protein/Compound similarity schemas
└── middleware/
    └── __init__.py        # Auth, rate limiting (TODO)
```

## Management Commands

```bash
# Start/stop/status
./bioyoda.sh api start              # Start v1 API (default)
./bioyoda.sh api start --bg         # Background mode
./bioyoda.sh api status             # Check status
./bioyoda.sh api stop               # Stop server

# Legacy API (for comparison)
./bioyoda.sh api start --legacy     # Start legacy search API
./bioyoda.sh api status --legacy    # Check legacy status
./bioyoda.sh api stop --legacy      # Stop legacy server

# Both can run simultaneously on different ports
./bioyoda.sh api start --bg --port 8000          # v1 on 8000
./bioyoda.sh api start --legacy --bg --port 8001 # legacy on 8001
```

## Performance

### Typical Latencies

| Endpoint | Latency | Notes |
|----------|---------|-------|
| Health check | <50ms | No external calls |
| ID mapping (3 IDs) | ~25ms | BioBTree queries |
| Protein similarity | ~250ms | Qdrant vector search |
| Drug discovery | 3-10s | Multi-path, many queries |
| Unified query (simple) | ~2.5s | Includes LLM routing |

### Optimization Tips

1. **Use direct endpoints** when you know the query type (skip LLM routing)
2. **Batch ID mappings** - single request for multiple IDs
3. **Limit similarity results** - request only what you need
4. **Use min_score filters** - reduce result processing

## Troubleshooting

### API won't start

**Error**: "Qdrant server is not running"
```bash
./bioyoda.sh qdrant start
```

**Error**: "Port 8000 already in use"
```bash
./bioyoda.sh api stop
# Or use different port
./bioyoda.sh api start --port 8001
```

### Queries failing

**Error**: "BioBTree query tool not available"
- Check BioBTree is running: `curl http://scc2:9292/`
- Check config points to correct host/port

**Error**: "Protein similarity search tool not available"
- Check Qdrant is running: `curl http://scc2:6333/healthz`
- Check ESM-2 collection exists

### Slow responses

1. **Drug discovery is slow by design** - runs 5+ parallel evidence paths
2. **Check network latency** to BioBTree/Qdrant servers
3. **LLM routing adds ~1-2s** - use direct endpoints for known query types

## Comparison: v1 API vs Legacy API

| Feature | v1 API (this) | Legacy API |
|---------|---------------|------------|
| Query routing | Intelligent (LLM) | None |
| Agents | id_mapping, drug_discovery | None |
| ID mapping | Yes (BioBTree) | No |
| Drug discovery | Yes (multi-path) | No |
| Protein similarity | Yes (ESM-2) | No |
| Compound similarity | Yes (Morgan FP) | No |
| PubMed search | Via agents | Yes (semantic) |
| Clinical trials search | Via agents | Yes (semantic) |
| RAG Q&A | Planned | Yes |

## Roadmap

### Current (v1.0)
- [x] Unified query endpoint with agent routing
- [x] ID mapping endpoint
- [x] Drug discovery endpoint
- [x] Protein similarity endpoint
- [x] Compound similarity endpoint
- [x] Health check with component status

### Next (v1.1)
- [ ] Response formatting (content blocks)
- [ ] Streaming for long queries (SSE)
- [ ] Authentication middleware
- [ ] Rate limiting

### Future
- [ ] Variant Analysis Agent
- [ ] Literature Search Agent (migrate from legacy)
- [ ] WebSocket support for real-time updates
- [ ] Result caching (Redis)

## Related Documentation

- [Agent System README](../agent_system/README.md) - Core agent architecture
- [Legacy API README](../api/README.md) - Original search API
- [BioBTree Integration](../agent_system/integrations/) - Data source details

---

**Questions?** Check the main project README or create an issue.
