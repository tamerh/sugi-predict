# BioYoda Agent System Architecture

## Vision

BioYoda is an AI agent system that combines **structured biological data** (BioBTree), **semantic search** (Qdrant vectors), and **LLM reasoning** to answer complex biomedical questions with evidence-backed insights.

**What makes BioYoda unique:**
- Generic LLMs hallucinate drug names, mechanisms, and trials
- BioYoda provides **traceable evidence chains** across 40+ biological databases
- Every claim links to source identifiers (ChEMBL IDs, PMIDs, patent numbers)

---

## Three Pillars of Intelligence

### 1. Structured Intelligence (BioBTree)
```
Deterministic • Complete • Traceable
disease → genes → proteins → drugs → patents → compounds
```
- 40+ biological databases with deterministic mappings
- Complete coverage (all results, not just what LLM "remembers")
- Evidence chains are explicit and reproducible

### 2. Semantic Intelligence (Qdrant)
```
Contextual • Discovery • Similarity
```
| Collection | Content | Embeddings |
|------------|---------|------------|
| PubMed | 35M+ abstracts | Text embeddings |
| Clinical Trials | Trial descriptions | Text embeddings |
| Patent Text | Patent claims/abstracts | Text embeddings |
| Patent Compounds | 30.8M compounds | Morgan fingerprints (2048-bit) |
| Proteins | 573K SwissProt | ESM-2 embeddings (1280-dim) |

### 3. Reasoning Intelligence (Agent)
```
Synthesis • Hypothesis • Prioritization • Discovery
```
- Synthesizes structured + semantic data
- Generates hypotheses about gaps and opportunities
- Prioritizes findings by evidence strength
- Explains "why this matters"

---

## v1.0 Agent Architecture (Launch/Preprint)

### Multi-Agent Design

**Separate pages per agent (no router for v1.0):**
```
bioyoda.org/drug-discovery  → Drug Discovery Agent
bioyoda.org/id-mapper       → ID Mapping Agent
bioyoda.org/literature      → Literature Search Agent (if ready)
```

**Why separate pages for v1.0:**
1. Clear demonstration of capabilities
2. Easier validation and benchmarking
3. No router misclassification errors
4. Faster to ship
5. Better for preprint (focus on depth)

### Agent Inventory

| Agent | Complexity | Purpose | Status |
|-------|------------|---------|--------|
| Drug Discovery | High | Disease → drugs with evidence | v1.0 |
| ID Mapper | Low | Cross-database ID mapping | v1.0 |
| Literature Search | Medium | Semantic PubMed search | v1.0 (stretch) |

---

## The Six-Phase Agent Reasoning Loop

This is what makes BioYoda an **agent**, not just an automation script.

```
┌─────────────────────────────────────────────────────────────┐
│                        USER QUERY                           │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   PHASE 1: UNDERSTAND     │
                    │   (LLM parses intent)     │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   PHASE 2: GATHER         │
                    │   (BioBTree tools)        │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   PHASE 3: SCORE          │
                    │   (Evidence + Patterns)   │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   PHASE 4: REASON         │◄────┐
                    │   (LLM thinking)          │     │
                    └─────────────┬─────────────┘     │
                                  │                   │
                         Need more data?              │
                           │      │                   │
                          YES     NO                  │
                           │      │                   │
              ┌────────────▼──┐   │                   │
              │ PHASE 5:      │   │                   │
              │ FOLLOW-UP     │───┘                   │
              │ (Qdrant)      │                       │
              └───────────────┘                       │
                                  │
                    ┌─────────────▼─────────────┐
                    │   PHASE 6: SYNTHESIZE     │
                    │   (Evidence-rich response)│
                    └─────────────────────────────────┘
```

### Phase Details

| Phase | Type | What It Does | Output |
|-------|------|--------------|--------|
| 1. Understand | LLM | Parse query intent, constraints, focus areas | Intent object |
| 2. Gather | Tool | Run BioBTree paths in parallel | Structured data |
| 3. Score | Code | Evidence scoring, pattern detection | Scored entities, patterns |
| 4. Reason | LLM | Generate observations, hypotheses, identify gaps | Reasoning object |
| 5. Follow-up | Tool | Semantic search to validate hypotheses | Additional evidence |
| 6. Synthesize | LLM | Create insight-rich response with evidence | Final response |

---

## Phase Implementation Details

### Phase 1: Understand

```python
intent = await llm.understand(user_query)

# Output:
{
    "disease": "glioblastoma",
    "goal": "find novel targets",
    "context": "treatment-resistant",
    "constraints": ["avoid temozolomide", "focus Phase 2+"],
    "focus_areas": ["resistance mechanisms", "emerging therapies"]
}
```

### Phase 2: Gather

```python
structured_data = await disease_drug_tool.execute(
    disease=intent.disease,
    min_indication_phase=2,
    include_gwas=True,
    include_clinvar=True,
    include_clinical_trials=True,
    include_patents=True
)

# Output: Comprehensive data from all BioBTree paths
# - 28 drugs with direct indications
# - 50 genes from GWAS/ClinVar
# - 94 clinical trials
# - 4,480 patents
```

### Phase 3: Score & Detect Patterns

```python
scored_data = evidence_scorer.score(structured_data)
patterns = pattern_detector.analyze(structured_data)

# Output:
{
    "high_confidence_entities": [
        {"gene": "EGFR", "score": 85, "sources": ["gwas", "clinvar", "trials", "patents"]},
        {"drug": "Bevacizumab", "score": 92, "sources": ["indication", "trials", "patents"]}
    ],
    "multi_source_genes": ["EGFR", "TP53", "PTEN"],
    "genes_without_approved_drugs": ["ATG5", "BECN1"],  # Gap identified!
    "drugs_in_active_trials": ["Pembrolizumab", "Nivolumab"],
    "recent_patent_activity": ["autophagy modulators", "IDH inhibitors"],
    "gaps_identified": [
        "ATG5 has 3 ClinVar variants but no targeting drugs",
        "Autophagy pathway in 8 patents but no approved drugs"
    ]
}
```

**Evidence Scoring Formula:**
```python
def calculate_score(entity):
    score = 0
    score += entity.in_direct_indications * 40  # Phase 4 approval
    score += entity.in_clinical_trials * 25     # Active trials
    score += entity.in_gwas * 15                # Genetic association
    score += entity.in_clinvar * 15             # Variant association
    score += entity.in_pubchem_fda * 10         # FDA approved
    score += entity.in_patents * 5              # IP activity
    score += entity.literature_mentions * 2     # Literature support
    return min(score, 100)
```

### Phase 4: Reason

```python
reasoning = await llm.reason(
    query=user_query,
    intent=intent,
    data=scored_data,
    patterns=patterns
)

# Output:
{
    "observations": [
        "EGFR is well-validated (4 sources) but resistance is common",
        "Autophagy genes (ATG5, BECN1) appear in variants but lack drugs",
        "Recent patents focus on BBB penetration and autophagy"
    ],
    "hypotheses": [
        "Autophagy pathway may be underexplored therapeutic target",
        "Combination therapy (EGFR + autophagy) might address resistance"
    ],
    "follow_up_queries": [
        {"type": "pubmed", "query": "glioblastoma autophagy therapeutic target"},
        {"type": "compound_similarity", "query": "temozolomide analogs"}
    ],
    "confidence": "medium - need literature validation"
}
```

### Phase 5: Follow-up

```python
if reasoning.follow_up_queries:
    for query in reasoning.follow_up_queries[:2]:  # Limit iterations
        if query.type == "pubmed":
            papers = await qdrant.search_pubmed(query.query, limit=5)
            reasoning.add_evidence("literature", papers)
        elif query.type == "compound_similarity":
            compounds = await qdrant.search_compounds(query.query, limit=5)
            reasoning.add_evidence("similar_compounds", compounds)

# Adds literature validation to hypotheses
```

### Phase 6: Synthesize

```python
response = await llm.synthesize(
    query=user_query,
    scored_data=scored_data,
    patterns=patterns,
    reasoning=reasoning
)

# Output: Rich response with evidence chains, confidence, next steps
```

---

## Full Example: Agent Loop in Action

### User Query
> "What are novel drug targets for treatment-resistant glioblastoma?"

### Phase 1: Understand
```
Intent:
- Disease: glioblastoma
- Goal: novel targets (not established ones)
- Context: treatment-resistant (standard therapy failed)
- Implicit: looking for underexplored/emerging targets
```

### Phase 2: Gather
```
BioBTree Results:
- 28 drugs with direct indications (Phase 3+)
- 50 genes from GWAS/ClinVar
- 94 clinical trials (12 recruiting)
- 4,480 patents from drug compounds
```

### Phase 3: Score & Patterns
```
Evidence Scores:
┌──────────┬───────┬─────────────────────────────────┬─────────────┐
│ Entity   │ Score │ Sources                         │ Category    │
├──────────┼───────┼─────────────────────────────────┼─────────────┤
│ EGFR     │ 85    │ GWAS, ClinVar, trials, patents  │ ESTABLISHED │
│ TP53     │ 72    │ GWAS, ClinVar, trials           │ ESTABLISHED │
│ ATG5     │ 35    │ ClinVar only, no drugs          │ NOVEL ⭐    │
│ BECN1    │ 32    │ ClinVar only, no drugs          │ NOVEL ⭐    │
└──────────┴───────┴─────────────────────────────────┴─────────────┘

Patterns Detected:
- Autophagy genes (ATG5, BECN1, ULK1) have variants but no targeting drugs
- 3 recent patents mention autophagy modulation for GBM
- EGFR drugs in trials but 40% resistance mentioned in literature
```

### Phase 4: Reason
```
Agent Thinking:
"The user wants NOVEL targets for RESISTANT cases. EGFR is well-established
but has resistance issues - not what they want.

I notice autophagy genes (ATG5, BECN1) appear in ClinVar but have NO drugs
targeting them. There are also patents mentioning autophagy. This could be
an underexplored avenue.

Let me check the literature to validate this hypothesis..."

Follow-up Query: Search PubMed for "glioblastoma autophagy therapeutic"
```

### Phase 5: Follow-up
```
PubMed Semantic Search Results:
- "Autophagy inhibition sensitizes GBM to temozolomide" (2023, PMID: 37845123)
- "ATG5 as emerging target in glioma therapy" (2024, PMID: 38123456)
- "Chloroquine derivatives for GBM autophagy modulation" (2023, PMID: 37654321)

Agent: "Literature confirms autophagy is emerging target!"
```

### Phase 6: Synthesize (Final Response)
```
Based on my analysis of genetic associations, clinical trials, patents,
and recent literature, I've identified novel targets for treatment-resistant
glioblastoma:

╔═══════════════════════════════════════════════════════════════════════╗
║ EMERGING TARGETS (High Novelty, Growing Evidence)                     ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 1. ATG5 (Autophagy Related 5)                                         ║
║    • Evidence: ClinVar variants in GBM patients                       ║
║    • Literature: "ATG5 as emerging target" (PMID: 38123456)           ║
║    • Opportunity: No approved drugs targeting this gene               ║
║    • Score: 35 (novel - limited but growing evidence)                 ║
║                                                                       ║
║ 2. BECN1 (Beclin 1)                                                   ║
║    • Evidence: ClinVar variants, autophagy regulator                  ║
║    • Patents: 3 filings mention BECN1 modulation (2023-24)            ║
║    • Opportunity: Druggable, no approved inhibitors for GBM           ║
║    • Score: 32 (novel)                                                ║
╠═══════════════════════════════════════════════════════════════════════╣
║ WHY AUTOPHAGY PATHWAY?                                                ║
╠═══════════════════════════════════════════════════════════════════════╣
║ • Temozolomide resistance is linked to autophagy upregulation         ║
║ • Literature: Autophagy inhibition sensitizes resistant cells         ║
║ • Patent activity: Emerging interest from pharma (3 filings 2023-24)  ║
║ • Gap: Genetic evidence exists but no drugs in development            ║
╠═══════════════════════════════════════════════════════════════════════╣
║ ESTABLISHED TARGETS (for comparison - user asked for NOVEL)           ║
╠═══════════════════════════════════════════════════════════════════════╣
║ • EGFR: Score 85 - Well-validated but 40% resistance rate             ║
║ • TP53: Score 72 - Difficult to drug directly                         ║
╠═══════════════════════════════════════════════════════════════════════╣
║ EVIDENCE CONFIDENCE: Medium-High                                      ║
╠═══════════════════════════════════════════════════════════════════════╣
║ ✓ Genetic evidence (ClinVar)                                          ║
║ ✓ Literature support (3 recent papers)                                ║
║ ✓ Patent activity (emerging)                                          ║
║ ✗ Clinical validation (no trials yet - true novelty)                  ║
╠═══════════════════════════════════════════════════════════════════════╣
║ SUGGESTED NEXT STEPS                                                  ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 1. Explore chloroquine derivatives (known autophagy inhibitors)       ║
║ 2. Search patent database for ATG5-targeting compounds                ║
║ 3. Review preclinical autophagy studies in GBM models                 ║
║ 4. Consider combination: EGFR inhibitor + autophagy modulator         ║
╚═══════════════════════════════════════════════════════════════════════╝

Evidence Sources:
- BioBTree: ClinVar, GWAS, ChEMBL, Patents
- Qdrant: PubMed semantic search
- PMIDs: 37845123, 38123456, 37654321
```

---

## API Design (v1.0)

### Endpoints

```
POST /api/v1/agents/drug-discovery/query
POST /api/v1/agents/id-mapper/query
POST /api/v1/agents/literature/query
```

### Request Format

```json
{
  "query": "What drugs are available for glioblastoma?",
  "parameters": {
    "include_patents": true,
    "include_clinical_trials": true,
    "min_phase": 3
  },
  "session_id": "optional-for-context"
}
```

### Response Format

```json
{
  "success": true,
  "agent": "drug_discovery",
  "response": {
    "answer": "Found 28 drugs for glioblastoma with evidence from multiple sources...",
    "structured_data": {
      "direct_indications": {"count": 28, "drugs": [...]},
      "gwas_targets": {"gene_count": 15, "drug_count": 303},
      "clinical_trials": {"count": 94, "recruiting": 12},
      "patents": {"count": 4480, "molecules": 14}
    },
    "evidence": [
      {
        "claim": "Bevacizumab is approved for glioblastoma",
        "source": "biobtree",
        "path": "glioblastoma >> efo >> chembl_molecule",
        "identifiers": ["CHEMBL1201583"],
        "confidence": 0.95
      }
    ],
    "patterns": {
      "high_confidence_genes": ["EGFR", "TP53"],
      "gaps_identified": ["ATG5 has variants but no drugs"]
    },
    "follow_up_suggestions": [
      "Search for ATG5-targeting compounds",
      "Review autophagy pathway drugs"
    ]
  },
  "metadata": {
    "latency_ms": 2300,
    "sources_queried": ["biobtree", "qdrant_pubmed"],
    "model": "claude-sonnet",
    "phases_completed": ["understand", "gather", "score", "reason", "synthesize"]
  }
}
```

---

## Comparison: BioYoda vs Generic LLMs

| Query | ChatGPT/Claude | BioYoda |
|-------|----------------|---------|
| "Drugs for glioblastoma" | Lists 5-10, may hallucinate | 28 verified, Phase 3+, with evidence paths |
| "EGFR to UniProt ID" | Often incorrect | Deterministic, always P00533 |
| "Similar compounds to temozolomide" | Cannot do | 30.8M compound similarity search |
| "Recruiting trials for GBM" | Outdated (knowledge cutoff) | Real-time from ClinicalTrials.gov |
| "Novel targets for resistant GBM" | Generic suggestions | ATG5/BECN1 identified via pattern detection |
| "What's the evidence?" | "I think..." | PMID, ChEMBL ID, patent numbers |

**The query only BioYoda can answer:**
> "Find me a compound that:
> 1. Targets a gene mutated in glioblastoma (BioBTree: ClinVar)
> 2. Is discussed positively in recent papers (Qdrant: PubMed)
> 3. Is structurally similar to temozolomide (Qdrant: Morgan FP)
> 4. Has patents but no approved drugs yet (BioBTree: gap detection)
> 5. Has a protein target similar to EGFR (Qdrant: ESM2)"

---

## Technology Stack (v1.0)

### No External Agent Framework

**Decision: Custom implementation, adopt patterns from frameworks**

**Rationale:**
- BioBTree gRPC client is specialized
- Qdrant embeddings are domain-specific
- Need tight control for evidence tracing
- Performance critical (framework overhead)
- Already 70% built

**Patterns adopted:**
- Tool abstraction (from LangChain)
- ReAct-style reasoning loop
- Evidence chain tracking
- Multi-agent communication interface (for future)

### Stack

```
┌─────────────────────────────────────────────────────────────┐
│                     WEB INTERFACE                           │
│         (Separate pages per agent for v1.0)                 │
└─────────────────────────────────┬───────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────┐
│                      API LAYER                              │
│              FastAPI with streaming support                 │
└─────────────────────────────────┬───────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────┐
│                    AGENT LAYER                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │    Drug     │ │     ID      │ │  Literature │           │
│  │  Discovery  │ │   Mapper    │ │   Search    │           │
│  │    Agent    │ │   Agent     │ │   Agent     │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                             │
│  Six-Phase Loop: Understand → Gather → Score → Reason →    │
│                  Follow-up → Synthesize                     │
└─────────────────────────────────┬───────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────┐
│                     TOOL LAYER                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              BioBTree Client (gRPC)                  │   │
│  │           40+ databases, deterministic paths         │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Qdrant Client (Vector)                  │   │
│  │      PubMed, Trials, Patents, ESM2, Morgan FP       │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Evidence Scorer                         │   │
│  │         Multi-source scoring + pattern detection     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────┐
│                     LLM LAYER                               │
│           Claude / GPT-4 / Gemini (configurable)           │
│                                                             │
│  Prompts: Understand, Reason, Synthesize                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### v1.0 (Launch / Preprint)

| Week | Focus | Deliverable |
|------|-------|-------------|
| 1 | Evidence Scoring | Score entities by source count, phase |
| 2 | Pattern Detection | Multi-source entities, gaps, clusters |
| 3 | Reasoning Prompt | LLM observes patterns, generates hypotheses |
| 4 | Follow-up Integration | Qdrant PubMed search for validation |
| 5 | Synthesis | Evidence-rich responses with confidence |
| 6 | API & Polish | REST API, documentation, testing |

**v1.0 Features:**
- Separate pages per agent (Drug Discovery, ID Mapper)
- Six-phase reasoning loop
- Evidence scoring and pattern detection
- PubMed semantic search integration
- REST API with evidence in responses
- No router (explicit agent selection)

### v1.5 (Post-Launch)

```
├── Add router on main page
│   └── LLM classifies query → routes to agent
├── More agents
│   ├── Clinical Trial Finder
│   ├── Patent Landscape Analyzer
│   └── Protein Structure Agent
├── Agent suggestions
│   └── "This result might also be relevant to Literature Search"
└── Improved Qdrant integration
    └── All collections connected
```

### v2.0 (Future)

```
├── Multi-agent collaboration
│   └── Drug Discovery asks Literature Agent for papers
├── Agent-to-agent communication
│   └── Shared context and handoffs
├── Persistent memory
│   └── Remember user preferences and past queries
├── Learning from feedback
│   └── Improve scoring based on user ratings
└── Complex multi-step reasoning
    └── Multi-iteration hypothesis testing
```

---

## Preprint Focus

### Title (Draft)
> "BioYoda: An Evidence-Based AI Agent System for Drug Discovery Integrating Structured Databases with Semantic Search"

### Key Claims
1. **Novel Integration**: First system combining BioBTree (40+ databases) with vector search for drug discovery
2. **Evidence Tracing**: Every claim backed by identifiers (ChEMBL, PMID, patents)
3. **Gap Detection**: Automated identification of underexplored targets
4. **Comparison**: Outperforms ChatGPT/Claude on accuracy and completeness

### Validation
- Benchmark queries with known answers
- Comparison with generic LLMs
- Case study: Rare disease drug discovery
- Expert evaluation of novel target suggestions

---

## Key Files

```
modules/agent_system/
├── AGENT_ARCHITECTURE.md      # This document
├── agents/
│   ├── drug_discovery/
│   │   ├── agent.py           # Drug Discovery Agent
│   │   ├── prompt.txt         # System prompt
│   │   └── README.md          # Agent documentation
│   └── id_mapper/
│       └── agent.py           # ID Mapper Agent
├── tools/
│   ├── disease_drug_tool.py   # Main drug discovery tool
│   ├── evidence_scorer.py     # Evidence scoring (TODO)
│   └── pattern_detector.py    # Pattern detection (TODO)
├── integrations/
│   ├── biobtree_client.py     # BioBTree gRPC client
│   └── qdrant_client.py       # Qdrant vector client
├── core/
│   ├── config.py              # Configuration
│   └── base.py                # Base classes
└── prompts/
    ├── understand.txt         # Intent parsing prompt
    ├── reason.txt             # Reasoning prompt
    └── synthesize.txt         # Response synthesis prompt
```

---

## Summary

BioYoda v1.0 is an **agent system**, not just an automation script, because it:

1. **Understands** user intent (not just keywords)
2. **Gathers** comprehensive data (BioBTree paths)
3. **Scores** evidence (multi-source validation)
4. **Reasons** about patterns (hypotheses, gaps)
5. **Validates** via follow-up (semantic search)
6. **Synthesizes** insights (not just formats data)

The combination of **structured data** (BioBTree) + **semantic search** (Qdrant) + **agent reasoning** (LLM) creates capabilities that no generic LLM can match.
