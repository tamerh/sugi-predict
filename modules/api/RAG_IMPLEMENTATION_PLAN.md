# BioYoda RAG Implementation Plan

**Version**: 1.0
**Date**: October 10, 2025
**Status**: Planning Complete - Ready for Implementation
**Target Timeline**: 2-3 weeks

---

## Overview

Transform BioYoda from a semantic search engine into an intelligent Q&A system using **Retrieval-Augmented Generation (RAG)**. Users will be able to ask natural language questions and receive comprehensive answers with proper citations from 30M+ PubMed abstracts and 500K+ clinical trials.

**Goal**: `/ask` endpoint that returns AI-generated answers grounded in retrieved scientific literature.

---

## Architecture Decision: Query Processing Strategy

### Phase 2: Direct Search (Current Plan) ✅

**Approach**: Use S-BioBERT embeddings directly without LLM query preprocessing

```
User Question → S-BioBERT Embedding → Qdrant Search → Top K Results → LLM Answer Generation
```

**Rationale:**
- S-BioBERT is already semantic (understands biomedical concepts)
- Handles 80-90% of queries effectively
- Lower latency (~700ms vs ~1200ms)
- Lower cost ($0.014 vs $0.017 per query)
- Simpler to debug and iterate
- Faster development cycle

**Example:**
```
Q: "What is CRISPR gene editing?"
→ Direct embedding search
→ Top 5 relevant papers
→ LLM generates answer with citations
```

### Phase 3: Enhanced Query Processing (Future)

**Optional enhancement** for complex multi-part questions:

```
User Question → LLM Query Processor → Multiple Query Variants → Parallel Searches → Merged Results → LLM Answer
```

**When to add:**
- Complex multi-aspect questions
- Need for synonym expansion
- A/B testing shows measurable improvement
- User requests comprehensive search mode

**Implementation**: Add as optional flag `enhance_query=True` parameter

---

## LLM Provider Selection

### Chosen Strategy: Flexible Multi-Provider Architecture

**Design**: Provider-agnostic system with easy switching between LLMs

### Provider Options

#### 1. Anthropic Claude (Primary - Recommended)

**Model**: `claude-3-5-sonnet-20241022`

**Strengths:**
- Long context window (200K tokens) - fits many abstracts
- Strong biomedical reasoning
- Low hallucination rate
- Excellent citation adherence
- Natural academic writing style

**Costs:**
- Input: $3 per 1M tokens
- Output: $15 per 1M tokens
- **Per query**: ~$0.014 (1.4 cents)
- **1000 queries/day**: ~$14/day or $420/month

**Best for**: High-quality research answers, accuracy-critical use cases

#### 2. OpenAI GPT-4 (Alternative)

**Model**: `gpt-4-turbo-preview`

**Strengths:**
- Mature ecosystem
- Excellent function calling
- Strong performance
- Wide adoption

**Costs:**
- Similar to Claude (~$10 per 1M input tokens)
- Per query: ~$0.015

**Best for**: Ecosystem compatibility, structured outputs

#### 3. Local Models (Future Cost Optimization)

**Models**:
- `Llama-3.1-70B-Instruct` - Best open-source reasoning
- `Mistral-Large-2` - Efficient, good quality
- `BioGPT` / `BioMistral` - Biomedical specialized

**Strengths:**
- Zero API costs
- Privacy (data stays local)
- No rate limits
- Run on HPC GPU nodes
- Full control and reproducibility

**Requirements:**
- 16-80GB VRAM depending on model
- Ollama or vLLM deployment
- More maintenance overhead

**Best for**: High-volume production, cost-sensitive, research reproducibility

### Configuration Design

```yaml
# config/api_config.yaml

rag:
  # Provider configuration (easily switchable)
  provider: "anthropic"  # anthropic | openai | local
  model: "claude-3-5-sonnet-20241022"
  api_key: "${ANTHROPIC_API_KEY}"

  # Alternative configs (comment/uncomment as needed):
  # provider: "openai"
  # model: "gpt-4-turbo-preview"
  # api_key: "${OPENAI_API_KEY}"

  # provider: "local"
  # model: "llama3.1:70b"
  # base_url: "http://localhost:11434"  # Ollama

  # RAG parameters
  default_top_k: 5
  max_top_k: 20
  default_temperature: 0.1  # Low for factual answers
  default_max_tokens: 1000

  # Safety and validation
  enable_validation: true
  require_citations: true
  max_context_length: 100000
```

---

## Implementation Plan

### Week 1: Foundation (Core RAG Engine)

#### Day 1-2: LLM Provider Abstraction

**File**: `modules/api/scripts/llm_providers.py`

**Components:**
1. Abstract base class `LLMProvider`
2. Concrete implementations:
   - `AnthropicProvider` (Claude)
   - `OpenAIProvider` (GPT-4)
   - `LocalProvider` (Ollama/vLLM)
3. Factory pattern for provider selection
4. Cost estimation methods

**Key Features:**
- Clean interface: `generate(prompt, max_tokens) -> str`
- Provider-specific configuration
- Error handling and retries
- Token counting and cost tracking

**Example:**
```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 1000) -> str:
        pass

    @abstractmethod
    def get_cost_estimate(self, prompt: str, response: str) -> float:
        pass

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 1000) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

# Factory
def get_llm_provider(config: Dict) -> LLMProvider:
    provider_type = config.get("provider", "anthropic")
    if provider_type == "anthropic":
        return AnthropicProvider(...)
    elif provider_type == "openai":
        return OpenAIProvider(...)
    elif provider_type == "local":
        return LocalProvider(...)
```

#### Day 2-3: Prompt Engineering Framework

**File**: `modules/api/scripts/prompts.py`

**Components:**
1. System prompt for biomedical domain
2. RAG prompt template with context injection
3. Citation formatting
4. Follow-up question support (future)

**Key Features:**
- Biomedical-specific instructions
- Citation requirements
- Hallucination prevention
- Structured output format

**Example:**
```python
class PromptTemplate:
    SYSTEM_PROMPT = """You are BioYoda, an expert biomedical AI assistant with access to a database of 30M+ PubMed abstracts and 500K+ clinical trials.

Your role:
- Answer questions accurately based ONLY on provided context
- Always cite specific PMIDs or trial IDs for claims
- If context is insufficient, say so clearly
- Use clear, accessible language while maintaining scientific accuracy
- Distinguish between established facts and emerging research

Remember: Never make up information. Only use the provided context."""

    @staticmethod
    def build_rag_prompt(
        question: str,
        search_results: List[Dict],
        include_citations: bool = True
    ) -> str:
        # Format context from search results
        context_parts = []
        for i, result in enumerate(search_results, 1):
            pmid = result['payload'].get('pmid', result['id'])
            text = result['payload'].get('chunk_text', '')
            score = result.get('score', 0.0)

            context_parts.append(f"""
[Source {i}] PMID: {pmid} (Relevance: {score:.3f})
{text}
---
""")

        context = "\n".join(context_parts)

        prompt = f"""{PromptTemplate.SYSTEM_PROMPT}

CONTEXT (Retrieved from vector search):
{context}

QUESTION: {question}

INSTRUCTIONS:
1. Answer the question using ONLY the context above
2. Cite specific PMIDs for each claim (e.g., "According to PMID:12345...")
3. If the context doesn't contain enough information, state this clearly
4. Provide a comprehensive but concise answer
5. End with a "Sources:" section listing all PMIDs used

Answer:"""

        return prompt
```

#### Day 3-4: Core RAG Module

**File**: `modules/api/scripts/rag.py`

**Components:**
1. `RAGEngine` class
2. Integration with existing `SearchEngine`
3. Context preparation and ranking
4. Answer generation
5. Citation extraction and validation

**Key Features:**
- Async/await for performance
- Timing metrics (search, LLM, total)
- Error handling
- Source tracking
- Validation hooks

**Example:**
```python
class RAGEngine:
    def __init__(self, search_engine: SearchEngine, llm_config: Dict):
        self.search_engine = search_engine
        self.llm_provider = get_llm_provider(llm_config)
        self.prompt_template = PromptTemplate()

    async def ask(
        self,
        question: str,
        collections: List[str] = None,
        top_k: int = 5,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> Dict:
        """
        Answer question using RAG

        Returns:
            {
                "question": str,
                "answer": str,
                "sources": List[Dict],
                "search_time_ms": float,
                "llm_time_ms": float,
                "total_time_ms": float,
                "model_used": str
            }
        """
        start_time = time.time()

        # Step 1: Retrieve relevant context
        search_results = await self.search_engine.search(
            query=question,
            collections=collections or ["pubmed_abstracts", "clinical_trials"],
            limit=top_k,
            merge_results=True
        )

        search_time_ms = (time.time() - search_start) * 1000

        # Step 2: Build prompt with context
        prompt = self.prompt_template.build_rag_prompt(
            question=question,
            search_results=search_results['results']
        )

        # Step 3: Generate answer
        answer = self.llm_provider.generate(
            prompt=prompt,
            max_tokens=max_tokens
        )

        # Step 4: Extract and validate citations
        sources = self._extract_sources(search_results['results'])
        validated_answer = self._validate_answer(answer, sources)

        return {
            "question": question,
            "answer": validated_answer,
            "sources": sources,
            "search_time_ms": search_time_ms,
            "llm_time_ms": llm_time_ms,
            "total_time_ms": total_time_ms,
            "model_used": self.llm_provider.model
        }
```

---

### Week 2: API Integration & Testing

#### Day 5-6: Add /ask Endpoint

**File**: `modules/api/scripts/main.py`

**Changes:**
1. Initialize RAG engine on startup
2. Add `/ask` endpoint
3. Request/response validation
4. Error handling

**New Pydantic Models** (`modules/api/scripts/models.py`):
```python
class AskRequest(BaseModel):
    question: str = Field(..., description="Question to answer")
    collections: Optional[List[str]] = Field(
        default=["pubmed_abstracts", "clinical_trials"]
    )
    top_k: int = Field(default=5, ge=1, le=20)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1000, ge=100, le=4000)

class Source(BaseModel):
    pmid: str
    score: float
    collection: str
    text_preview: str

class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[Source]
    search_time_ms: float
    llm_time_ms: float
    total_time_ms: float
    model_used: str
```

**Endpoint Implementation:**
```python
@app.on_event("startup")
async def startup_event():
    global search_engine, rag_engine

    # Existing search engine
    search_engine = SearchEngine(...)

    # New RAG engine
    llm_config = config['rag']
    rag_engine = RAGEngine(search_engine, llm_config)

    logger.info("✅ RAG engine initialized")

@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Ask a question and get an AI-generated answer with citations
    """
    try:
        result = await rag_engine.ask(
            question=request.question,
            collections=request.collections,
            top_k=request.top_k,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        return AskResponse(**result)

    except Exception as e:
        logger.error(f"RAG error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### Day 6: Configuration Updates

**File**: `config/api_config.yaml`

Add new `rag` section with all provider configurations and parameters.

#### Day 6-7: Basic Testing

**File**: `tests/integration/test_rag_integration.py`

**Test Coverage:**
1. Basic `/ask` functionality
2. Citation validation
3. Error handling (no results, API failures)
4. Multi-collection support
5. Response format validation

---

### Week 3: Polish & Advanced Features

#### Day 7-8: CLI Tool Enhancement

**File**: `bioyoda.sh` (add RAG commands)

```bash
# New commands
./bioyoda.sh ask "What is CRISPR?"
./bioyoda.sh ask "Latest Alzheimer treatments?" --collections pubmed_abstracts
./bioyoda.sh ask "COVID-19 vaccine efficacy" --top-k 10
```

**Interactive mode:**
```bash
./bioyoda.sh ask  # Interactive Q&A mode
bioyoda> ask What is CRISPR?
bioyoda> ask More details about Cas9
bioyoda> quit
```

#### Day 8-9: Citation Validation & Quality Checks

**Features:**
1. Verify LLM cited sources from context
2. Flag potential hallucinations
3. Check PMID format validity
4. Measure citation coverage (% of sources cited)
5. Quality scoring

**Implementation:**
```python
def _validate_answer(self, answer: str, sources: List[Dict]) -> Dict:
    """Validate answer quality and citations"""

    # Check citation presence
    mentioned_pmids = []
    for source in sources:
        pmid = source['pmid']
        if str(pmid) in answer:
            mentioned_pmids.append(pmid)

    citation_coverage = len(mentioned_pmids) / len(sources)

    # Flag if low citation coverage
    validation = {
        "cited_pmids": mentioned_pmids,
        "citation_coverage": citation_coverage,
        "warning": None
    }

    if citation_coverage < 0.3:
        validation["warning"] = "Low citation coverage - answer may not be well-grounded"

    if not mentioned_pmids:
        validation["warning"] = "No citations found - high hallucination risk"

    return validation
```

#### Day 9-10: Comprehensive Testing

**Test Suite** (`tests/integration/test_rag_api.py`):

```python
def test_ask_basic_question():
    """Test basic Q&A functionality"""
    response = client.post("/ask", json={
        "question": "What is CRISPR?",
        "collections": ["pubmed_abstracts"],
        "top_k": 5
    })

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["sources"]) > 0
    assert "PMID" in data["answer"]

def test_ask_with_citations():
    """Verify proper citation format"""
    response = client.post("/ask", json={
        "question": "How does metformin work?"
    })

    data = response.json()
    # Check PMIDs are mentioned
    for source in data["sources"]:
        assert source["pmid"] in data["answer"]

def test_ask_unknown_topic():
    """Test graceful handling of no results"""
    response = client.post("/ask", json={
        "question": "asdfqwerzxcv"  # Nonsense query
    })

    data = response.json()
    assert "don't have enough information" in data["answer"].lower() \
        or "cannot answer" in data["answer"].lower()

def test_ask_multi_collection():
    """Test searching across multiple collections"""
    response = client.post("/ask", json={
        "question": "Are there clinical trials for CRISPR?",
        "collections": ["pubmed_abstracts", "clinical_trials"]
    })

    data = response.json()
    # Should have sources from both collections
    collections = {s["collection"] for s in data["sources"]}
    assert len(collections) >= 1

def test_ask_temperature_control():
    """Test temperature parameter effects"""
    # Low temp (factual)
    resp_low = client.post("/ask", json={
        "question": "What is CRISPR?",
        "temperature": 0.0
    })

    # Higher temp (more creative)
    resp_high = client.post("/ask", json={
        "question": "What is CRISPR?",
        "temperature": 0.5
    })

    # Both should succeed
    assert resp_low.status_code == 200
    assert resp_high.status_code == 200

def test_ask_performance():
    """Test response time is acceptable"""
    start = time.time()
    response = client.post("/ask", json={
        "question": "What is gene editing?"
    })
    elapsed = time.time() - start

    assert elapsed < 5.0  # Should be under 5 seconds

    data = response.json()
    assert data["total_time_ms"] < 5000
```

---

## File Structure

```
modules/api/
├── README.md                          # API documentation
├── IMPLEMENTATION_STATUS.md           # Current status
├── RAG_IMPLEMENTATION_PLAN.md         # This file
└── scripts/
    ├── main.py                        # FastAPI app (add /ask endpoint)
    ├── config.py                      # Config loader (existing)
    ├── models.py                      # Pydantic models (add AskRequest/Response)
    ├── search.py                      # Search engine (existing)
    ├── llm_providers.py               # NEW: LLM abstraction
    ├── prompts.py                     # NEW: Prompt templates
    └── rag.py                         # NEW: RAG engine core

config/
└── api_config.yaml                    # Add 'rag' section

tests/
├── integration/
│   └── test_rag_integration.py        # NEW: RAG tests
└── unit/
    └── test_rag_components.py         # NEW: Unit tests

bioyoda.sh                             # Add 'ask' subcommand
```

---

## Success Metrics

### Quality Metrics
- **Citation Rate**: >90% of answers include proper PMIDs
- **Accuracy**: Answers validated against source papers
- **Hallucination Rate**: <5% (measured by citation validation)

### Performance Metrics
- **Latency**: <3 seconds total (search + LLM generation)
- **Search Time**: <500ms
- **LLM Time**: <2000ms
- **Uptime**: >99% availability

### Cost Metrics (Claude)
- **Per Query**: <$0.02
- **Daily (1000 queries)**: <$20
- **Monthly**: <$600

### User Experience
- **Answer Completeness**: Addresses question fully
- **Readability**: Clear, well-structured responses
- **Citation Quality**: Relevant, recent papers cited

---

## Dependencies

### New Python Packages

Add to `config/tamer.yml`:

```yaml
dependencies:
  # Existing dependencies...

  # LLM providers
  - anthropic>=0.25.0         # Claude API
  - openai>=1.12.0            # GPT-4 API (optional)

  # Optional: Local model support
  # - ollama                  # For local Llama/Mistral
  # - vllm                    # Alternative local inference
```

### Environment Variables

```bash
# Required for Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional for OpenAI
export OPENAI_API_KEY="sk-..."

# Optional for local models
# (no API key needed)
```

---

## Phased Rollout Strategy

### Phase 2: Core RAG (Weeks 1-3) - Current Plan

**Features:**
- ✅ Direct semantic search (no query preprocessing)
- ✅ Claude integration (primary)
- ✅ `/ask` endpoint
- ✅ Citation generation
- ✅ Basic validation
- ✅ CLI tool integration

**Success Criteria:**
- API returns accurate answers with citations
- Performance <3 seconds per query
- Tests passing
- Documentation complete

### Phase 3: Query Enhancement (Weeks 4-6) - Future

**Features:**
- LLM query preprocessing (optional)
- Query expansion and synonym generation
- Multi-aspect question handling
- Biomedical term normalization

**Trigger:**
- A/B testing shows >10% quality improvement
- Complex queries show poor performance
- User feedback indicates need

### Phase 4: Advanced Features (Months 2-3) - Future

**Features:**
- Conversation memory (follow-up questions)
- Multi-turn dialogue
- Query result caching
- Provider auto-fallback
- Cost optimization
- Answer confidence scoring

---

## Risk Mitigation

### Risk 1: High API Costs

**Mitigation:**
1. Start with test dataset (10-100 queries)
2. Monitor costs daily
3. Set monthly budget alerts
4. Implement caching for common queries
5. Fallback to local models if needed

### Risk 2: Poor Answer Quality

**Mitigation:**
1. Extensive prompt engineering
2. Human evaluation of initial answers
3. Validation metrics and monitoring
4. A/B test different prompts
5. Iterative improvement based on feedback

### Risk 3: LLM Hallucinations

**Mitigation:**
1. Strong system prompts ("only use context")
2. Citation validation checks
3. Flag low-citation-coverage answers
4. Temperature = 0.1 (low, factual)
5. Post-generation validation

### Risk 4: Slow Response Times

**Mitigation:**
1. Async/await architecture
2. Parallel operations where possible
3. Context length limits
4. Caching layer (Phase 4)
5. Monitor and optimize bottlenecks

### Risk 5: Provider Downtime

**Mitigation:**
1. Multi-provider architecture (easy switching)
2. Retry logic with exponential backoff
3. Health checks and monitoring
4. Local model fallback option
5. Graceful error messages

---

## Future Enhancements (Post Phase 2)

### Enhanced Query Processing
- LLM query preprocessing
- Synonym expansion
- Biomedical term normalization
- Multi-aspect question decomposition

### Conversation Support
- Dialogue history tracking
- Follow-up question handling
- Context preservation across turns
- Session management

### Quality Improvements
- Answer confidence scores
- Fact-checking against context
- Source diversity metrics
- Automatic answer evaluation

### Performance Optimization
- Result caching (Redis)
- Context pre-loading
- Batch query processing
- Model quantization for local

### Production Features
- Rate limiting per user
- API key authentication
- Usage analytics
- Cost tracking per user
- Monitoring dashboard

---

## Questions for Tomorrow

Before starting implementation:

1. **API Keys**: Do you have Anthropic API key ready? (or should we start with OpenAI?)
2. **Testing Approach**: Use test dataset first or dive into full dataset?
3. **Priorities**: Any specific use cases to focus on first?
4. **Timeline**: Any hard deadlines or milestones to hit?
5. **Budget**: Any cost constraints we should plan for?

---

## References

- **Current API**: `modules/api/README.md`
- **Implementation Status**: `modules/api/IMPLEMENTATION_STATUS.md`
- **System Improvements**: `vibe/IMPROVEMENTS.md`
- **Main README**: Root `README.md`

---

**Plan Status**: ✅ Ready for Implementation
**Next Step**: Start Week 1, Day 1 - LLM Provider Abstraction
**Owner**: Implementation team
**Review Date**: Daily check-ins during development

---

*This plan will be updated as implementation progresses and new insights emerge.*
