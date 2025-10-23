# Clinical Trials Conditions/Diseases Feature

## Overview

The clinical trials module now extracts and processes **disease/condition data** from the AACT database. This enables disease-aware search, filtering, and retrieval across clinical trials in the BioYoda system.

**Status:** ✅ Implemented and functional (October 2025)

---

## Current Implementation

### What Gets Extracted

From the AACT `conditions.txt` table, we extract disease and condition names associated with each clinical trial:

**Example Data:**
```json
{
  "nct_id": "NCT03755154",
  "brief_title": "Study of S65487 in Acute Myeloid Leukemia",
  "conditions": [
    "Relapsed or Refractory Acute Myeloid Leukemia",
    "Relapsed or Refractory Non-Hodgkin Lymphoma",
    "Relapsed or Refractory Multiple Myeloma",
    "Relapsed or Refractory Chronic Lymphocytic Leukemia"
  ],
  "interventions": [
    {"intervention_type": "Drug", "name": "S65487"}
  ],
  "phase": "Phase 1",
  "study_type": "Interventional"
}
```

### Data Flow

```
AACT Database (conditions.txt)
    ↓
Extract & Process (download_and_extract.py)
    ↓
JSON Chunks (trials_chunk_*.json)
    ↓ conditions: [...]
Generate Embeddings (process_trials_chunk.py)
    ↓ conditions included in metadata
FAISS Indices + Metadata
    ↓
Qdrant Vector Database (insert_from_faiss.py)
    ↓ payload: {..., conditions: [...], ...}
Search API & RAG
```

### Where Conditions Are Used

#### 1. **Embedding Generation** (`process_trials.py`)
Conditions are included in the metadata of every text chunk:
- Summary chunks (line 119)
- Description chunks (line 138)
- Outcome chunks (lines 157, 176)
- Eligibility chunks (line 222)

**Impact:** While the condition names aren't directly in the embedded text, they're available in metadata for filtering and display.

#### 2. **Qdrant Storage** (`insert_from_faiss.py`)
All metadata (including conditions) is stored in the Qdrant payload:

```python
payload = {
    "nct_id": "NCT12345678",
    "chunk_type": "summary",
    "text": "...",
    "brief_title": "...",
    "conditions": ["Diabetes", "Obesity"],  # ✓ Available for filtering
    "interventions": [...],
    "phase": "Phase 3",
    "overall_status": "Completed"
}
```

#### 3. **Search API** (`modules/api/scripts/search.py`)
Supports filtering by any metadata field, including conditions:

```python
# Filter implementation at search.py:394-416
def _build_filter(self, filters: Dict[str, Any]) -> Optional[Filter]:
    """Build Qdrant filter from dictionary"""
    conditions = []
    for key, value in filters.items():
        conditions.append(
            FieldCondition(key=key, match=MatchValue(value=value))
        )
    return Filter(must=conditions)
```

---

## Current Capabilities

### ✅ **1. Metadata Filtering**

Filter clinical trials by disease/condition through the API.

**Example API Request:**
```json
POST /search
{
  "query": "insulin resistance treatment",
  "collections": ["clinical_trials"],
  "limit": 20,
  "filters": {
    "conditions": "Diabetes"
  }
}
```

**Use Cases:**
- Find all trials for a specific disease
- Combine with other filters:
  ```json
  {
    "filters": {
      "conditions": "Heart Failure",
      "phase": "Phase 3",
      "overall_status": "Completed"
    }
  }
  ```

### ✅ **2. Rich Metadata in Results**

Every search result includes the full conditions list:

**Example Response:**
```json
{
  "results": [
    {
      "id": "12345",
      "score": 0.87,
      "collection": "clinical_trials",
      "payload": {
        "nct_id": "NCT06027398",
        "brief_title": "SARS-COV-2 Detection From Used Surgical Mask",
        "conditions": ["SARS-CoV-2 Virus"],
        "interventions": [{"type": "Diagnostic", "name": "RNA detection"}],
        "phase": "N/A",
        "chunk_type": "summary"
      }
    }
  ]
}
```

### ✅ **3. Document Aggregation with Disease Context**

The API aggregates multiple chunks per trial while preserving conditions:

```json
// Before aggregation (3 chunks from same trial)
[
  {"nct_id": "NCT123", "chunk_type": "summary", "conditions": ["Diabetes"]},
  {"nct_id": "NCT123", "chunk_type": "eligibility", "conditions": ["Diabetes"]},
  {"nct_id": "NCT123", "chunk_type": "outcomes", "conditions": ["Diabetes"]}
]

// After aggregation (1 document)
{
  "doc_id": "NCT123",
  "score": 0.92,  // max/avg/sum of chunk scores
  "conditions": ["Diabetes"],
  "num_chunks": 3,
  "best_chunk_type": "summary"
}
```

### ✅ **4. RAG with Disease Context**

The RAG engine (`modules/api/scripts/rag.py`) receives conditions in the context:

```python
# User question: "What are recent diabetes treatments?"
# Retrieved context includes:
context = """
Trial NCT06259227: Incomplete Spinal Cord Injury
Conditions: Incomplete Spinal Cord Injury, Exercise Training
Interventions: Cardiorespiratory fitness training

Trial NCT01926509: Pulmonary Arterial Hypertension Study
Conditions: Pulmonary Arterial Hypertension
Interventions: MK-8892, Placebo
"""
# LLM generates disease-aware response
```

---

## Potential Enhancements

Below are features that could be built on top of the current implementation:

### 🔧 **A. Multi-Value Condition Filtering**

**Current:** Only supports single value matching
```json
{"filters": {"conditions": "Diabetes"}}  // Exact match
```

**Enhancement:** Support multiple conditions (OR logic)
```json
{"filters": {"conditions": ["Diabetes", "Obesity", "Heart Failure"]}}
```

**Implementation:**
```python
# In search.py _build_filter method
def _build_filter(self, filters: Dict[str, Any]) -> Optional[Filter]:
    conditions = []
    for key, value in filters.items():
        if isinstance(value, list):
            # Multiple values = OR condition
            conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchAny(any=value)
                )
            )
        else:
            # Single value = exact match
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=value))
            )
    return Filter(must=conditions)
```

**API Enhancement:**
```json
POST /search
{
  "query": "metabolic syndrome treatment",
  "collections": ["clinical_trials"],
  "filters": {
    "conditions": ["Diabetes", "Obesity", "Hypertension"]  // Match ANY
  }
}
```

---

### 📊 **B. Condition-Based Faceted Search**

**Goal:** Provide aggregated statistics about conditions in search results.

**Use Cases:**
- "How many trials per condition in these results?"
- "What are the most common diseases being studied?"
- "Disease co-occurrence analysis"

**Implementation:**

Add new endpoint: `POST /search/facets`

```python
# In search.py
def get_condition_facets(
    self,
    results: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Aggregate condition counts from search results.

    Returns:
        Dictionary mapping condition names to counts
    """
    condition_counts = {}

    for result in results:
        conditions = result.get('payload', {}).get('conditions', [])
        for condition in conditions:
            condition_counts[condition] = condition_counts.get(condition, 0) + 1

    # Sort by frequency
    return dict(sorted(
        condition_counts.items(),
        key=lambda x: x[1],
        reverse=True
    ))
```

**Example Response:**
```json
{
  "results": [...],  // Regular search results
  "facets": {
    "conditions": {
      "Diabetes": 45,
      "Obesity": 32,
      "Heart Failure": 28,
      "Hypertension": 25,
      "Cancer": 18
    }
  },
  "total_trials": 87
}
```

**Frontend Use:**
```javascript
// Display as filter sidebar
<h3>Filter by Condition</h3>
<ul>
  <li><input type="checkbox"> Diabetes (45)</li>
  <li><input type="checkbox"> Obesity (32)</li>
  <li><input type="checkbox"> Heart Failure (28)</li>
</ul>
```

---

### 🤖 **C. Condition-Aware RAG**

**Goal:** Automatically detect diseases in user questions and apply smart filtering.

**Enhancement:** Add disease detection to RAG pipeline

**Implementation:**

```python
# In rag.py
import re

class RAGEngine:

    def __init__(self, ...):
        # Load common disease keywords
        self.disease_keywords = self._load_disease_keywords()

    def _load_disease_keywords(self) -> Set[str]:
        """Load common disease names for detection"""
        return {
            'diabetes', 'cancer', 'obesity', 'hypertension',
            'alzheimer', 'parkinson', 'heart failure',
            'stroke', 'asthma', 'copd', 'covid', 'depression',
            # ... expand with comprehensive list
        }

    def _detect_diseases(self, query: str) -> List[str]:
        """
        Detect disease mentions in user query.

        Args:
            query: User question

        Returns:
            List of detected disease names
        """
        query_lower = query.lower()
        detected = []

        for disease in self.disease_keywords:
            if disease in query_lower:
                detected.append(disease.title())

        return detected

    def ask(self, question: str, collections: List[str], ...) -> Dict:
        """Enhanced RAG with disease detection"""

        # Detect diseases in question
        detected_diseases = self._detect_diseases(question)

        # Auto-apply disease filter if detected
        filters = filters or {}
        if detected_diseases and 'clinical_trials' in collections:
            logger.info(f"Detected diseases: {detected_diseases}")
            # Apply filter for clinical trials collection
            filters['conditions'] = detected_diseases[0]  # Use first detected

        # Continue with normal RAG flow
        context = self._retrieve_context(
            question,
            collections,
            filters=filters,  # ← Disease filter applied
            ...
        )

        response = self._generate_response(question, context)

        return {
            'answer': response,
            'detected_diseases': detected_diseases,  # ← Show in response
            'filters_applied': filters,
            'context': context
        }
```

**Example Interaction:**

```python
# User: "What are the latest diabetes treatments?"

# System detects: ["Diabetes"]
# Auto-applies filter: {"conditions": "Diabetes"}
# Retrieves only diabetes trials
# LLM generates diabetes-specific answer

Response:
{
  "answer": "Based on recent clinical trials for diabetes, several treatments show promise...",
  "detected_diseases": ["Diabetes"],
  "filters_applied": {"conditions": "Diabetes"},
  "sources": [
    {"nct_id": "NCT123", "title": "Metformin Study", "conditions": ["Diabetes"]},
    ...
  ]
}
```

---

### 🏥 **D. Disease Ontology Mapping** (Advanced)

**Goal:** Map free-text condition names to standardized medical ontologies.

**Why?**
- Handle synonyms: "Diabetes Mellitus" = "Diabetes" = "Type 2 Diabetes"
- Enable hierarchical queries: "All cancer types"
- Better disease grouping and analysis

**Ontologies to Consider:**
- **MeSH (Medical Subject Headings)** - NIH standard
- **ICD-10** - International disease classification
- **Disease Ontology (DO)** - Open biomedical ontology
- **SNOMED CT** - Clinical terminology

**Implementation Approach:**

1. **Pre-processing step** during data extraction:

```python
# In download_and_extract.py
import requests

class DiseaseOntologyMapper:
    """Map condition names to standardized IDs"""

    def __init__(self):
        # Load MeSH mappings or use API
        self.mesh_api = "https://id.nlm.nih.gov/mesh/lookup/descriptor"

    def map_condition(self, condition_name: str) -> Dict:
        """
        Map condition to MeSH term.

        Returns:
            {
                'original': 'Diabetes',
                'mesh_id': 'D003920',
                'mesh_term': 'Diabetes Mellitus',
                'synonyms': ['Diabetes', 'Sugar Disease'],
                'hierarchy': ['Diseases', 'Metabolic Diseases', 'Glucose Metabolism Disorders']
            }
        """
        # Query MeSH API or local database
        response = requests.get(
            self.mesh_api,
            params={'label': condition_name}
        )

        if response.ok:
            data = response.json()
            return {
                'original': condition_name,
                'mesh_id': data.get('ui'),
                'mesh_term': data.get('label'),
                'synonyms': data.get('synonyms', []),
                'hierarchy': data.get('treeNumbers', [])
            }

        return {'original': condition_name}  # Fallback
```

2. **Enhanced metadata structure:**

```json
{
  "nct_id": "NCT123",
  "conditions": ["Diabetes", "Obesity"],
  "conditions_mapped": [
    {
      "original": "Diabetes",
      "mesh_id": "D003920",
      "mesh_term": "Diabetes Mellitus",
      "synonyms": ["Sugar Disease", "Diabetes"],
      "category": "Metabolic Diseases"
    },
    {
      "original": "Obesity",
      "mesh_id": "D009765",
      "mesh_term": "Obesity",
      "category": "Metabolic Diseases"
    }
  ]
}
```

3. **Enhanced search capabilities:**

```python
# Search by MeSH ID (handles all synonyms)
{
  "query": "diabetes treatment",
  "filters": {
    "conditions_mapped.mesh_id": "D003920"  // Matches all diabetes variants
  }
}

# Hierarchical search (all cancer types)
{
  "query": "cancer immunotherapy",
  "filters": {
    "conditions_mapped.category": "Neoplasms"  // Includes all cancers
  }
}
```

**Benefits:**
- ✓ Synonym handling (automatic)
- ✓ Disease categorization
- ✓ Hierarchical filtering
- ✓ Better analytics and reporting
- ✓ Interoperability with other medical systems

---

### 🌐 **E. Cross-Collection Disease Search**

**Goal:** Search both literature (PubMed) and trials (Clinical Trials) by disease.

**Challenge:** PubMed doesn't have a `conditions` field like clinical trials.

**Solution Approaches:**

#### Option 1: Disease Extraction from PubMed Abstracts

```python
# During PubMed processing
from scispacy.linking import EntityLinker

class PubMedDiseaseExtractor:
    """Extract disease mentions from abstracts using NER"""

    def __init__(self):
        import spacy
        self.nlp = spacy.load("en_core_sci_md")
        self.nlp.add_pipe("scispacy_linker", config={"resolve_abbreviations": True})

    def extract_diseases(self, abstract_text: str) -> List[str]:
        """Extract disease entities from text"""
        doc = self.nlp(abstract_text)

        diseases = []
        for ent in doc.ents:
            if ent.label_ in ['DISEASE', 'DISORDER']:
                diseases.append(ent.text)

        return list(set(diseases))  # Deduplicate
```

#### Option 2: Unified Disease Search

```json
POST /search/by-disease
{
  "disease": "Diabetes",
  "query": "treatment outcomes",  // Optional refinement
  "collections": ["pubmed_abstracts", "clinical_trials"],
  "limit": 20
}

// Response combines both:
{
  "disease": "Diabetes",
  "clinical_trials": [
    // Trials filtered by conditions field
  ],
  "literature": [
    // PubMed filtered by disease mentions in text
  ],
  "total_results": 142
}
```

**Implementation:**

```python
# New API endpoint
@app.post("/search/by-disease")
async def search_by_disease(
    disease: str,
    collections: List[str],
    limit: int = 10
):
    """Disease-centric search across collections"""

    results = {}

    for collection in collections:
        if collection == "clinical_trials":
            # Use conditions filter
            results[collection] = search_engine.search_single_collection(
                query=disease,
                collection=collection,
                filters={"conditions": disease}
            )
        elif collection == "pubmed_abstracts":
            # Use text search (disease in abstract)
            results[collection] = search_engine.search_single_collection(
                query=f"{disease} disease",  # Enhance query
                collection=collection
            )

    return results
```

---

### 📈 **F. Disease Trend Analysis**

**Goal:** Analyze trends in clinical research by disease over time.

**Capabilities:**
- "Which diseases have the most active trials?"
- "Disease research trends over years"
- "Emerging vs. declining disease areas"

**Implementation:**

```python
# New analytics endpoint
@app.get("/analytics/disease-trends")
async def get_disease_trends(
    start_year: int,
    end_year: int,
    top_n: int = 20
):
    """
    Analyze disease research trends.

    Returns:
        Disease counts by year, top diseases, growth rates
    """
    # Query Qdrant with year filters
    results = {}

    for year in range(start_year, end_year + 1):
        year_results = client.scroll(
            collection_name="clinical_trials",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="start_date",
                        range=RangeFilter(
                            gte=f"{year}-01-01",
                            lte=f"{year}-12-31"
                        )
                    )
                ]
            ),
            limit=10000
        )

        # Aggregate conditions
        disease_counts = {}
        for point in year_results[0]:
            conditions = point.payload.get('conditions', [])
            for condition in conditions:
                disease_counts[condition] = disease_counts.get(condition, 0) + 1

        results[year] = disease_counts

    return {
        'trends': results,
        'top_diseases': _get_top_diseases(results, top_n),
        'fastest_growing': _calculate_growth_rates(results)
    }
```

**Example Response:**
```json
{
  "trends": {
    "2020": {"COVID-19": 1523, "Cancer": 892, "Diabetes": 654},
    "2021": {"COVID-19": 2341, "Cancer": 934, "Diabetes": 678},
    "2022": {"COVID-19": 987, "Cancer": 1023, "Diabetes": 701}
  },
  "top_diseases": [
    {"disease": "COVID-19", "total_trials": 4851},
    {"disease": "Cancer", "total_trials": 2849},
    {"disease": "Diabetes", "total_trials": 2033}
  ],
  "fastest_growing": [
    {"disease": "Alzheimer", "growth_rate": 2.3},
    {"disease": "Long COVID", "growth_rate": 4.1}
  ]
}
```

---

## Configuration

### Enabling/Disabling Conditions Extraction

In `config/config.yaml` or `config/config_gpu.yaml`:

```yaml
clinical_trials:
  # ... other settings ...

  # Conditions extraction (default: true)
  include_conditions: true

  # Other extraction flags
  include_interventions: true
  include_outcomes: true
  include_eligibility: true
  include_detailed_description: true
```

To disable conditions extraction:
```yaml
clinical_trials:
  include_conditions: false
```

---

## Testing

### Verify Conditions Are Extracted

```bash
# Run test extraction
conda run -n bioyoda python << EOF
import sys
sys.path.insert(0, 'modules/clinical_trials/scripts')
from download_and_extract import AACTTextExtractor

extractor = AACTTextExtractor('snapshots/out_all/raw_data/clinical_trials/extracted')
extractor.load_extraction_info()

studies = extractor.extract_studies_text(
    limit=5,
    include_conditions=True
)

for study in studies:
    print(f"NCT: {study['nct_id']}")
    print(f"Conditions: {study.get('conditions', [])}")
    print()
EOF
```

### Test API Filtering

```bash
# Start API
./bioyoda.sh api start

# Test disease filter
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "treatment outcomes",
    "collections": ["clinical_trials"],
    "filters": {"conditions": "Diabetes"},
    "limit": 5
  }'
```

---

## Performance Considerations

### Storage Impact
- **Conditions per trial:** Average 1-3 conditions
- **Storage overhead:** Minimal (~0.5% increase in metadata size)
- **Example:**
  - 554K trials × 2 conditions × 20 bytes = ~22 MB additional

### Query Performance
- **Filtering:** Very fast (indexed field in Qdrant)
- **Faceting:** O(n) where n = result set size (not total DB)
- **Ontology mapping:** One-time cost during data processing

### Recommendations
- ✓ Use conditions filtering to reduce result set size
- ✓ Cache facet results for repeated queries
- ✓ For ontology mapping, process offline and store results

---

## Future Directions

### Integration with External APIs
- **ClinicalTrials.gov API:** Real-time trial updates
- **PubMed API:** Link trials to related publications
- **Disease databases:** OMIM, Orphanet for rare diseases

### Machine Learning Enhancements
- **Disease similarity:** Cluster similar conditions
- **Predictive analytics:** Forecast emerging disease areas
- **Auto-tagging:** Suggest additional conditions based on trial text

### Visualization
- **Disease network graphs:** Show condition co-occurrences
- **Timeline views:** Disease research evolution
- **Geographic heatmaps:** Disease prevalence by trial location

---

## References

### AACT Database
- **Source:** Clinical Trials Transformation Initiative (CTTI)
- **URL:** https://aact.ctti-clinicaltrials.org/
- **Tables used:** `conditions.txt`, `studies.txt`, `interventions.txt`, etc.

### Medical Ontologies
- **MeSH:** https://www.nlm.nih.gov/mesh/
- **ICD-10:** https://www.who.int/classifications/icd/
- **Disease Ontology:** https://disease-ontology.org/
- **SNOMED CT:** https://www.snomed.org/

### Related Documentation
- `modules/clinical_trials/README.md` - Clinical trials module overview
- `modules/qdrant/README.md` - Vector database documentation
- `modules/api/README.md` - Search API documentation

---

## Changelog

### Version 0.4.0 (October 2025)
- ✅ **Added:** Conditions extraction from AACT database
- ✅ **Added:** Conditions included in Qdrant payloads
- ✅ **Added:** API filtering support for conditions
- ✅ **Updated:** Metadata structure to include conditions list
- ✅ **Updated:** Documentation with conditions feature

### Planned (Future Versions)
- ⏳ Multi-value condition filtering
- ⏳ Faceted search with condition aggregation
- ⏳ Disease ontology mapping (MeSH/ICD-10)
- ⏳ Condition-aware RAG enhancement
- ⏳ Disease trend analytics endpoint

---

**Last Updated:** October 23, 2025
**Module Version:** 0.4.0
**Author:** BioYoda Development Team