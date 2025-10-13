# Biobtree v2 Integration Plan

## Project Understanding

### BioYoda (Main RAG System)
- **Purpose**: AI-powered biomedical literature search with semantic search + RAG Q&A
- **Data**: ~30M PubMed abstracts + ~500K clinical trials
- **Tech Stack**: Python, Snakemake, S-BioBERT embeddings, Qdrant vector DB, FastAPI
- **Capabilities**: Semantic search, document aggregation, LLM-powered Q&A with citations

### Biobtree v2 (Identifier Mapping Service)
- **Purpose**: Bioinformatics identifier mapping and cross-referencing tool
- **Datasets**: Ensembl, Uniprot, ChEMBL, HMDB, Taxonomy, GO, EFO, HGNC, ECO, etc.
- **Tech Stack**: Go, LMDB (B+ tree database), REST/gRPC APIs, Vue.js UI
- **Capabilities**: Chain queries, identifier mapping, keyword search across datasets
- **Publication**: F1000Research 2020 (peer-reviewed, solid project)
- **Location**: `external/biobtreev2/` (git submodule)

---

## 🎯 Integration Vision: "Identifier-Aware RAG"

**Goal**: Transform BioYoda from a text-only RAG system into an **identifier-aware knowledge system** that can:
1. Extract biomedical identifiers from search results (genes, proteins, drugs, diseases)
2. Enrich responses with structured knowledge from biobtree
3. Enable cross-database queries and mappings
4. Provide deep contextual answers with linked data

---

## 📋 Integration Plan

### Phase 1: Foundation (Weeks 1-2)
**Goal**: Set up biobtree as a standalone service alongside BioYoda

#### 1.1 Biobtree Setup Module
```
modules/biobtree/
├── README.md                           # Integration documentation
├── Snakefile                           # Build workflows
└── scripts/
    ├── build_biobtree.sh              # Build Go binary
    ├── setup_datasets.sh              # Download & build datasets
    ├── start_service.sh               # Start biobtree web service
    ├── stop_service.sh                # Stop service
    └── check_status.sh                # Health check
```

**Tasks**:
- [x] Add biobtree as git submodule (✅ already done)
- [ ] Create build wrapper scripts
- [ ] Select initial dataset configuration (recommendation below)
- [ ] Build biobtree binary from Go source
- [ ] Configure dataset selection for biomedical focus
- [ ] Build initial LMDB database
- [ ] Start biobtree service (port 8888 by default)
- [ ] Test REST API endpoints

**Recommended Initial Datasets**:
```bash
# Focus on biomedical core - manageable size, high impact
biobtree -d "uniprot,hgnc,taxonomy,go,efo,interpro,chembl_molecule,chembl_target" build
```

**Configuration Updates**:
```yaml
# config/config.yaml - Add biobtree section
biobtree:
  enabled: true
  service_url: "http://localhost:8888"
  timeout: 30
  datasets: ["uniprot", "hgnc", "taxonomy", "go", "efo", "interpro", "chembl_molecule", "chembl_target"]
  build:
    out_dir: "external/biobtreev2/out"
    memory_mb: 32768
    runtime_hours: 24
```

---

### Phase 2: Identifier Extraction (Weeks 3-4)
**Goal**: Detect and extract biomedical identifiers from text

#### 2.1 Identifier Extraction Module
```python
# modules/api/scripts/identifier_extractor.py

class IdentifierExtractor:
    """Extract biomedical identifiers from text"""

    def __init__(self, config):
        self.patterns = {
            'gene_symbol': r'\b[A-Z][A-Z0-9]{1,10}\b',  # e.g., TP53, BRCA1
            'uniprot_id': r'\b[OPQ][0-9][A-Z0-9]{3}[0-9]\b',  # e.g., P12345
            'pmid': r'\bPMID:?\s*(\d{7,8})\b',
            'nct_id': r'\bNCT\d{8}\b',
            'ensembl_gene': r'\bENSG\d{11}\b',
            'go_term': r'\bGO:\d{7}\b',
            'chembl_id': r'\bCHEMBL\d+\b',
            'disease': r'\b[A-Z][a-z]+\s+(disease|syndrome|disorder)\b'
        }
        self.biobtree_client = BiobtreeClient(config)

    def extract_from_text(self, text):
        """Extract all identifiers from text"""
        identifiers = {}
        for id_type, pattern in self.patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                identifiers[id_type] = list(set(matches))
        return identifiers

    def extract_from_search_results(self, results):
        """Extract identifiers from search result payloads"""
        all_ids = {}
        for result in results:
            text = result['payload'].get('chunk_text', '')
            ids = self.extract_from_text(text)
            # Merge with all_ids
            for id_type, id_list in ids.items():
                if id_type not in all_ids:
                    all_ids[id_type] = []
                all_ids[id_type].extend(id_list)

        # Deduplicate
        for id_type in all_ids:
            all_ids[id_type] = list(set(all_ids[id_type]))

        return all_ids
```

#### 2.2 Biobtree Client
```python
# modules/api/scripts/biobtree_client.py

class BiobtreeClient:
    """Client for biobtree REST API"""

    def __init__(self, config):
        self.base_url = config.get('biobtree', {}).get('service_url', 'http://localhost:8888')
        self.timeout = config.get('biobtree', {}).get('timeout', 30)

    def search(self, identifier, dataset=None):
        """Search for an identifier"""
        params = {'i': identifier}
        if dataset:
            params['s'] = dataset
        response = requests.get(f"{self.base_url}/ws/", params=params, timeout=self.timeout)
        return response.json()

    def map(self, identifier, target_datasets, source_dataset=None):
        """Map identifier to target datasets"""
        params = {
            'i': identifier,
            'm': ','.join(target_datasets)
        }
        if source_dataset:
            params['s'] = source_dataset
        response = requests.get(f"{self.base_url}/ws/map/", params=params, timeout=self.timeout)
        return response.json()

    def get_entry(self, identifier, dataset):
        """Get full entry for identifier"""
        params = {'i': identifier, 's': dataset}
        response = requests.get(f"{self.base_url}/ws/entry/", params=params, timeout=self.timeout)
        return response.json()

    def bulk_map(self, identifiers, target_datasets):
        """Map multiple identifiers efficiently"""
        results = {}
        for identifier in identifiers:
            try:
                results[identifier] = self.map(identifier, target_datasets)
            except Exception as e:
                results[identifier] = {'error': str(e)}
        return results
```

**Tasks**:
- [ ] Implement regex-based identifier extraction
- [ ] Add NER-based extraction (optional: BioBERT-NER for genes/proteins/diseases)
- [ ] Create biobtree REST client
- [ ] Add caching layer for biobtree queries
- [ ] Write unit tests for extraction

---

### Phase 3: API Enhancement (Weeks 5-6)
**Goal**: Extend search and RAG APIs with identifier enrichment

#### 3.1 Enhanced Search Endpoint
```python
# POST /search/enriched

@app.post("/search/enriched")
async def search_with_identifiers(request: EnrichedSearchRequest):
    """
    Search with automatic identifier extraction and mapping

    Response includes:
    1. Standard search results
    2. Extracted identifiers
    3. Biobtree mappings for each identifier
    """
    # Standard search
    results = await search_engine.search(
        query=request.query,
        collections=request.collections,
        limit=request.limit
    )

    # Extract identifiers
    extractor = IdentifierExtractor(config)
    identifiers = extractor.extract_from_search_results(results['results'])

    # Enrich with biobtree
    enriched_ids = {}
    if request.enrich_identifiers:
        for id_type, id_list in identifiers.items():
            enriched_ids[id_type] = {}
            for identifier in id_list[:request.max_ids_per_type]:  # Limit to avoid overload
                try:
                    mapping = biobtree_client.map(
                        identifier,
                        target_datasets=request.target_datasets
                    )
                    enriched_ids[id_type][identifier] = mapping
                except Exception as e:
                    enriched_ids[id_type][identifier] = {'error': str(e)}

    return {
        "search_results": results,
        "identifiers": identifiers,
        "enriched_identifiers": enriched_ids
    }
```

#### 3.2 Enhanced RAG Endpoint
```python
# POST /ask/enriched

@app.post("/ask/enriched")
async def ask_with_context(request: EnrichedAskRequest):
    """
    RAG Q&A with biobtree context enrichment

    Workflow:
    1. Semantic search for relevant documents
    2. Extract identifiers from results
    3. Query biobtree for mappings
    4. Include biobtree context in LLM prompt
    5. Generate answer with cross-references
    """
    # Standard RAG
    search_results = await search_engine.search(...)

    # Extract identifiers
    identifiers = extractor.extract_from_search_results(search_results)

    # Get biobtree context
    biobtree_context = {}
    for id_type, id_list in identifiers.items():
        for identifier in id_list[:5]:  # Top 5 per type
            biobtree_context[identifier] = biobtree_client.get_entry(...)

    # Enhanced prompt
    prompt = f"""
    Answer the question using the provided context and cross-referenced data.

    Question: {request.question}

    Literature Context:
    {format_search_results(search_results)}

    Biological Context (from biobtree):
    {format_biobtree_context(biobtree_context)}

    Provide a comprehensive answer with:
    1. Direct answer to the question
    2. Supporting evidence from literature
    3. Related biological entities and their relationships
    """

    # Generate answer
    answer = await llm.generate(prompt)

    return {
        "question": request.question,
        "answer": answer,
        "sources": search_results,
        "identifiers": identifiers,
        "biobtree_context": biobtree_context
    }
```

#### 3.3 New Identifier Mapping Endpoint
```python
# POST /identifiers/map

@app.post("/identifiers/map")
async def map_identifiers(request: IdentifierMappingRequest):
    """
    Batch identifier mapping endpoint

    Example: Map gene symbols to Uniprot IDs, GO terms, and pathways
    """
    results = biobtree_client.bulk_map(
        identifiers=request.identifiers,
        target_datasets=request.target_datasets
    )
    return results
```

**Tasks**:
- [ ] Implement `/search/enriched` endpoint
- [ ] Implement `/ask/enriched` endpoint
- [ ] Implement `/identifiers/map` endpoint
- [ ] Add request/response models (Pydantic)
- [ ] Update API documentation (Swagger)
- [ ] Add caching for biobtree queries (Redis optional)

---

### Phase 4: Use Case Implementation (Weeks 7-9)
**Goal**: Implement specific high-value use cases

#### 4.1 Use Case: Gene-Centric Search
```python
# Example: Search for "BRCA1 mutations" and enrich with:
# - Protein structure (Uniprot)
# - Pathways (GO terms)
# - Drug targets (ChEMBL)
# - Disease associations

query = "BRCA1 breast cancer mutations"
results = bioyoda.search_enriched(
    query=query,
    collections=['pubmed_abstracts'],
    enrich_identifiers=True,
    target_datasets=['uniprot', 'go', 'chembl_molecule']
)

# Response includes:
# - PubMed papers about BRCA1
# - BRCA1 gene info from HGNC
# - Protein P38398 from Uniprot
# - GO terms for DNA repair pathways
# - ChEMBL compounds targeting BRCA1
```

#### 4.2 Use Case: Drug Discovery RAG
```python
# Question: "What are FDA-approved drugs targeting EGFR?"

response = bioyoda.ask_enriched(
    question="What are FDA-approved drugs targeting EGFR?",
    collections=['pubmed_abstracts', 'clinical_trials'],
    target_datasets=['chembl_molecule', 'chembl_target']
)

# LLM receives:
# - PubMed papers on EGFR inhibitors
# - Clinical trials for EGFR drugs
# - ChEMBL target info for EGFR
# - ChEMBL molecules mapped to EGFR
# - Drug-target binding data

# Answer includes:
# - List of FDA-approved drugs (gefitinib, erlotinib, osimertinib)
# - Mechanism of action
# - Clinical evidence from trials
# - ChEMBL IDs for each drug
```

#### 4.3 Use Case: Cross-Species Analysis
```python
# Question: "What are the mouse orthologs of human TP53?"

response = bioyoda.ask_enriched(
    question="What are the mouse orthologs of human TP53 and their functions?",
    collections=['pubmed_abstracts'],
    target_datasets=['ensembl', 'go', 'taxonomy']
)

# Biobtree provides:
# - Human TP53: ENSG00000141510
# - Mouse ortholog: Trp53 (ENSMUSG00000059552)
# - Taxonomy mapping (human: 9606, mouse: 10090)
# - GO terms for p53 pathway
```

**Tasks**:
- [ ] Implement gene-centric search use case
- [ ] Implement drug discovery use case
- [ ] Implement cross-species analysis use case
- [ ] Create example notebooks (Jupyter)
- [ ] Add CLI commands for common workflows

---

### Phase 5: Production Readiness (Weeks 10-12)
**Goal**: Optimize, monitor, and deploy

#### 5.1 Performance Optimization
- [ ] Cache biobtree queries (Redis or in-memory)
- [ ] Batch biobtree requests where possible
- [ ] Pre-compute common gene/protein mappings
- [ ] Add request rate limiting
- [ ] Profile and optimize slow paths

#### 5.2 Monitoring & Logging
- [ ] Track identifier extraction accuracy
- [ ] Monitor biobtree service health
- [ ] Log API usage patterns
- [ ] Alert on biobtree service failures

#### 5.3 Documentation
- [ ] Integration architecture diagram
- [ ] API usage examples
- [ ] Jupyter notebook tutorials
- [ ] Deployment guide (HPC cluster)

#### 5.4 Testing
- [ ] Unit tests for all components
- [ ] Integration tests for enriched APIs
- [ ] End-to-end use case tests
- [ ] Load testing

---

## 🏗️ Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         BioYoda RAG System                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────┐         ┌─────────────────┐                   │
│  │  Search Query   │         │   RAG Question  │                   │
│  └────────┬────────┘         └────────┬────────┘                   │
│           │                            │                             │
│           ↓                            ↓                             │
│  ┌───────────────────────────────────────────────┐                 │
│  │     Enhanced Search/RAG Engine                │                 │
│  │  - Semantic search (S-BioBERT + Qdrant)       │                 │
│  │  - Identifier extraction (regex + NER)        │                 │
│  │  - Context enrichment                         │                 │
│  └────────┬──────────────────────────┬───────────┘                 │
│           │                           │                             │
│           ↓                           ↓                             │
│  ┌──────────────────┐       ┌────────────────────┐                │
│  │  Qdrant Vector   │       │  Biobtree Client   │                │
│  │  Database        │       │  (REST/gRPC)       │                │
│  │  - PubMed        │       └─────────┬──────────┘                │
│  │  - Trials        │                 │                            │
│  └──────────────────┘                 │                            │
│                                        ↓                            │
└────────────────────────────────────────┼────────────────────────────┘
                                         │
                     ┌───────────────────┼───────────────────┐
                     │   Biobtree v2 Service (Port 8888)     │
                     ├───────────────────────────────────────┤
                     │  LMDB Database (B+ tree)              │
                     │  - Uniprot      - HGNC                │
                     │  - ChEMBL       - GO                  │
                     │  - Ensembl      - Taxonomy            │
                     │  - InterPro     - EFO                 │
                     └───────────────────────────────────────┘
```

---

## 📊 Implementation Priority Matrix

| Use Case | Impact | Complexity | Priority |
|----------|--------|------------|----------|
| Gene-centric search | 🟢 High | 🟡 Medium | **P0** (Must have) |
| Basic identifier extraction | 🟢 High | 🟢 Low | **P0** |
| `/search/enriched` endpoint | 🟢 High | 🟡 Medium | **P0** |
| Drug discovery RAG | 🟢 High | 🟡 Medium | **P1** (Should have) |
| `/ask/enriched` endpoint | 🟢 High | 🔴 High | **P1** |
| Cross-species analysis | 🟡 Medium | 🔴 High | **P2** (Nice to have) |
| Pre-computed mappings | 🟡 Medium | 🔴 High | **P2** |

---

## 🚀 Quick Start (Recommended First Steps)

1. **Build biobtree binary**:
   ```bash
   cd external/biobtreev2
   go build
   ```

2. **Build initial dataset** (start small):
   ```bash
   ./biobtree -d "uniprot,hgnc,go" build
   ```

3. **Start biobtree service**:
   ```bash
   ./biobtree web
   # Runs on http://localhost:8888
   ```

4. **Test biobtree API**:
   ```bash
   # Search for TP53 gene
   curl "http://localhost:8888/ws/?i=TP53&s=hgnc"

   # Map to Uniprot
   curl "http://localhost:8888/ws/map/?i=TP53&m=uniprot&s=hgnc"
   ```

5. **Create biobtree module** in BioYoda:
   ```bash
   mkdir -p modules/biobtree/scripts
   # Add build/start/stop scripts
   ```

6. **Implement basic identifier extraction** in API module

7. **Test end-to-end**: Search for "BRCA1" → extract gene symbol → query biobtree → return enriched results

---

## 💡 Key Design Decisions

1. **Biobtree as submodule** ✅ (Already done)
   - Keep biobtree code independent
   - Easy to update from upstream

2. **Service-based integration**
   - Biobtree runs as separate service (port 8888)
   - BioYoda API calls biobtree via REST
   - Benefits: loose coupling, independent scaling

3. **Gradual rollout**
   - Start with basic identifier extraction
   - Add enrichment as optional feature
   - Keep existing APIs working

4. **Caching strategy**
   - Cache biobtree queries aggressively
   - Many identifiers queried repeatedly
   - Consider Redis for distributed cache

5. **Dataset selection**
   - Start with core biomedical datasets
   - Expand based on user needs
   - Full build takes hours + significant storage

---

## 📈 Success Metrics

- **Identifier extraction accuracy**: >85% precision for genes/proteins
- **API latency**: <500ms for enriched search (with cache hits)
- **Coverage**: Extract identifiers from >50% of search results
- **User adoption**: >30% of queries use enriched endpoints after launch
- **Quality**: RAG answers include cross-referenced data in >70% of responses

---

## 🎯 Next Steps

**Immediate priorities**:
1. Build biobtree with core datasets (uniprot, hgnc, go, taxonomy)
2. Create `modules/biobtree/` with management scripts
3. Implement basic `IdentifierExtractor` class
4. Add `/search/enriched` endpoint (simpler than RAG)
5. Test with gene-centric search use case

---

## 📚 Additional Ideas & Future Enhancements

*(To be expanded with user's additional ideas)*

- TBD: User has mentioned having more ideas beyond this initial plan
- This document serves as the foundation - additional use cases and features to be added iteratively

---

**Version**: 1.0
**Created**: October 2025
**Last Updated**: October 2025
