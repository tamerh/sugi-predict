# BioYoda Search API

**Status**: MVP Implementation Complete ✅
**Version**: 0.1.0
**Last Updated**: October 2025

## Overview

RESTful API for semantic search across biomedical literature and clinical trials.

### Features

- ✅ **Single collection search** - Search PubMed or Clinical Trials independently
- ✅ **Multi-collection search** - Search across both collections simultaneously
- ✅ **Result merging & ranking** - Intelligent cross-collection result ranking
- ✅ **Metadata filtering** - Filter results by specific fields
- ✅ **Fast semantic search** - Sub-second query response times
- ✅ **Interactive documentation** - Swagger UI and ReDoc
- 🚧 **RAG Integration** - Coming in Phase 2 (see Roadmap)

### Current Collections

1. **PubMed Abstracts** (~30M papers)
   - Biomedical research literature
   - S-BioBERT embeddings

2. **Clinical Trials** (~500K trials)
   - ClinicalTrials.gov data
   - Chunked by section (title, summary, eligibility, etc.)

## Quick Start

### Prerequisites

1. **Qdrant server must be running** with data inserted:
   ```bash
   ./bioyoda.sh qdrant start
   ./bioyoda.sh qdrant status  # Verify data is loaded
   ```

2. **API dependencies are included in conda environment**:
   ```bash
   # Dependencies already included in config/tamer.yml
   # Just activate the environment:
   conda activate bioyoda

   # Or recreate environment if needed:
   conda env update -f config/tamer.yml
   ```

   **Note**: API dependencies are managed through the conda environment files.

### Start API Server

**Production mode** (foreground):
```bash
./bioyoda.sh api start
```

**Background mode**:
```bash
./bioyoda.sh api start --bg
```

**Test mode** (uses test config, auto-backgrounds):
```bash
./bioyoda.sh api start --test
```

API will be available at: **http://localhost:8000**

### Quick Test

```bash
# Run comprehensive API tests
./run_tests.sh api
```

This will:
- Start the API server in test mode if not running
- Run all 6 endpoint tests
- Stop the server when done

### CLI Search Tool (Easy Way to Search!)

Use the included CLI tool to search from command line:

```bash
# Simple search (from project root)
./bioyoda.sh search "CRISPR gene editing"

# Via api subcommand
./bioyoda.sh api search "cancer treatment" --collection pubmed_abstracts

# Interactive mode (recommended!)
./bioyoda.sh search  # No query = interactive

# Or call directly
python modules/api/scripts/bioyoda_search.py "Alzheimer disease" --limit 5
```

**Interactive mode example:**
```
bioyoda> search CRISPR gene editing
bioyoda> pubmed Alzheimer disease
bioyoda> trials cancer immunotherapy
bioyoda> collections
bioyoda> quit
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs (interactive testing)
- **ReDoc**: http://localhost:8000/redoc (clean documentation)
- **OpenAPI spec**: http://localhost:8000/openapi.json

## API Endpoints

### GET /

Root endpoint with API information.

### GET /health

Health check - returns API status and component health.

**Response**:
```json
{
  "status": "healthy",
  "qdrant_connected": true,
  "model_loaded": true,
  "collections_available": ["pubmed_abstracts", "clinical_trials"],
  "version": "0.1.0"
}
```

### GET /collections

List available collections with statistics.

**Response**:
```json
[
  {
    "name": "pubmed_abstracts",
    "description": "PubMed abstracts - 30M+ biomedical research papers",
    "display_name": "PubMed",
    "points_count": 30000000,
    "status": "green",
    "vector_size": 768
  }
]
```

### POST /search

Semantic search endpoint.

**Request**:
```json
{
  "query": "CRISPR gene editing",
  "collections": ["pubmed_abstracts", "clinical_trials"],
  "limit": 10,
  "filters": null,
  "merge_results": true
}
```

**Response**:
```json
{
  "query": "CRISPR gene editing",
  "total_results": 20,
  "results_per_collection": {
    "pubmed_abstracts": 10,
    "clinical_trials": 10
  },
  "results": [
    {
      "id": "12345",
      "score": 0.92,
      "collection": "pubmed_abstracts",
      "payload": {
        "pmid": "12345",
        "chunk_text": "Title: CRISPR...\nAbstract: ..."
      }
    }
  ],
  "search_time_ms": 234.56
}
```

## Usage Examples

### Python

```python
import requests

# Simple search
response = requests.post("http://localhost:8000/search", json={
    "query": "Alzheimer disease treatment",
    "collections": ["pubmed_abstracts"],
    "limit": 10
})

results = response.json()
print(f"Found {results['total_results']} results")

for result in results['results']:
    print(f"Score: {result['score']:.3f}")
    print(f"PMID: {result['payload']['pmid']}")
    print(f"Text: {result['payload']['chunk_text'][:200]}...")
    print()
```

### cURL

```bash
# Search PubMed
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cancer immunotherapy",
    "collections": ["pubmed_abstracts"],
    "limit": 5
  }'

# Multi-collection search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "COVID-19 vaccine efficacy",
    "collections": ["pubmed_abstracts", "clinical_trials"],
    "limit": 3
  }'
```

### JavaScript/TypeScript

```javascript
async function search(query, collections = ['pubmed_abstracts'], limit = 10) {
  const response = await fetch('http://localhost:8000/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, collections, limit })
  });

  return await response.json();
}

// Usage
const results = await search('gene therapy', ['pubmed_abstracts'], 5);
console.log(`Found ${results.total_results} results`);
```

## Configuration

Edit `config/api_config.yaml` (in project root) to customize:

```yaml
api:
  host: "0.0.0.0"
  port: 8000
  title: "BioYoda Search API"
  version: "0.1.0"

qdrant:
  url: "http://localhost:6333"
  timeout: 30

search:
  model_name: "pritamdeka/S-BioBERT-snli-multinli-stsb"  # Change model
  default_limit: 10                                       # Default result count
  max_limit: 100                                          # Maximum allowed

collections:
  pubmed_abstracts:
    name: "pubmed_abstracts"
    description: "PubMed abstracts - 30M+ biomedical research papers"
  clinical_trials:
    name: "clinical_trials"
    description: "ClinicalTrials.gov - 500K+ clinical trial records"
```

**Note**: Configuration file is located at `config/api_config.yaml` (not in modules/api/).
This allows consistent config management with the rest of the BioYoda system.

## Development

### Running with Auto-Reload

```bash
./bioyoda.sh api start --reload
```

Changes to Python files will automatically restart the server.

### Running Tests

```bash
# From project root - handles server lifecycle automatically
./run_tests.sh api
```

This will:
1. Check if API server is running
2. Start it in test mode if needed (using `config/test_config.yaml`)
3. Run all API endpoint tests
4. Stop the server if it started it

**Test coverage**:
- Root endpoint (GET /)
- Health check (GET /health)
- List collections (GET /collections)
- Search PubMed (POST /search)
- Multi-collection search (POST /search)
- Error handling (invalid collection)

### Adding a New Collection

1. Process and insert data (using existing pipeline)
2. Add collection to `config/api_config.yaml`
3. Restart API server

That's it! The API automatically discovers and uses new collections.

## Architecture

```
┌─────────────────┐
│   API Client    │  (Web UI, Python, cURL, etc.)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  FastAPI App    │  (modules/api/scripts/main.py)
│  - Endpoints    │
│  - Validation   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Search Engine  │  (modules/api/scripts/search.py)
│  - Query encode │
│  - Multi-search │
│  - Result merge │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Qdrant Client  │  (qdrant-client)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Qdrant Server  │  (Vector Database)
│  - Collections  │
│  - Vectors      │
└─────────────────┘
```

### Module Structure

```
modules/api/
├── README.md                      # This file
├── IMPLEMENTATION_STATUS.md       # Development status
└── scripts/
    ├── main.py                    # FastAPI application
    ├── config.py                  # Config loader
    ├── models.py                  # Pydantic models
    ├── search.py                  # Search engine
    └── bioyoda_search.py         # CLI search tool

config/
└── api_config.yaml               # API configuration (root level)
```

## Performance

### Typical Latencies

- **Health check**: <10ms
- **Collection list**: <50ms
- **Single query**: 200-500ms
  - Encoding: 50-100ms
  - Qdrant search: 100-300ms
  - Result formatting: <50ms

### Optimization Tips

1. **Use local storage**: Qdrant on SSD/NVMe (not NFS)
2. **Increase RAM**: Cache more vectors in memory
3. **Batch queries**: Group related queries together
4. **Adjust limits**: Request only what you need

## Troubleshooting

### API won't start

**Error**: "Qdrant server is not running"
```bash
# Start Qdrant first
./bioyoda.sh qdrant start
./bioyoda.sh qdrant status
```

**Error**: "Model not found"
```bash
# Model will download on first run (~300MB)
# Ensure internet connection available
```

**Error**: "Port 8000 already in use"
```bash
# Stop existing server first
./bioyoda.sh api stop

# Or use different port
./bioyoda.sh api start --port 8001
```

### Search returns no results

1. Check collections have data:
   ```bash
   curl http://localhost:8000/collections
   ```

2. Verify Qdrant connection:
   ```bash
   curl http://localhost:6333
   ```

3. Check collection names are correct:
   ```bash
   curl http://localhost:6333/collections
   ```

### Slow searches

1. **Check Qdrant storage**:
   - Should be on local fast disk (SSD/NVMe)
   - Not on NFS or network storage

2. **Monitor memory**:
   ```bash
   # Qdrant should have enough RAM for hot data
   free -h
   ```

3. **Review collection size**:
   - Very large collections may need optimization
   - Consider adding HNSW index parameters

## Roadmap

### Phase 1: Core Search ✅ (Current)
- ✅ Basic search implementation
- ✅ Multi-collection support
- ✅ Result ranking
- ✅ Metadata filtering
- ✅ API documentation

### Phase 2: RAG Integration (Next - 2-3 weeks)
- [ ] `/ask` endpoint for Q&A
- [ ] LLM integration (OpenAI/Anthropic/Local)
- [ ] Prompt engineering framework
- [ ] Citation generation
- [ ] Answer validation
- [ ] Context window management

See main README.md for full RAG implementation plan.

### Phase 3: Advanced Search (4-6 weeks)
- [ ] Query expansion (synonyms)
- [ ] Biomedical term normalization
- [ ] Advanced filtering (date ranges)
- [ ] Result highlighting
- [ ] Search analytics

### Phase 4: Production (2-3 months)
- [ ] Authentication & API keys
- [ ] Rate limiting
- [ ] Caching layer
- [ ] Monitoring & metrics
- [ ] Web UI frontend

## Contributing

This is an active development project. See `vibe/IMPROVEMENTS.md` for planned improvements.

## License

Apache 2.0

---

**Questions?** Check the main README or create an issue.
